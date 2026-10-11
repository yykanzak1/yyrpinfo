# 獺祭 AI コンソール / OpenCode 操作ガイド

`local-helper/server.py` は、ブラウザーからローカルの **opencode**（コードエージェント）を操作する中継役です。AI画面にPC上の作業フォルダーを編集・実行させる構成ではHelperが必要です。ログオン時に自動起動する設定を一度行えば、毎回手動でHelperを設定・起動する必要はありません。
以前の Ollama 版と違い、モデルはローカルではなく opencode が接続しているプロバイダ（OpenCode Zen など）を使います。

## ファイル構成
- `index.html`（サイト本体）: キーボードで Ctrl + Alt + K を押すとログイン画面が開きます
- `ai.html`（AIコンソール）: ヘルパーでログインしていないと表示されません
- `server.py`（ヘルパー）: opencode サーバ(`opencode serve`)の起動・終了・チャット中継と、ログイン認証を担当します

## 1. ログインID・パスワード
Windowsの一度だけセットアップでは、AI画面のログインID・パスワードを入力し、Helperがログオン時に使えるよう現在のWindowsユーザー専用DPAPIで暗号化保存します。設定したログインIDとパスワードは、ブラウザーでAI画面にサインインするときにも使います。

**手動運用する場合のみ**、パスワードはコードへ書かず、起動時の環境変数で指定します。未設定の場合はログインできません。

- Windows PowerShell:
  ```
  $env:DASSAI_LOGIN_ID="任意のID"
  $env:DASSAI_LOGIN_PASSWORD="十分に長い任意のパスワード"
  python server.py
  ```
- macOS / Linux:
  ```
  export DASSAI_LOGIN_ID="任意のID"
  export DASSAI_LOGIN_PASSWORD="十分に長い任意のパスワード"
  python3 server.py
  ```

IDの既定値は `dassai` です。Windowsのセットアップでは、AI画面に設定済みのログインIDを入力してください。

## 2. opencode の確認
- `opencode` コマンドが使えることを確認してください（`opencode --version`）。
- モデルを使うには opencode でプロバイダの認証が完了している必要があります（`opencode auth list`）。
  - OpenCode Zen を使う場合は**アカウントに残高が必要**です。残高不足だと 402 (Insufficient account funds) になり応答できません。

## 2-A. Gemini APIを無料枠のエージェント候補に加える
Gemini APIはツール呼び出しに対応しているため、OpenCodeのファイル編集・コマンド実行エージェントとして利用できます。モデル推論はGoogle側で行われるので、ローカルOllamaのようにゲーム中のGPUを使いません。Gemini API無料枠はモデル・アカウントごとに制限があり、無料枠の入力内容はGoogleの製品改善に使用される場合があります。秘密情報を含むコードは送らないでください。

**Windowsの一度だけのセットアップ:**
1. [Google AI Studio](https://aistudio.google.com/apikey)でAPIキーを用意します。キーはチャットに貼らず、Google AI Studioの無料枠だけを使い、課金を有効にしないでください。
2. 作業中のAI生成があれば保存し、既に起動しているOpenCodeサーバーはAI画面の「設定・サーバー」から停止します。Helperのウィンドウがあれば `Ctrl+C` で停止します。
3. **コマンドプロンプト（CMD）**で、次をまとめて貼り付けて実行します。
   ```bat
   cd /d "%USERPROFILE%\yyrpinfo"
   git pull --ff-only
   cd /d "%USERPROFILE%\yyrpinfo\local-helper"
   powershell -NoProfile -ExecutionPolicy Bypass -File ".\setup-gemini.ps1"
   ```
4. 初回だけ獺祭AIのログインID・パスワード、Google AI StudioのAPIキー、既定の作業フォルダーを入力します。キーとパスワードはWindowsユーザー専用DPAPIで暗号化し、`%APPDATA%\DASSAI-AI\helper-secrets.json` に保存します。キーはGemini互換用の `GEMINI_API_KEY` とGoogle標準プロバイダー（`google/...`）用の `GOOGLE_GENERATIVE_AI_API_KEY` の両方にHelperの実行中だけ渡されます。キーは `opencode.json` に平文保存しません。
5. スクリプトがWindowsタスクスケジューラへログオン時の自動起動を登録し、HelperとOpenCodeを今すぐバックグラウンド起動します。以後は**Windowsにサインインするだけ**で起動します。ターミナルを開いたままにする必要はありません。Helperログは `%LOCALAPPDATA%\DASSAI-AI\helper.log`（エラーは `helper-error.log`）、OpenCodeログは `local-helper\opencode_serve.log` にあります。
6. AI画面には必要に応じてログインしてください。ブラウザーの認証はセキュリティのため残ります。モデル一覧を再読み込みすると、無料枠切れ時は接続済みの無料候補へ切り替わります。現在セットアップされる無料の代替先はGemini 3.8 Flashです。無料枠を使い切った場合も自動的に有料へは切り替えません。
7. OpenCode TUIでも無料枠自動切替を使う場合は、初回セットアップの確認で `y` を選びます。この選択をするとTUIからキーを読めるよう、APIキーがDPAPIファイルに加えてWindowsユーザー環境変数にも保存され、同じWindowsアカウントのアプリから読み取れる状態になります。**獺祭AIのWeb画面だけ使う場合は `N`（既定）を選んでください**。Helperの自動起動・Web画面でのGemini利用には影響しません。無料枠・429・残高不足を検出すると、同じセッションのメッセージをGemini 3.8 Flashへ再送します。

保存したキーを変更する場合は、AI画面でOpenCodeとHelperを停止した後、`setup-gemini.ps1 -ResetCredentials` を実行します。Windowsの自動起動を解除する場合は、タスクスケジューラでタスク `DASSAI AI Helper` を無効化または削除してください。

無料枠を超えると拒否され、課金されないアカウントだけを追加してください。Gemini無料枠では入力内容がGoogleの製品改善に使われる場合があるため、秘密情報を含むコードは送らないでください。

## 3. 起動手順
1. 初回セットアップ後は、WindowsへサインインするとHelperとOpenCodeが自動起動します。PCの電源投入後、Windowsへサインインする前に起動する設定ではありません。
2. 別のターミナルで `index.html` と `ai.html` があるフォルダに移動し、次を実行します。
   ```
   python -m http.server 8000
   ```
3. ブラウザで `http://localhost:8000/index.html` を開きます。
4. **Ctrl + Alt + K** でログイン画面を開き、ID とパスワードを入力します。成功すると `ai.html` に移動します。
5. `ai.html` で「起動」を押すとヘルパーが `opencode serve` を起動します。
6. サイドバーの **作業ディレクトリ** に opencode に作業させたいフォルダを入力します（既定は環境変数 `OPENCODE_CWD`、未設定ならホーム）。
7. モデルを選び（`プロバイダ/モデル` 形式）、プロンプトを送信します。ファイル編集やコマンド実行も opencode が実行します。

## 4. 環境変数（server.py）
| 変数 | 既定 | 説明 |
|---|---|---|
| `HELPER_PORT` | `8765` | ヘルパーの待受ポート |
| `OPENCODE_CMD` | `opencode` | opencode コマンド（PATH から解決） |
| `OPENCODE_API` | `http://127.0.0.1:4096` | opencode サーバの待受 |
| `OPENCODE_CWD` | ホーム | opencode を起動する作業ディレクトリ |
| `OPENCODE_SERVER_PASSWORD` | （なし） | 設定時は opencode サーバへ Basic 認証で接続 |
| `DASSAI_LOGIN_ID` | `dassai` | コンソールのログインID |
| `DASSAI_LOGIN_PASSWORD` | （なし） | コンソールのログインパスワード（未設定はログイン不可） |
| `DASSAI_FREE_MODELS` | （なし） | カタログ価格が0でない「無料枠専用」モデルを明示許可するID（完全一致・カンマ区切り） |
| `ALLOWED_ORIGINS` | （なし） | ページからヘルパーを呼べるオリジンを追加（カンマ区切り） |
| `DASSAI_TOKEN_TTL` | `28800` | トークンの有効秒数（8時間） |

`DASSAI_FREE_MODELS` は、プロバイダー側で**無料枠を超えると課金されず拒否される**と確認できたモデルだけを指定してください。モデルIDはAI画面のモデル詳細に出る `プロバイダー/モデルID` を完全一致で記載します。無料枠のない有料アカウントや、上限後に自動課金されるアカウントのモデルを登録しないでください。指定モデルも通常の無料判定モデルと同じく、利用上限エラー時に次の無料モデルへ切り替わります。

Windows PowerShellでの例（モデルIDは実際に表示される値へ置き換えます）:
```powershell
$env:DASSAI_FREE_MODELS="google-gemini/gemini-3.8-flash,another-provider/model-id"
python server.py
```
この変数はヘルパー起動時に読み込まれるため、変更後は `server.py` を再起動してください。APIキーは `DASSAI_FREE_MODELS` に書かず、OpenCodeの `/connect` またはプロバイダーの認証設定へ登録します。

## 5. キーの注意
- Ctrl + Alt + K は、AltGr を使うキーボード配列（ドイツ語・フランス語など）では AltGr と競合する場合があります。その場合は index.html 内の `e.code==='KeyK'` の条件を変更してください。

## 6. 認証の仕組みと限界
- 認証はヘルパー（server.py）側で行い、発行されたトークンで `/start` `/stop` `/models` `/new` `/chat` を保護しています。トークンは8時間で失効し、ログアウトで破棄されます。
- ログイン失敗が5回続くと5分間ロックします。
- ヘルパーは 127.0.0.1 でのみ待ち受けるため、同じPCからしか使えません。
- `ai.html` の画面自体はHTMLに含まれますが、トークンがないと操作（起動・停止・チャット）はすべて拒否されます。
- 通信は http（暗号化なし）です。ローカルのみでの利用を前提にしてください。外部公開する場合は HTTPS のリバースプロキシとサーバー側の本格的な認証を用意してください。

## 7. トラブルシューティング
- 「ヘルパーに接続できません」: `python server.py` が起動しているか、ポート 8765 が空いているかを確認します。
- 「パスワードが未設定です」: DASSAI_LOGIN_PASSWORD を設定してから server.py を起動し直してください。
- モデルが表示されない: opencode にプロバイダの認証が入っているか `opencode auth list` で確認してください。
- 応答が 402 で失敗する: OpenCode Zen の残高が不足しています。アカウントへチャージするか、別のプロバイダを認証してください。
- 起動に失敗する: `opencode_serve.log` を確認してください。
