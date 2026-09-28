"""Build an explicitly local, unpublished r7 preview beside the public-site output."""

from collections import Counter
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

import build
from r7_data import BASE, CATEGORIES, OP_NAMES, PATH_NAMES, ROOT, Snapshot, TOOLS, build_candidate, digest

OUTPUT = ROOT / "site/dist/r7-preview/TeoJansen_Rhinoceros"


def table(headers, rows):
    return ('<div class="matrix-scroll" role="region" aria-label="同一定義の比較表" tabindex="0"><table class="improvement-matrix">'
            '<thead><tr>' + "".join(f'<th scope="col">{escape(str(h))}</th>' for h in headers) + '</tr></thead><tbody>'
            + "".join('<tr><th scope="row">' + escape(str(row[0])) + '</th>'
                      + "".join(f'<td>{escape(str(cell))}</td>' for cell in row[1:]) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def comparison_html(guides, snapshot):
    cards = []
    for ident, guide in guides.items():
        row = guide["summary"]
        cards.append(f'''<article><h3>{ident}案 · {row["rotorDiameterMm"]:g} mm／{row["reduction"]:g}:1</h3>
          <dl><div><dt>名目全体質量（実測・スライスではない）</dt><dd>{row["cadMassG"]:.3f} g</dd></div>
          <div><dt>個別初回部材費（共同lot平均ではない）</dt><dd>{row["firstBuildCostJpy"]:,.2f} 円</dd></div>
          <div><dt>原供給代理／名目要求</dt><dd>{row["rawGuardedSupplyMilliNm"]:.4f} / {row["nominalRequiredMilliNm"]:.4f} mN·m</dd></div>
          <div><dt>到達位相での最小差（名目条件）</dt><dd>{row["nominalReachableMarginMilliNm"]:+.4f} mN·m</dd></div>
          <div><dt>原供給×0.5との差（不足）</dt><dd>{row["halfProxyMarginMilliNm"]:+.4f} mN·m</dd></div>
          <div><dt>床滑り仕事／クランク1周期</dt><dd>{row["groundSlipWorkNmm"]:.2f} Nmm</dd></div>
          <div><dt>入力120 rpmを仮定した30 cm換算</dt><dd>{row["minutesFor300mmAtAssumed120InputRpm"]:.2f} 分（実速度ではない）</dd></div></dl>
          <p>設計予算は約{row["approvedApproximateBudgetJpy"]:,}円／台。未保有工具DN-03は約396円、送料・未確定税・手数料は別。
          初回試験片・組立台を費用に含み、歩行質量には含みません。材料係数・サポート量が変わる場合は予算内を保証しません。</p>
          <a href="r7.html?design={ident}#viewer">{ident}を360°と12工程で見る →</a>
          <p><a href="{guide["links"]["purchase"]}">個別購入lot・感度の正本</a></p></article>''')
    baseline = snapshot.json(BASE + "baseline_A_same_model.json")
    nominal = next(case for case in baseline["cases"] if case["case"] == "nominal")
    current = guides["A"]["summary"]
    old_slip = nominal["workPerCycleNmm"]
    if isinstance(old_slip, dict):
        slip_keys = [key for key in old_slip if "slip" in key.lower()]
        if len(slip_keys) != 1:
            raise ValueError("Identify the exact nonnegative baseline slip-work field")
        old_slip = old_slip[slip_keys[0]]
    old_mass, old_input = baseline["cadMassKg"] * 1000, nominal["requiredInputMaximumNm"] * 1000
    rows = [
        ("名目質量 g", f"{old_mass:.3f}", f"{current['cadMassG']:.3f}", f"{(current['cadMassG']/old_mass-1)*100:+.2f}%"),
        ("同じ最終式の入力要求 mN·m", f"{old_input:.4f}", f"{current['nominalRequiredMilliNm']:.4f}", f"{(current['nominalRequiredMilliNm']/old_input-1)*100:+.2f}%"),
        ("非負の床滑り仕事 Nmm/周期", f"{old_slip:.4f}", f"{current['groundSlipWorkNmm']:.4f}", f"{(current['groundSlipWorkNmm']/old_slip-1)*100:+.2f}%"),
    ]
    return '<div class="r7-specs">' + "".join(cards) + '</div>', table(
        ["定義", "保存した旧A・最終式で再計算", "r7 A", "変化"], rows)


def static_guides(guides):
    sections = []
    for ident, guide in guides.items():
        links = guide["links"]
        downloads = "".join(f'<a href="{links[key]}">{label}</a>' for key, label in (
            ("native", "FreeCAD原本"), ("cad", "STEP原本"), ("stl", "この案のSTL"),
            ("bom", "使用数量BOM"), ("purchase", "個別購入lot"), ("canonical", "正規配置"),
            ("stages", "schema2工程"), ("access", "経路と在庫"), ("print", "印刷向き・PET型紙情報"),
            ("assembly", "共通組立原文"), ("readme", "案別の説明")))
        items = []
        for stage in guide["steps"][1:]:
            operations = []
            for index, op in enumerate(stage["orderedOperations"]):
                counts = Counter(guide["instances"][name]["partId"] for name in op["instances"])
                part_lines = "".join(f'<li><code>{escape(part)}</code> × {count} · {CATEGORIES[guide["parts"][part]["category"]]}</li>'
                                     for part, count in sorted(counts.items()))
                operations.append(f'<li><strong>操作{index+1}：{OP_NAMES[op["operation"]]} {len(op["instances"])}点</strong>'
                                  f'<details><summary>部品IDと数量</summary><ul>{part_lines}</ul></details></li>')
            for bench in stage.get("footFirstBenchSubassemblies", []):
                counts = Counter(guide["instances"][name]["partId"] for name in bench["instances"])
                current = ", ".join(f"{part} ×{count}" for part, count in sorted(counts.items()))
                operations.append(f'<li><strong>先に足モジュール：Y={bench["stationYmm"]:g} mm、'
                                  f'{"左" if bench["side"] < 0 else "右"}、{len(bench["instances"])}点</strong>。'
                                  'DN-03で市販M2×12とM2ナイロンナットを締結後、残る脚リンクを加えます。'
                                  f'<details><summary>現在の部品ID（追跡IDの旧寸法名は使いません）</summary><p>{escape(current)}</p></details></li>')
            if stage["prepareOnly"]:
                operations.append(f'<li><strong>別作業台で準備する {len(stage["prepareOnly"])}点</strong>。本体へ装着した数量ではありません。</li>')
            routes = [p for p in guide["paths"].values() if p["workflowStageId"] == stage["id"]]
            route_items = "".join(f'<li><strong>{escape(PATH_NAMES[p["id"]])}</strong><br>'
                                  f'操作{p["afterOperationIndex"]+1}後の境界 · 移動{len(p["movingNames"])}点／固定{len(p["fixedNames"])}点。'
                                  f'方向 {escape(str(p["direction"]))}、定数移動 {escape(str(p["constantOffsetMm"]))} mm、'
                                  f'標本 {escape(str(p["distancesMm"]))} mm。'
                                  f'<br><code>{p["id"]}</code>／在庫hash <code>{p["inventorySha256"]}</code></li>' for p in routes)
            extra = "<p>手による仮支持が必要です。入力軸がない段階の自己保持は認めていません。</p>" if stage["temporarilyHandSupported"] else ""
            if stage["additionalToolRequirement"]:
                if stage.get("footFirstBenchSubassemblies"):
                    extra += "<p>市販ENGINEER DN-03の作業端・全軸・柄と把持空間を有限幾何で確認。所有・実操作・ナイロン部保持トルクは未確認です。精密切断・薄口工具を前提にしていません。</p>"
                else:
                    extra += "<p>この工程の追加工具条件は正規の工具経路資料を参照してください。現物の工具操作は未確認です。</p>"
            if stage["collarClocking"]:
                extra += "<p>カラーのクロックは正規CAD配置へ反映済み。二重に回転を加えません。現物のバランスは未測定です。</p>"
            items.append(f'<article class="static-step" id="r7-guide-{ident}-{stage["id"]}"><h4>{escape(stage["id"])} · {escape(stage["title"])}</h4>'
                         f'<p>{escape(stage["cautions"])}</p><p class="small-note">停止角0°／締付トルク未指定。工具：'
                         f'{escape("、".join(TOOLS[k] for k in stage["tools"]) or "指定なし")}</p>'
                         f'<ol class="r7-operation-list">{"".join(operations)}</ol>{extra}'
                         + (f'<details><summary>操作境界に対応する有限経路標本</summary><ul class="r7-path-list">{route_items}</ul></details>' if routes else "")
                         + '</article>')
        sections.append(f'<section class="static-guide" id="r7-guide-{ident}" aria-labelledby="r7-guide-{ident}-title">'
                        f'<h3 id="r7-guide-{ident}-title">r7 {ident}案 · 12工程／{guide["model"]["instanceCount"]}点</h3>'
                        f'<div class="r7-downloads">{downloads}</div>{"".join(items)}</section>')
    return "".join(sections)


def validate_preview(output, manifest):
    if manifest["localOnly"] is not True or manifest["publicationAuthorized"] is not False:
        raise ValueError("r7 output must remain explicitly unpublished")
    pages = manifest["pages"]
    documents = {}
    for page in pages:
        text = (output / page).read_text()
        if "{{" in text or "/Users/" in text or "file://" in text:
            raise ValueError("Unresolved template or private path in local preview")
        parser = build.DocumentLinks()
        parser.feed(text)
        documents[page] = parser
    for page, parser in documents.items():
        for link in parser.links:
            split = urlsplit(link)
            if split.scheme or split.netloc:
                if manifest["candidateCommit"] in link or "/integrated_r7/" in link:
                    raise ValueError("An unpublished candidate was incorrectly linked as a public resource")
                if split.scheme != "https":
                    raise ValueError("Unexpected external protocol")
                continue
            target = (output / unquote(split.path or page)).resolve()
            if not target.is_relative_to(output.resolve()) or not target.is_file():
                raise ValueError(f"Missing/unsafe local r7 resource: {link}")
            if split.fragment and target.suffix == ".html" and unquote(split.fragment) not in documents[target.name].ids:
                raise ValueError(f"Missing local r7 anchor: {link}")
    expected = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()}
    registered = set(manifest["allFiles"])
    if expected != registered | {"r7-preview-manifest.json", "LOCAL_ONLY_DO_NOT_DEPLOY"}:
        raise ValueError("Local preview contains unregistered files")
    for path, data in manifest["allFiles"].items():
        if digest((output / path).read_bytes()) != data["sha256"]:
            raise ValueError(f"Local preview hash differs: {path}")


def create_preview():
    if os.environ.get("CI"):
        raise ValueError("Unpublished r7 previews are local-only; no CI/deployment entry point is enabled")
    snapshot = Snapshot()
    ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    public_manifest = build.build(OUTPUT, ref, include_r7=False, validate_output=False)
    guides, catalog, assets, downloads = build_candidate(OUTPUT, snapshot)
    comparison, baseline = comparison_html(guides, snapshot)
    fallbacks = []
    for ident, guide in guides.items():
        path = OUTPUT / guide["links"]["section"]
        svg = ET.fromstring(path.read_bytes())
        width, height = svg.attrib["width"], svg.attrib["height"]
        fallbacks.append(f'<figure><img src="{guide["links"]["section"]}" width="{width}" height="{height}" loading="lazy"'
                         f' alt="r7 {ident}案の正規組立基準図。停止姿勢の説明図で、実歩行の写真ではありません。">'
                         f'<figcaption>{ident} · 正規組立基準図（ローカル原本・床接触姿勢ではありません）</figcaption></figure>')
    substitutions = {
        "{{r7_robots}}": '<meta name="robots" content="noindex, nofollow">',
        "{{r7_page_title}}": "r7統合候補・ローカル表示 — リノセウス",
        "{{r7_local_only}}": "true", "{{r7_brand_note}}": "ローカル候補",
        "{{r7_scope_label}}": "LOCAL CANDIDATE", "{{r7_status_title}}": "ローカル表示 · 実機未検証の設計候補",
        "{{r7_resource_notice}}": "このプレビューの資料はローカルにコピーした原本です。公開サイトへの差替えとは別です。",
        "{{r7_scope_short}}": "ローカル表示", "{{r7_footer_note}}": "r7ローカル表示 · 物理的な合格は未確認。",
        "{{r7_comparison_image}}": "", "{{r7_media}}": "", "{{r7_diagnostics}}": "",
        "{{r7_revision}}": snapshot.source["revisionId"],
        "{{r7_candidate_revision}}": snapshot.source["candidateRevision"],
        "{{r7_commit}}": snapshot.commit,
        "{{r7_slice_notice}}": "代表の元5点＋新Cの相手歯車2点を層確認。Z0.2 mm支持薄膜の除去、下面の仕上げと実はめあいは未確認です。",
        "{{r7_comparison}}": comparison, "{{r7_baseline}}": baseline,
        "{{r7_guides}}": static_guides(guides),
        "{{r7_payload}}": "転送サイズ " + "／".join(f"{ident} {g['model']['transportBytes']/1e6:.2f} MB" for ident, g in guides.items()),
        "{{r7_fallback}}": '<div class="r7-fallback">' + "".join(fallbacks) + '</div>',
        "{{r7_sources}}": "".join(f'<a href="{url}">{escape(label)}</a>' for key, label in (
            ("contract", "schema2統合契約"), ("manifest", "正規manifest"), ("readme", "r7全体の説明"),
            ("review", "独立レビューと限定是正"), ("comparisonCsv", "比較CSV"), ("baseline", "保存旧A・同一定義比較"),
            ("slicing", "固定候補のスライス状況"), ("slicingReport", "代表スライスの限定結果"),
            ("contactFrames", "保存フレームの近似・不足成分"),
            ("accessories", "別枠の試験片・組立台"), ("sharedLots", "共同購入lot（個別費用とは別）"))
            for url in [catalog["links"][key]]),
    }
    html = (ROOT / "site/r7.html").read_text()
    for key, value in substitutions.items():
        html = html.replace(key, value)
    (OUTPUT / "r7.html").write_text(html)
    shutil.copyfile(ROOT / "site/r7.css", OUTPUT / "r7.css")
    banner = ('<aside class="r7-local-banner"><strong>ローカル統合プレビュー：</strong>このページは公開履歴の内容です。'
              '<a href="r7.html">別版r7候補を表示</a> · r7の公開・合格を意味しません。</aside>')
    for page in public_manifest["pages"]:
        path = OUTPUT / page
        text = path.read_text().replace('<main id="main" tabindex="-1">', '<main id="main" tabindex="-1">' + banner)
        text = text.replace('</head>', '<link rel="stylesheet" href="r7.css">\n</head>')
        path.write_text(text)
    handoff = {
        "schemaVersion": 2, "localOnly": True, "candidateCommit": snapshot.commit,
        "revision": catalog["revision"], "sourceContractSha256": snapshot.source["contractSha256"],
        "geometryUnits": "metres", "cadAxes": "X shaft / Y stride / Z height",
        "assemblyOffsetUnits": "mm, added to canonical CAD translations, not a new mechanical placement",
        "designs": {ident: {
            "model": guide["modelUrl"], "modelSha256": guide["model"]["sha256"],
            "transportSha256": guide["model"]["transportSha256"],
            "guide": f"assets/r7-assembly-{ident}.json",
            "guideSha256": assets[f"assets/r7-assembly-{ident}.json"]["sha256"],
            "instanceCount": guide["model"]["instanceCount"],
            "signedInputRevolutionsPerCrank": guide["signedInputRevolutionsPerCrank"],
            "contactFrames": guide.get("contactFrames"),
        } for ident, guide in guides.items()},
        "walkingMotion": {
            "status": "partial_canonical_states_received",
            "reason": "73 saved body/foot-center states are available. Independent rocker angles and exact rigid body world4x4 remain unsolved; no zero fill.",
            "owner": "engineering final package",
            "required": ["same-revision source hashes", "crank/input angle and signed ratio",
                         "body world pose / forward trajectory", "per-foot compression/rocker/contact or canonical instance transforms",
                         "time/RPM assumptions and approximation scope"],
        },
        "renderingStatus": "Static and assembly rendering authorized; full walking is not inferred from missing degrees of freedom.",
    }
    (OUTPUT / "blender-handoff.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n")
    (OUTPUT / "LOCAL_ONLY_DO_NOT_DEPLOY").write_text("Unpublished candidate. This output is not a Pages artifact.\n")
    fingerprints = {str(p.relative_to(OUTPUT)): {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
                    for p in OUTPUT.rglob("*") if p.is_file() and p.name not in {"r7-preview-manifest.json", "LOCAL_ONLY_DO_NOT_DEPLOY"}}
    manifest = {"schemaVersion": 2, "localOnly": True, "publicationAuthorized": False,
                "candidateCommit": snapshot.commit, "source": snapshot.source,
                "pages": [*public_manifest["pages"], "r7.html"], "candidateAssets": assets,
                "localDownloads": downloads, "allFiles": fingerprints,
                "motionStatus": "Partial canonical contact states supplied; rocker angles and exact rigid world pose are not independent solver outputs. No complete walking video implied.",
                "note": "Existing public output remains separate. Do not upload this local candidate directory."}
    (OUTPUT / "r7-preview-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    validate_preview(OUTPUT, manifest)
    print(f"Local-only r7 preview: {OUTPUT.relative_to(ROOT)}")
    print(f"{sum(g['model']['instanceCount'] for g in guides.values())} exact instances; 12 stages/design; "
          f"{sum(len(g['paths']) for g in guides.values())} source-bound paths. No push, publish or physics execution.")


if __name__ == "__main__":
    create_preview()
