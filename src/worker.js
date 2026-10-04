// 獺祭 DASSAI | Blue Gang — Discordサーバー参加者だけに公開するためのゲート
// 流れ: 未ログイン→ログイン画面(OGPつき) → Discord OAuth2 → サーバー参加(+任意でロール)確認 → 署名付きCookie → 本体を配信
const enc = new TextEncoder();
const SESSION = 'dassai_session';
const STATE = 'dassai_oauth_state';
const PUBLIC_FILES = new Set(['/og-image-bluegang-20261002.png']);
const API = 'https://discord.com/api';

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

async function loginPage(url, env) {
  const res = await asset(env, url, '/login.html');
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
    const [meRes, memRes] = await Promise.all([
      fetch(`${API}/users/@me`, { headers: auth }),
      fetch(`${API}/users/@me/guilds/${env.GUILD_ID}/member`, { headers: auth }),
    ]);
    if (!meRes.ok) return fail('oauth');
    if (memRes.status === 404 || memRes.status === 403) return fail('denied'); // サーバー未参加
    if (!memRes.ok) return fail('server');
    const member = await memRes.json();
    if (env.REQUIRED_ROLE_ID && !(member.roles || []).includes(env.REQUIRED_ROLE_ID)) return fail('role');
    const me = await meRes.json();
    const days = Number(env.SESSION_DAYS) || 7;
    const token = await sign(env, { u: me.id, n: me.global_name || me.username, exp: Math.floor(Date.now() / 1000) + days * 86400 });
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
    if (path === '/auth/callback') return callback(request, url, env);
    if (path === '/auth/logout') return redirect('/', [setCookie(SESSION, '', '/', 0)]);
    if (PUBLIC_FILES.has(path)) return env.ASSETS.fetch(request);

    const session = await verify(env, getCookie(request, SESSION));
    if (path === '/' || path === '/index.html') {
      return session ? secure(await asset(env, url, '/_app/index.html')) : loginPage(url, env);
    }
    return session ? new Response('Not found', { status: 404 }) : redirect('/');
  },
};
