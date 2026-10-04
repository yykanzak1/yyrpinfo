# 獺祭 DASSAI ｜Blue Gang

Blue Gang のメンバー向けに、サーバー内のギャング情報や各種マニュアルをまとめた静的サイトです。

> 本サイトの犯罪・武器・クラフト情報は、ゲーム内ロールプレイ用の案内です。現実の犯罪行為を推奨・案内するものではありません。

## 公開サイト

- **URL:** https://yydassai.f5.si/

## 主なコンテンツ

- ギャング INFO
- 犯罪マニュアル：ドラッグ販売、ATM、コンビニ、ウィード、フリーカ、宝石店、ボブキャット、客船、貨物機、列車、ユニオンなど
- クラフトレシピ：通常・上級の必要素材、アイテム画像、制作コスト
- リサイクルセンターの素材価格と換金所の情報
- Vimeoの実演参考動画

## 主な機能

- PC・スマートフォンに対応したレスポンシブ表示
- ライトモード／ダークモード
- リアルタイム検索と候補表示（キーボード操作対応）
- 素材画像付きのレシピ・必要アイテム表示
- 犯罪マニュアルの更新履歴
- Discordなどのリンクプレビュー向けOGP設定

## ファイル構成

公開時は、次のファイルをリポジトリのルートに置いてください。

- `index.html` — サイト本体
- `og-image-bluegang-20261002.png` — Discordなどで使う共有プレビュー画像
- `README.md` — この説明書
- `CNAME` — カスタムドメインをGitHub Pagesで使う場合に必要なファイル（内容は `yydassai.f5.si`）

サイト内の小さなアイコンや画像の多くはHTMLに埋め込まれています。実演動画の動画ファイルはリポジトリに含めず、Vimeoから配信しています。

## ローカルで確認する

Python 3が使える場合、ファイルのあるフォルダーで次を実行し、ブラウザーで `http://localhost:8000` を開いてください。

```bash
python3 -m http.server 8000
```

## GitHub Pagesで公開する

1. `index.html`、`og-image-bluegang-20261002.png`、`README.md` をリポジトリのルートにアップロードします。
2. カスタムドメイン `yydassai.f5.si` を使う場合は、ルートの `CNAME` に同じドメインを記載し、GitHubの **Settings → Pages → Custom domain** にも設定します。すでに公開できている場合、DNS設定はむやみに変更しないでください。
3. **Settings → Pages → Build and deployment** で **Deploy from a branch** を選び、公開ブランチ（例：`main`）と `/(root)` を指定します。
4. デプロイ完了後、https://yydassai.f5.si/ を開いて表示を確認します。

カスタムドメインを変更する場合は、`index.html` 内のcanonical URL、`og:url`、`og:image`、`twitter:image` も新しいURLに合わせてください。OGP画像のファイル名を変えた場合は、画像ファイルと各メタタグのパスを一致させます。

## Firebase Hostingで公開する場合

```bash
npm install -g firebase-tools
firebase login
firebase init hosting
firebase deploy --only hosting
```

初期設定では、公開フォルダーにサイトのファイルがあるフォルダーを指定します。既存の `index.html` を上書きしないように注意してください。

## Vimeo動画について

動画はVimeoの埋め込みプレイヤーで表示されます。再生できない場合は、Vimeo側のプライバシー設定と埋め込み許可ドメインに `yydassai.f5.si` が含まれているか確認してください。プレイヤーは遅延読み込みです。

## Discordのリンクプレビューについて

プレビュー画像は `og-image-bluegang-20261002.png` を参照します。Discordは過去のプレビュー情報をキャッシュすることがあるため、更新後すぐに画像が切り替わらない場合があります。確認用にURL末尾へクエリを付けた新しいリンクを投稿すると、更新後の表示を確認しやすくなります。
