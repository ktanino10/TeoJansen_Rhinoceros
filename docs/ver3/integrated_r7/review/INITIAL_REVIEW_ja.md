# 初回独立レビュー保存版

原本の所見・数値・判定は変えず、作業環境の絶対パスだけを `<worktree>` / `<private-review>` に置き換えています。本文中の `probes/` は原監査ディレクトリを指します。原本と実行プローブはセッション監査保管にあり、下記JSONに原本ハッシュを保存しています。是正後の追認とは区別してください。

# R7 全機統合パッケージ・独立レビュー

## Review Summary

**Verdict: REQUEST CHANGES**

凍結済みモデル・計算・調達数量の代表検証では、多くの対応関係を再現できた。一方、**Bの工程07は、工程04で装着済みの部品を経路検査から除外したままPASSになっており、実native形状では途中干渉する**。同一構成・同一工程の統合検証が完了した状態としては受け入れられない。

これは**新規の独立R7レビュー1回分**であり、旧R6担当`dae672f2-99c0-495a-a6ca-059e1bfbf790`、旧R6-1担当`5c0e8d4c-4f0a-4981-bcf7-91b479a2c8d2`の継続・承認ではない。追加エージェント／別セッション／factoryは使用していない。

## 不変の対象

- Repository: `ktanino10/TeoJansen_Rhinoceros`
- Worktree: `<worktree>`
- Branch: `ktanino10-ver3-feasibility-redesign`
- 対象commit: `922a47c5ab815fc186dd1486726123ab08552ede`
- Source commit: `2bec2d1784c0850946cc6a426aab7fd206bcf02c`
- Revision: `v3-integrated-walkers-r7-15`
- SourceHash: `f537ee3120f5ea8dbbe8fbe501142375e65d67a3b53ffb2f540b7cb5df3a9574`
- `targets.json`の279ファイルは開始時・終了時とも一致。manifestおよびcontractの指定ハッシュも終了時一致。HEAD・branch不変、`git status --porcelain=v1 --untracked-files=all`は空。
- repositoryへの書込み、CAD保存、再生成、履歴変更、インストール、機器操作、購入、公開は行っていない。レビュー成果だけをこの私有ディレクトリへ保存した。

## 指摘：高確信・判断を変更するもののみ

### Critical Issues

| ID | 重要度／確信度 | 正確な対象 | 最小再現・期待値／観測値 | 影響と最小是正 |
|---|---|---|---|---|
| **R7-I1** | **Critical／High** | `scripts/ver3/check_integrated_access.py:98–101`, `stages()`の`front_basket_and_rotor_lower`。対応する`build_integrated_contract.py:104–124`, `assembly_stages()`の工程04→06→07。B nativeの対象IDは下記。 | 工程04の装着品を残し、工程07の移動品をnative基準から`[0,0,+10]mm`へ移動。期待は交差体積`<=1e-5 mm³`。実際は`H_INPUT_HUB_001`対`S_GUARD_UPPER_RIGHT_2_001`が**9.6624645869mm³**、`P_ROTOR_CAGE_FRONT_001`対`H_BOLT_M3_20_011`が**2.5404894418mm³**。両者とも最終位置0mmでは交差0。 | 現在のPASSは実工程より部品の少ない別構成の検査結果。工程在庫をorderedOperationsから導出／照合し、実在するPET・保持ボルトを固定側へ含める。可能な工程順または経路を定め、必要な取外し・同一IDでの再挿入・仮支持を明示して再検査する。表示とcontractも同じ工程へ更新する。部品を検査から隠す／閾値を上げる修正では不可。 |

### R7-I1の根拠

- `B/assembly_stages.json`では上側PETと中間軸右保持品を`04_upper_sheets`で追加する。対象3部品は工程06終了時にも装着済みで、工程07前のremove指定はない。
- しかし`B/assembly_access.json`の同経路は`fixedNames`にそれらを含まない。生成元は`"fixed": frames+drive`であり、`guards`と`bearing_caps`が落ちる。
- `H_BOLT_M3_20_012`も同じ欠落。前ケージとの交差は+5mmで**2.3327578031mm³**、+20mmで**2.1102895710mm³**。+10mmでは0であり、一点だけで全行程を判断していない。
- 対照プローブは既存の検査距離**0／5／10／20mm**を使用した。したがって「角度・距離刻みを細かくすれば解消する検査漏れ」ではなく、**検査対象の在庫不一致**である。
- 対象native: `FreeCAD/Ver.3/integrated_r7/B/Walker_B.FCStd`、SHA256 `dd6a68352a5fab903d5d9adb594b7bf1429a039a187ca375a344576e88ba9f02`。
- 実物のDハブ開放状態や微小な軸／ハブ参照交差を問題にしていない。ここで確認したのは、凍結名目形状のハブ／PETおよびケージ／装着済みボルトという別界面。
- **Bで確認した指摘**。A/Cにも同じ検査生成パターンはあるが、そのnative工程干渉までは計算しておらず、同じ数値・同じ不成立を断定しない。

### Important Issues / Suggestions

追加の高確信・判断変更級の指摘なし。未実測の摩擦、空力、工具、実スライス、公差限界を新規欠陥として数えていない。

## 実行した独立プローブ

すべて`probes/`に保存。作者の65試験・216姿勢・162支持ケースの再実行で代用していない。

1. **`p01_contact.py` — PASS**
   - 非中心荷重・異なるばね率・3接地＋3空中の解析ケース。期待反力`[1.96133, 3.4323275, 4.4129925, 0, 0, 0]N`と一致。
   - 胴体を0.1mm上げた位置エネルギー差：期待`0.02646`、観測`0.026460000000043 Nmm`。ばね沈下を含む系の仕事を確認。
   - 独自の余弦定理による12角度の円交点再構成：最大位置差`3.99e-14mm`、PC実ピッチ26.5mm。359.999→0.001°の最大移動`0.00049530mm`。
   - 六脚の0/180°と凍結CADのロッカー中心：最大差`2.01e-14mm`。Bの切替付近を含む9状態の力・モーメント残差は最大`8.81e-12`、`N cos(gamma)=k c`も一致。実COP全周期の再反復はしていない。

2. **`p02_work_air.py` — PASS**
   - 歯数・軸中心からBの`[-512,64,-8,1]`、Cの`[156,-13,1]`と歯位相を再構成。
   - 同軸合成後に途中で動力方向が逆転する解析ケース：入力要求`[0.546015625, 0.9311848958, 0.6949074074]Nmm`を再現。実高速回転28品の重力仕事を独立有限差分と比較し、最大差`5.78e-10 Nmm`。
   - 独自の光線／パネル計算で、保存最悪位相における原供給をB **1.15656705**、C **1.46293226mN·m**と再現。保存要求との差は各**+0.21195715／+0.10595992mN·m**。要求の全周期最大値そのものは新たに再探索していない。
   - 新しい72状態の粗い接地計算で、摩擦力と滑り速度の内積による散逸**50.46866Nmm**、非負Coulomb上界**50.50830Nmm**。力残差`3.72e-8N`、ヨー残差`7.26e-7Nmm`。保存720点の滑り積分50.96853、位置エネルギー周回差0、風の抵抗仕事+11.67401Nmmも別途集計。粗い値を保存値と同一精度とは扱わない。

3. **`p03_native.py` — 断面等はPASS、最後の工程検査はR7-I1でFAIL**
   - 7代表品の凍結mesh変換をnativeへ照合：包絡差最大0.0012601mm、重心差最大`3.46e-13mm`。左脚に二重の鏡映は行っていない。
   - Bの18歯／M3ナット：13mm半ピッチへ戻したコピーでは交差0.00167536mm³、凍結14mmでは交差0、径方向隙間**0.9745735195mm**。工具外幅7.6mmの円形先端包絡と全歯先円の差は0.35mmであり、実工具の柄や所有を認定するものではない。
   - 実5mm-AF軸断面**21.65063509mm²**、8mm丸ジャーナルから5.12mm-AF穴を除いた断面**27.56314611mm²**、平滑4mmスリーブ体積**175.30087007mm³**が解析値と一致。左内輪の保持隙間0.2mm、スリーブ／ABリンクの径方向隙間0.1mm。
   - 足の0/3/6mm行程で交差0。6.01mmの正の対照では実スロット付きストップに**0.0554438399mm³**交差し、解析値と一致。6mm時の案内重なり13mm、案内端の余り1mm。
   - x=28mmでガードの実nativeを6光線で照合：3透過／3遮蔽、遮蔽時の材料通過長3.5mm。B上側PETの新しい2位置は実工程在庫183品に対して交差なし。一方、風車下降の在庫補完でR7-I1を検出した。

4. **`p04_contract.py` — 在庫・identity・変換整合はPASS**
   - A/B/Cの**756／791／756＝2303インスタンス**、72／75／72品種、全36工程を独立に照合・再生。
   - 各案addは各総数、remove/reinsertは各65で数量一致。Bの工程末在庫は`83,135,205,239,277,276,292,293,317,329,329,791`。
   - BOM数量／category／SKU、mesh索引、全nativeオブジェクトのPartId・revision・質量、同一品の相対placement、全工程の工具ID・停止角0°・仮支持IDを確認。40件のsource/dependencyからSourceHashを再計算。
   - **在庫再生が正しいことと、経路検査がその在庫を使うことは別**。後者の不一致がR7-I1。

5. **`p05_budget.py` — PASS**
   - 単独初回費用を実instance数量、引用済みlot、税区分、材料から再集計：A **22,204.43円**／B **22,634.67円**／C **22,064.71円**。共同購入平均には置換していない。
   - 初回付属品は6品種7個、**118.36397g**。各単独費用に1組、歩行質量には0g。
   - BはPET装着4片／切出し3矩形／購入1シート。軸500mmから`100×3＋58×2`、負側寸法2mm・各切断2mmを控除して残り72mm。
   - 50個単位スリーブ、ばね12個、ねじ・ナット・ワッシャーの余剰を含めて照合。未確定国内税準備金178円、任意輸入税準備金568.32円を分離。Bの材料係数1.5は**23,249.04円**で、既存の超過開示と一致。工具費・実材料係数の未確認は残る。

6. **`p06_stage_collision.py` — R7-I1再現PASS**
   - 上記3部品対×既存4距離＝12組だけを再検査。最終位置0mmは全て交差0、途中5/10/20mmに交差あり。工程04追加・工程06後も在庫内・検査fixedNamesに不在であることもassert。

実行コマンド（この私有フォルダーを`R`と表記）：

```bash
R=<private-review>
PYTHONDONTWRITEBYTECODE=1 python3 "$R/probes/p01_contact.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$R/probes/p02_work_air.py"
PYTHONDONTWRITEBYTECODE=1 /Applications/FreeCAD.app/Contents/Resources/bin/python "$R/probes/p03_native.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$R/probes/p04_contract.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$R/probes/p05_budget.py"
PYTHONDONTWRITEBYTECODE=1 /Applications/FreeCAD.app/Contents/Resources/bin/python "$R/probes/p06_stage_collision.py"
```

`p03`の初期プローブ側のCompound処理／ストップ面積の期待値修正と、最終FAILは`probes/probe_notes.md`に記録した。

## What's Done Well

- 定常の入力位相、連続した脚の枝、実足中心、ばね仕事、同軸合成後の歯車損失という対応を明示し、独立計算と照合できる。
- Bのナット角修正は実断面と全歯先円で再現できた。平滑ジャーナルと正係合を分けた構成もnativeで確認できる。
- 使用数量と購入lot、単独初回と共同購入、税準備金と基準予算、原代理と不利条件・実測UNKNOWNが分離されている。

## Verification Story・未計算境界

- **Tests reviewed: yes** — 仕様を先に読み、`test_walker_math.py`の全187行を実装より先に確認。作者の全試験スイートは再実行していない。
- **Build verified: no（再生成なし）** — read-onlyのため全CADビルドは実行せず。FreeCAD 1.1.3独立CLIで既存B nativeの実solid断面・接触・代表経路を確認した。STEPはハッシュを確認したが全再読込み対応検査はしていない。
- **Security checked: 対象外** — 依頼どおり機械／モデル／データ統合レビューであり、セキュリティレビューではない。
- 全公差区間・連続全経路、A/Cの同工程native干渉、全接触点・全歯形の新しい掃引、全機solid FEM、実工具操作、スライサー・物性・実空力・実始動・実30cmは未検証。
- 6プローブでこの1回のレビューを終了する。指摘がない範囲も製造可能性や30cm成功の証明ではない。**manufacturingRelease=false／qualifiedWalkingPrototypeCount=0／physical operation UNKNOWNは維持**。是正後の限定差分が指定された場合のみ、この文脈で追跡する。
