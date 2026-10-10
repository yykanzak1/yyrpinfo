# 獺祭 DASSAI ｜Blue Gang — Discord限定公開版

Discordサーバーに参加している人だけが閲覧できるようにした構成です。
判定はサーバー側（Cloudflare Workers）で行い、未ログインの人には本体のHTMLを送りません。

## 仕組み

1. `/` にアクセス → 未ログインなら `login.html`（Discordのリンクプレビュー用OGPつき）を表示
2. 「Discordでログイン」→ Discord OAuth2 で認証
3. 指定サーバーの参加（任意でロール）を確認 → 署名付きCookieを発行
4. Cookieが有効な間だけ `public/_app/index.html`（既存サイト本体）を配信

取得する情報は「ユーザー名」と「そのサーバーのメンバー情報」だけです。アクセストークンは保存せず、確認後に破棄します。

## ファイル構成

- `src/worker.js` — 認証・配信ロジック
- `wrangler.jsonc` — 設定（IDなどを書き換える）
- `public/_app/index.html` — サイト本体（ログイン必須。右上にログアウトボタン追加済み）
- `public/login.html` — ログイン画面
- `public/og-image-bluegang-20261002.png` — リンクプレビュー画像（未ログインでも取得可）

## セットアップ

### 1. Discordアプリを作る
1. https://discord.com/developers/applications → **New Application**
2. **OAuth2** で `Client ID` と `Client Secret` を控える
3. **OAuth2 → Redirects** に `https://（公開URL）/auth/callback` を追加（後述の手順3で確定したURL）
4. Discordアプリの設定 → 詳細設定 → **開発者モード** をON → サーバーアイコンを右クリック → **サーバーIDをコピー**
   （ロールで絞る場合は、ロールを右クリック → IDをコピー）

### 2. Cloudflareにデプロイ（無料枠でOK）
```bash
npm install
npx wrangler login
```
`wrangler.jsonc` の `vars` を編集:
- `DISCORD_CLIENT_ID` … Application ID
- `GUILD_ID` … サーバーID
- `REQUIRED_ROLE_ID` … 特定ロールだけに絞るならロールID（不要なら空のまま）
- `INVITE_URL` … 未参加の人に出す招待リンク（不要なら空）
- `SESSION_DAYS` … ログインの有効日数（サーバーを抜けた人が閲覧できなくなるまでの最大日数）

秘密情報は `vars` ではなくシークレットとして登録します:
```bash
npx wrangler secret put DISCORD_CLIENT_SECRET
npx wrangler secret put SESSION_SECRET     # openssl rand -base64 32 などで作った長いランダム文字列
npx wrangler deploy
```

### 3. URLを確定してRedirectsに登録
デプロイ後に `https://dassai-bluegang.（あなたのサブドメイン）.workers.dev` が発行されます。
このURLに `/auth/callback` を付けたものを、手順1-3のRedirectsに登録してください。

### 4. 動作確認
- シークレットウィンドウで開く → ログイン画面になるか
- サーバー参加済みアカウントでログイン → 本体が表示されるか
- 未参加アカウントでログイン → 「参加していません」と出るか

## 注意

- **GitHubのリポジトリを必ずPrivateにしてください。** Publicのままだと `index.html` の中身がそのまま誰でも読めます。
- 今回の構成では `yydassai.f5.si` のままWorkersに割り当てられません（Workersの独自ドメインはCloudflareで管理しているドメインのみ）。`workers.dev` のURLを使うか、自分で取得した独自ドメインをCloudflareに登録してください。
- 新しいURLを使う場合、Vimeoの埋め込み許可ドメインにそのドメインを追加してください。
- 旧 `yydassai.f5.si` は、新URLへの案内ページに差し替えるのがおすすめです。
- ログイン済みの人がスクリーンショットや内容を共有することまでは防げません。
- サーバーを抜けた人は、Cookieの有効期限（`SESSION_DAYS`）が切れて再ログインした時点で閲覧できなくなります。
- ローカル確認は `npx wrangler dev`（`.dev.vars.example` を `.dev.vars` にコピーして値を入れる）。Redirectsに `http://localhost:8787/auth/callback` も追加が必要です。

## AI コンソールについて

- `public/ai.html`（獺祭 AI コンソール）は、opencode でコード作業・ファイル操作を行うためのチャットUIです。詳細は `local-helper/RUN_GUIDE_ja.md` を参照してください。
- ヘルパー `local-helper/server.py` は **opencode**（`opencode serve`）の起動・終了とチャット中継を担当します。Ollama ではありません。
- モデルは opencode が接続するクラウドプロバイダ（例: OpenCode Zen）を使うため、**アカウントの残高／APIキー**が必要です。
