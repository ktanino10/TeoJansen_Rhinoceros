"""Whole Ver.3.4 A and a separate development landing page."""

import gzip
import hashlib
from html import escape
import json
from pathlib import Path

from viewer_data import export_glb

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/ver3/m3_a34"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_integrated(output, ref, text, source_link):
    summary = json.loads((DOC / "summary.json").read_text())
    data = json.loads((DOC / "assembly.json").read_text())
    if summary["revisionId"] != data["revisionId"] or summary["manufacturingRelease"] is not False:
        raise ValueError("Unqualified or mismatched integrated development revision")
    for relative, expected in {**data["sourceHashes"], **summary["sourceHashes"],
                               **json.loads((DOC / "files.json").read_text())}.items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Changed 3.4 source: " + relative)
    library = json.loads(gzip.decompress((ROOT / data["cadMeshes"]).read_bytes()))
    trial = json.loads((ROOT / "docs/ver3/m3_r1/assembly.json").read_text())
    trial_mesh = json.loads(gzip.decompress((ROOT / trial["cadMeshes"]).read_bytes()))
    coupons = trial["coupons"]
    manifest = {"id": "A", "instances": data["instances"], "parts": dict(data["parts"])}
    for pid in coupons:
        library[pid] = trial_mesh[pid]
        manifest["parts"][pid] = {**trial["parts"][pid], "spec": trial["parts"][pid]["description"]}
    source = {"revisionId": data["revisionId"], "canonicalCommit": ref, "localOnly": False,
              "label": text("Ver.3.4 A・M3統合開発版・実機未検証", "Ver.3.4 A / integrated M3 development / physically unverified"),
              "manufacturingRelease": False}
    raw = output / "assets/a34-A.glb"
    model = export_glb(manifest, library, raw, source, coupon_ids=tuple(coupons), max_model_bytes=15_000_000)
    compressed = output / "assets/a34-A.glb.gz"
    compressed.write_bytes(gzip.compress(raw.read_bytes(), mtime=0))
    raw.unlink()
    model.update(compression="gzip", transportSha256=digest(compressed), transportBytes=compressed.stat().st_size)
    original_guide = json.loads((output / "assets/r7-assembly-A.json").read_text())
    names = {}
    for pid in manifest["parts"]:
        names[pid] = (original_guide["parts"][pid]["name"] if pid in original_guide["parts"]
                      else text("改訂・試験部品 " + pid, "Revised / trial part " + pid))
    all_ids = [i["name"] for i in data["instances"]]
    changed = data["m3Integration"]["changedInstances"]
    states = [
        (text("未配置表示", "Unplaced view"), [], [], []),
        (text("保存した嵌合試験片", "Retained fit coupons"), [], [], coupons),
        (text("全体構成", "Whole assembly"), all_ids, [], []),
        (text("変更部を強調", "Highlight changed parts"), [], changed, []),
        (text("全体の参照状態", "Whole reference state"), [], [], []),
    ]
    description = text("これは構成の表示切替で、組立順や挿入運動ではありません。実作業は下の番号付き計画を参照してください。",
                       "These are discovery views, not assembly order or insertion motion. See the numbered assembly plan below.")
    steps = [{"id": str(n), "title": title, "operation": description, "cautions": description,
              "tools": "", "add": members, "preview": preview, "coupons": specimen,
              "hidden": [], "view": "isometric", "arrow": None}
             for n, (title, members, preview, specimen) in enumerate(states)]
    guide = {
        "schemaVersion": 1, "design": "A", "revision": source, "model": model, "modelUrl": "assets/a34-A.glb.gz",
        "renderGroundGrid": False, "steps": steps, "completeStep": 4, "inspections": [],
        "mapping": "component-discovery-not-assembly-order",
        "parts": {pid: {"name": names[pid], "category": p["category"], "description": p["spec"], "quantity": p["quantity"],
                        "vertices": model["parts"][pid]["vertices"], "triangles": model["parts"][pid]["triangles"]}
                  for pid, p in manifest["parts"].items()},
        "instances": {i["name"]: {"partId": i["part_id"], "group": i["group"]} for i in data["instances"]},
        "focusGroups": {"modified": changed},
        "links": {"section": f"https://github.com/ktanino10/TeoJansen_Rhinoceros/blob/{ref}/docs/ver3/m3_a34/gear-section-3.4.svg"},
    }
    path = output / "assets/a34-assembly-A.json"
    path.write_text(json.dumps(guide, ensure_ascii=False, separators=(",", ":")) + "\n")
    index = {"schemaVersion": 1, "revision": source, "designs": {
        "A": {"guideUrl": "assets/a34-assembly-A.json", "guideSha256": digest(path), "modelUrl": guide["modelUrl"],
              "bytes": model["bytes"], "instances": len(all_ids), "parts": len(manifest["parts"])}}}
    (output / "assets/a34-viewer-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")
    assets = {}

    def asset(name, original, copy=False, loading="on-demand"):
        if copy:
            (output / name).write_bytes((ROOT / original).read_bytes())
        target = output / name
        assets[name] = {"source": original, "source_sha256": digest(ROOT / original), "sha256": digest(target),
                        "bytes": target.stat().st_size, "bundle_group": "ver3-development", "loading": loading}

    asset("assets/a34-A.glb.gz", data["cadMeshes"])
    asset("assets/a34-assembly-A.json", "docs/ver3/m3_a34/assembly.json")
    asset("assets/a34-viewer-index.json", "site/ver3_4_data.py")
    for name in ("gear-section-3.4.svg", "gear-end-3.4.svg", "pin-section-3.4.svg"):
        asset("assets/a34-" + name, "docs/ver3/m3_a34/" + name, True, "lazy-image")

    def link(name, ja, en, raw=False):
        return source_link("docs/ver3/m3_a34/" + name, text(ja, en), ref, raw)

    def figure(name, ja, en):
        label = escape(text(ja, en), quote=True)
        return (f'<figure class="media"><img src="assets/a34-{name}" width="960" height="600" '
                f'alt="{label}" loading="lazy" decoding="async"><figcaption>{label}</figcaption></figure>')

    def page(title, content, viewer=False):
        catalog = ' data-viewer-catalog="assets/a34-viewer-index.json"' if viewer else ""
        engine = '<link rel="stylesheet" href="viewer.css"><script src="viewer-loader.js" type="module"></script>' if viewer else ""
        return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css">
<script src="i18n.js" defer></script><script src="app.js" defer></script>{engine}</head><body{catalog}>
<a class="skip-link" href="#main">{text("本文へ移動", "Skip to content")}</a>
<header class="site-header"><div class="header-inner"><a class="brand" href="index.html">RHINOCEROS</a>
<nav aria-label="{text("開発資料の目次", "Development contents")}"><a href="production.html">{text("完成版Ver.2・制作記録", "Completed Ver.2 / build record")}</a>
<a href="development.html">{text("Ver.3開発入口", "Ver.3 development index")}</a><a href="ver3-4.html#viewer">Ver.3.4 / 360°</a></nav></div></header>
<main id="main" tabindex="-1" data-public-version="3.4" data-engineering-revision="{data["revisionId"]}">{content}</main>
<footer class="site-footer"><a href="production.html">{text("完成版Ver.2は変更していません", "The completed Ver.2 is unchanged")}</a>
<a href="development.html">{text("開発入口へ", "Development index")}</a></footer></body></html>'''

    title = text("Ver.3.4 A — M3組立優先の開発版", "Ver.3.4 A — assembly-first M3 development")
    boundary = text("完成版Ver.2とは別の作業中です。旧3.1の表示名を変えただけではなく、Aの実接合を変更しました。実印刷・実組立・実風歩行は未検証です。",
                    "This is work in progress, separate from the completed Ver.2. Actual A connections changed; this is not a relabelled 3.1 model. Physical printing, assembly and wind walking are unverified.")
    counts = text(f'全体{summary["instances"]}点。印刷{summary["printedTypes"]}種類・{summary["printedQuantity"]}点のうち、変更した印刷品は{summary["changedPrintedQuantity"]}点です。',
                  f'The assembly has {summary["instances"]} instances. Of {summary["printedTypes"]} printed types and {summary["printedQuantity"]} prints, {summary["changedPrintedQuantity"]} prints changed.')
    change_note = text("前・中央の同期歯車に捕捉ナット座、全6脚のA/DピンにM3と平滑6mmスリーブを統合。干渉を避けるためP/B/C/E、足とアイドラーのM2は残します。",
                       "Captive seats are integrated into the front/centre synchronizing gears; A/D pins on all6 legs use M3 and smooth6mm sleeves. P/B/C/E, feet and idlers retain M2 to avoid interference.")
    controls = (ROOT / "site/viewer.html").read_text().split('      <div id="viewer-workspace" hidden>', 1)[1].split('      <div class="record-scope"><h3>この3Dを、', 1)[0]
    controls = '      <div id="viewer-workspace" hidden>' + controls
    controls = controls.replace("組立を順番に見る", text("構成の表示切替（組立順ではない）", "Discovery views (not assembly order)"))
    controls = controls.replace("原典に対応する工程", text("表示する範囲", "View scope"))
    controls = controls.replace('{{tree:docs/ver3/drawings}}', guide["links"]["section"])
    controls = controls.replace('<label for="access-select">', '<label for="access-select" hidden>')
    controls = controls.replace("工具経路は原典の部分組立前提でのみCAD標本確認されています。キャリアを残した完成状態を通り抜ける証明ではありません。",
                                text("旧版の工具経路を新形状へ合格として転記していません。ねじ頭側の作業は、脚とクランクの単体組立時に行います。",
                                     "Old tool-path passes are not transferred to new geometry. Head-side fastening is performed while the leg and crank are separate subassemblies."))
    assembly_steps = [
        ("1. 版・部品を仕分ける", "1. Sort the revision and parts",
         "3.4の印刷一覧とBOMを使います。変更品と3.1から保持した品を混同せず、試験片で実スリーブ・ナット・軸を確認します。",
         "Use the3.4 print list and BOM. Separate changed and retained3.1 parts, and check real sleeves, nuts and shafts using coupons."),
        ("2. 歯車接合を単体で準備", "2. Prepare the gear connections separately",
         "側面溝へ内側座金と内ナットを入れ、M3×20・頭側座金・外ナットで割締め。既存5mm対辺軸へ合う穴の向きを維持します。",
         "Side-load the inner washer and nut; use M3x20, a head-side washer and outer nut for the split clamp. Preserve the bore clocking for the existing5mm-AF shaft."),
        ("3. 左側から軸・歯車を置く", "3. Load shafts and gears from the left",
         "固定側軸受、六角軸、減速歯車と同期歯車を準備。後ろの同期歯車と減速段の既存構成は変えません。",
         "Prepare locating bearings, hex shafts, reducer and synchronizing gears. The rear synchronizing gear and reducer arrangement remain unchanged."),
        ("4. 位置決めキーで右フレームを閉じる", "4. Close the right frame on locating keys",
         "前の六角キーと後の逃げキーを合わせ、M3継手を締結。固定側と浮動側を区別し、PET板を軸受の圧縮スペーサーにしません。",
         "Align the front hex key and relieved rear key, then fasten the M3 joints. Distinguish locating/floating supports; PET is not a bearing compression spacer."),
        ("5. PETと入力風車・ガード", "5. PET, input rotor and guards",
         "保持した3.1手順のPET退避と風車バスケット経路を参照。金属6Dハブ・入力カラー・M4締結は保持し、旧動画を新しい作業の実証としません。",
         "Refer to retained3.1 PET-offset and rotor-basket instructions. Metal6D hub, input collars and M4 fasteners remain; old videos are not proof of new assembly."),
        ("6. 脚とクランクを単体で準備", "6. Prepare leg and crank subassemblies",
         "AはM3×30と連続20mmスリーブ、DはM3×15と8mmスリーブ。8mm頭側座金を側面から置き、6.2mm通路からねじを挿入。本体の外で二重ナットを締結します。",
         "A uses M3x30 with a continuous20mm sleeve; D uses M3x15 with an8mm sleeve. Side-load the8mm head washer and insert the screw through the6.2mm passage. Fasten both nuts outside the machine."),
        ("7. 座金座と残りの脚を準備", "7. Prepare thrust seats and retained joints",
         "M6座金は0.3mm逃げへ配置し、リンクを挟みません。P/B/C/Eと足は元のM2構成を保持します。",
         "Place M6 washers in the0.3mm reliefs without clamping the links. P/B/C/E and feet retain the original M2 arrangement."),
        ("8. 本体へ取り付けて位相を合わせる", "8. Install and set phase",
         "主軸の正係合と固定Pを合わせます。左右位相は前から0/180、180/0、0/180度。単体での工具作業を先に終え、保持とガードを戻します。",
         "Align the positive main-shaft coupling and fixed P. Left/right phases from the front are0/180, 180/0, 0/180degrees. Complete subassembly tool work first, then restore retention and guards."),
        ("9. 接合ごとの確認を記録", "9. Record checks at each connection",
         "回り止め、軸方向保持、自由回転を別々に確認。実工具の到達、すきま、白化、ねじ緩み、摩耗を記録します。購入・印刷・送風運転は実施していません。",
         "Check anti-rotation, axial retention and free rotation separately. Record actual tool access, clearances, whitening, loosening and wear. No purchasing, printing or powered airflow was performed."),
    ]
    instructions = "".join(f'<article class="static-step"><h3>{text(a,b)}</h3><p>{text(c,d)}</p></article>' for a,b,c,d in assembly_steps)
    documents = (
        link("README_ja.md", "組立計画・固定・注意点", "Assembly plan, retention and cautions"),
        link("print-list.csv", "全機の印刷リスト", "Whole-machine print list", True),
        link("purchase-list.csv", "全機の購入部品リスト", "Whole-machine hardware list", True),
        link("BOM.csv", "全機BOM", "Whole-machine BOM", True),
        source_link(summary["native"], "FreeCAD", ref, True), source_link(summary["step"], "STEP", ref, True),
    )
    comparison = json.loads((DOC / "drive_comparison.json").read_text())
    rows = "".join(f'<tr><th scope="row">{row["case"]}</th><td>{row["oldRequiredNm"]*1000:.4f}</td>'
                   f'<td>{row["newRequiredNm"]*1000:.4f}</td><td>{row["rawSupplyMinimumNm"]*1000:.4f}</td>'
                   f'<td>{row["rawPhaseMarginNm"]*1000:.4f}</td><td>{row["halfSupplyPhaseMarginNm"]*1000:.4f}</td></tr>'
                   for row in comparison["caseRows"])
    body = f'''<section class="section viewer-intro" id="top"><p class="eyebrow">INTEGRATED DEVELOPMENT / NOT A PHYSICAL RELEASE</p>
<h1>{title}</h1><aside class="warning"><h2>{boundary}</h2><p><strong>manufacturingRelease=false</strong> / {data["revisionId"]}</p></aside>
<p>{counts}</p><p>{change_note}</p><div class="document-strip">{"".join(documents)}</div>
<nav class="journey-nav"><a href="#viewer">{text("全体の360度", "Whole assembly in 360 degrees")}</a><a href="#joints">{text("固定の実断面", "Actual joint sections")}</a>
<a href="#assembly">{text("組立計画", "Assembly plan")}</a><a href="#drive">{text("駆動計算", "Drive calculation")}</a><a href="#files">{text("印刷・購入ファイル", "Print and purchase files")}</a></nav></section>
<section class="section" id="joints"><h2>{text("回り止めと抜け止めは別です", "Anti-rotation and axial retention are different")}</h2>
<p>{text("歯車は六角面でトルクを伝え、割締めと二重ナットで軸方向を保持。脚は平滑スリーブの外周で回り、ねじ山を摺動面にしません。",
 "Gears transmit torque through hex flats, with split clamps and double nuts retaining axially. Links run on smooth sleeve exteriors, not screw threads.")}</p>
<div class="two-column">{figure("gear-section-3.4.svg", "3.4全体CADから切り出した歯車の締結断面", "Gear-fastening section from the3.4 whole-machine CAD")}
{figure("pin-section-3.4.svg", "3.4全体CADから切り出したAピン・座金・ナットの断面", "A-pin, washer and nut section from the3.4 whole-machine CAD")}</div></section>
<section class="section viewer-section" id="viewer"><h2>{text("Ver.3.4 Aを360度で見る", "Explore Ver.3.4 A in360 degrees")}</h2><p>{description}</p>
<p class="small-note">{text("個体IDは3.1からの追跡用IDを保持します。名称にM2が残る場合も、規格・購入は更新したPartIdと3.4のBOMを参照してください。",
 "Instance IDs retain their3.1 tracking identity. Even when a name contains M2, use the updated PartId and3.4 BOM for specifications and purchasing.")}</p>
<div class="viewer-toolbar"><label for="design-select">{text("表示対象", "Model")}<select id="design-select"><option value="A">A / {data["revisionId"]}</option></select></label>
<button type="button" class="button primary" id="load-viewer" hidden>{text("Ver.3.4全体の3Dを読み込む", "Load the complete Ver.3.4 3D model")}</button></div>
<p id="viewer-status" role="status" aria-live="polite">{text("操作時だけ、この版のCADメッシュを取得します。", "Only this revision's CAD mesh is fetched, on request.")}</p>
<p id="viewer-error" class="media-error" role="alert" hidden></p><div id="viewer-fallback">
{figure("gear-end-3.4.svg", "3.4の実歯車形状と回り止め穴", "Actual3.4 gear geometry and positive bore")}
<a href="#files">{text("CAD・静的資料へ", "CAD and static documents")}</a></div>
<noscript><p>{text("JavaScriptなしでも手順とダウンロードを利用できます。", "Instructions and downloads work without JavaScript.")}</p></noscript>
{controls}</section>
<section class="section" id="assembly"><h2>{text("番号付き組立計画", "Numbered assembly plan")}</h2>
<p>{text("実組立は未実施です。3Dの構成表示を作業順と混同せず、単体組立と全機への取付けを分けます。",
 "Physical assembly has not been performed. Do not confuse 3D discovery views with work order; keep subassembly preparation separate from installation.")}</p>{instructions}</section>
<section class="section" id="drive"><h2>{text("実CAD質量・反力から始動要求を再計算", "Startup requirements recalculated from actual CAD mass and reactions")}</h2>
<p>{text(f'名目質量は{comparison["oldMassG"]:.2f}gから{comparison["newMassG"]:.2f}g。A/Dの径4→6mmは同荷重なら摩擦トルク1.5倍ですが、新しい質量と反力で全位相を解き直しています。',
 f'Nominal mass changes from{comparison["oldMassG"]:.2f}g to{comparison["newMassG"]:.2f}g. A/D diameters change from4 to6mm: friction torque would rise1.5-fold at equal load, but all phases are re-solved with new masses and reactions.')}</p>
<div class="matrix-scroll" role="region" aria-label="{text("全位相トルク比較", "All-phase torque comparison")}" tabindex="0"><table><thead><tr>
<th>{text("抵抗ケース", "Resistance case")}</th><th>{text("旧要求 mN·m", "Old demand mN·m")}</th><th>{text("新要求 mN·m", "New demand mN·m")}</th>
<th>{text("供給代理最小 mN·m", "Minimum proxy supply mN·m")}</th><th>{text("同位相余裕 mN·m", "Same-phase margin mN·m")}</th><th>{text("供給半減時 mN·m", "Half-supply margin mN·m")}</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>{text("減速は12×12＝144:1を保持。冷風6.4m/s・広がり20mmは未校正の代理条件です。高抵抗や供給半減では不足し、負荷付き速度・自己始動・実30cm歩行はUNKNOWNです。",
 "Reduction remains12x12=144:1. Cold air at6.4m/s with20mm spread is an uncalibrated proxy. High resistance or half supply is insufficient; loaded speed, self-starting and physical30cm walking are UNKNOWN.")}</p>
<p>{link("work_budget.json", "各段・全位相の駆動計算", "Per-stage, all-phase drive calculation")} / {link("drive_comparison.json", "同条件の新旧比較", "Same-condition old/new comparison")} /
{link("motion_check.json", "可動域の有限確認", "Finite motion checks")} / {link("floor_check.json", "全物体の床確認", "All-part floor check")}</p></section>
<section class="section" id="files"><h2>{text("印刷・購入・組立ファイルを同じ版で", "One revision for printing, purchasing and assembly")}</h2>
<div class="document-strip">{"".join(documents)}</div>
<p>{text("一覧は全機の必要数で、未確認の手持ちは差し引いていません。変更STLと保持した3.1 STLを区別します。0.2mmはノズル径で、P1S/PETGは検査用仮定です。",
 "Lists show whole-machine requirements without subtracting unverified on-hand stock. Changed STLs are distinguished from retained3.1 STLs. 0.2mm is nozzle diameter; P1S/PETG are inspection assumptions.")}</p>
<p>{link("slicing.json", "新しい3.4形状の0.2mm実層", "Actual0.2mm layers of new3.4 geometry")} / {link("summary.json", "数量・工具・調達例外", "Quantities, tools and sourcing exceptions")}</p>
<p>{text("M3が最多ですが、全工具の種類は減っていません。20mm連続金属スリーブは国内メーカーの調達例外です。900円は保存した接合試験の締結4品だけで、全機価格ではありません。",
 "M3 is the most numerous screw diameter, but the whole tool set is not reduced. Continuous20mm metal sleeves are a documented domestic-maker exception. JPY900 covers only4 fastener items for the retained joint trial, not the whole machine.")}</p>
<p><a href="ver3-2.html">{text("保存した3.2接合試験へ", "Retained3.2 joint trial")}</a> / <a href="r7.html?design=A#viewer">{text("元の3.1全体参照へ", "Original3.1 whole reference")}</a></p></section>'''
    (output / "ver3-4.html").write_text(page(title, body, True))
    landing_title = text("Ver.3以降の開発入口", "Development index for Ver.3 and later")
    landing = f'''<section class="section viewer-intro"><p class="eyebrow">COMPLETED BUILD / SEPARATE DEVELOPMENT</p>
<h1>{landing_title}</h1><p>{boundary}</p><div class="two-column">
<article class="download-card"><h2>{text("完成版Ver.2", "Completed Ver.2")}</h2><p>{text("元の見た目・写真・動画・PDF・STL・既存URLを維持します。", "Original presentation, photographs, videos, PDFs, STLs and URLs remain intact.")}</p>
<a href="production.html">{text("完成版の制作記録へ", "Completed-build record")}</a></article>
<article class="download-card"><h2>Ver.3.4 A</h2><p>{change_note}</p><a class="button primary" href="ver3-4.html">{text("3.4の全体360度・組立・印刷・購入", "3.4 whole360-degree view, assembly, printing and hardware")}</a></article>
<article class="download-card"><h2>{text("Ver.3.1：全体の参照設計", "Ver.3.1: whole reference design")}</h2><a href="r7.html?design=A#viewer">{text("旧形状の360度と12工程", "Original geometry in360 degrees and12 stages")}</a></article>
<article class="download-card"><h2>{text("Ver.3.2：保存した接合試験", "Ver.3.2: retained connection trial")}</h2><a href="ver3-2.html">{text("試験体・嵌合片・限定結果", "Bench assembly, fit coupons and limited results")}</a></article></div>
<p>{text("Ver.3.3を完成したことにはしていません。大きい版番号は完成や性能保証の意味ではありません。",
 "No completed Ver.3.3 is claimed. Higher version numbers do not mean completion or guaranteed performance.")}</p></section>'''
    (output / "development.html").write_text(page(landing_title, landing))
    notice = (f'<aside class="record-scope" id="ver3-development"><strong>{boundary}</strong><p>'
              f'<a href="development.html">{text("Ver.3開発入口：組立・印刷・購入部品・新M3接合", "Ver.3 development: assembly, printing, hardware and new M3 joints")}</a></p></aside>')
    return notice, assets, source
