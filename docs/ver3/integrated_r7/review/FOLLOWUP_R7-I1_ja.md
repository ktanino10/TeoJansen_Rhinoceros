# 同じ独立担当によるR7-I1限定是正確認（保存版）

原本の所見・数値・CONFIRMED判定は変えず、作業環境の絶対パスだけを伏せています。本文中のプローブは原監査ディレクトリの保存物です。製作・実歩行の合格や新しい全機レビューとは区別します。

# R7-I1 限定是正差分の独立確認

## 結論：CONFIRMED

**R7-I1は、宣言された有限CAD組立経路の検証範囲で是正を確認した。残存するR7-I1指摘なし。**

初回と同じ独立レビュー文脈で実施した1回の限定追跡であり、新しい全機レビューや別担当による承認ではない。元commitに対する初回のCritical指摘は正当な履歴として残る。初回`REVIEW_ja.md`、`findings.json`、`probes/`、対象packet、作者の検証結果は変更していない。

## 凍結対象・identity

- Original: `922a47c5ab815fc186dd1486726123ab08552ede`
- Corrective candidate: `a756a229ed133d15b70149ea949a5347ad24d684`
- Corrective source: `124cf4a4555c7b68dd6a01deb41146ca39ed29e6`
- SourceHash: `197e5533bd60783c3ba5ff7222798223ffaa2712d92eb38e3d3c0b7a8aec5ee1`
- Revision: `v3-integrated-walkers-r7-15`／candidateRevision: `v3-integrated-walkers-r7-15-review1`
- Worktree: `<worktree>`
- Branch: `ktanino10-ver3-feasibility-redesign`
- B native（変更なし）: `FreeCAD/Ver.3/integrated_r7/B/Walker_B.FCStd`、SHA256 `dd6a68352a5fab903d5d9adb594b7bf1429a039a187ca375a344576e88ba9f02`
- 是正patch SHA256: `2d8cc37eacf9ca3a29d456ae98209ef78a4d84f94e70720634d887fe61877769`。packetのpatchは元commit→候補commitの対象ソース／文書差分と完全一致した。

## 実際に再確認した範囲

### 1. 操作途中の在庫と単一の定義元

追加7テストを読み、`build_integrated_contract.py`の操作定義と`assembly_path_scenarios()`（179–256行）、`validate_path_inventory()`（259–270行）、`check_integrated_access.py`（41–98行）、package検証の呼出しを確認した。

自作`f01_inventory_contract.py`は、**各instanceの操作履歴の最後のイベント**から在庫を再構成する。`visibleAfter`や作者helperの出力を期待値の代用にしていない。A/B/C各10経路の境界・scene・moving/fixed・固定姿勢・在庫hash・経路定義hashを、保存結果と照合した。

Bの変更された境界は次のとおり。

| 工程・境界 | scene数 | moving | fixed | 経路後に追加 | 工程末 |
|---|---:|---:|---:|---:|---:|
| 03、operation 0後 | 185 | 50 | 135 | 継手20品 | 205 |
| 07、operation 1後 | 288 | 12 | **276** | カラー／スペーサー4品 | 292 |
| 09、operation 0後 | 294 | 1 | 293 | 保持／接合締結品23品 | 317 |

- A/Cの工程07固定側は各241品。各案の工程末在庫は元の工程JSONと完全一致する。
- Bの`S_GUARD_UPPER_RIGHT_2_001`、`H_BOLT_M3_20_011`、`H_BOLT_M3_20_012`は、**新しい両区間で固定側に存在し、固定姿勢overrideなし**。
- 工程06の別作業台sceneは未装着の`prepareOnly`12品だけ。装着済み本体との集合は交わらず、sceneOffsetは`[300,0,0]mm`。本体の装着品を通常の挿入sceneから隠す仕組みではない。
- 工程03の継手、工程07のカラー等、工程09の締結品が、検査境界より前に追加された扱いにはなっていない。変更境界に本指摘を残す新たな在庫の曖昧さは見つからなかった。

### 2. 同じ実nativeによる旧干渉と新経路

`f02_native_paths.py`を既存FreeCAD 1.1.3の独立CLIで実行。元の形状を保存・再生成せず、コピーの平行移動と実solid単位のBooleanを使用した。

**旧経路の正の対照：**

- `[0,0,+10]mm`のハブ／PET：期待・実測とも **9.662464586877448mm³**
- 同位置の前ケージ／ボルト011：期待・実測とも **2.5404894418411144mm³**
- `[0,0,+5]mm`の前ケージ／ボルト012：期待・実測とも **2.332757803137632mm³**

**是正経路：** 移動12品と操作履歴から得た固定276品を全て候補とし、包絡が重なる組を実B-repで検査した。固定品はnative位置のまま。

- X=+4mmでの下降：Zオフセット **40／20／10／7.5／2.5／0mm**
- 最終高さでの軸方向着座：Xオフセット **4／2.5／1.5／0mm**
- 合計10検査点（共通端点の区間別確認を含む）、**124回のB-rep部品対検査、最大交差0mm³**。
- 判定閾値は元と同じ`1e-5mm³`。7.5、2.5、1.5mmという保存サンプル間の代表点も含めた。
- 下降終点と着座始点はともに**`[4,0,0]mm`**。移動品・固定品・固定姿勢・sceneは同じ。着座終点は**`[0,0,0]mm`**で、完成形状を移動したままにはしていない。

**固定姿勢の扱いの対照：** 工程04の上側PETを`[0,-4,-40]mm`に置き、固定183品を保持した。3本の主軸だけをX方向−53mmとする条件を実形状へ適用すると交差0。`S_GUARD_UPPER_RIGHT_1_001`と`H_MAIN_HEX100_001`は、引込みなしでは**1.3021210203793088mm³**、指定の引込みありでは**0mm³**。軸を一覧から削除して通したわけではない。

### 3. 不正な結果を受理しないこと

自作プローブで保存結果の**メモリ上のコピーだけ**を改変し、以下の拒否を確認した。

- 装着済みPETまたは保持ボルトをfixed/sceneから落とし、在庫・経路hashを再計算しても、`fixedNames`不一致で拒否。
- `afterOperationIndex`の変更を拒否。
- ボルトを固定姿勢overrideで退避させる改変を拒否。
- path定義への手書き除外、2区間の0.25mm不連続、装着済み部品を別作業台に混ぜる定義を拒否。

contract生成とpackage検証が使用する共有validatorの両入口で上記の結果改変4種を拒否し、scenario生成では追加3種を拒否した（計11回の否定対照）。生成器全体は出力を伴うため実行していない。

`verify_integrated_package.main()`は、候補の`independentFollowUpStatus=PENDING`で**期待どおり停止**した。これは新規欠陥ではなく、追認を先取りしないgateの確認である。候補内のPENDINGは書き換えていない。

### 4. 文書・結果・凍結範囲

- `ASSEMBLY_ja.md`、工程JSON、経路JSON、ソース定義、schema 2の契約が、X+4下降→X4→0着座と後付け締結の順序に一致する。
- 候補284ファイルとmanifest／contractの指定hashを検査。元279件中、是正対象の16件以外の**263ファイルは同一hash**で、CAD・数値・BOM・価格を含む不変領域に差分なし。
- source/dependency41件からSourceHashを再計算した。
- 初回報告・プローブ・packet・作者結果の15私有ファイル、および`before_correction`の12コピーを確認。後者は元Git blobとも一致する。元commitはGit内に存続。
- HEADは候補commit、branch不変、作業ツリーclean。repository、candidate、初回成果、作者成果は編集していない。

## 保存したプローブと実行コマンド

```bash
R=<private-review>
PYTHONDONTWRITEBYTECODE=1 python3 "$R/followup_probes/f01_inventory_contract.py"
PYTHONDONTWRITEBYTECODE=1 /Applications/FreeCAD.app/Contents/Resources/bin/python "$R/followup_probes/f02_native_paths.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$R/followup_probes/f03_integrity.py"
```

3本とも完了。作者の72回帰試験・全A/B/C経路検査を再実行して独立確認の代わりにはしていない。

## このCONFIRMEDの境界

R7-I1の是正差分だけを確認した。新しい全5分野レビュー、A/Cのnative経路再計算、全連続経路・全製作公差・実際の手保持や工具作業の証明ではない。別の幾何／空力／価格の再評価も行っていない。

**manufacturingRelease=false、qualifiedWalkingPrototypeCount=0、実始動・実30cm・物理未知は維持する。** 本確認の候補側記録とgateの更新は調整担当の作業であり、このレビューでは行わない。追加調査を開始せず、この限定追跡を終了する。
