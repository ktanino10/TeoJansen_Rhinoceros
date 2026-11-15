"""Small development entry reusing the existing exact-mesh 360-degree viewer."""

from collections import Counter
import csv
import gzip
import hashlib
from html import escape
import json
from pathlib import Path
import re

from viewer_data import export_glb

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/ver3/m3_r1"
REVISION = "v3.2-m3-r1-bench"
MESSAGES = {}


def text(ja, en):
    en = re.sub(r"\b([A-Za-z][a-z]{1,})(?=\d)", r"\1 ", en)
    en = re.sub(r"(\d)x(?=\d)", r"\1×", en)
    MESSAGES[ja] = en
    return ja


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_link(path, label, ref, raw=False):
    if not (ROOT / path).exists() or not (ROOT / path).resolve().is_relative_to(ROOT):
        raise ValueError("Missing development source: " + path)
    kind = "raw" if raw else "tree" if (ROOT / path).is_dir() else "blob"
    return f'<a href="https://github.com/ktanino10/TeoJansen_Rhinoceros/{kind}/{ref}/{path}">{escape(label)}</a>'


def steps(assembly):
    tools = text("2.5mm六角キー・5.5mmスパナ・ノギス", "2.5mm hex key, 5.5mm spanner, caliper")
    definitions = [
        ("未配置", "Unplaced", "まだ組み立てていない状態です。", "No parts have been assembled.", []),
        ("はめあい試験片", "Fit coupons", "実ナット・平滑スリーブ・六角軸を試験片で確認。無理な押込みはしません。",
         "Check the real nuts, smooth sleeve and hex shaft in the coupons. Do not force them.", []),
        ("歯車の捕捉座", "Gear captive seats", "新しい歯車の側面から内側座金、内ナットの順に挿入します。",
         "Insert the inner washer, then inner nut through each new gear's side opening.",
         ["P_M3_GEAR42_001", "P_M3_GEAR42_002", "H_M3_WASHER_002", "H_M3_WASHER_004", "H_M3_NUT_001", "H_M3_NUT_003"]),
        ("六角軸と割締め", "Hex shafts and clamps", "六角面で回り止め。ねじ、外側座金、外ナットを加え、内ナットに当てます。",
         "The hex flats transmit torque. Add screws, head-side washers and outer nuts; jam against the inner nuts.",
         ["H_HEX5_30_001", "H_HEX5_30_002", "H_M3_20_001", "H_M3_20_002",
          "H_M3_WASHER_001", "H_M3_WASHER_003", "H_M3_NUT_002", "H_M3_NUT_004"]),
        ("歯車対の参照配置", "Gear-pair reference position", "42mm軸間の1:1試験対。支持治具や動力源は含まず、動力運転しません。",
         "Trial pair 1:1 on 42mm centres. No support jig or powered drive is included; do not power it.", []),
        ("脚ピンの準備", "Prepare the pivot", "ブラケット側面から上座金と内ナットを入れ、リンクを耳の間に置きます。",
         "Side-load the upper washer and inner nut into the bracket, then place the link between the lugs.",
         ["P_M3_PIVOT_001", "P_M3_LINK_001", "H_M3_WASHER_006", "H_M3_NUT_005"]),
        ("金属スリーブを通す", "Insert the metal sleeve", "平滑な12mm金属スリーブへリンクを通す。ねじ山は回転面にしません。",
         "The link runs on a smooth 12mm metal sleeve. Screw threads are not a bearing surface.",
         ["H_M3_SLEEVE12_001"]),
        ("抜け止め", "Axial retention", "下からM3ねじと座金、上に外ナット。締結力は金属端面へ逃がし、リンクを挟みません。",
         "Add the M3 screw and lower washer from below, then the outer nut above. Clamp the metal sleeve ends, not the link.",
         ["H_M3_20_003", "H_M3_WASHER_005", "H_M3_NUT_006"]),
        ("試験体の全点", "All bench instances", "自由回転、相対滑り、軸方向保持を別々に確認。全機キットへの統合は設計待ちです。",
         "Check free rotation, relative slip and axial retention separately. Whole-machine integration is still pending.", []),
    ]
    rows, assigned = [], []
    for number, (ja, en, body_ja, body_en, members) in enumerate(definitions):
        assigned.extend(members)
        rows.append({"id": str(number), "referenceStep": number, "title": text(ja, en),
                     "operation": text(body_ja, body_en),
                     "cautions": text("完成位置での工程表示です。挿入運動や実物の組立成功を表しません。",
                                      "Stages use final reference positions, not insertion motion or proof of physical assembly."),
                     "tools": tools, "add": members, "hidden": [], "preview": [],
                     "coupons": assembly["coupons"] if number == 1 else [], "view": "isometric", "arrow": None})
    if len(assigned) != len(set(assigned)) or set(assigned) != {i["name"] for i in assembly["instances"]}:
        raise ValueError("Development stages must introduce every bench instance exactly once")
    return rows


def register_translations():
    from localization import JAPANESE, message_id, shape
    folder = ROOT / "site/locales"
    sources = json.loads((folder / "sources.json").read_text())
    english = json.loads((folder / "en.json").read_text())
    existing_documents = json.loads((folder / "documents.en.json").read_text())
    for ja, en in MESSAGES.items():
        if not JAPANESE.search(ja):
            continue
        key, values = shape(ja)
        english_key, english_values = shape(en)
        if values != english_values:
            # Identical numeric values may appear in a different grammatical order.
            if Counter(values) != Counter(english_values):
                raise ValueError(f"Translation changes numeric parameters: {ja!r} -> {en!r}")
            from collections import defaultdict, deque
            positions = defaultdict(deque)
            for index, value in enumerate(values):
                positions[value].append(index)
            slots = {str(i): str(positions[v].popleft()) for i, v in enumerate(english_values)}
            import re
            english_key = re.sub(r"\{(\d+)\}", lambda m: "{" + slots[m[1]] + "}", english_key)
        ident = message_id(key)
        if ident in sources:
            continue
        if ident in existing_documents:
            raise ValueError("Development message collides with a document translation")
        sources[ident] = {"source": key, "example": ja, "origins": ["site/ver3_data.py"]}
        english[ident] = english_key
    for name, data in (("sources.json", sources), ("en.json", english)):
        (folder / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def build_development(output, ref):
    assembly = json.loads((DOC / "assembly.json").read_text())
    checks = json.loads((DOC / "checks.json").read_text())
    if assembly["revisionId"] != REVISION or checks["revisionId"] != REVISION or checks["status"] != "PASS_WITH_SCOPE":
        raise ValueError("Development CAD/check revision mismatch")
    for relative, expected in {**assembly["sourceHashes"], **json.loads((DOC / "files.json").read_text())}.items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Changed development source: " + relative)
    source = {"revisionId": REVISION, "canonicalCommit": ref, "localOnly": False,
              "label": text("Ver.3.2 M3接合試験・全機未統合", "Ver.3.2 M3 joint trial; not integrated into a whole machine"),
              "manufacturingRelease": False}
    library = json.loads(gzip.decompress((ROOT / assembly["cadMeshes"]).read_bytes()))
    model = export_glb(assembly, library, output / "assets/m3-A.glb", source,
                       coupon_ids=tuple(assembly["coupons"]), max_model_bytes=1_000_000)
    names = {
        "P_M3_GEAR42": text("捕捉座付き42歯", "42-tooth gear with captive seat"),
        "P_M3_PIVOT": text("M3固定ブラケット", "M3 fixed bracket"),
        "P_M3_LINK": text("自由回転リンク", "Free-running link"),
        "Q_SLEEVE_FIT": text("平滑スリーブ試験片", "Smooth-sleeve coupon"),
        "Q_NUT_HEX_FIT": text("ナット・六角軸試験片", "Nut and hex-shaft coupon"),
    }
    guide = {
        "schemaVersion": 1, "design": "A", "revision": source, "model": model,
        "modelUrl": "assets/m3-A.glb", "steps": steps(assembly), "completeStep": 8, "inspections": [],
        "parts": {pid: {"name": names.get(pid, pid), "category": p["category"], "description": p["description"],
                        "quantity": p["quantity"], "vertices": model["parts"][pid]["vertices"],
                        "triangles": model["parts"][pid]["triangles"]} for pid, p in assembly["parts"].items()},
        "instances": {i["name"]: {"partId": i["part_id"], "group": i["group"]} for i in assembly["instances"]},
        "links": {"section": f"https://github.com/ktanino10/TeoJansen_Rhinoceros/blob/{ref}/docs/ver3/m3_r1/gear-3.2.svg"},
    }
    guide_path = output / "assets/m3-assembly-A.json"
    guide_path.write_text(json.dumps(guide, ensure_ascii=False, separators=(",", ":")) + "\n")
    index = {"schemaVersion": 1, "revision": source, "designs": {
        "A": {"guideUrl": "assets/m3-assembly-A.json", "guideSha256": digest(guide_path),
              "modelUrl": "assets/m3-A.glb", "bytes": model["bytes"], "instances": 22, "parts": len(assembly["parts"])}}}
    (output / "assets/m3-viewer-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")
    assets = {}

    def asset(name, original, copy=False, lazy=True):
        if copy:
            (output / name).write_bytes((ROOT / original).read_bytes())
        path = output / name
        assets[name] = {"source": original, "source_sha256": digest(ROOT / original), "sha256": digest(path),
                        "bytes": path.stat().st_size, "bundle_group": "ver3-development",
                        "loading": "on-demand" if lazy else "static"}

    asset("assets/m3-A.glb", assembly["cadMeshes"])
    asset("assets/m3-assembly-A.json", "docs/ver3/m3_r1/assembly.json")
    asset("assets/m3-viewer-index.json", "site/ver3_data.py")
    for name in ("gear-3.2.svg", "gear-top-3.2.svg", "pivot-3.2.svg", "fit-3.2.svg", "input-3.1.svg", "supports-3.1.svg"):
        asset("assets/m3-" + name, "docs/ver3/m3_r1/" + name, True)

    def link(name, ja, en, raw=False):
        return source_link("docs/ver3/m3_r1/" + name, text(ja, en), ref, raw)

    def figure(name, ja, en):
        return (f'<figure class="media"><img src="assets/m3-{name}" width="960" height="600" '
                f'alt="{escape(text(ja, en), quote=True)}" loading="lazy" decoding="async">'
                f'<figcaption>{escape(text(ja, en))}</figcaption></figure>')

    title = text("Ver.3.2 M3接合試験・保存版", "Ver.3.2 M3 joint trial / retained revision")
    lead = text("完成版Ver.2はそのまま。仕組みを理解してから、少量で試す。",
                "The completed Ver.2 stays intact. Understand the mechanism, then try a small batch.")
    notice = text("Ver.3以降は作業中です。3.1は全体の参照設計、3.2はM3接合試験で、完成版の置換ではありません。",
                  "Ver.3 and later are work in progress. 3.1 is a full reference design; 3.2 is an M3 joint trial, not a replacement completed build.")
    full = text("全体の仕組み：Ver.3.1 A", "Full mechanism: Ver.3.1 A")
    trial = text("新しい接合：Ver.3.2 M3試験", "New connections: Ver.3.2 M3 trial")
    parts_note = text("全体750点の旧形状と、試験体22点の新形状は別です。旧動画を新しい形状の証明に使いません。",
                      "The old 750-instance machine and new 22-instance trial are different geometry. Old videos do not prove the new design.")
    controls = (ROOT / "site/viewer.html").read_text()
    controls = controls.split('      <div id="viewer-workspace" hidden>', 1)[1].split('      <div class="record-scope"><h3>この3Dを、', 1)[0]
    controls = '      <div id="viewer-workspace" hidden>' + controls
    controls = controls.replace("正規座標：X＝軸方向、Y＝歩行平面、Z＝高さ。正面は−Y側、左は−X側。3Dは組立基準姿勢で、歩行・接触・風のシミュレーションではありません。",
                                text("試験体の軸方向はZ。組立参照配置で、歩行・風・負荷のシミュレーションではありません。",
                                     "The trial shafts use Z. This is an assembly reference, not a walking, wind or load simulation."))
    controls = controls.replace('{{tree:docs/ver3/drawings}}', guide["links"]["section"])
    controls = controls.replace('<label for="access-select">', '<label for="access-select" hidden>')
    controls = controls.replace("工具経路は原典の部分組立前提でのみCAD標本確認されています。キャリアを残した完成状態を通り抜ける証明ではありません。",
                                text("工具包絡と側面挿入は試験体だけの有限確認です。実物の工具・はめあい・締付けは未確認です。",
                                     "Tool envelopes and side insertion have finite bench checks only. Real tools, fit and tightening are unverified."))
    sections = []
    for step in guide["steps"][1:]:
        sections.append(f'<article class="static-step" id="trial-step-{step["id"]}"><h3><span>{step["id"]}.</span> {escape(step["title"])}</h3>'
                        f'<p>{escape(step["operation"])}</p></article>')
    with (DOC / "print-list.csv").open() as stream:
        print_rows = list(csv.DictReader(stream))
    prints = "".join(f'<tr><th scope="row">{source_link(r["file"], r["part_id"] + ".stl", ref, True)}</th>'
                     f'<td>{r["trial_quantity"]}</td><td>{escape(names[r["part_id"]])}</td></tr>' for r in print_rows)
    with (DOC / "purchase-list.csv").open() as stream:
        purchase_rows = list(csv.DictReader(stream))
    purchases = "".join(f'<tr><th scope="row">{escape(r["part_id"])}</th><td>{r["trial_needed"]}</td>'
                        f'<td>{escape(r["specification"])}</td><td><a href="{escape(r["official_url"], quote=True)}">{escape(text(r["sku"].replace("3x12", "3×12"), r["sku"].replace("BSカラー", "BS collar")))}</a></td>'
                        f'<td>{escape(r["minimum_cost_if_none_owned_jpy"])}</td></tr>' for r in purchase_rows)
    payload = f'''<!doctype html>
<html lang="ja">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="viewer.css">
<script src="i18n.js" defer></script><script src="app.js" defer></script>
<script src="viewer-loader.js" type="module"></script></head>
<body data-viewer-catalog="assets/m3-viewer-index.json">
<a class="skip-link" href="#main">{text("本文へ移動", "Skip to content")}</a>
<header class="site-header"><div class="header-inner"><a class="brand" href="index.html">RHINOCEROS</a>
<nav aria-label="{text("開発資料の目次", "Development contents")}"><a href="production.html">{text("完成版Ver.2・制作記録", "Completed Ver.2 / build record")}</a>
<a href="#viewer">360°</a><a href="#assembly">{text("組立", "Assembly")}</a><a href="#prints">{text("印刷", "Printing")}</a><a href="#purchase">{text("購入部品", "Hardware")}</a></nav></div></header>
<main id="main" tabindex="-1" data-public-version="3.2" data-engineering-revision="{REVISION}">
<section class="section viewer-intro" id="top"><p class="eyebrow">WORK IN PROGRESS / NOT A COMPLETE KIT</p>
<h1>{title}<br><span>{lead}</span></h1><aside class="warning"><h2>{notice}</h2>
<p>{parts_note}</p><p><strong>manufacturingRelease=false</strong> / {REVISION}</p></aside>
<div class="two-column"><article class="download-card"><h2>{full}</h2>
<p>{text("風車→入力軸→減速歯車→同期軸→脚。回転・拡大・部品選択と既存12工程で構成を確認できます。",
         "Rotor to input shaft, reduction gears, synchronizing shafts and legs. Rotate, zoom, select parts and inspect the existing 12 stages.")}</p>
<p><a href="r7.html?design=A#viewer">{text("全体を360度で見る", "Explore the full assembly in 360 degrees")}</a></p>
<p><a href="r7.html?design=A&amp;focus=connection#viewer">{text("歯車と軸の接合へ", "Gear and shaft connections")}</a> /
<a href="r7.html?design=A&amp;focus=retention#viewer">{text("抜け止めへ", "Axial retention")}</a> /
<a href="r7.html?design=A&amp;focus=legs#viewer">{text("脚の仕組みへ", "Leg mechanism")}</a></p>
<p>{link("print-list-3.1-A.csv", "旧Aの印刷一覧", "Original A print list", True)} /
{link("purchase-list-3.1-A.csv", "旧Aの購入一覧", "Original A purchase list", True)}</p></article>
<article class="download-card"><h2>{trial}</h2><p>{text("新STLは5種類・6点。M3ねじ3本、ナット6個、座金6枚。全機の購入・印刷数は未確定です。",
 "New STLs: 5 types, 6 prints. M3 screws: 3; nuts: 6; washers: 6. Whole-machine purchasing and print quantities are not established.")}</p>
<p>{link("README_ja.md", "詳しい組立・印刷・入手先", "Detailed assembly, printing and sources")} /
{link("BOM.csv", "試験体BOM", "Trial BOM", True)}</p>
<p>{source_link("FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.FCStd", "FreeCAD", ref, True)} /
{source_link("FreeCAD/Ver.3/m3_r1/M3AssemblyTrial.step", "STEP", ref, True)}</p></article></div></section>
<section class="section" id="joints"><h2>{text("固定する面と、自由に回す面を分ける", "Separate fixed and freely rotating surfaces")}</h2>
<p>{text("六角面がトルクを伝え、割締めと二重ナットが軸方向を保持。脚では金属スリーブだけを締め、リンクは挟みません。",
 "Hex flats transmit torque; split clamps and double nuts retain axially. At the pivot, clamp only the metal sleeve, not the link.")}</p>
<p>{link("joints.csv", "接合表：旧方式・新方式・工具方向・確認方法", "Joint table: old/new methods, tool directions and checks", True)}</p>
<div class="two-column">{figure("gear-3.2.svg", "新しい歯車接合の実断面：ねじ・座金・内外ナット", "Actual new gear section: screw, washers and inner/outer nuts")}
{figure("pivot-3.2.svg", "新しい脚ピンの実断面：平滑スリーブと自由すきま", "Actual new pivot section: smooth sleeve and free clearance")}</div>
<details><summary>{text("既存入力ハブ・左右支持のCAD図（3.1参照）", "Existing input hub and support CAD diagrams (3.1 reference)")}</summary>
<div class="two-column">{figure("input-3.1.svg", "既存3.1の入力軸・ハブ・保持部品", "Existing 3.1 input shaft, hub and retention")}
{figure("supports-3.1.svg", "既存3.1の左右支持と軸受キャップ", "Existing 3.1 supports and bearing caps")}</div></details></section>
<section class="section viewer-section" id="viewer"><h2>{text("M3接合試験体を360度で見る", "Explore the M3 bench trial in 360 degrees")}</h2>
<p>{text("全体の歩行機ではありません。形と金具は新しいCADそのものです。試験片は工程1で表示します。",
 "This is not the complete walker. Geometry and hardware come from the new CAD. Coupons appear in stage 1.")}</p>
<div class="viewer-toolbar"><label for="design-select">{text("表示対象", "Model")}<select id="design-select"><option value="A">A / {REVISION}</option></select></label>
<button type="button" class="button primary" id="load-viewer" hidden>{text("新しい接合の3Dを読み込む", "Load the new 3D connection model")}</button></div>
<p id="viewer-status" role="status" aria-live="polite">{text("3Dは操作時だけ読み込みます。", "3D loads only on request.")}</p>
<p id="viewer-error" class="media-error" role="alert" hidden></p>
<div id="viewer-fallback">{figure("gear-top-3.2.svg", "新しい六角穴・捕捉座のCAD形状", "New hex bore and captive-seat CAD")}
<a href="#assembly">{text("静的な組立手順へ", "Static assembly instructions")}</a></div>
<noscript><p>{text("JavaScriptなしでも下の手順とファイルを利用できます。", "Instructions and downloads remain available without JavaScript.")}</p></noscript>
{controls}</section>
<section class="section" id="assembly"><h2>{text("番号付き組立手順", "Numbered assembly sequence")}</h2>
<p>{link("README_ja.md", "詳細な順序・ねじの積層・注意点", "Detailed sequence, fastener stack and cautions")}</p>
{"".join(sections)}</section>
<section class="section" id="prints"><h2>{text("印刷リスト：まず試験片から", "Print list: start with the coupons")}</h2>
<p>{text("mm・100%。0.2mmはノズル径です。P1S・PETG・層高0.10mmは検査上の仮定で、本人の機種・材料は未確認です。",
 "Use mm at 100%. 0.2mm is nozzle diameter. P1S, PETG and 0.10mm layers are inspection assumptions; the user's printer and material are unconfirmed.")}</p>
<div class="matrix-scroll" role="region" aria-label="{text("試験用印刷一覧", "Trial print list")}" tabindex="0"><table><thead><tr><th>STL</th><th>{text("数", "Qty")}</th><th>{text("用途", "Purpose")}</th></tr></thead><tbody>{prints}</tbody></table></div>
<p>{link("print-list.csv", "姿勢・支持・未確認を含むCSV", "CSV with orientation, support and unknowns", True)} /
{link("slicing.json", "0.2mmノズルの実層検査", "Actual layer inspection with the 0.2mm nozzle")}</p></section>
<section class="section" id="purchase"><h2>{text("必要な購入部品：手持ちは先に差し引く", "Required hardware: subtract verified on-hand stock first")}</h2>
<p>{text("締結4品は手持ちゼロなら最小900円。軸材・工具・材料・送料は別です。2026-11-15の公式掲載で、来店時の在庫保証ではありません。",
 "The 4 fastener items have a minimum order total of JPY900 if none are owned. Shaft stock, tools, filament and shipping are extra. Official listings were checked on 2026-11-15; store availability is not guaranteed.")}</p>
<div class="matrix-scroll" role="region" aria-label="{text("試験用購入一覧", "Trial purchase list")}" tabindex="0"><table><thead><tr><th>ID</th><th>{text("数", "Qty")}</th><th>{text("規格", "Specification")}</th><th>{text("公式取扱い", "Official listing")}</th><th>JPY</th></tr></thead><tbody>{purchases}</tbody></table></div>
<p>{link("purchase-list.csv", "材質・販売単位・必要数・確認日のCSV", "CSV: materials, packs, quantities and check date", True)}</p></section>
<section class="section" id="limits"><h2>{text("計算と現物未確認を分ける", "Separate computed checks from physical unknowns")}</h2>
<p>{text("試験対は42歯・モジュール1・圧力角25度・1:1。接触比1.362、最小歯先厚0.539mm。歯の許容荷重・摩耗・実風歩行は未認定です。",
 "The trial pair has 42 teeth, module 1, a 25-degree pressure angle and 1:1 ratio. Contact ratio is 1.362; minimum tip thickness is 0.539mm. Allowable tooth load, wear and real wind-powered walking are unqualified.")}</p>
<p>{text("比較対象の3接合だけで、ねじ種類は2から1、締結工具寸法は4から2。ナットは省かず、座金とハブの質量は増えます。全機の削減率ではありません。",
 "Across the 3 matched joints only, screw variants fall from 2 to 1 and fastening-tool sizes from 4 to 2. Nuts remain; washers and hub mass increase. This is not a whole-machine reduction.")}</p>
<p>{link("checks.json", "CAD・挿入・工具・可動域・歯形の検査値", "CAD, insertion, tool, motion and tooth-profile checks")} /
{link("comparison.json", "部品・工具・質量の比較", "Part, tool and mass comparison")}</p>
<p>{text("空転、軸方向の抜け、樹脂クリープ、穴摩耗、ねじ緩み、歯の破損は別の故障です。購入・印刷・機器運転は実施していません。",
 "Relative slip, axial escape, plastic creep, bore wear, loosening and tooth breakage are separate failures. No purchasing, printing or machine operation was performed.")}</p></section>
</main><footer class="site-footer"><a href="production.html">{text("完成版Ver.2は変更していません", "The completed Ver.2 is unchanged")}</a>
<a href="#top">{text("先頭へ", "Back to top")}</a></footer></body></html>'''
    notice_html = (f'<aside class="record-scope" id="ver3-development"><strong>{escape(notice)}</strong>'
                   f'<p><a href="development.html">{escape(text("Ver.3開発入口：組立・印刷・購入部品・新M3接合", "Ver.3 development: assembly, printing, hardware and new M3 joints"))}</a></p></aside>')
    (output / "ver3-2.html").write_text(payload)
    from ver3_4_data import build_integrated
    notice_html, integrated_assets, integrated_source = build_integrated(output, ref, text, source_link)
    assets.update(integrated_assets)
    return {"{{ver3_development_notice}}": notice_html}, assets, {"3.2": source, "3.4": integrated_source}


if __name__ == "__main__":
    import argparse
    import subprocess
    parser = argparse.ArgumentParser()
    parser.add_argument("--register-translations", action="store_true", required=True)
    args = parser.parse_args()
    output = ROOT / "site/dist/TeoJansen_Rhinoceros"
    build_development(output, subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    register_translations()
    print(f"Registered {len(MESSAGES)} development-only translation messages without changing existing entries.")
