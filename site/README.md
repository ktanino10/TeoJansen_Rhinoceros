# Ver.1 / Ver.2 / Ver.3 紹介サイト

既存READMEと是正済みの機械資料を読むための、日本語中心の静的サイトです。機械CAD・物理結果は変更せず、表示派生だけを生成します。`r7.html` は床是正版の比較・360°・12工程・同版CG／説明動画／限定診断図です。`index.html` は全体紹介、`production.html` はVer.1/2製作記録、`comparison.html` と `viewer.html` は第一カットのMatrix・360°・組立履歴、`calculations.html` は別版r3の固定計算資料とr4入力軸カードです。旧動画は第一カットの履歴に限定し、新r7の歩行実証として使いません。

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
- `site/dist/TeoJansen_Rhinoceros/` のみを配信します。従来の静的資産12 MB／操作時3D18 MBの枠は維持し、r7の3モデル・同版CG・6本の操作時動画等を別枠30 MB、全体60 MB以内で選別配信します。全CAD／STL／Blenderや一時フレームはPagesへコピーせず、GitHubの確定版へリンクします。ページ間アンカー、許可ファイル、メタデータを検証し、`build-manifest.json` に各版の出典・ハッシュを保存。非選択モデルや動画は初期ロードしません。
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

360°・組立表示は第一カットです。別版の解析は同じ `revisionId / designId / loadcaseId` に、method（梁モデル／FEM／実CFD／説明模式図）、支点・荷重・材質・境界条件、単位、変形表示倍率、判定と閾値、図／result JSONのハッシュを揃えた単位で取り込みます。「流体・駆動→材料・構造→機構・組立→調達」を同じ条件でたどれるようにし、UNKNOWNをFAILEDやPASSへ丸めません。

資料不足のV2参考モデルを実測beforeと表示したり、数値のないカラーマップや流線を作ったりしません。追従するドライヤー冷風で無押し始動し30 cm歩く目標は別の再設計条件であり、第一カットの達成事実ではありません。

## 固定計算資料の公開adapter

- `calculation-source.json` は `v3-commercial-r3-01` の入力commit `c192be0`、成果物commit `adfa922` と原manifestのSHA256を固定します。`calculation_data.py` は全入力・成果物・図ごとの出典を読み取り照合するだけで、梁計算器・風モデル・CAD生成器を実行しません。
- 16 SVGと比較JSON／CSV・トルク内訳CSV・原manifestの計20ファイルだけを、バイト単位で変更せず配信します（約0.67 MB）。SVGは許可した描画要素・属性だけを認め、script、metadata、外部参照、private pathを拒否します。巨大なcandidate JSONや解析の全ディレクトリーをPagesへコピーしません。
- 各図にrevision／geometry revision、design ID、loadcase、method、データと図の単位、部材別変形倍率、結果の意味、元SVG・数値へのリンクを表示します。A/B/C選択で他案を非表示、画像はlazyです。JavaScriptなしでは各案のdetailsを開いて閲覧できます。
- 拡大dialogの100%はSVGの1200 px幅、200%は画像表示の拡大です。物理的な変形表示倍率（軸1000倍／固定ピボット・AC20倍等）とは別です。元SVGを独立タブで開く導線、キーボード・Escape・focus復帰、読込失敗時の原典リンクも保持します。
- A150×48／16:1、B70×48／125:1、C100×48／25:1は未完成CADの条件付き骨格解析。既存360°のA300／B90／C180とは分離し、新しい図を旧GLBに貼り付けません。
- 合格案0、名目・高抵抗の各27セルで0/27、実始動・30 cm歩行UNKNOWNを上部と結果近傍に明示。供給減率0.5は設計仮定、要求の2倍は入力軸受後の下流だけに適用し、入力軸受を一回戻す定義です。
- Panasonicの操作仕様、別機種の文献冷風6.4 m/s、Gaussianピーク・σ・±20%などの仮定を分けます。未校正パネル抗力はCFDではありません。部材図は1D梁／偏心圧縮、Cの16断面はリブ試験片の探索であり、最終FEM・全フレーム生成設計ではありません。
- `test_calculations.py` は図・データの原本ハッシュ、全16図の契約、同一ピークトルクと実たわみ値、版分離、メタデータ・不正SVG拒否を検査します。`calculations.spec.mjs` は1440px／375pxで全案の表示・非選択案の遅延取得、SVG拡大と元サイズ、単位・版、リンクのGET/hash、無JS、エラー、axeを確認します。既存workflowのliveモードにも同じ計算ページ検査を含めます。

`calculations.html#common-input` の短いカードは、別版 `v3-common-input-r4-01` の共通入力軸だけを紹介します。`cartridge-source.json` で入力・成果物commitとmanifestハッシュを固定し、質量と概算費用はその版の調達JSONから読みます。約3.94 MBの原CADプレビューSVGは、detailsを開いた時だけ固定commitのGitHubから取得します。原本を加工せず、Pagesへの巨大画像追加・新ページ・新GLB・予算上限の緩和もありません。外部参照は `build-manifest.json` の `external_images` に限定記録し、live検証でも原本ハッシュを照合します。R3の16図と第一カットは変更しません。

## r7床是正版の統合契約

`r7-source.json` がartifact・入力・統合契約・全manifest・公開元commitを固定します。
現在は **v3-integrated-walkers-r7-16-floor2**、artifact `09d49e3`／source `369434e`、
機械資料main `2a53020` です。通常公開ビルドでは作業コピーをhash照合し、浅いCI checkoutでも旧Git履歴を必要としません。
ローカル候補を検討するときは `Snapshot(use_git=True)` で指定Gitスナップショットを読み取れます。
変更後の原本と旧図を混在させず、`publicationHold` があれば本番レンダーと公開を拒否します。

```bash
# 開発用・公開とは別の出力
python3 site/build_r7_preview.py
python3 -m unittest discover -s site/r7_tests -p 'test_*.py'
python3 site/r7_blender.py --validate
PLAYWRIGHT_SOFTWARE_GPU=1 npm --prefix site test -- --config playwright.r7.config.mjs
```

開発用の `site/dist/r7-preview/TeoJansen_Rhinoceros/` はCADダウンロード原本も含むため、
`LOCAL_ONLY_DO_NOT_DEPLOY` を付けてCI・外部URLでの候補検査を拒否します。通常Pagesビルドとは別です。
サーバー例は `python3 site/serve.py --port 4176`、
URLは `http://127.0.0.1:4176/r7-preview/TeoJansen_Rhinoceros/r7.html` です。

- `r7_data.py` は正規mesh・assembly・BOM・工程・経路・native参照hashを照合し、**A750／B785／C750＝2285点**を保持します。
  頂点・三角形の間引きはなく、GLBをgzip転送するだけです。1案ずつlazy取得し、圧縮／展開後のhashを照合します。
- 旧第一カットの18／18／16状態を流用しません。r7の12工程は`orderedOperations`の各境界から在庫を再構成。
  `afterOperationIndex`、装着済み全非移動品、`visibleAfter`、再挿入履歴、経路・在庫hashが違えば停止します。
  手書きの障害物除外、異なる固定在庫の連続経路、未知ID、未装着品の取外しを許しません。
- 本体在庫と表示シーンは別欄。`prepareOnly`は独立した作業台シーンで、本体へ取り付けた数に加えません。
  主軸X−53mm、PETのY−4mm、工程07のX＋4mm下降→同じ高さでX0へ着座、
  後付け締結品・同IDの再挿入・停止角0°・手による仮支持・カラー角の反映済み属性を保持します。
  操作境界を完成参照位置で示す場合と、記録された経路標本を示す場合を分け、連続経路の新しい物理検査は行いません。
- `footFirstBenchSubassemblies` は6脚の足部を先に市販M2×12／ナイロンナット・DN-03で準備する独立状態です。
  A/Bの安定追跡IDに古い寸法名が残る場合も、`part_id`・BOM・`nativeLabelOverrides`を現行仕様として表示します。
- r7では、無圧縮の組立基準姿勢にZ0の床を重ねて接地を主張しません。
  比較は個別初回費用、仮120rpmの時間、名目原代理と要求、不利条件・床滑り仕事を分離します。
  旧Aの同じ最終式による計算比較は、Ver.2実測や公開第一カットAとは別の基準です。
- 公開時のnative／STEP／STL／BOMは機械是正の確定commitへ直接リンクします。編集用Blenderは媒体原本のcommitへ。
  約24,000円／台の部材目安と、未保有DN-03約396円・送料・未確定税を分け、共同購入平均で個別額を置き換えません。
- 旧floor不整合の反例は原機械資料のレビュー記録とローカル旧媒体に保持。
  `r7_floor_gate.py` は保存済み73位相だけを使い、元包絡と直交表示の全非接地部を照合します。
  接触solver・風・荷重を再計算しません。ローリングパッド2体だけを除外し、ロッカー芯は全±5°で確認します。

### 同版CG・説明動画・限定診断

`blender-handoff.json` は同じ2285点・全工程・圧縮／展開hash・符号付き減速比を保持します。
`r7_blender.py` は新規backgroundプロセスのみで実行し、ロックで同時生成を拒否します。
既存ライブシーンは触りません。`--build`、`--verify-native`、`--stills`、`--assembly`を直列に実行します。
旧媒体のラベル付替えでなく、床是正・足締結を含む新メッシュから全三案の比較CG・編集native・組立／逆順参照を生成します。
表示の時間は説明用、状態間は原典の境界と有限経路標本を保持し、途中経路を新たに物理検証済みとは扱いません。
字幕は日本語VTTで、灰色の装着部品・透明PETの存在と、取外し／未配置を区別します。

`r7_motion_diagnostic.py`／`r7_diagnostic_render.py` は保存された0／120／240°だけを表示します。
小角の非直交写像でCADをせん断せず、極分解による**描画専用**の直交フレームと計算点との差を数値で残します。
荷重足の対称パッド中心を等高にする表示角が機械範囲で一意なら使いますが、独立solver角nullは保持。
空中足など未確定のロッカー・ばね線材は省略します。床補正・任意前進・伸縮リンク・補間は追加しません。
**完全なCAD歩行動画は未生成**で、サイトに再生ボタンを用意しません。

`r7_finalize_media.py` は同版床ゲート・全メッシュ／在庫検証・MP4フレーム数とデコードを確認し、
`docs/ver3/r7_display_floor2/` と `Blender/Ver.3/integrated_r7/r7_floor2.blend` に原本とmanifestを保存します。
CIはそこから表示派生を作るだけでBlenderや物理計算を再実行しません。
元5点＋新Cの相手歯車2点の実層確認も、支持薄膜除去・実はめあい・実造形済みの認定とはしません。
