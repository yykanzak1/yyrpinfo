# 獺祭 AI コンソール / OpenCode 操作ガイド

`local-helper/server.py` が、ローカルの **opencode**（コードエージェント）を操作する中継役になりました。
以前の Ollama 版と違い、モデルはローカルではなく opencode が接続しているプロバイダ（OpenCode Zen など）を使います。

## ファイル構成
- `index.html`（サイト本体）: キーボードで Ctrl + Alt + K を押すとログイン画面が開きます
- `ai.html`（AIコンソール）: ヘルパーでログインしていないと表示されません
- `server.py`（ヘルパー）: opencode サーバ(`opencode serve`)の起動・終了・チャット中継と、ログイン認証を担当します

## 1. ログインID・パスワードの設定
パスワードはコードに書かず、起動時の環境変数で指定します。未設定の場合はログインできません。

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

ID は既定で `dassai` ですが、このPCでは環境変数 `DASSAI_LOGIN_ID=kanzaki` が既に設定されているため `kanzaki` でログインします。

## 2. opencode の確認
- `opencode` コマンドが使えることを確認してください（`opencode --version`）。
- モデルを使うには opencode でプロバイダの認証が完了している必要があります（`opencode auth list`）。
  - OpenCode Zen を使う場合は**アカウントに残高が必要**です。残高不足だと 402 (Insufficient account funds) になり応答できません。

## 3. 起動手順
1. 上記の環境変数を設定して `server.py` を起動します（このウィンドウは閉じないでください）。
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
| `ALLOWED_ORIGINS` | （なし） | ページからヘルパーを呼べるオリジンを追加（カンマ区切り） |
| `DASSAI_TOKEN_TTL` | `28800` | トークンの有効秒数（8時間） |

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