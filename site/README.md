# Ver.1 / Ver.2 / Ver.3 紹介サイト

既存READMEと是正済みの機械資料を読むための、日本語中心の静的サイトです。CADや動画は再生成しません。Ver.1/2の実物記録、Ver.3の概念設計・規定歩行、未検証事項を区別します。

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

表示確認はリポジトリのルートで `python3 site/serve.py --port 4173` の後、`http://127.0.0.1:4173/TeoJansen_Rhinoceros/` を開きます。プレビューサーバーはループバックのみで待ち受け、並列の画像取得に対応します。テスト自体もこのリポジトリ配下のパスで実行します。

## 正規資料と公開物

- `build.py` は `docs/ver3/comparison.json` とC構造探索の値から三案の寸法・比率・質量・残差・時間倍率・体積代理量を生成します。
- 写真／CGは明示した14画像だけをWebPへ縮小。原写真の画面が入る部分を表示用にトリミングし、EXIF・XMP・ICCなどを派生表示画像から除去します。原本は変更しません。
- 既存のMP4五本と、操作するまで読まないGIF一本を選別コピーします。初期表示で動画/GIF/YouTube/外部フォントは取得しません。
- CAD、STL、BOM、文書等は確定コミットを参照するGitHubリンクです。全リポジトリや原データ162 MBをPagesへ配信しません。
- `site/dist/TeoJansen_Rhinoceros/` のみを配信します。12 MBの上限、ファイル許可リスト、参照リンク、画像メタデータをビルドで確認し、`build-manifest.json` に出典・ハッシュ・画像処理を記録します。
- CIのPR実行は生成と実ブラウザー確認のみ。`main`へのpushまたは`main`の手動実行は、同じ検証に合格した静的出力だけを公式Pages Actionsで配信します。deploy jobのみ`pages:write`/`id-token:write`を持ちます。

公開後は `SITE_URL` にデプロイが返した実URLを指定して `npm --prefix site test` を実行できます。公開URLのGET、主要画像・MP4、GitHub側の代表ダウンロードも確認します。CI成功だけを実配信の確認として扱いません。

## 保持する制限

Ver.3は実機未検証、全案の接地残差3 mm目標は未達、Bは名目トルク入力不足です。規定120 rpm入力の映像にはA1×／B8×／C2×を表示します。Cは組立・接合・抵抗測定候補であり、風力完成機の推奨ではありません。パラメトリック生成設計の体積代理量の改善を、装置全体の軽量化率と混同しません。
