# サイトと資料の使い方

[日本語](USER_GUIDE_ja.md) | [English](USER_GUIDE_en.md) | [資料の対応一覧](README_ja.md)

## ページを選ぶ

[日本語サイト](https://ktanino10.github.io/TeoJansen_Rhinoceros/)は従来のURLです。[English](https://ktanino10.github.io/TeoJansen_Rhinoceros/en/)は同じ内容の英語版です。各ページ上部の切替は、同じページ・選択案のクエリ・見出しアンカーを保持します。言語の選択にアカウント、通信による設定保存、アクセス解析は使いません。

| ページ | 内容と版 |
|---|---|
| [全体紹介](https://ktanino10.github.io/TeoJansen_Rhinoceros/index.html) | 現行Ver.3.1の画像・比較値・配布先を主入口に、Ver.1/2/3.0の履歴を分離 |
| [製作記録](https://ktanino10.github.io/TeoJansen_Rhinoceros/production.html) | Ver.1の工程と、記録が残るVer.2の改良・完成写真・当時のテスト |
| [Ver.3.0 初期比較案・履歴](https://ktanino10.github.io/TeoJansen_Rhinoceros/comparison.html) | 旧A300/B90/C180 mmのMatrix・CG・規定動画・旧ダウンロード |
| [Ver.3.0 旧360°・組立](https://ktanino10.github.io/TeoJansen_Rhinoceros/viewer.html) | 同じ旧版の全メッシュ・部品ID・原典対応工程。現行ではない |
| [計算資料](https://ktanino10.github.io/TeoJansen_Rhinoceros/calculations.html) | 別版r3の材料・構造・流体モデル、r4入力カートリッジ |
| [Ver.3.1 比較・360°・12工程](https://ktanino10.github.io/TeoJansen_Rhinoceros/r7.html) | 現行の床是正版A750/B785/C750＝2285部品。内部ID r7/floor2 |
| [Ver.3.1 連続歩行](https://ktanino10.github.io/TeoJansen_Rhinoceros/walking.html) | 同じ現行形状を使う、別版の運動学・準静的な表示モデルと日英動画 |

Ver.3.1は既存の床是正版の公開名で、設計原本の改訂ではありません。内部ID `v3-integrated-walkers-r7-16-floor2` と成果物・入力コミット・ハッシュは[出典契約](../site/r7-source.json)で追えます。動画のr7表記もこの形状を指します。`r7-floor2-walking-kinematic-v1` は同じ形状に追加した別版の姿勢モデルです。r2/r3/r4/r6は内部研究・部分設計のIDで、作品のVer.2やVer.3.1を意味しません。

古い `index.html#ver3` も現在はVer.3.1へ案内します。旧 `comparison.html`／`viewer.html` はVer.3.0履歴として残し、現行へのリンクを明示しています。[現行の配布資料](https://ktanino10.github.io/TeoJansen_Rhinoceros/index.html#downloads)と[旧配布資料](https://ktanino10.github.io/TeoJansen_Rhinoceros/comparison.html#downloads)は混用しません。

## 3Dと動画を操作する

案を選び「読み込む」を押すまで、3Dエンジン・GLB・運動データは取得しません。歩行は停止状態で始まります。ドラッグ／指1本で回転、ホイール／指2本で拡大・移動できます。3D領域へフォーカスすると矢印で回転、＋／−で拡大縮小、Homeで全体表示。組立ではShift＋矢印で移動、歩行ではSpaceで再生／停止できます。操作説明は各ビューの近くにもあります。

組立の「全完成」は画面上の参照状態で、実組立済みを意味しません。r7では「操作境界／経路標本」で在庫・一時取外し・同ID再挿入を追えます。別作業台の準備は本体の装着数量へ加算しません。JavaScriptやWebGLが使えない場合も、静的な工程・部品表・画像・資料を参照できます。

動画は自動再生しません。連続歩行の日本語ページには日本語注記版、英語ページには英語注記版を表示します。歩行のCCは既定で重ねず、利用者が任意にONにできます。選択済みのCCを繰り返し強制OFFにはしません。小さい画面では全画面表示・任意字幕・動画の近くの通常サイズ本文を利用してください。字幕の可読性を一律の縮小CSSで変更しません。

歩行動画は全案とも**規定入力120 rpm・時間圧縮16×・4周期**です。A約18秒/B約64秒/C約20秒、約37 cmの前進は計算表示で、実時間の歩行性能や実測距離ではありません。空中ロッカーの中立復帰と手続きばねは明示した表示仮定で、原解析の独立ロッカー角nullを変更しません。

[日英媒体の来歴](ver3/r7_walking_locales_v1/manifest.json)は、同じ運動・時刻から作った言語別の注記・poster・字幕を記録します。元の歩行モデル資料と初版の媒体・配信枠の記載は固定された履歴として保持し、現在の日英表示と区別しています。

## 資料・印刷データの凡例

主要18資料の英語版は日本語原本を変更しない対訳です。英語版冒頭に原本へのリンクとSHA256があります。[対応manifest](translation-manifest.json)に範囲とハッシュを記録しています。元READMEの日英ペアはVer.1/2の製作記録です。

- **CAD・STEP・STL・GLB**：日英で共通。言語のための再設計、再モデリング、部品の省略はしていません。
- **BOM 7点・数値JSON/CSV**：BOMの項目は既に英語・共通で、原本をそのまま共有します。数量・部品ID・SKU・価格・URLは不変。JSONの原注記は日本語の場合がありますが、主要解説は対訳資料を使えます。
- **Ver.1原図PDF**：[組立参考図](テオヤンセン2Dv1.pdf)／[詳細参考図](テオヤンセン2D図面最新.pdf)は**原図（日本語）**です。英訳図面やVer.2専用図面とは表示しません。記載のない寸法・公差・工程を写真から補いません。
- **r7のPET型紙・断面図**：部品IDと寸法の原本を共用。案・版・部品IDを照合し、記載のmm寸法を優先します。図の線・穴・寸法を翻訳のために変更していません。切断・工具条件は各案の説明と共通組立にあります。
- **写真・旧動画**：元の実物写真とCGの区別を維持。外部YouTube動画は元の言語で、再投稿していません。旧r7組立動画の焼込みラベルは英語で、日英の工程字幕を対応ページから使えます。

Ver.1/2の過去の倍率150%／脚160%をVer.3へ重ねません。Ver.3はmm・100%。代表スライスは限定したソフトウェア検査で、全機の印刷・支持除去・はめあいの認定ではありません。プリンターへの送信・印刷開始はしません。

## 判定と予算を読み分ける

現行Ver.3.1（内部r7/floor2）の部材費目安は**約24,000円／台**。個別初回A23,305.13円/B23,735.37円/C23,154.43円と、未保有DN-03約396円・送料・未確定税等は区別します。共同購入平均を個別費用へ置換せず、旧20,000円／23,000円条件はその版の履歴です。

`manufacturingRelease=false`、実機合格数0、実風・実自己始動・実30 cm歩行はUNKNOWNです。デジタルの有限標本PASSは、連続する全経路・全公差・CFD/FEM・耐久・実機運転の認定ではありません。使用材料や接着・硬化・工具は製品の指示と現物確認を優先し、過去の記録だけを安全保証にしないでください。
