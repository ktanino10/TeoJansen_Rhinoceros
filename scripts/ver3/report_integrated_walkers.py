"""Japanese handoff from one matching set of saved whole-machine results."""

import csv
import hashlib
import html
import json
import math
from pathlib import Path

import numpy as np

from walker_geometry import ROOT,OUT,CAD,PRINT,body_points,rigids


def read(path):
    return json.loads(path.read_text())


def plan_svg(data,path):
    c=data["parameters"]["common"];axis=data["inputLayout"]["axisYz"]
    radius=data["candidate"]["rotorDiameterMm"]/2
    extent=max(230,axis[1]+radius+12)
    scale=520/extent
    origin=np.array([340.,650.])
    def project(point):
        return origin+np.array([point[0],-point[1]])*scale
    def line(a,b,color,width=2,dash=False):
        a,b=project(a),project(b)
        return f'<path d="M{a[0]:.2f},{a[1]:.2f}L{b[0]:.2f},{b[1]:.2f}" fill="none" stroke="{color}" stroke-width="{width}"'+(' stroke-dasharray="5 3"' if dash else '')+'/>'
    def circle(center,r,color,width=2):
        p=project(center)
        return f'<circle cx="{p[0]:.2f}" cy="{p[1]:.2f}" r="{r*scale:.2f}" fill="none" stroke="{color}" stroke-width="{width}"/>'
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="930" viewBox="0 0 960 930">',
         '<rect width="960" height="930" fill="#fff"/>',
         f'<text x="30" y="32" font-size="21">Ver.3 {data["designId"]} / {html.escape(data["revisionId"])}</text>',
         '<text x="30" y="55" font-size="13">CAD寸法からの側面組立模式図。実形状・穴・工具経路はnative/STEPと検査JSONを参照。</text>']
    for m in data["frameMembersBeforeUnion"]:
        svg.append(line(np.array(m["aMm"])[1:],np.array(m["bMm"])[1:],"#a8b5c7",3))
    train=data["reduction"]
    for stage in train["stages"]:
        for index,teeth,tip in ((stage["pinionAxis"],stage["pinion"],stage["pinionAddendumCoefficient"]),
                                (stage["wheelAxis"],stage["wheel"],stage["wheelAddendumCoefficient"])):
            svg.append(circle(train["axesYzMm"][index],teeth/2+tip,"#a97521",1.2))
    for y in c["synchronization"]["gearCentersYmm"]:
        svg.append(circle([y,0],c["synchronization"]["teeth"]/2+1,"#926b27",1))
    stations=(-c["stationPitchMm"],0,c["stationPitchMm"])
    for station,phases in zip(stations,c["legPhasesDeg"]):
        for side,phase,color in ((-1,phases[0],"#2563a5"),(1,phases[1],"#d25732")):
            points=body_points(math.radians(phase),common=c)
            for name,nodes in rigids().items():
                pairs=list(zip(nodes,nodes[1:]))+([(nodes[-1],nodes[0])] if len(nodes)==3 else [])
                for a,b in pairs:svg.append(line(points[a]+[station,0],points[b]+[station,0],color,1.5,side<0))
    svg += [circle(axis,radius,"#bb4c25",2.5),
            circle(axis,radius+c["guards"]["radialClearanceMm"]+c["guards"]["radialWallMm"],"#2d8f8e",1.5)]
    for index,yz in enumerate(train["axesYzMm"]):
        p=project(yz)
        svg.append(f'<text x="{p[0]+5:.1f}" y="{p[1]-5:.1f}" font-size="12">軸{index}</text>')
    texts=[
        f'風車径 {2*radius:g} mm / 受風幅32 mm / 外形38 mm',
        f'減速 {math.prod(data["candidate"]["stageRatios"]):g}:1 / 主軸ピッチ {c["stationPitchMm"]:g} mm',
        f'PC実ピッチ {c.get("linkDimensionOverridesMm",{}).get("PC",39.3*c["linkScale"]):g} mm',
        '左脚:青破線 / 右脚:橙 / 歯車:黄 / 非回転ガード:緑',
        'この図の輪郭円は外径の模式表示。干渉判定に置換していません。',
        '異なるX面の投影は重なります。無圧縮姿勢で、床接触・前進量は別計算です。']
    for i,text in enumerate(texts):
        svg.append(f'<text x="30" y="{810+19*i}" font-size="13">{html.escape(text)}</text>')
    svg.append("</svg>")
    path.write_text("\n".join(svg)+"\n")


def report():
    packages={}
    for design in "ABC":
        folder=OUT/design
        data={key:read(folder/name) for key,name in (
            ("assembly","assembly.json"),("work","work_budget.json"),("price","purchase_lots.json"),
            ("static","static_collisions.json"),("motion","gait_motion.json"),
            ("access","assembly_access.json"),("contact","contact_sensitivity.json"),
            ("structure","structure.json"),("exports","step_correspondence.json"),
            ("environment","environment_sensitivity.json"),("rotations","rotating_clearance.json"))}
        revision=data["assembly"]["revisionId"]
        for key in ("work","static","motion","access","contact","structure","environment","rotations"):
            if data[key]["revisionId"]!=revision:
                raise ValueError(f"{design} contains a stale {key} result")
        packages[design]=data
    revisions={p["assembly"]["revisionId"] for p in packages.values()}
    if len(revisions)!=1:raise ValueError("Do not report mixed revisions of A/B/C")
    revision=revisions.pop()
    common=packages["A"]["assembly"]["parameters"]["common"]
    approval=read(OUT/"requirements_approval.json")
    baseline=read(OUT/"baseline_A_same_model.json")
    directions={"A":"大風車・少段","B":"小風車・高減速/低速","C":"中間径・軽量フレーム"}
    rows=[]
    for name,p in packages.items():
        a,w,cost=p["assembly"],p["work"],p["price"]
        nominal=w["cases"][1]
        rows.append({"design":name,"rotorDiameterMm":a["candidate"]["rotorDiameterMm"],
                     "reduction":abs(a["reduction"]["speedRatios"][0]),"instanceCount":len(a["instances"]),
                     "cadMassG":a["nominalTotalMassG"],"cadCogMm":a["nominalCenterOfMassMm"],
                     "firstBuildCostJpy":cost["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"],
                     "domesticTaxReserveJpy":cost["includedUnclearDomesticTaxReserveJpy"],
                     "optionalImportReserveJpy":cost["optionalImportTaxReserve10PercentJpy"],
                     "nominalRequiredMilliNm":nominal["requiredInputMaximumNm"]*1000,
                     "rawGuardedSupplyMilliNm":nominal["rawSupplyMinimumNm"]*1000,
                     "nominalReachableMarginMilliNm":nominal["rawPhaseMinimumMarginNm"]*1000,
                     "halfProxyMarginMilliNm":nominal["halfProxyPhaseMinimumMarginNm"]*1000,
                     "inputPairDragNecessaryMaximumMilliNm":nominal["maximumInputBearingPairForRawBalanceNm"]*1000,
                     "groundSlipWorkNmm":nominal["workPerCycleNmm"]["groundSlip"],
                     "guideWorkNmm":nominal["workPerCycleNmm"]["guide"],
                     "journalWorkNmm":nominal["workPerCycleNmm"]["legJournals"],
                     "predictedSlideMm":w["contact"]["maximum_predicted_loaded_episode_slip_mm"],
                     "nominalAdvanceMm":abs(w["contact"]["advance_per_cycle_mm"]),
                     "contactPassed":p["contact"]["passed"],"contactTotal":p["contact"]["total"],
                     "minutesFor300mmAtAssumed120InputRpm":w["kinematicTravel"]["minutesAt120InputRpmNotPredicted"],
                     "approvedApproximateBudgetJpy":approval["approvedApproximateBudgetJpyPerMachine"],
                     "budgetStatus":cost["completeMachineBudgetStatus"],
                     "staticStatus":p["static"]["status"],"motionStatus":p["motion"]["status"],
                     "accessStatus":p["access"]["status"],"sectionScreenStatus":p["rotations"]["status"],
                     "physicalSelfStart":"UNKNOWN"})
        plan_svg(a,OUT/name/"assembly_layout.svg")
        table=["|抵抗感度|入力要求 mN·m|独立min/max包絡差 mN·m|到達位相の最小差 mN·m|原供給×0.5との差 mN·m|",
               "|---|---:|---:|---:|---:|"]
        for case in w["cases"]:
            table.append(f'|{case["case"]}|{case["requiredInputMaximumNm"]*1000:.4f}|{case["rawEnvelopeMarginNm"]*1000:+.4f}|{case["rawPhaseMinimumMarginNm"]*1000:+.4f}|{case["halfProxyPhaseMinimumMarginNm"]*1000:+.4f}|')
        wind_table=["|共通送風感度（仮定）|名目抵抗での最小差 mN·m|","|---|---:|"]
        wind_labels={"speed80percent":"風速5.12m/s（基準の80%）","speed120percent":"風速7.68m/s（基準の120%）",
                     "narrowJet":"噴流σ15mm","wideJet":"噴流σ25mm","aim10mmInward":"照準10mm内側","aim10mmOutward":"照準10mm外側"}
        for row in p["environment"]["windCases"]:
            wind_table.append(f'|{wind_labels[row["airCase"]["id"]]}|{row["cases"][1]["rawPhaseMinimumMarginNm"]*1000:+.4f}|')
        imbalance_table=["|風車の静的偏心仮定 mm|不利な偏心向きでの最小差 mN·m|","|---:|---:|"]
        for row in p["environment"]["staticRotorImbalance"]:
            imbalance_table.append(f'|{row["rotorComOffsetMm"]:.2f}|{row["cases"][1]["minimumMarginWithAdverseOrientationNm"]*1000:+.4f}|')
        angles=a.get("inputCollarClocking") or {}
        angle_text="、".join(f'{v["name"]}: {v["additionalClockingDeg"]:+.2f}°' for v in angles.get("collars",[]))
        body=f"""# {name}：全体モデルの判断資料

版：`{revision}`。**実測始動・30cm歩行は未確認、製作リリースではありません。**

![組立基準図](assembly_layout.svg)

|項目|保存データ|
|---|---|
|方向|{directions[name]}|
|風車／減速|径{a["candidate"]["rotorDiameterMm"]}mm、受風幅32mm、外形38mm／{abs(a["reduction"]["speedRatios"][0]):g}:1|
|名目質量|{a["nominalTotalMassG"]:.3f}g。実CADソリッド体積・仮密度・購入品の表示値/明示推定の合計|
|基準姿勢の重心 X,Y,Z|{", ".join(f"{x:.3f}" for x in a["nominalCenterOfMassMm"])}mm|
|購入・初回材料|{cost["sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy"]:,.0f}円。送料別|
|国内税の未確定分／任意輸入税準備金|{cost["includedUnclearDomesticTaxReserveJpy"]:,.0f}円／{cost["optionalImportTaxReserve10PercentJpy"]:,.0f}円。確定税額ではない|
|初回試験片・組立台|{cost["firstBuildAccessoryMassG"]:.2f}g分を費用に含む。歩行質量には含まない|
|承認予算|1台約{approval["approvedApproximateBudgetJpyPerMachine"]:,.0f}円、{approval["recordedDateJst"]} JSTにユーザー承認（親調整担当から伝達）。送料・未確定税等別|
|native/STEP／静止／有限作動域／段階挿入|{a.get("nativeStepStatus","UNKNOWN")}／{p["static"]["status"]}／{p["motion"]["status"]}／{p["access"]["status"]}|
|実歯形断面／回転包絡スクリーニング|{p["rotations"]["status"]}。指定断面のチェックで、連続全角度や製作公差を保証するものではない|
|公差・支持の有限ケース|{p["contact"]["passed"]}/{p["contact"]["total"]}。入力トルク偶力の両符号とガイド摩擦感度を含む|

## 同じ冷風基準での条件

6.4m/sをGaussianピーク、σ20mmに置く従来の仮定です。特定のPanasonic/ReFaの保証値ではありません。
ガードの実配置で遮られる光線を除外し、圧力回復・ガード後流・回転時の空力は補っていません。
原供給の静止代理・角度サンプル最小は **{nominal["rawSupplyMinimumNm"]*1000:.4f}mN·m**。
Bの時計回り入力は、鏡映した羽根と軸の上側への同量オフセット照準で符号を合わせています。

冷風速度の参考値は[Scott/Curran, ASEE2025 paper46692, §2.2/Fig.8](https://peer.asee.org/laboratory-fixture-for-heat-transfer-using-a-hair-drier.pdf)の別機種実験です。
[Panasonic EH-NE5L](https://panasonic.jp/hair/products/EH-NE5L.html)はCOLD動作仕様の参考であり、この実測流速を保証していません。
メーカー指定用途外の機器操作を勧めたり、許可したものではありません。

{chr(10).join(table)}

独立包絡は供給の全角最小と要求の全角最大、到達位相差は実減速比・組付け位相を保った対応角での差です。
両者は同じ意味ではなく、包絡を緩めて物理合格にしたものではありません。
low/nominal/highは、軸受1個あたり0.1/0.3/1.0mN·m、摺動摩擦係数0.05/0.10/0.18、
1噛合い効率0.95/0.90/0.80の未測定感度です。実部品の低抵抗が証明された値ではありません。

名目条件の床滑り仕事 {nominal["workPerCycleNmm"]["groundSlip"]:.3f}、案内摩擦 {nominal["workPerCycleNmm"]["guide"]:.3f}、
脚ジャーナル {nominal["workPerCycleNmm"]["legJournals"]:.3f}Nmm/クランク1回転。
往復移動を相殺していません。ばねの蓄積・回収は位置エネルギーに一度だけ含みます。
負荷中の最大滑り推定 {w["contact"]["maximum_predicted_loaded_episode_slip_mm"]:.2f}mmで、旧3mm目標は別判定のままです。

下流条件を名目のまま固定した場合、入力軸受2個の合計抵抗が満たすべき上限は
**{nominal["maximumInputBearingPairForRawBalanceNm"]*1000:.4f}mN·m**。実部品がこの値以下とは未確認です。
規定RPMは達成値ではありません。速度の対応・慣性・仕事残差は[work_budget.json](work_budget.json)に保存しています。
仮に入力120RPMを維持できれば、30cmに{w["kinematicTravel"]["minutesAt120InputRpmNotPredicted"]:.2f}分相当です。

### 不利条件を原代理の合格と混ぜない

{chr(10).join(wind_table)}

{chr(10).join(imbalance_table)}

送風速度±20%、噴流σ15/25mm、照準の内外10mmは感度入力で、機器の保証範囲や信頼区間ではありません。
各送風条件では支持力・重心/接触・負荷も再計算しています。偏心は静止重力トルクの不利方向包絡であり、遠心力や運転中のバランス検証ではありません。
原供給×0.5、下流要求×2、実測下限UNKNOWNは別判定です。[全感度データ](environment_sensitivity.json)

## 組付け固有値

主軸は5mm-AF、ピッチ{common["stationPitchMm"]}mm、同期歯車{common["synchronization"]["teeth"]}歯。
入力6D軸140mmは切断・端面タップ不要。下流の国内六角材は100mmと58mmへ切断・端面処理します。
カラーの追加クロック角は {angle_text}。
これは名目形状の静的1面バランスであり、購入品の実重心・印刷偏心・動釣合いの認定ではありません。
左右/前後の当たり面と組立順は[共通組立手順](../ASSEMBLY_ja.md)を参照してください。

## 一式

- [native](../../../../FreeCAD/Ver.3/integrated_r7/{name}/Walker_{name}.FCStd)／[STEP](../../../../FreeCAD/Ver.3/integrated_r7/{name}/Walker_{name}.step)
- [印刷STL](../../../../STL/Ver.3/integrated_r7/{name}/)／[部品表](BOM.csv)／[最低購入lot](purchase_lots.json)
- [全インスタンス・正規パラメータ](assembly.json)／[静止交差](static_collisions.json)／[作動域](gait_motion.json)／[挿入経路](assembly_access.json)
- [接地・公差](contact_sensitivity.json)／[局部構造・軸梁](structure.json)／[供給・要求](work_budget.json)／[回転断面](rotating_clearance.json)
- [STL姿勢・実寸PET型紙](print_geometry.json)／[機械可読の組立工程](assembly_stages.json)

材料の異方性、固定部とフレーム接合の変形、実際の工具寸法・印刷はめあい、実風・実抵抗は別の確認が必要です。
部品が存在し、有限CAD検査を通ることと、実機運転の合格は分けて扱います。
"""
        if name=="B":
            body+="""

### 最後の回転確認による限定是正

18歯ピニオンとM3ナットの「角」に、静止姿勢では出ない名目接触が見つかりました。
保持ねじの半ピッチ13→14mmを、キャップ・フレーム・穴・締結品・PET型紙へ共通値から反映しました。
歯形や判定閾値は変更していません。名目の最小径方向隙間は0.9746mm、キャップの穴縁肉厚2.75mm、支持ボス3.25mmです。
要求工具の先端外幅7.6mm・厚さ1.8mmの空間を確認しましたが、市販工具の型番・実外形・手元への適合は未確認です。
これを実公差込みの保証にはしていません。[是正根拠](retainer_corner_correction.json)／[要求工具の確認](retainer_tool_access.json)
"""
        (OUT/name/"README_ja.md").write_text(body)
    result={"revisionId":revision,"manufacturingRelease":False,"qualifiedWalkingPrototypeCount":0,
            "rows":rows,"published":False,"physicalTestsPerformed":False}
    (OUT/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    with (OUT/"comparison.csv").open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys(),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)
    summary=["# Ver.3 統合3案：全体実体と条件付き判断","","**主要求の「実証済みで成立する3台」は未完です。**",
             "旧r3/r4/r6と公開first-cutは不変。このフォルダーは新しい全機CAD、全BOM、接地・駆動計算、組立経路を同版でまとめたローカル成果です。",
             "製作リリース=false、合格歩行機数=0。購入・印刷・ドライヤー操作・公開は実施していません。","",
             f'現在の設計予算は**1台約{approval["approvedApproximateBudgetJpyPerMachine"]:,.0f}円**（{approval["recordedDateJst"]} JSTユーザー承認）。送料・未確定税等別。購入はしていません。',
             "",
             "|案|径／減速比|名目g|個別初回 円|原代理／名目要求 mN·m|滑り仕事 Nmm/cycle|仮120RPMの30cm 分|",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        summary.append(f'|[{r["design"]}]({r["design"]}/README_ja.md)|{r["rotorDiameterMm"]}/{r["reduction"]:g}|{r["cadMassG"]:.2f}|{r["firstBuildCostJpy"]:,.0f}|{r["rawGuardedSupplyMilliNm"]:.4f}/{r["nominalRequiredMilliNm"]:.4f}|{r["groundSlipWorkNmm"]:.2f}|{r["minutesFor300mmAtAssumed120InputRpm"]:.2f}|')
    base=baseline["cases"][1];new=rows[0]
    summary+=["","## 旧Aとの同一定義比較","",
              "|項目|保存した旧A|最終A|変化|","|---|---:|---:|---:|",
              f'|名目質量 g|{baseline["cadMassKg"]*1000:.3f}|{new["cadMassG"]:.3f}|{100*(new["cadMassG"]/(baseline["cadMassKg"]*1000)-1):+.2f}%|',
              f'|同じ最終式・0.5度刻みの入力要求 mN·m|{base["requiredInputMaximumNm"]*1000:.4f}|{new["nominalRequiredMilliNm"]:.4f}|{100*(new["nominalRequiredMilliNm"]/(base["requiredInputMaximumNm"]*1000)-1):+.2f}%|',
              f'|非負の床滑り仕事 Nmm/cycle|{base["workPerCycleNmm"]["groundSlip"]:.4f}|{new["groundSlipWorkNmm"]:.4f}|{100*(new["groundSlipWorkNmm"]/base["workPerCycleNmm"]["groundSlip"]-1):+.2f}%|',
              "",
              "旧2.84621mN·mは旧モデルの履歴値です。同じ式で再計算した基準と区別し、数式修正を機械改良の効果へ混ぜていません。旧Aには今回の全ガード・初回付属品が揃っていなかったため、価格や完成度を同等扱いしません。",
              "全案の有限静止・216姿勢・162支持ケースは、その対象と仮定の確認です。入力120RPMは到達予測ではありません。"]
    summary+=["","## 今回の実変更",
              "4mmの平滑な市販金属スリーブとM2の軸方向締結へ整理し、ねじ山を摺動面にしていません。",
              "PCピッチを25.545→26.5mmへ変更し、ピッチ誤差＋両端ピンすきまでも円交点が閉じる余裕を確保。座標大小で組立枝を飛び移る実装を、同じ組立枝を保つ式へ修正しました。",
              f'{common["synchronization"]["teeth"]}歯の同期歯車と{common["stationPitchMm"]}mm軸ピッチは、下流大歯車・ガードとの実逃げを確保する変更です。足を広げたり重りを追加した対処ではありません。',
              "16角柱の実断面、キー付き左右フレーム、前バスケットと後部キャップに分かれる風車ガード、鋼ワッシャーで締結荷重を逃がすPET側面ガードを含みます。",
              "2つの既製カラーは位置を変えずにクロックし、名目の重力不釣合いを減らしました。現物バランスは未測定です。","",
              "## V2からの改善対応","",
              "|確認された課題|r7の具体対応|まだ認定していないこと|",
              "|---|---|---|",
              "|風車/歯車が軸に対して滑り、トルクを伝えなかった|入力は市販金属6Dハブ、下流は5mm-AF正係合と平滑金属ジャーナル|実締付け・はめあい・耐久トルク。軸受焼付きがV2の原因だったとはしていない|",
              "|自己始動が弱かった|実質量と滑り仕事を反映した144/512/156:1、4mmジャーナル、名目不釣合いを減らすカラー向き|未校正空力と未測定摩擦、負荷付きの回転速度|",
              "|歯車の軸方向逃げ|固定/浮動側を分けたキャップ、肩・カラー・スリーブ、キー付きフレーム|現物公差、接合たわみ、締め過ぎによる予圧|",
              "|接地切替と製作誤差|PC26.5mm、連続した組立枝、84mm同期軸、実ばね/案内/ロッカー、公差162ケース|衝撃・摩耗と実30cm歩行。滑りがゼロになったわけではない|",
              "|調達と組立を伴う一体設計が不足|国内下流部品、全締結/ガード/台/試験片、分割フレームと機械可読工程|V2のnative CADは無いため、そのまま差し替え可能とは認定しない|","",
              "## 計算の修正と機械改良を混ぜない",
              "同軸上の対向脚・回転締結品は先に仕事を合成してから、実在する各歯車対の損失を一回ずつ計上します。釣合った4本のボルトへ架空の歯車損失を課す旧実装は使いません。",
              "送風の水平力とヨー偶力を床のCoulomb反力へ含め、全位相の実CAD重心と接触姿勢を反復して整合させています。",
              "これらの数式・実装修正による数値差は、部品軽量化や性能向上の成果とは区別します。保存した旧977.709g基準は、同じ式で再計算して比較します。",
              "滑り仕事は非負で残り、8mm足上げ・3mm滑りは設計者の旧目標です。ユーザー条件に言い換えたり、未達を消していません。","",
              "## 残る本質条件",
              "1. 実空力と実抵抗：各案の入力軸受抵抗上限、印刷偏心、負荷付き回転速度を満たすか。静止代理の原値、設計減率0.5、実測下限UNKNOWNは別欄です。",
              "2. 製作・接合：実スライスと試験片によるはめあい・薄い歯先・積層強度、フレーム接合/保持/工具の現物確認。梁の局部固定境界を全機剛性の証明にしません。",
              "3. 床上の成立：有限公差ケースの支持と、滑り・衝突・始動を含む実30cm歩行。未実施なので3台合格には数えません。","",
              "[共通組立](ASSEMBLY_ja.md)／[初回試験片・組立台](common/accessories.json)／[3台共同購入lot](purchase_lots.json)／[統合契約](integration_contract.json)／[スライス未実施の範囲](slicing_status.json)"]
    summary+=["","## 再現環境",
              "既存FreeCAD1.1.3の独立Python、numpy/scipy/Shapely/trimesh/Pillow/PyMuPDFを使用しました。新しい大型ソフトは導入していません。",
              "Python依存関係は`scripts/ver3/requirements_integrated_r7.txt`、正規入力は`scripts/ver3/walker_r7.json`です。FreeCADの実行ファイル/ライブラリ位置はCLI引数で明示します。",
              "最終ソース・ファイルハッシュは`integration_contract.json`と`manifest.json`に保存します。公開や旧ページの置換はこの成果物とは別の承認事項です。"]
    (OUT/"README_ja.md").write_text("\n".join(summary)+"\n")
    files=[]
    for base in (OUT,CAD,PRINT):
        files.extend(p for p in base.rglob("*") if p.is_file() and p.name!="manifest.json")
    contract=read(OUT/"integration_contract.json")
    files.extend(ROOT/item["path"] for item in contract["sourceFiles"])
    files.extend(ROOT/item["path"] for item in contract["readOnlyExistingDependencies"])
    files=sorted(set(files))
    manifest={"revisionId":revision,"manufacturingRelease":False,"qualifiedWalkingPrototypeCount":0,
              "sourceCommit":contract["sourceCommit"],"sourceHash":contract["sourceHash"],
              "files":[{"path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in files]}
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")


if __name__=="__main__":report()
