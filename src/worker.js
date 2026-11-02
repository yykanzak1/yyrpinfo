// 獺祭 DASSAI | Blue Gang — Discordサーバー参加者だけに公開するためのゲート
// 流れ: 未ログイン→ログイン画面(OGPつき) → Discord OAuth2 → サーバー参加(+任意でロール)確認 → 署名付きCookie → 本体を配信
const enc = new TextEncoder();
const SESSION = 'dassai_session';
const STATE = 'dassai_oauth_state';
const LOGIN_ASSET = '/x9Qm4Lz7Vp2N8kR';
const PUBLIC_FILES = new Set(['/og-image-bluegang-20261002.png']);
const API = 'https://discord.com/api';
const MERCENARY_ASSETS = new Set([
  '/assets/fivem/exchange/golden-bogo.webp',
  '/assets/fivem/rewards/cash.webp',
  '/assets/fivem/rewards/gold-bar.webp',
  '/assets/fivem/rewards/zentorno.webp',
]);

const b64u = {
  enc: (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''),
  dec: (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0)),
};
const hmacKey = (secret, usage) =>
  crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, usage);

async function sign(env, payload) {
  const body = b64u.enc(enc.encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign('HMAC', await hmacKey(env.SESSION_SECRET, ['sign']), enc.encode(body));
  return `${body}.${b64u.enc(sig)}`;
}
async function verify(env, token) {
  const [body, sig] = (token || '').split('.');
  if (!body || !sig) return null;
  try {
    const ok = await crypto.subtle.verify('HMAC', await hmacKey(env.SESSION_SECRET, ['verify']), b64u.dec(sig), enc.encode(body));
    if (!ok) return null;
    const p = JSON.parse(new TextDecoder().decode(b64u.dec(body)));
    return p.exp > Date.now() / 1000 ? p : null;
  } catch { return null; }
}

const getCookie = (req, name) =>
  (req.headers.get('Cookie') || '').split(/;\s*/).map((c) => c.split('=')).find(([k]) => k === name)?.[1];
const setCookie = (name, value, path, maxAge) =>
  `${name}=${value}; Path=${path}; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`;

function redirect(location, cookies = []) {
  const h = new Headers({ Location: location, 'Cache-Control': 'no-store' });
  cookies.forEach((c) => h.append('Set-Cookie', c));
  return new Response(null, { status: 302, headers: h });
}
function secure(res) {
  const r = new Response(res.body, res);
  r.headers.set('Cache-Control', 'private, no-store');
  r.headers.set('X-Robots-Tag', 'noindex, nofollow');
  return r;
}
const asset = (env, url, path) => env.ASSETS.fetch(new Request(new URL(path, url)));
const removeElement = { element(element) { element.remove(); } };
function mercenaryManual(response) {
  return new HTMLRewriter()
    .on('#info', removeElement)
    .on('#craft .craft-layout', {
      element(element) {
        element.setAttribute('class', 'craft-layout mercenary-craft-layout');
        element.setAttribute('style', 'grid-template-columns: minmax(0, 1fr);');
      },
    })
    .on('#craft .mercenary-hide', removeElement)
    .on('#exchange', removeElement)
    .on('#crewlog', removeElement)
    .on('.search-bar', removeElement)
    .on('.search-bar', removeElement)
    .on('#searchInput', removeElement)
    .on('#searchSuggestions', removeElement)
    .on('#searchEmpty', removeElement)
    .on('#updatesBtn', removeElement)
    .on('#siteUpdatesOverlay', removeElement)
    .on('#ds-login', removeElement)
    .on('button.tab-btn', {
      element(element) {
        const onclick = element.getAttribute('onclick') || '';
        const isCrime = onclick.includes("switchTab('crime')");
        const isFines = onclick.includes("switchTab('fines')");
        const isJoining = onclick.includes("switchTab('joining')");
        const isCraft = onclick.includes("switchTab('craft')");
        if (!isCrime && !isFines && !isJoining && !isCraft) element.remove();
        else element.setAttribute('class', isCrime ? 'tab-btn active' : 'tab-btn');
        if (isCraft) element.setInnerContent('クラフトレシピ', { html: false });
      },
    })
    .on('#crime', {
      element(element) { element.setAttribute('class', 'tab-content active'); },
    })
    .transform(secure(response));
}
function roleIds(value) {
  return String(value || '').split(',').map((id) => id.trim()).filter(Boolean);
}
function gangPage(response) {
  return new HTMLRewriter()
    .on('#joining', removeElement)
    .on('button.tab-btn', {
      element(element) {
        if ((element.getAttribute('onclick') || '').includes("switchTab('joining')")) element.remove();
      },
    })
    .transform(secure(response));
}


function jsonResponse(data, status = 200, extraHeaders = {}) {
  const headers = new Headers({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  for (const [key, value] of Object.entries(extraHeaders)) headers.set(key, value);
  return new Response(JSON.stringify(data), { status, headers });
}
function parsePlayersJson(value) {
  try {
    const players = JSON.parse(value || '[]');
    return Array.isArray(players) ? players.filter((player) => player && /^\d{17,20}$/.test(player.id) && typeof player.name === 'string') : [];
  } catch { return []; }
}
function normalizePlayers(value) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > 50) return null;
  const seen = new Set(), players = [];
  for (const player of value) {
    const id = typeof player?.id === 'string' ? player.id : '';
    const name = typeof player?.name === 'string' ? player.name.trim() : '';
    if (!/^\d{17,20}$/.test(id) || !name || name.length > 80) return null;
    if (!seen.has(id)) { seen.add(id); players.push({ id, name }); }
  }
  return players;
}
async function discordGuildMembers(url, env) {
  if (!env.DISCORD_BOT_TOKEN) throw new Error('Discord bot token is not configured');
  const guildId = String(env.GUILD_ID || '').split(',')[0].trim();
  if (!guildId) throw new Error('Discord guild is not configured');
  const cache = globalThis.caches?.default;
  const cacheKey = new Request(new URL(`/__internal/discord-members/${guildId}`, url.origin));
  if (cache) {
    try {
      const cached = await cache.match(cacheKey);
      if (cached) return await cached.json();
    } catch {}
  }
  const members = [];
  let after = '';
  for (let pageNumber = 0; pageNumber < 500; pageNumber++) {
    const endpoint = new URL(`${API}/v10/guilds/${guildId}/members`);
    endpoint.searchParams.set('limit', '1000');
    if (after) endpoint.searchParams.set('after', after);
    const response = await fetch(endpoint, { headers: { Authorization: `Bot ${env.DISCORD_BOT_TOKEN}` } });
    if (!response.ok) throw new Error(`Discord member request failed (${response.status})`);
    const page = await response.json();
    if (!Array.isArray(page)) throw new Error('Invalid Discord member response');
    for (const member of page) {
      const user = member?.user;
      if (!user?.id || user.bot) continue;
      members.push({ id: user.id, name: member.nick || user.global_name || user.username || user.id });
    }
    if (page.length < 1000) break;
    const nextAfter = page.at(-1)?.user?.id;
    if (!nextAfter || nextAfter === after) throw new Error('Discord member pagination did not advance');
    after = nextAfter;
    if (pageNumber === 499) throw new Error('Discord member list exceeded the pagination limit');
  }
  members.sort((a, b) => a.name.localeCompare(b.name, 'ja'));
  if (cache) {
    try {
      await cache.put(cacheKey, new Response(JSON.stringify(members), { headers: { 'Cache-Control': 'public, max-age=20' } }));
    } catch {}
  }
  return members;
}
async function crewLogApi(request, url, env, access, userId) {
  const path = url.pathname;
  const canDelete = access === 'boss' || access === 'underboss';
  const sameOrigin = request.headers.get('Origin') === url.origin;
  const method = request.method;
  try {
    if (path === '/api/members' && method === 'GET') {
      if (!['gang', 'boss', 'underboss'].includes(access)) return jsonResponse({ error: 'Forbidden' }, 403);
      if (!env.DISCORD_BOT_TOKEN) return jsonResponse({ error: 'discord_bot_not_configured' }, 503);
      try {
        const members = await discordGuildMembers(url, env);
        return jsonResponse(members, 200, { 'Cache-Control': 'private, max-age=15' });
      } catch (error) {
        console.error('Discord member list error', error);
        return jsonResponse({ error: 'discord_member_fetch_failed' }, 502);
      }
    }
    if (!env.CREW_LOG_DB) return jsonResponse({ error: 'Database unavailable' }, 503);
    if (path === '/api/records' && method === 'GET') {
      const { results = [] } = await env.CREW_LOG_DB.prepare(
        'SELECT id, activity, result, cashed, occurred_at, created_by, players_json FROM crew_log ORDER BY occurred_at DESC LIMIT 10000'
      ).all();
      const records = results.map(({ created_by, players_json, ...record }) => ({
        ...record,
        players: parsePlayersJson(players_json),
        can_edit: access === 'gang' && Boolean(userId) && created_by === userId,
      }));
      return jsonResponse(records, 200, { 'X-Crew-Can-Delete': canDelete ? '1' : '0' });
    }
    if (path === '/api/records' && method === 'POST') {
      if (!userId) return jsonResponse({ error: 'Forbidden' }, 403);
      if (!sameOrigin) return jsonResponse({ error: 'Forbidden origin' }, 403);
      const contentLength = Number(request.headers.get('Content-Length') || 0);
      if (contentLength > 8192) return jsonResponse({ error: 'Request too large' }, 413);
      let input;
      try { input = await request.json(); } catch { return jsonResponse({ error: 'Invalid JSON' }, 400); }
      const activity = typeof input?.activity === 'string' ? input.activity.trim() : '';
      const players = normalizePlayers(input?.players);
      if (!activity || activity.length > 80 || !['caught', 'not_caught'].includes(input?.result) || !['yes', 'no'].includes(input?.cashed) || !players) {
        return jsonResponse({ error: 'Invalid record' }, 400);
      }
      const record = {
        id: crypto.randomUUID(), activity,
        result: input.result, cashed: input.cashed,
        occurred_at: new Date().toISOString(), players,
      };
      await env.CREW_LOG_DB.prepare(
        'INSERT INTO crew_log (id, activity, result, cashed, occurred_at, created_by, players_json) VALUES (?, ?, ?, ?, ?, ?, ?)'
      ).bind(record.id, record.activity, record.result, record.cashed, record.occurred_at, userId, JSON.stringify(players)).run();
      return jsonResponse({ ...record, can_edit: access === 'gang' }, 201);
    }
    if (path === '/api/records' && method === 'DELETE') {
      if (!canDelete) return jsonResponse({ error: 'Forbidden' }, 403);
      if (!sameOrigin) return jsonResponse({ error: 'Forbidden origin' }, 403);
      await env.CREW_LOG_DB.prepare('DELETE FROM crew_log').run();
      return jsonResponse({ ok: true });
    }
    const match = path.match(/^\/api\/records\/([^/]+)$/);
    if (match && method === 'PUT') {
      if (access !== 'gang') return jsonResponse({ error: 'Forbidden' }, 403);
      if (!sameOrigin) return jsonResponse({ error: 'Forbidden origin' }, 403);
      if (!userId) return jsonResponse({ error: 'Forbidden' }, 403);
      const contentLength = Number(request.headers.get('Content-Length') || 0);
      if (contentLength > 8192) return jsonResponse({ error: 'Request too large' }, 413);
      let id;
      try { id = decodeURIComponent(match[1]); } catch { return jsonResponse({ error: 'Invalid id' }, 400); }
      let input;
      try { input = await request.json(); } catch { return jsonResponse({ error: 'Invalid JSON' }, 400); }
      const activity = typeof input?.activity === 'string' ? input.activity.trim() : '';
      const players = normalizePlayers(input?.players);
      if (!activity || activity.length > 80 || !['caught', 'not_caught'].includes(input?.result) || !['yes', 'no'].includes(input?.cashed) || !players) {
        return jsonResponse({ error: 'Invalid record' }, 400);
      }
      const { results: existing = [] } = await env.CREW_LOG_DB.prepare(
        'SELECT created_by FROM crew_log WHERE id = ?'
      ).bind(id).all();
      if (!existing.length) return jsonResponse({ error: 'Record not found' }, 404);
      if (existing[0].created_by !== userId) return jsonResponse({ error: 'Forbidden' }, 403);
      await env.CREW_LOG_DB.prepare(
        'UPDATE crew_log SET activity = ?, result = ?, cashed = ?, players_json = ? WHERE id = ? AND created_by = ?'
      ).bind(activity, input.result, input.cashed, JSON.stringify(players), id, userId).run();
      const { results: updated = [] } = await env.CREW_LOG_DB.prepare(
        'SELECT id, activity, result, cashed, occurred_at, players_json FROM crew_log WHERE id = ?'
      ).bind(id).all();
      if (!updated.length) return jsonResponse({ error: 'Record not found' }, 404);
      const { players_json, ...record } = updated[0];
      return jsonResponse({ ...record, players: parsePlayersJson(players_json), can_edit: true });
    }
    if (match && method === 'DELETE') {
      if (!canDelete) return jsonResponse({ error: 'Forbidden' }, 403);
      if (!sameOrigin) return jsonResponse({ error: 'Forbidden origin' }, 403);
      let id;
      try { id = decodeURIComponent(match[1]); } catch { return jsonResponse({ error: 'Invalid id' }, 400); }
      await env.CREW_LOG_DB.prepare('DELETE FROM crew_log WHERE id = ?').bind(id).run();
      return jsonResponse({ ok: true });
    }
    return jsonResponse({ error: 'Not found' }, path.startsWith('/api/records') ? 405 : 404);
  } catch (error) {
    console.error('crew log API error', error);
    return jsonResponse({ error: 'Unable to access shared log' }, 500);
  }
}
async function loginPage(url, env) {
  const res = await asset(env, url, LOGIN_ASSET);
  const html = (await res.text())
    .replaceAll('{{ORIGIN}}', url.origin)
    .replaceAll('{{INVITE_URL}}', env.INVITE_URL || '');
  return secure(new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } }));
}

function startLogin(url, env) {
  const state = b64u.enc(crypto.getRandomValues(new Uint8Array(24)));
  const q = new URLSearchParams({
    client_id: env.DISCORD_CLIENT_ID,
    response_type: 'code',
    redirect_uri: `${url.origin}/auth/callback`,
    scope: 'identify guilds.members.read',
    state,
    prompt: 'none',
  });
  return redirect(`https://discord.com/oauth2/authorize?${q}`, [setCookie(STATE, state, '/auth', 600)]);
}

async function callback(request, url, env) {
  const clearState = setCookie(STATE, '', '/auth', 0);
  const fail = (code) => redirect(`/?error=${code}`, [clearState]);
  if (url.searchParams.get('error')) return fail('cancel');
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  if (!code || !state || state !== getCookie(request, STATE)) return fail('state');
  try {
    const tokenRes = await fetch(`${API}/oauth2/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: env.DISCORD_CLIENT_ID,
        client_secret: env.DISCORD_CLIENT_SECRET,
        grant_type: 'authorization_code',
        code,
        redirect_uri: `${url.origin}/auth/callback`,
      }),
    });
    if (!tokenRes.ok) return fail('oauth');
    const { access_token } = await tokenRes.json();
    const auth = { Authorization: `Bearer ${access_token}` };
    const guilds = String(env.GUILD_ID).split(',').map((g) => g.trim()).filter(Boolean);
    const gangRoles = roleIds(env.GANG_ROLE_ID);
    const mercenaryRoles = roleIds(env.MERCENARY_ROLE_ID);
    const bossRoles = roleIds(env.BOSS_ROLE_ID);
    const underbossRoles = roleIds(env.UNDERBOSS_ROLE_ID);
    if (!gangRoles.length || !mercenaryRoles.length || !bossRoles.length || !underbossRoles.length) return fail('config');
    const [meRes, ...memRes] = await Promise.all([
      fetch(`${API}/users/@me`, { headers: auth }),
      ...guilds.map((g) => fetch(`${API}/users/@me/guilds/${g}/member`, { headers: auth })),
    ]);
    if (!meRes.ok) return fail('oauth');
    // BOSS・アンボス・ギャングは全ページ、傭兵は許可したページとクラフトレシピのみ閲覧。
    const rank = { mercenary: 1, gang: 2, underboss: 3, boss: 4 };
    let joined = false, access = null, error = false;
    for (const r of memRes) {
      if (r.status === 404 || r.status === 403) continue;
      if (!r.ok) { error = true; continue; }
      joined = true;
      const member = await r.json();
      const memberRoles = member.roles || [];
      const candidate = bossRoles.some((id) => memberRoles.includes(id)) ? 'boss'
        : underbossRoles.some((id) => memberRoles.includes(id)) ? 'underboss'
        : gangRoles.some((id) => memberRoles.includes(id)) ? 'gang'
        : mercenaryRoles.some((id) => memberRoles.includes(id)) ? 'mercenary' : null;
      if (candidate && (!access || rank[candidate] > rank[access])) access = candidate;
    }
    if (!access) return fail(joined ? 'role' : error ? 'server' : 'denied');
    const me = await meRes.json();
    const days = Number(env.SESSION_DAYS) || 7;
    const token = await sign(env, { v: 2, u: me.id, n: me.global_name || me.username, a: access, exp: Math.floor(Date.now() / 1000) + days * 86400 });
    return redirect('/', [setCookie(SESSION, token, '/', days * 86400), clearState]);
  } catch {
    return fail('server');
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === '/auth/login') return startLogin(url, env);
    if (path === LOGIN_ASSET) return loginPage(url, env);
    if (path === '/auth/callback') return callback(request, url, env);
    if (path === '/auth/logout') return redirect('/', [setCookie(SESSION, '', '/', 0)]);
    if (PUBLIC_FILES.has(path)) return env.ASSETS.fetch(request);

    const session = await verify(env, getCookie(request, SESSION));
    // 旧形式のCookieには権限情報がないため再ログインを必須にする。
    const allowedRoles = new Set(['gang', 'mercenary', 'boss', 'underboss']);
    const access = session && session.v === 2 && allowedRoles.has(session.a) ? session.a : null;
    if (path === '/api/members' || path === '/api/records' || path.startsWith('/api/records/')) {
      if (!access) return redirect('/');
      if (access === 'mercenary') return new Response('Not found', { status: 404 });
      return crewLogApi(request, url, env, access, session.u);
    }
    if (path.startsWith('/assets/')) {
      if (!access) return redirect('/');
      if (access === 'mercenary' && !MERCENARY_ASSETS.has(path)) return new Response('Not found', { status: 404 });
      const response = secure(await env.ASSETS.fetch(request));
      response.headers.set('Cache-Control', 'private, max-age=86400');
      return response;
    }
    if (path === '/' || path === '/index.html') {
      if (!access) return loginPage(url, env);
      const page = await asset(env, url, '/_app/index.html');
      if (access === 'gang') return gangPage(page);
      if (access === 'mercenary') return mercenaryManual(page);
      return secure(page);
    }
    if (path === '/crew-log' || path === '/crew-log/') {
      if (!access) return redirect('/');
      if (access === 'mercenary') return new Response('Not found', { status: 404 });
      return secure(await asset(env, url, '/crew-log/index.html'));
    }
    if (path === '/mercenary-guide' || path === '/mercenary-guide/') {
      if (!access) return redirect('/');
      if (access === 'gang') return new Response('Not found', { status: 404 });
      return secure(await asset(env, url, '/mercenary-guide/index.html'));
    }
    return access ? new Response('Not found', { status: 404 }) : redirect('/');
  },
};
