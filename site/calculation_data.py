"""Publish fixed calculation evidence without recomputing or changing geometry."""

from __future__ import annotations

import csv
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/calculation-source.json"
BASE = "docs/ver3/commercial_basis_r3/"
REPOSITORY = "https://github.com/ktanino10/TeoJansen_Rhinoceros"
FIGURE_STEMS = {f"{kind}_{design}" for design in "ABC" for kind in
                ("deflection", "startup", "torque_budget", "improvement")} | {
                    "gait_improvement", "linkage_layout", "bearing_interface", "rib_section_screen_C"}
METHODS = {
    "deflection": "Euler–Bernoulli 1D梁・偏心圧縮の限定計算。完成機の立体FEMではありません。",
    "startup": "準静的な反力と明示した摩擦・損失の計算。接触動力学・実機始動ではありません。",
    "torque_budget": "未校正の静止パネル抗力による供給推定と設計余裕。CFDではありません。",
    "improvement": "同じ風場で要因を順に変えた条件比較。実測の性能改善率ではありません。",
    "gait_improvement": "同じ尺度・脚向きの剛体閉リンクの運動学比較。V2実測beforeではありません。",
    "linkage_layout": "寸法を記した2D機構模式図。最終製造CAD・組立図ではありません。",
    "bearing_interface": "メーカー寸法に基づく当たり面の模式図。購入品の実CADではありません。",
    "rib_section_screen_C": "16断面の梁試験片探索。完成フレーム全体の生成設計ではありません。",
}
TITLES = {
    "deflection": "支点・荷重と部材のたわみ",
    "startup": "クランク角ごとの必要入力",
    "torque_budget": "風車角ごとの供給・要求トルク",
    "improvement": "比・リンク・同期を変えた要因比較",
    "gait_improvement": "共通リンク：上下動を減らしたときの変化",
    "linkage_layout": "共通リンク：変更した五つのピン間寸法",
    "bearing_interface": "軸受とスペーサの当たり面",
    "rib_section_screen_C": "C案：16断面のリブ試験片比較",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_source(path: str) -> Path:
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT) or not result.is_file():
        raise ValueError(f"Invalid calculation source: {path}")
    return result


def svg_dimensions(data: bytes) -> tuple[int, int]:
    text = data.decode("utf-8")
    if re.search(r"<!|/Users/|file://|https?://(?!www\.w3\.org/2000/svg)", text, re.I):
        raise ValueError("Unexpected declaration, private path or external SVG resource")
    tree = ET.fromstring(data)
    tags = {"svg", "rect", "text", "path", "polyline", "polygon", "circle"}
    attributes = {"width", "height", "viewBox", "x", "y", "cx", "cy", "r", "d", "points",
                  "fill", "stroke", "stroke-width", "stroke-dasharray", "font-family", "font-size"}
    if tree.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("Expected a standalone SVG")
    for node in tree.iter():
        if node.tag not in {f"{{http://www.w3.org/2000/svg}}{tag}" for tag in tags}:
            raise ValueError("Unexpected SVG element; scripts, links and metadata are not permitted")
        if not set(node.attrib) <= attributes or any(re.search(r"url\s*\(|javascript:|data:", value, re.I)
                                                    for value in node.attrib.values()):
            raise ValueError("Unexpected SVG attribute or embedded resource")
    width, height = int(tree.attrib["width"]), int(tree.attrib["height"])
    if width <= 0 or height <= 0 or tree.attrib.get("viewBox") != f"0 0 {width} {height}":
        raise ValueError("SVG dimensions and viewBox differ")
    return width, height


def read_study():
    source = json.loads(SOURCE.read_text())
    if source["schemaVersion"] != 1 or source["revisionId"] != "v3-commercial-r3-01":
        raise ValueError("Integrate a new calculation revision explicitly")
    for key in ("artifactCommit", "inputCommit"):
        if not re.fullmatch(r"[a-f0-9]{40}", source[key]):
            raise ValueError("Calculation source commits must be immutable")
    path = safe_source(source["manifest"])
    if digest(path) != source["manifestSha256"]:
        raise ValueError("Calculation manifest changed; do not mix evidence revisions")
    manifest = json.loads(path.read_text())
    if manifest["revisionId"] != source["revisionId"] or manifest["sourceCommit"] != source["inputCommit"]:
        raise ValueError("Calculation input/artifact contract differs")
    if (manifest["qualifiedPrototypeCount"] != 0 or manifest["siteMappingToFirstCutCadPermitted"] is not False
            or any(manifest[key] is not None for key in ("finalCadMeshHashes", "finalAssemblyHashes", "finalBomHashes"))):
        raise ValueError("Expected an unqualified calculation skeleton, separate from first-cut CAD")
    for name, expected in {**manifest["sourceHashes"], **manifest["artifactHashes"]}.items():
        if digest(safe_source(name)) != expected:
            raise ValueError(f"Calculation source hash differs: {name}")
    figures = {Path(record["file"]).stem: record for record in manifest["figures"]}
    if set(figures) != FIGURE_STEMS or len(manifest["figures"]) != 16:
        raise ValueError("Expected exactly the sixteen reviewed calculation figures")
    for record in figures.values():
        if (record["revisionId"] != source["revisionId"] or record["sourceGeometryRevision"] != source["revisionId"]
                or record["isFinalCadGeometry"] is not False or record["resultStatus"] != "UNKNOWN"):
            raise ValueError("A figure belongs to another geometry revision or evidence status")
        if record["designId"] not in ("A", "B", "C", None):
            raise ValueError("Unknown calculation design ID")
        for name, expected in record["sourceHashes"].items():
            path = BASE + name if "/" not in name else name
            if digest(safe_source(path)) != expected:
                raise ValueError(f"Figure source hash differs: {name}")
        data = json.loads(safe_source(record["dataFile"]).read_text())
        for key in record.get("dataPointer", "").strip("/").split("/") if record.get("dataPointer") else []:
            data = data[int(key)] if isinstance(data, list) else data[key]
        svg_dimensions(safe_source(record["file"]).read_bytes())
    comparison = json.loads(safe_source(BASE + "comparison.json").read_text())
    candidates = {ident: json.loads(safe_source(BASE + f"candidate_{ident}.json").read_text()) for ident in "ABC"}
    if comparison["revisionId"] != source["revisionId"] or comparison["qualifiedPrototypeCount"] != 0:
        raise ValueError("Comparison revision/status differs")
    if any(c["revisionId"] != source["revisionId"] or c["designId"] != ident
           or c["qualifiedPrototype"] is not False or c["physicalStatus"] != "UNKNOWN" for ident, c in candidates.items()):
        raise ValueError("Candidate calculation revision/status differs")
    with safe_source(BASE + "torque_decomposition.csv").open(newline="") as file:
        decomposition = list(csv.DictReader(file))
    if {(row["design"], row["case"]) for row in decomposition} != {(d, c) for d in "ABC" for c in ("low", "nominal", "high")}:
        raise ValueError("Expected all nine same-angle torque decompositions")
    return source, manifest, figures, comparison, candidates, decomposition


def url(path, source, raw=False):
    safe_source(path)
    return f"{REPOSITORY}/{'raw' if raw else 'blob'}/{source['artifactCommit']}/{quote(path, safe='/')}"


def asset_name(path):
    return "assets/calculation-" + Path(path).name.replace("_", "-")


def figure(stem, record, source):
    kind = stem if stem in TITLES else stem.rsplit("_", 1)[0]
    title = (f"{record['designId']}案 · " if record["designId"] and stem != "rib_section_screen_C" else "") + TITLES[kind]
    width, height = svg_dimensions(safe_source(record["file"]).read_bytes())
    amplification = record["displayAmplification"]
    if isinstance(amplification, dict):
        scale = "、".join(f"{part}：{value:g}倍" for part, value in amplification.items())
    else:
        scale = f"契約値 {amplification:g}倍（グラフ・模式図のため変形拡大ではありません）"
    note = ("図中の灰色が変形前、色付きが計算変形。色は各部材の変位0からその最大値で、共通の応力尺度ではありません。下表の実たわみ値と、図の変形拡大倍率を分けて読みます。"
            if kind == "deflection" else
            "図は原典のままです。loadcase IDは資料の管理キーで、図中の低・名目・高抵抗や角度の区別は凡例を優先してください。")
    href = asset_name(record["file"])
    figure_units = record["figureUnits"].replace("mN*m", "mN·m").replace("deg_or_scenario_index", "角度°／ケース番号").replace(",", "・")
    return f'''<figure class="media calculation-figure" id="figure-{stem}" data-figure="{stem}"
      data-revision="{escape(record["revisionId"])}" data-design="{record["designId"] or "shared"}">
      <h4>{escape(title)}</h4>
      <img src="{href}" alt="{escape(title)}。{escape(METHODS[kind])} 支点・荷重・単位は図と説明に記載。"
        width="{width}" height="{height}" loading="lazy" decoding="async">
      <p class="media-error" role="status" hidden>図を読み込めませんでした。下の原典SVGをご確認ください。</p>
      <figcaption><p>{escape(METHODS[kind])}</p><p>{escape(note)}</p>
        <p><strong>図の単位：</strong>{escape(figure_units)} ／ <strong>実データ：</strong>{escape(record["units"])}</p>
        <p><strong>変形表示倍率：</strong>{escape(scale)}</p>
        <div class="figure-actions"><button class="button" type="button" data-enlarge="{href}" data-title="{escape(title)}"
          data-width="{width}" data-height="{height}" hidden>図を拡大して読む</button>
          <a href="{href}" target="_blank" rel="noopener">元サイズのSVGを別タブで開く ↗</a></div>
        <details><summary>この図の版・荷重ケース・出典</summary>
          <dl><dt>revision / geometry revision</dt><dd>{escape(record["revisionId"])}</dd>
          <dt>design ID / loadcase ID</dt><dd>{record["designId"] or "共通"} / {escape(record["loadcaseId"])}</dd>
          <dt>method（原契約）</dt><dd>{escape(record["method"])}</dd>
          <dt>resultStatus</dt><dd>UNKNOWN · 実物・最終CADの確認ではありません。</dd></dl>
          <p><a href="{url(record["file"], source)}">原典SVG</a> ·
          <a href="{url(record["dataFile"], source)}">数値の正本 {escape(record.get("dataPointer", ""))}</a> ·
          <a href="{url(BASE + "manifest.json", source)}">図とデータのハッシュ契約</a></p>
        </details>
      </figcaption></figure>'''


def table(headers, rows, caption):
    return (f'<div class="calculation-table" role="region" aria-label="{escape(caption)}" tabindex="0"><table>'
            f'<caption>{escape(caption)}</caption><thead><tr>'
            + "".join(f'<th scope="col">{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>'
            + "".join('<tr>' + f'<th scope="row">{escape(str(row[0]))}</th>'
                      + "".join(f'<td>{escape(str(cell))}</td>' for cell in row[1:]) + '</tr>' for row in rows)
            + '</tbody></table></div>')


def render_design(ident, candidate, comparison, figures, decomposition, source):
    nominal = next(row for row in candidate["startup"] if row["id"] == "nominal")
    values = next(row for row in decomposition if row["design"] == ident and row["case"] == "nominal")
    counts = {}
    for case in ("nominal", "high"):
        cells = [result for cell in candidate["sensitivity"]["cells"] for result in cell["cases"] if result["resistance"] == case]
        counts[case] = (sum(row["conditional_half_capture_status"] == "PASS" for row in cells), len(cells))
        if counts[case] != (0, 27):
            raise ValueError("Revisit gate language: expected zero qualifying cells out of 27")
    members = candidate["structure"]["members"]
    member_rows = []
    for member in members:
        supports = " / ".join(f"{x:g} mm {'変位拘束' if kind == 'translation' else '回転拘束'}"
                              for x, kind in member["supports"])
        loads = " / ".join(f"x={x:g} mm：{force:.4f} N" for x, force in member["loads_n"])
        if member.get("distributed_load_n_per_mm"):
            loads += f'、分布荷重 {member["distributed_load_n_per_mm"]:.6f} N/mm'
        member_rows.append((member["partId"], supports, loads,
                            f'{member["max_deflection_mm"]:.6f}', f'{member["max_bending_stress_mpa"]:.3f}',
                            f'{member["displayAmplification"]:g}倍'))
    torque_labels = [
        ("脚の要求を理想減速", "ideal_ratio_nm"), ("歯車の損失", "gear_loss_nm"),
        ("ロッドの負荷に伴う損失", "coupling_load_loss_nm"),
        ("ロッドの予荷重・自重の損失", "coupling_preload_loss_nm"),
        ("入力以外の軸受の換算抵抗", "other_bearing_loss_nm"),
        ("入力軸受2個の抵抗（一回分）", "input_bearing_pair_nm"),
        ("総要求", "total_required_nm"), ("下流要求の2倍目標", "net_2x_target_nm"),
        ("入力軸受を一回戻した総目標", "gross_target_nm"),
    ]
    torque_rows = [(label, f'{float(values[key])*1000:.3f}') for label, key in torque_labels]
    support = comparison["bearingInterfaceUpdate"]
    old = comparison["boundedSearch"]["originalMetrics"]
    new = comparison["boundedSearch"]["selectedMetrics"]
    tolerance = comparison["linkageTolerance"]
    figs = lambda name: figure(f"{name}_{ident}", figures[f"{name}_{ident}"], source)
    return f'''<details class="analysis-design" id="analysis-{ident}" {"open" if ident == "A" else ""}>
      <summary><h2>{ident}案 · 径{candidate["candidate"]["rotorDiameterMm"]:g} × 幅48 mm／減速{candidate["gears"]["total_reduction"]:g}:1</h2></summary>
      <div class="analysis-design-body">
      <p class="small-note">骨格条件の解析版 {escape(source["revisionId"])} · 最終CAD／全BOMはありません。既存360°とは別版です。</p>
      <div class="analysis-results" data-result="{ident}">
        <p><strong>計算予算：FAIL</strong> · 名目 {counts["nominal"][0]}/{counts["nominal"][1]}、高抵抗 {counts["high"][0]}/{counts["high"][1]}セルで目標達成。</p>
        <p>基準風場の最小供給代理値×0.5：<strong>{nominal["proxy_min_raw_nm"]*0.5*1000:.3f} mN·m</strong> ／
        同じケースの総目標：<strong>{float(values["gross_target_nm"])*1000:.3f} mN·m</strong>。</p>
        <p><strong>実自己始動・30 cm歩行：UNKNOWN（未実測）</strong>。モデル予算のFAILを、手元ReFaの実測結果と読み替えていません。</p>
      </div>
      <section id="structure-{ident}" class="calculation-topic"><h3>① 材料・構造：どこを支え、どこが曲がるか。</h3>
        <p>高抵抗ケースの反力・入力を1D梁計算へ渡した結果です。図は入力軸・中間軸・主軸・固定ピボット・AC部材の支点と荷重を示します。
        D軸は弱い曲げ方向の断面、固定ピボットはM3ボルト芯の限定モデル。スリーブを中実鋼棒の剛性として数えていません。</p>
        {figs("deflection")}
        {table(["部材", "支点（軸方向位置）", "荷重（符号付き）", "実たわみ最大 mm", "曲げ応力 MPa", "図の変形倍率"], member_rows, f"{ident}案・高抵抗ケースの部材計算")}
        <p class="small-note">表は梁の曲げ成分です。ACの偏心圧縮による追加たわみ・組合せ応力は原データのscenariosに別記されています。
        支持筐体・軸受はめあい・根元・ロッド層の剛性や衝撃を含む、完成機全体のFEMではありません。部材の限定判定だけで組立全体を合格にしません。</p>
        {figure("rib_section_screen_C", figures["rib_section_screen_C"], source) if ident == "C" else ""}
      </section>
      <section id="linkage-{ident}" class="calculation-topic"><h3>② リンク：上下動の改善と、足上げ・公差の代償。</h3>
        <p>共通リンクの名目上下動は旧R2計算の{old["body_bounce_mm"]:.3f} mmから{new["body_bounce_mm"]:.3f} mmへ低減。
        一方、足上げは{old["swing_gap_max_mm"]:.2f} mmから{new["swing_gap_max_mm"]:.2f} mmへ減っています。
        単独寸法±0.1 mmの誤差では最小{tolerance["minimum_swing_gap_mm"]:.2f} mmで8 mm基準未達、
        切替速度係数差は最大{tolerance["maximum_handoff_rate_jump_mm_per_rad"]:.2f} mm/radへ悪化します。</p>
        <p>比較相手は旧解析R2であり、Ver.2実物の測定前後ではありません。リンクは剛体として解き、表示の中で伸ばしたり、任意の前進を足したりしていません。</p>
        <a href="#shared-linkage">共通の寸法図・上下動グラフと公差表を見る →</a>
      </section>
      <section id="fluid-{ident}" class="calculation-topic"><h3>③ 流体・駆動：供給と損失を同じ単位で読む。</h3>
        <p>供給は未校正の静止パネル抗力推定で、CFD・流速場の実測ではありません。速度分布、照準、減率0.5はいずれも設計入力です。
        風車角の最小供給とクランク角の最大要求を使った保守的な予算で、異なる軸の角度を同一角として重ねていません。</p>
        <div class="calculation-figure-grid">{figs("torque_budget")}{figs("startup")}</div>
        <h4>同じ名目ケース、総要求ピーク {float(values["peak_crank_deg"]):g}°の内訳</h4>
        <p>各損失の別々のピークを足した表ではありません。原典CSVの同じクランク角から読み取り、Nmを表示用にmN·mへ単位換算しています。</p>
        {table(["項目", "入力軸換算 mN·m"], torque_rows, f"{ident}案・同一ピーク角のトルク内訳")}
        <p><strong>設計側の「2倍」は入力軸受後の下流要求だけ。</strong>そこへ入力軸受2個分の抵抗を一回加えた値が総目標です。総要求を丸ごと2倍したものではなく、出力を測った後に同じ損失を再控除することもありません。</p>
        {figs("improvement")}
        <p class="small-note">「比のみ」は旧質量・風作用位置・リンクを固定し、減速比だけを変えた比較です。その後に改訂リンク・風作用位置・ローター増量、既比較の同期ロッドを順に加えています。
        慣性・関節摩擦による全内部反力の再分配・加速や接触衝撃までは解いていません。</p>
      </section>
      <section id="interface-{ident}" class="calculation-topic"><h3>④ 軸受・スペーサ：寸法が見つかったことと、適合は別。</h3>
        <p>採用候補の外径{support["candidateSpacerRetail"]["dimensionsMm"][1]:g} mmスペーサは、
        686AZZ1シールド側の軸肩外径上限{support["shieldedShaftShoulderMaximumMm"]:g} mmを超えるため、この組合せには使いません。
        小売の「ISC 686ZZ」とメーカー表の686AZZ1の同一性も未確定です。</p>
        <p>NSK 626ZZ＋IWATA SC0607CB2は別の資料照合候補にとどまります。19 mm座への変更、現物の当たり面、増量・抵抗・価格が残り、今回の計算へは代入していません。</p>
        <a href="#shared-interface">当たり面の寸法図と調達の残留点を見る →</a>
      </section>
      <section id="procurement-{ident}" class="calculation-topic"><h3>⑤ 調達：1台2万円は、まだ合格していない。</h3>
        <p>材料費の条件は1台{comparison["requirements"]["materialsBudgetJpyPerMachine"]:,}円、送料は別です。
        旧部分見積のA/C 11,816円・B 13,296円は、新しいロッド追加部、歯車、支持部の変更をすべて含む完成BOMではありません。
        ねじ・シム・材料・輸入税・配送なども未確定です。</p>
        <p>現時点で新しい完成機の購入リスト・印刷部品一式・組立経路は提供していません。風速計や測定器の購入を新たな前提にはせず、ここにない測定値を埋めて合格にもしません。</p>
        <div class="document-strip"><a href="{url(BASE+f"candidate_{ident}.json", source)}">{ident}案の正規計算JSON</a>
        <a href="{url(BASE+"torque_decomposition.csv", source, True)}">全案・全抵抗ケースの内訳CSV</a>
        <a href="{url(BASE+"DESIGN_GATE_ja.md", source)}">設計ゲートと出典の原文</a></div>
      </section></div></details>'''


def build_calculations(output):
    source, manifest, figures, comparison, candidates, decomposition = read_study()
    copies = [record["file"] for record in figures.values()] + [
        BASE + name for name in ("comparison.json", "comparison.csv", "torque_decomposition.csv", "manifest.json")]
    assets = {}
    for original in copies:
        name = asset_name(original)
        destination = output / name
        shutil.copyfile(safe_source(original), destination)
        assets[name] = {"source": original, "source_sha256": digest(safe_source(original)),
                        "sha256": digest(destination), "bytes": destination.stat().st_size,
                        "calculation_revision": source["revisionId"], "unchanged_original": True}
    shared = {f"{{{{calculation_{stem}}}}}": figure(stem, figures[stem], source)
              for stem in ("gait_improvement", "linkage_layout", "bearing_interface")}
    old, new = comparison["boundedSearch"]["originalMetrics"], comparison["boundedSearch"]["selectedMetrics"]
    tolerance = comparison["linkageTolerance"]
    gait_rows = [
        ("上下動 mm", f'{old["body_bounce_mm"]:.3f}', f'{new["body_bounce_mm"]:.3f}', f'最大 {tolerance["maximum_bounce_mm"]:.3f}'),
        ("足上げ最大 mm", f'{old["swing_gap_max_mm"]:.2f}', f'{new["swing_gap_max_mm"]:.2f}', f'最小 {tolerance["minimum_swing_gap_mm"]:.2f} · 8 mm未達'),
        ("切替水平速度係数差 mm/rad", f'{old["horizontal_handoff_jump_mm_per_rad"]:.2f}', f'{new["horizontal_handoff_jump_mm_per_rad"]:.2f}', f'最大 {tolerance["maximum_handoff_rate_jump_mm_per_rad"]:.2f}'),
    ]
    replacements = {
        **shared, "{{calculation_designs}}": "".join(render_design(d, candidates[d], comparison, figures, decomposition, source) for d in "ABC"),
        "{{calculation_gait_table}}": table(["指標", "旧解析R2", "R3名目", "単独±0.1 mm誤差"], gait_rows, "共通リンクの改善と公差感度"),
        "{{calculation_revision}}": source["revisionId"], "{{calculation_input_commit}}": source["inputCommit"],
        "{{calculation_artifact_commit}}": source["artifactCommit"],
        "{{calculation_gate_url}}": url(BASE + "DESIGN_GATE_ja.md", source),
        "{{calculation_manifest_url}}": url(BASE + "manifest.json", source),
        "{{calculation_tolerance_url}}": url(BASE + "linkage_tolerance.json", source),
    }
    return replacements, assets, source
