# テオ・ヤンセン リノセウス 試作2号機  
🇺🇸 [English version available here](./README.md)

---

## 背景  

[テオ・ヤンセン ストランビースト](https://youtu.be/MYGJ9jrbpvg?si=qMYy9t26JGlFZo1x) の動画をYouTubeで見て、風で動く自然な動きの美しさに強く惹かれました。  
一方で、その内部機構にも興味を持ち、「自分の手で再現してみたい」と思ったことがこのプロジェクトのきっかけです。  

ただし私は、完全な模倣ではなく、**よりメカニカルな造形美と自分の好きなデザイン要素**を取り入れたいと考えました。特に私は『νガンダム』のデザインが好きで、今回はそのカラーリングや構造的ニュアンスを参考にしています。

---

## リポジトリの活用方法と概要  

このリノセウスは、複数回の試作と改良を経て **Ver.1 → Ver.2** へと進化してきました。  
詳細な手順書はありませんが、下記のPDFやアニメーションを参考にすれば、十分に製作可能だと思います。  

各バージョンには対応する **STLファイル** が格納されています。  
初めて挑戦される方は、まず **Ver.1** の構造や動きを理解することをおすすめします。  

私自身の製作過程（Log）については、記憶している範囲で次の章にまとめています。


| バージョン | 概要 | 図面 | 動画 |
|-------------|------|------|------|
| Ver.1 | 初期設計。Fusion 360 でモデリング | 1.[テオヤンセン2Dv1.pdf](./docs/テオヤンセン2Dv1.pdf)<br> 2.[テオヤンセン2D図面.pdf](./docs/テオヤンセン2D図面最新.pdf)  | 1.[組み立て動画](https://youtu.be/Q7d0sq1SNJ0?si=nhAsBmjNhFsv74Ju)<br>2.[動きのシミュレーション](https://www.youtube.com/watch?v=RxUTcOTfPt0) |
| Ver.2 | 改良版。150%スケール、安定した動作 ||1. [初回動作テスト動画](https://youtu.be/T3U7c1Mr3Y8?si=hUQZJXoczCW0qAUG)<br>2.[紹介動画](https://youtu.be/JzXOxTJvHzw?si=1MGZkGYogJQsFP-6) |

- **その他**：本モデルは、Bambu Lab社が提供する3Dプリンタ向けコミュニティサイト [**MakerWorld**](https://makerworld.com/ja/models/1971139-n-gundam-style-strandbeest-ver-2) にも掲載しています。
---


# Ver.1 製作過程

## 1. 情報収集
YouTube や各種画像を観察し、構造や動作原理を推測・理解しました。  
世界中の多くの制作者が作品を公開しているため、**ネットでのリサーチや動画閲覧**が非常に参考になります。

<a href="https://youtu.be/MYGJ9jrbpvg?si=qMYy9t26JGlFZo1x" target="_blank">
  <img src="https://img.youtube.com/vi/MYGJ9jrbpvg/0.jpg" width="480" alt="Theo Jansen Strandbeest YouTube thumbnail">
</a>

---

## 2. 設計
Autodesk **Fusion 360** を使用して、すべてのパーツを3Dモデリングしました。  
初期段階では、主に実際の作品を観察しながら形状を写し取ることを重視しており、  
細かな力学計算などはほとんど行っていませんでした。  

このため、後の段階で試作と微調整を何度も繰り返すことになり、  
最も時間と労力を要した工程の一つとなりました。  
下記の図面は、あくまで**参考資料の一つ**としてご覧ください。  

### 📄 **Ver.1 設計図面（2D Drawing）**  
[テオヤンセン2D図面.pdf](./docs/テオヤンセン2D図面最新.pdf)

> ※GitHub上ではPDFが直接プレビューされない場合があります。その場合は上のリンクから開いてください。

### 🎨 Ver.1 完成予想図レンダリング（Fusion 360 Rendering）

Ver.1 モデルを Fusion 360 上でレンダリングした完成イメージです。  
実際の3Dプリントを行う前に、形状・構造・色味・陰影を確認するために作成しました。  
設計段階で“動くアート”としての姿を可視化することを目的としています。

---

<div align="center">

| 斜めビュー | 正面ビュー | 側面ビュー |
|-------------|-------------|-------------|
| <img src="./docs/images/テオヤンセン1.png" width="280" alt="斜めビュー"> | <img src="./docs/images/テオヤンセン2.png" width="280" alt="正面ビュー"> | <img src="./docs/images/テオヤンセン3.png" width="280" alt="側面ビュー"> |

| 裏面ビュー | 反対側面ビュー | 逆斜めビュー |
|-------------|----------------|----------------|
| <img src="./docs/images/テオヤンセン4.png" width="280" alt="裏面ビュー"> | <img src="./docs/images/テオヤンセン5.png" width="280" alt="反対側面ビュー"> | <img src="./docs/images/テオヤンセン6.png" width="280" alt="逆斜めビュー"> |

</div>

### 🧩 Ver.1 組み立てイメージ  
📄 **2D図面（組み立て参考）**  
[テオヤンセン2Dv1.pdf](./docs/テオヤンセン2Dv1.pdf)

> ※GitHub上ではPDFが直接プレビューされない場合があります。その場合は上のリンクから開いてください。

🎥 **組み立て動画**  
<a href="https://youtu.be/Q7d0sq1SNJ0?si=nhAsBmjNhFsv74Ju" target="_blank">
  <img src="https://img.youtube.com/vi/Q7d0sq1SNJ0/0.jpg" width="480" alt="Ver.1 Assembly YouTube thumbnail">
</a>


### 🦿 Ver.1 動作イメージ  
🎥 **Simulation Video**  
<a href="https://www.youtube.com/watch?v=RxUTcOTfPt0" target="_blank">
  <img src="https://img.youtube.com/vi/RxUTcOTfPt0/0.jpg" width="480" alt="Ver.1 Motion Simulation YouTube thumbnail">
</a>

---

---

## 3. 3Dプリント
印刷方向・分割を工夫しながら出力。精度と強度のバランスを最適化しました。  

<img src="./docs/images/88187.jpg" width="500" alt="3Dプリンター出力中">

---

## 印刷時の推奨設定  

- **スケール**：150%（脚部のみ160%推奨）  
- **素材**：ABS樹脂（ガンプラにも使用される、耐熱約80℃）  
- **プリンタ**：Bambu Lab製FDMプリンタ  
- **接着剤**：タミヤ製 ABS用セメント  
- **後処理**：400 → 600 → 800番のヤスリで研磨  
- **その他**：本モデルは、Bambu Lab社が提供する3Dプリンタ向けコミュニティサイト [**MakerWorld**](https://makerworld.com/ja/models/1971139-n-gundam-style-strandbeest-ver-2) にも掲載しています。

---

🎥 **テストプリント動画**  
[![Watch on YouTube](https://img.youtube.com/vi/IP1fvOTGgno/0.jpg)](https://www.youtube.com/shorts/IP1fvOTGgno)

---

## 4. 研磨
電動やすりでクランクシャフトを研磨しました。  
**400 → 600 → 800番** の順にやすりをかけ、滑らかな表面に仕上げています。  

<img src="./docs/images/88075_0.jpg" width="500" alt="クランクシャフト研磨後">

🎥 **研磨工程の動画**  
[![Watch on YouTube](https://img.youtube.com/vi/w-jB8-OUFfA/0.jpg)](https://www.youtube.com/watch?v=w-jB8-OUFfA)

---

## 5. 超音波洗浄
研磨後のパーツを **超音波洗浄機** で洗浄しました。  
洗浄水には **少量の洗剤** を加え、表面張力を下げて気泡が細部まで入り込み、微細な粉や削りカスを効果的に除去しています。  

<img src="./docs/images/88073_0.jpg" width="500" alt="超音波洗浄の様子">

🎥 **超音波洗浄の動画**  
[![Watch on YouTube](https://img.youtube.com/vi/2DyWBz1phlA/0.jpg)](https://www.youtube.com/watch?v=2DyWBz1phlA)

---

## 6. 塗装
塗装ブースでエアブラシ塗装を行いました。  
使用した機材は以下の通りです。

- エアブラシ  
  <img src="./docs/images/2339528.jpg" width="500" alt="使用したエアブラシ">

- 塗装ブース  
  <img src="./docs/images/88072.jpg" width="500" alt="使用した塗装ブース">

安全面にも配慮し、防塵マスクを着用しています。  
<img src="./docs/images/339.png" width="300" alt="防塵マスク">


### 🎨 塗装済み部品
塗装後の部品と研磨・塗装前後の比較を示します。

- 塗装済み部品の乾燥中  
  <img src="./docs/images/88089_0.jpg" width="500" alt="塗装済み部品乾燥中">

- クランクシャフト比較（左：研磨前・塗装前／右：研磨後・塗装後）  
  <img src="./docs/images/88209_0.jpg" width="500" alt="クランクシャフト比較1">  
  <img src="./docs/images/88210_0.jpg" width="500" alt="クランクシャフト比較2">

- 塗装完了後の全体  
  <img src="./docs/images/88208_0.jpg" width="500" alt="塗装済み製品">

---
## 7. デカール貼付
専用剤でデカールを接着し、綿棒で位置を整えた後、トップコートで艶消し仕上げを行いました。  
細部のディテールを際立たせ、より立体的で完成度の高い外観に仕上げています。  

### 📸 デカール貼付の様子
貼り付け作業中および仕上げ直後の様子を以下に示します。  

<img src="./docs/images/88060_0.jpg" width="500" alt="デカール貼付作業1">  
<img src="./docs/images/88061_0.jpg" width="500" alt="デカール貼付作業2">  
<img src="./docs/images/88062_0.jpg" width="500" alt="デカール貼付作業3">  
<img src="./docs/images/88059_0.jpg" width="500" alt="デカール貼付作業4">

---


## 8. 最終組立と動作確認
歯車伝達、クランクシャフト回転、風力動作を確認し、滑らかなメカニズムの動きを確認しました。  








---

## Ver.1 が失敗した主な要因  

1. **歯車設計の不備**  
   クランクシャフトに対してギア比が小さすぎ、風力での駆動が困難でした。  
   → 改良ではトルクを考慮し、大歯車と小歯車の組み合わせを再設計。  

2. **風車形状の非効率性**  
   六枚羽構造では風を十分に捉えられず、サボニウス型風車へ改良。  

3. **噛み合わせ精度の問題**  
   回転軸やジョイントのクリアランスを見直し、摩擦ロスを低減。  

4. **軽量化の検討**  
   Fusion 360 の Generative Design を用いて構造最適化を試みました。  

---

## Ver.2 の改良と成果  

これらの課題をすべて見直し、構造強度と動作の安定性を向上。  
以下が、**初めて実際に動作した瞬間**の映像です。  

🎥 **初動テスト動画**  
[![Watch on YouTube](https://img.youtube.com/vi/T3U7c1Mr3Y8/0.jpg)](https://youtu.be/T3U7c1Mr3Y8?si=hUQZJXoczCW0qAUG)

🎥 **紹介・再検証動画**  
[![Watch on YouTube](https://img.youtube.com/vi/JzXOxTJvHzw/0.jpg)](https://youtu.be/JzXOxTJvHzw?si=1MGZkGYogJQsFP-6)

📄 **設計図面**  
- [テオヤンセン2D図面最新.pdf](./docs/テオヤンセン2D図面最新.pdf)

---

## 🖼️ Fusion 360 モデル画像：歯車比較  

このセクションでは、Ver.1 と Ver.2 の歯車設計の違いを示しています。  
Ver.1 は初期設計、Ver.2 はギア比とトルク伝達を見直して再設計したモデルです。

### ⚙️ Ver.1（初期設計）

<div align="center">

| 正面ビュー | 側面ビュー |
|-------------|-------------|
| <img src="./docs/images/テオヤンセンv2joint v32.png" width="350" alt="Ver1 Front View"> | <img src="./docs/images/テオヤンセンv2joint v322.png" width="350" alt="Ver1 Side View"> |

</div>

---

### ⚙️ Ver.2（改良設計）

<div align="center">

| 正面ビュー | 側面ビュー |
|-------------|-------------|
| <img src="./docs/images/テオヤンセンv4joint v15.1.png" width="350" alt="Ver2 Front View"> | <img src="./docs/images/テオヤンセンv4joint v15.png" width="350" alt="Ver2 Side View"> |

</div>

---

##  比較ポイント  

| 観点 | Ver.1（初期設計） | Ver.2（改良設計） |
|------|--------------------|--------------------|
| **ギア比** | 小さく設定していたため、風力では十分なトルクを得られず回転が不安定。 | ギア比を見直し、トルク伝達効率を最適化。より軽い風でも駆動可能に。 |
| **歯車形状** | 厚み・ピッチが不均一で、噛み合い時に抵抗が発生。 | 歯形を修正し、より滑らかな噛み合いを実現。摩擦ロスを低減。 |
| **クランク配置** | 駆動軸との位置関係がずれ、回転エネルギーが分散。 | クランク角とギア軸の位置を再設計し、力の伝達経路を効率化。 |
| **構造安定性** | 部品数が多く、強度にムラがあった。 | 補強リブと一体構造設計を導入し、剛性を向上。 |
| **見た目（デザイン）** | 初期の実験的構成で、部品の配置に無駄が多い。 | 機能と美観を両立した構造へ。メカニカルで均整の取れた外観に。 |
| **動作結果** | クランクシャフトが風力で自立回転せず。 | 風車から歯車群を経てスムーズにクランクが回転し、脚部が連動。 |

---
 **まとめ**  
Ver.1 は「アイデアの具現化」に焦点を当てた初期モデルで、歯車設計やクランク配置に改善の余地がありました。  
Ver.2 では力学的バランスを再構築し、**風の力だけで自然に歩行するリノセウス**へと進化しています。  


🖼️ **3Dプリントパーツ写真**  
![Printed Parts](./images/3dparts.jpg)

---

## 🧪 試作ギャラリー（Prototyping Gallery）

本プロジェクトでは、多数の試作と検証を通じて、構造・形状・強度・美観を改良してきました。  
ここでは、その一部を紹介します。

---

### ⚙️ クランクシャフトと脚部フックの試作  

<div align="center">
<img src="./docs/images/87812.jpg" width="600" alt="クランクシャフトと脚部フックの試作">
</div>

フック構造はクランクの回転力を脚部の揺動に伝える重要要素。  
複数の寸法・角度で試作を繰り返し、強度と可動範囲のバランスを最適化しました。

---

### ⚙️ 歯車の試作群  

<div align="center">
<img src="./docs/images/87813.jpg" width="600" alt="歯車の試作群">
</div>

ギアピッチ、厚み、噛み合わせ精度を比較。  
初期モデルでは摩擦ロスが大きかったため、トルク伝達効率と滑らかさを重視して形状を改良しました。

---

### 🎨 クランクシャフトの仕上げ比較  

<div align="center">
<img src="./docs/images/87814.jpg" width="600" alt="クランクシャフト仕上げ比較">
</div>

左：印刷直後　右：研磨＋塗装済み。  
ABS樹脂の層跡を丁寧に磨き、エアブラシ塗装とトップコートで滑らかな質感へ。  
機能性と美しさの両立を目指しました。

---

### 🌬️ 風車の試作比較  

<div align="center">
<img src="./docs/images/87816.jpg" width="600" alt="風車の試作比較">
</div>

左3枚：**羽根型風車**　右：**サボニウス型風車**。  

羽根型風車は、一見すると風を十分に受け止められない構造に見えますが、  
実際には**風を逃がすことで柔らかく動く特性**を持っていました。  
この挙動の観察から、「風をどう受け止めるか」だけでなく、  
**「風をどう逃がすか・どう調和させるか」**という視点を得ることができました。  

この考察を踏まえ、サボニウス型風車では風の流路とトルク伝達効率を両立させ、  
より安定した回転が可能となりました。

---


---


## 🌬️ 今後の展望  

Ver.3ではさらなる「自然な歩行」を目指し、以下の改善を検討しています。  
ただ、今は少し休暇を取り、これまでの学びを整理する時間を取ろうと思っています。  

---

### 💡 改良構想  

- **Generative Design（GD）の導入**  
  Fusion 360 のジェネレーティブデザイン機能を用い、  
  最適構造・軽量化・強度バランスの探索を進めています。  

  <div align="center">

  🧠 **GD設計中の様子**  
  <img src="./docs/images/GD1.jpg" width="420" alt="GD Design Process">

  ⚙️ **Ver.2モデルとの比較（上：GD設計案／下：Ver.2）**  
  <img src="./docs/images/87811_0.jpg" width="420" alt="GD vs Ver2 Comparison">

  </div>

---

- **軽量化とトルク伝達効率の向上**  
  部品の一体化や支点位置の最適化により、  
  クランクシャフト〜歯車系の損失を低減し、風エネルギー伝達を最大化します。  

- **CFD解析による風エネルギーの可視化**  
  SimScaleなどのクラウドCAEを利用し、  
  風車翼からクランク機構へのエネルギー伝達過程をシミュレーションする予定です。  

---

## 感想

このプロジェクトを通じて、私は**テオ・ヤンセン氏の思想とエンジニアリングの融合**を深く体感しました。  
歯車比やクランク機構など、車のエンジンや時計の動力伝達の基本を“風力のみ”で再現することは、まさに**機械工学とアートの接点**でした。  

今後もこのプロジェクトを教育や展示、創作活動を通して広げていけたらと思います。  
新しいアイデアや改良案があれば、ぜひ教えてください。

---

📘 **English version:** [README.md](./README.md)

