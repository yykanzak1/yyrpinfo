# 獺祭 DASSAI ギャングポータル（GitHub Pages用）

## 内容
`index.html` と `assets/` を同じリポジトリのルートに置いてください。動画はHTMLにBase64埋め込みせず、相対パスから読み込みます。

- `assets/cruise-reference.mp4` — 客船強盗
- `assets/bobcat-tutorial.mp4` — ボブキャット
- `assets/atm-tutorial.mp4` — ATM強盗
- `assets/weed-tutorial.mp4` — ウィード
- `assets/conveni-tutorial.mp4` — コンビニ強盗
- `assets/jewel-tutorial.mp4` — 宝石店強盗

動画は犯罪マニュアル内の各項目を開くと、客船強盗と同じプレイヤーで再生できます。追加動画は画質を保ちながらWeb向けに圧縮し、すべての動画ファイルを100MB未満にしています。

## GitHub Pagesへの公開
1. ZIPを展開し、`index.html` と `assets/` フォルダをリポジトリのルートへ置きます。フォルダ構成を変えないでください。
2. GitHub DesktopまたはGitコマンドでコミット・プッシュします。動画ファイルが大きいため、GitHub Desktop/Gitを使う方法が確実です。
3. リポジトリの **Settings → Pages** で **Deploy from a branch** を選び、対象ブランチ（通常 `main`）とフォルダー `/ (root)` を指定します。
4. 公開後、各犯罪項目を開いて動画を再生できることを確認してください。

相対パスを使っているため、`https://ユーザー名.github.io/リポジトリ名/` のようなプロジェクトサイトでも動作します。
