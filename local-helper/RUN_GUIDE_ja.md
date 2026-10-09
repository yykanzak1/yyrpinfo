# 獺祭 AI コンソール / Ollama 操作ガイド

## ファイル構成
- `index.html`（サイト本体）: キーボードで Ctrl + Alt + K を押すとログイン画面が開きます
- `ai.html`（AIコンソール）: ヘルパーでログインしていないと表示されません
- `server.py`（ヘルパー）: Ollama の起動・終了・チャット中継と、ログイン認証を担当します

## 1. ログインID・パスワードの設定（server.py の環境変数）
パスワードはコードに書かず、起動時の環境変数で指定します。未設定の場合はログインできません。

- macOS / Linux:
  ```
  export DASSAI_LOGIN_ID="任意のID"
  export DASSAI_LOGIN_PASSWORD="十分に長い任意のパスワード"
  python3 server.py
  ```
- Windows PowerShell:
  ```
  $env:DASSAI_LOGIN_ID="任意のID"
  $env:DASSAI_LOGIN_PASSWORD="十分に長い任意のパスワード"
  python server.py
  ```
ID は既定で `dassai` です（DASSAI_LOGIN_ID 未設定時）。

## 2. 起動手順
1. Ollama をインストールし、`ollama` コマンドが使えることを確認します。
2. 上記の環境変数を設定して `server.py` を起動します（このウィンドウは閉じないでください）。
3. 別のターミナルで `index.html` と `ai.html` があるフォルダに移動し、次を実行します。
   ```
   python -m http.server 8000
   ```
4. ブラウザで `http://localhost:8000/index.html` を開きます。
5. **Ctrl + Alt + K** でログイン画面を開き、ID とパスワードを入力します。成功すると `ai.html` に移動します。
6. `ai.html` で「起動」「終了」「更新」により Ollama を制御し、モデルを選んでプロンプトを送信します。

## 3. キーの注意
- Ctrl + Alt + K は、AltGr を使うキーボード配列（ドイツ語・フランス語など）では AltGr と競合する場合があります。その場合は index.html 内の `e.code==='KeyK'` の条件を変更してください。

## 4. 認証の仕組みと限界
- 認証はヘルパー（server.py）側で行い、発行されたトークンで `/start` `/stop` `/models` `/chat` を保護しています。トークンは8時間で失効し、ログアウトで破棄されます。
- ログイン失敗が5回続くと5分間ロックします。
- ヘルパーは 127.0.0.1 でのみ待ち受けるため、同じPCからしか使えません。
- `ai.html` の画面自体はHTMLに含まれますが、トークンがないと操作（起動・停止・チャット）はすべて拒否されます。
- 通信は http（暗号化なし）です。ローカルのみでの利用を前提にしてください。外部公開する場合は HTTPS のリバースプロキシとサーバー側の本格的な認証を用意してください。

## 5. Ollama への接続（CORS）
- ページ（ai.html）から Ollama を直接呼ばず、ヘルパーが中継します。そのため `OLLAMA_ORIGINS` の設定は通常不要です。
- ヘルパーは localhost / 127.0.0.1 以外のページからの呼び出しを 403 で拒否します。他のオリジンを許可する場合は `ALLOWED_ORIGINS` を指定します。

## 6. トラブルシューティング
- 「ヘルパーに接続できません」: `python server.py` が起動しているか、ポート 8765 が空いているかを確認します。
- 「パスワードが未設定です」: DASSAI_LOGIN_PASSWORD を設定してから server.py を起動し直してください。
- 「モデルなし」: `ollama pull モデル名` で取得してください（例: `ollama pull llama3.2`）。
- 起動に失敗する: `ollama_serve.log` を確認してください。
