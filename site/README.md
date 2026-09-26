# Ver.1 / Ver.2 / Ver.3 紹介サイト

既存READMEと是正済みの機械資料を読むための、日本語中心の静的サイトです。CADや動画は再生成しません。Ver.1/2の実物記録、Ver.3の概念設計・規定歩行、未検証事項を区別します。`index.html` は三版の全体紹介、`production.html` はVer.1の製作工程とVer.2の改良・完成記録、`comparison.html` はV2→V3の画像付きMatrix、`viewer.html` は実3Dと全案の具体的組立ガイドです。

## ローカル生成・確認

リポジトリのルートから実行します。Python 3.13以降、Node.js 24以降を使用できます。

```bash
python3 -m pip install -r site/requirements.txt
npm ci --prefix site --ignore-scripts
python3 site/build.py
npm --prefix site run test:static
cd site
npx playwright install chromium
npm test
```

既存Chromeを使う場合は、`PLAYWRIGHT_CHROMIUM_EXECUTABLE` にその実行ファイルを指定すればブラウザーの追加ダウンロードを省略できます。テストはヘッドレスの独立プロファイルで行い、使用中のブラウザーを操作しません。

ヘッドレスのGPU起動が不安定な環境では、`PLAYWRIGHT_SOFTWARE_GPU=1 npm --prefix site test` でSwiftShaderを使えます。実際のWebGL描画をCPU上で行うもので、3Dのモックや静止画への代替ではありません。実行ファイルがない場合は、`cd site && npx playwright install chromium --only-shell` で必要なテスト用ランタイムだけを用意できます。利用者の通常Chromeを停止・再設定しません。

表示確認はリポジトリのルートで `python3 site/serve.py --port 4173` の後、`http://127.0.0.1:4173/TeoJansen_Rhinoceros/` を開きます。プレビューサーバーはループバックのみで待ち受け、並列の画像取得に対応します。テスト自体もこのリポジトリ配下のパスで実行します。

## 正規資料と公開物

- `build.py` は `docs/ver3/comparison.json` とC構造探索の値から三案の寸法・比率・質量・残差・時間倍率・体積代理量を生成します。
- 写真／CG／スライサー形状画像は明示した48画像だけをWebPへ縮小。原写真の画面・周囲の私物が入る範囲を表示用にトリミングし、EXIF・XMP・ICCなどを派生表示画像から除去します。原本は変更しません。顔の写る着用写真は派生に含めません。
- 既存のMP4五本と、操作するまで読まないGIF一本を選別コピーします。初期表示で動画/GIF/YouTube/外部フォントは取得しません。
- CAD、STL、BOM、文書等は確定コミットを参照するGitHubリンクです。全リポジトリや原データ162 MBをPagesへ配信しません。
- `site/dist/TeoJansen_Rhinoceros/` のみを配信します。HTML・画像・既存動画・表示ライブラリは12 MB、操作時だけ取得する3Dデータは別枠18 MB、合計30 MBが上限です。現在は約10.1 MB＋14.7 MB。ページ間アンカー、許可ファイル、メタデータをビルドで確認し、`build-manifest.json` にページ・出典・ハッシュ・画像処理・3Dの版を記録します。追加写真は該当ページで遅延読み込みし、トップページでは取得しません。
- CIのPR実行は生成と実ブラウザー確認のみ。`main`へのpushまたは`main`の手動実行は、同じ検証に合格した静的出力だけを公式Pages Actionsで配信します。deploy jobのみ`pages:write`/`id-token:write`を持ちます。

公開後は `SITE_URL` にデプロイが返した実URLを指定して `npm --prefix site test` を実行できます。公開URLのGET、主要画像・MP4、GitHub側の代表ダウンロードも確認します。CI成功だけを実配信の確認として扱いません。

公開済みファイルのGET・出典・ハッシュ・画像メタデータは、ビルド後に `python3 site/verify_live.py --expected-commit <配信コミットの40文字SHA>` で確認できます。接続先はこのプロジェクトの既存Pages URLだけです。

ローカルでブラウザを起動できない場合も、既存の **Showcase Pages** workflowを`main`から`verify_live=true`で手動実行できます（`gh workflow run pages.yml --ref main -f verify_live=true`）。このモードは全配信アセットのGET/hashと、公開URLでのdesktop／375pxブラウザ検査を行い、PNG証跡を1日保持します。通常PR／pushの全検査は維持し、live検証モードではPages artifactのuploadとdeployを両方スキップします。別workflow・別ホスト・追加権限・ローカルの利用者ブラウザ操作は不要です。

## 保持する制限

Ver.3は実機未検証、全案の接地残差3 mm目標は未達、Bは名目トルク入力不足です。規定120 rpm入力の映像にはA1×／B8×／C2×を表示します。Cは組立・接合・抵抗測定候補であり、風力完成機の推奨ではありません。パラメトリック生成設計の体積代理量の改善を、装置全体の軽量化率と混同しません。

## 製作記録の編集と確認

- `production.html` の `figure:画像キー|alt|説明` テンプレートは、`build.py` の明示した画像だけを表示し、確定コミットの原典リンクを付けます。追加時は原典READMEの版対応と実画像を確認してください。
- 工程は主にVer.1のログです。Ver.2は記録された変更・STL構成・完成写真・テストだけを整理します。CGを実写真に、風車欄に重複したクランク写真を風車に、ファイル名中の版番号を作品の版に読み替えません。
- 当時のABS・150%／脚160%をVer.3へ適用しません。接着の待ち時間を完全硬化の保証とせず、製品の指示を優先します。独立したVer.2全工程ログ、専用PDF、未提供のFusionネイティブを補完しません。
- 静的テストは工程の本文・媒体・出典、各版6方向の実写真、未整備資料、メタデータ・原本ハッシュ、ページ間リンクの不正アンカー拒否を確認します。実ブラウザテストは1440px／375pxで両ページをたどり、全画像・目次・キーボード・axe・reduced-motion・失敗時原典リンク・JavaScriptなしの表示を確認します。

## 3D・組立adapterの契約

- `viewer-source.json` は機械資料の版ID・確定コミット・SHA256を固定します。assembly JSON、render geometry、BOM、access、組立原文、comparison、採用CGを同じ版で照合し、不一致なら停止します。機械改訂時にハッシュだけを機械的に更新せず、工程・CG・BOMもまとめて統合してください。
- `viewer_data.py` は既存 `render_geometry.json.gz` の全頂点・全三角形をそのままGLBへ変換します。ローカルmmとrow-major 4×4配置をmへ変換し、ルートでZ-upをY-upへ回すだけです。インスタンスID・部品ID・購入／印刷／加工の区分を保持し、BOMと照合します。3Dのための間引き・機構再設計はしません。
- 正規インスタンスはA 791点、B 796点、C 755点。GLBは約4.9／4.9／4.4 MB、各6 MBが上限です。`Q_BEARING_FIT` と `Q_JOINT_FIT` は本体数量0の試験片で、工程1のみ別の表示用レイアウトに出します。正規インスタンス数へ混ぜません。
- `make_guide` は原典の14基本手順を読み、全正規インスタンスを一度ずつ `add` へ対応付けます。`hidden` は各段階の絶対集合、`preview` は仕分け表示、`coupons` は試験片です。準備サブアセンブリを完成位置で示す説明であり、物理的な挿入運動を再現しません。
- BはS1窓→S3、Aはベルト→S1窓→キャリアを戻す順序に分けます。窓ねじの工具確認は、原典accessの `removed_parts` を正確に反映する別の部分組立表示です。Aの調整中の仮組み・再取外しを、単なる一方向アニメーションで置き換えていません。
- `viewer-loader.js` が利用者の操作後にだけThree.js・選択案のJSON/GLBを取得します。GLBのSHA256もブラウザで照合し、不一致、通信失敗、WebGL不可／context lossは静止画・原本・静的手順を伴う明示エラーにします。
- `viewer.js` は同じ部品メッシュを描画バッチにまとめますが、元の全インスタンスIDと配置を維持します。回転・ズーム・パン、全方向／fit、部品選択、段階表示、方向矢印、表示クリップを提供。Three.jsはMITライセンスを同梱し、esbuildでローカルにbundle化します。CDN・外部3Dサービスは使いません。
- 静的ガイドは対話ガイドと同じ工程データから生成します。JavaScriptやWebGLなしでも、A/B/Cすべての部品ID・数量・区分・工具・向き・締結注意を読めます。

検査は、GLBの全座標／三角形／配置・BOM数量・float32誤差0.001 mm未満、全工程の網羅性と順序、旧新混在・未対応部品の拒否を含みます。実ブラウザでは実際に描画したインスタンス数、未配置→試験片→全工程→完成→未配置、工具経路の部分状態、全方向fit、360°回転・タッチのpinch/pan・キーボード・選択・ロード失敗・WebGL喪失を確認します。重い全工程の操作テストは初回失敗時スクリーンショットに加え、CIの初回retry時にtraceを保存します。

## 次の機械・解析改訂との接続

現表示は第一カットです。将来の解析は同じ `revisionId / designId / loadcaseId` に、method（梁モデル／FEM／実CFD／説明模式図）、支点・荷重・材質・境界条件、単位、変形表示倍率、判定と閾値、図／result JSONのハッシュを揃えた単位で取り込みます。「流体・駆動→材料・構造→機構・組立→調達」を同じ条件でたどれるようにし、UNKNOWNをFAILEDやPASSへ丸めません。

現時点では新しいたわみ・応力・流体解析図を追加していません。資料不足のV2参考モデルを実測beforeと表示したり、数値のないカラーマップや流線を作ったりしません。追従するドライヤー冷風で無押し始動し30 cm歩く目標は別の再設計条件であり、第一カットの達成事実ではありません。
