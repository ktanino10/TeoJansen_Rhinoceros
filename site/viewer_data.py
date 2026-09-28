"""Display-only adapters for existing CAD meshes and documented assembly states."""

from __future__ import annotations

from collections import Counter
import csv
import gzip
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import struct
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/viewer-source.json"
REPOSITORY = "https://github.com/ktanino10/TeoJansen_Rhinoceros"
MAX_MODEL_BYTES = 6_000_000
MAX_DISPLAY_BYTES = 18_000_000
CATEGORIES = {"printed": "印刷品", "purchased": "購入品", "cut_to_length": "購入・切断加工品"}
NAMES = {
    "H_REX_HUB": "REX金属ハブ", "H_608": "608軸受", "H_COLLAR8": "8 mm軸方向カラー",
    "H_COLLAR6": "固定軸カラー", "H_PIVOT_ROD6": "6 mm固定軸", "H_BODY_TIE": "本体タイロッド",
    "H_CASE_TIE_LEFT": "左ケースロッド", "H_CASE_TIE_RIGHT": "右ケースロッド",
    "H_PULLEY24": "24T購入プーリー", "H_PULLEY48": "48T購入プーリー", "H_BELT520": "HTD5M購入ベルト",
    "P_CRANK_CHEEK": "共有クランク頬板", "P_BEARING_RETAINER": "軸受外輪押さえ",
    "P_FRAME_LEFT": "主左フレーム", "P_FRAME_RIGHT": "主右フレーム", "P_FRAME_CORE": "中間フレーム",
    "P_FRAME_FRONT_LEFT": "左前側キャリア", "P_FRAME_FRONT_RIGHT": "右前側キャリア",
    "P_INPUT_CARRIAGE_LOC": "入力軸受キャリッジ・位置決め", "P_INPUT_CARRIAGE_FLOAT": "入力軸受キャリッジ・逃がし",
    "P_ROTOR_CORE": "風車端板", "P_ROTOR_CORE_R": "風車反対端板",
    "P_ROTOR_YOKE": "風車一体フォーク", "P_ROTOR_YOKE_R": "風車反対端フォーク", "P_ROTOR_CUP": "風車カップ",
    "P_SHOE": "可動靴", "S_SOLE": "交換式足裏", "H_SOLE_STRAP": "足裏保持タイ",
    "Q_BEARING_FIT": "軸受フィット試験片", "Q_JOINT_FIT": "関節フィット試験片",
}


def part_name(ident: str) -> str:
    if ident in NAMES:
        return NAMES[ident]
    if ident.startswith("L_"):
        return f"脚リンク {ident[2:]}" + ("（鏡映）" if ident.endswith("_R") else "")
    for prefix, label in (
        ("H_shaft_", "REX軸"), ("H_bolt_", "六角穴付きボルト"), ("H_button_", "ボタン頭ボルト"),
        ("H_countersunk_", "皿頭ボルト"), ("H_endwasher_", "軸端止め座金"), ("H_washer_", "座金"),
        ("H_locknut_", "緩み止めナット"), ("H_nut_", "六角ナット"), ("H_inner_spacer_", "内輪専用スペーサ"),
        ("H_crank_sleeve_", "共有クランク金属スリーブ"), ("H_pivot_sleeve_", "固定軸スリーブ"),
        ("H_sleeve_", "関節金属スリーブ"), ("H_tie_tube_", "タイロッド用チューブ"),
        ("P_GUARD_", "段別ガード"), ("S_WINDOW_", "段別PETG窓"),
    ):
        if ident.startswith(prefix):
            return f"{label} · {ident[len(prefix):].replace('p', '.')}"
    if re.fullmatch(r"P_S\d_(PINION|WHEEL)", ident):
        _, stage, kind = ident.split("_")
        return f"{stage} " + ("小歯車" if kind == "PINION" else "大歯車")
    raise ValueError(f"Add a reviewed part label for {ident}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_url(path: str, source: dict, raw: bool = False) -> str:
    if not (ROOT / path).exists():
        raise ValueError(f"Missing viewer reference: {path}")
    route = "raw" if raw else ("tree" if (ROOT / path).is_dir() else "blob")
    return f"{REPOSITORY}/{route}/{source['canonicalCommit']}/{quote(path, safe='/')}"


def read_source() -> dict:
    source = json.loads(SOURCE.read_text())
    if source["schemaVersion"] != 1 or source["adapter"] != "first-cut-assembly-v1":
        raise ValueError("Unsupported display adapter; integrate the new engineering revision explicitly")
    if not re.fullmatch(r"[0-9a-f]{40}", source["canonicalCommit"]):
        raise ValueError("Viewer source must name an immutable canonical commit")
    for path, expected in source["sourceHashes"].items():
        if digest(ROOT / path) != expected:
            raise ValueError(f"Engineering revision changed: {path}. Update the complete reviewed source contract, not individual old/new assets.")
    return source


def read_inputs(ident: str) -> tuple[dict, dict, dict, dict]:
    manifest = json.loads((ROOT / f"docs/ver3/assembly_{ident}.json").read_text())
    if manifest["id"] != ident or manifest["units"] != "mm":
        raise ValueError(f"{ident}: expected canonical millimetre assembly")
    library = json.loads(gzip.decompress((ROOT / manifest["cad_meshes"]).read_bytes()))
    with (ROOT / f"docs/ver3/BOM_{ident}.csv").open(newline="") as file:
        bom = {row["part_id"]: row for row in csv.DictReader(file)}
    access = json.loads((ROOT / f"docs/ver3/assembly_access_{ident}.json").read_text())
    if set(library) != set(manifest["parts"]) or set(bom) != set(library):
        raise ValueError(f"{ident}: CAD meshes, part definitions and BOM differ")
    names = [item["name"] for item in manifest["instances"]]
    if len(names) != len(set(names)):
        raise ValueError(f"{ident}: duplicate canonical instance ID")
    counts = Counter(item["part_id"] for item in manifest["instances"])
    if not set(counts) <= set(library):
        raise ValueError(f"{ident}: instances reference missing part definitions")
    for part, definition in manifest["parts"].items():
        if int(bom[part]["quantity"]) != counts[part]:
            raise ValueError(f"{ident}: BOM instance count differs for {part}")
        if definition["category"] != library[part]["category"] or definition["category"] != bom[part]["category"]:
            raise ValueError(f"{ident}: category differs for {part}")
        if not counts[part] and part not in {"Q_BEARING_FIT", "Q_JOINT_FIT"}:
            raise ValueError(f"{ident}: unrepresented non-coupon part {part}")
    return manifest, library, bom, access


def bounds(vertices: list) -> list[list[float]]:
    return [[min(v[axis] for v in vertices) for axis in range(3)],
            [max(v[axis] for v in vertices) for axis in range(3)]]


def transform(point: list, matrix: list) -> list[float]:
    return [sum(matrix[row][col] * point[col] for col in range(3)) + matrix[row][3] for row in range(3)]


def export_glb(manifest: dict, library: dict, destination: Path, source: dict, *,
               coupon_ids=("Q_BEARING_FIT", "Q_JOINT_FIT"), max_model_bytes=MAX_MODEL_BYTES) -> dict:
    binary = bytearray()
    views, accessors, meshes = [], [], []
    geometry_stats, mesh_indices = {}, {}

    def add_accessor(values, components, component_type, target, value_bounds=None):
        flat = [component for value in values for component in value]
        code = "f" if component_type == 5126 else "I"
        payload = struct.pack(f"<{len(flat)}{code}", *flat)
        while len(binary) % 4:
            binary.append(0)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload), "target": target})
        binary.extend(payload)
        accessor = {"bufferView": len(views) - 1, "componentType": component_type,
                    "count": len(flat) // components, "type": "VEC3" if components == 3 else "SCALAR"}
        if value_bounds:
            accessor.update(min=value_bounds[0], max=value_bounds[1])
        accessors.append(accessor)
        return len(accessors) - 1

    for part, geometry in library.items():
        vertices, triangles = geometry["vertices"], geometry["triangles"]
        if not vertices or not triangles or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in vertices):
            raise ValueError(f"Invalid exact CAD mesh: {part}")
        if any(len(t) != 3 or any(not isinstance(i, int) or not 0 <= i < len(vertices) for i in t) for t in triangles):
            raise ValueError(f"Invalid CAD triangle indices: {part}")
        metres = [[coordinate * 0.001 for coordinate in vertex] for vertex in vertices]
        positions = add_accessor(metres, 3, 5126, 34962, bounds(metres))
        indices = add_accessor(triangles, 1, 5125, 34963)
        mesh_indices[part] = len(meshes)
        meshes.append({"name": part, "primitives": [{"attributes": {"POSITION": positions}, "indices": indices}],
                       "extras": {"partId": part, "category": geometry["category"]}})
        geometry_stats[part] = {"vertices": len(vertices), "triangles": len(triangles), "boundsMm": bounds(vertices)}
    nodes = []
    world_min, world_max = [math.inf] * 3, [-math.inf] * 3
    for item in manifest["instances"]:
        matrix = item["transform"]
        if len(matrix) != 4 or any(len(row) != 4 for row in matrix) or matrix[3] != [0, 0, 0, 1]:
            raise ValueError(f"Invalid row-major transform: {item['name']}")
        converted = [[matrix[row][col] * (0.001 if col == 3 and row < 3 else 1)
                      for col in range(4)] for row in range(4)]
        nodes.append({"name": item["name"], "mesh": mesh_indices[item["part_id"]],
                      "matrix": [converted[row][col] for col in range(4) for row in range(4)],
                      "extras": {"instanceId": item["name"], "partId": item["part_id"], "group": item["group"],
                                 "category": manifest["parts"][item["part_id"]]["category"], "role": "assembly"}})
        for vertex in library[item["part_id"]]["vertices"]:
            point = transform(vertex, matrix)
            for axis in range(3):
                world_min[axis] = min(world_min[axis], point[axis])
                world_max[axis] = max(world_max[axis], point[axis])
    assembly_nodes = list(range(len(nodes)))
    coupons = []
    for index, part in enumerate(coupon_ids):
        coupons.append(len(nodes))
        nodes.append({"name": f"specimen-{part}", "mesh": mesh_indices[part],
                      "translation": [index * 0.10, 0, 0],
                      "extras": {"partId": part, "category": "printed", "role": "coupon",
                                 "note": "Display layout only; canonical assembly quantity is zero."}})
    root_index = len(nodes)
    nodes.append({"name": "CAD millimetres converted to metres; Z-up to Y-up",
                  "rotation": [-math.sqrt(0.5), 0, 0, math.sqrt(0.5)],
                  "children": assembly_nodes + coupons})
    document = {"asset": {"version": "2.0", "generator": "Rhinoceros display-only exact-mesh adapter",
                          "extras": {"revision": source["revisionId"], "sourceCommit": source["canonicalCommit"],
                                     "units": "metres", "sourceUnits": "mm", "simplifiedByAdapter": False}},
                "scene": 0, "scenes": [{"nodes": [root_index]}], "nodes": nodes, "meshes": meshes,
                "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(binary)}]}
    encoded = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary.extend(b"\0" * (-len(binary) % 4))
    result = (struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
              + struct.pack("<I4s", len(encoded), b"JSON") + encoded
              + struct.pack("<I4s", len(binary), b"BIN\0") + binary)
    if len(result) > max_model_bytes:
        raise ValueError(f"{manifest['id']}: display model exceeded its {max_model_bytes} byte opt-in budget")
    destination.write_bytes(result)
    return {"parts": geometry_stats, "instanceCount": len(assembly_nodes),
            "boundsMm": [world_min, world_max], "bytes": len(result),
            "sha256": hashlib.sha256(result).hexdigest(), "couponPreviewCount": len(coupon_ids)}


def instructions() -> dict:
    text = (ROOT / "docs/ver3/ASSEMBLY_ja.md").read_text()
    section = text.split("## 番号付き組立順\n", 1)[1].split("\n## 共有クランク", 1)[0]
    records = re.findall(r"(?ms)^(\d+)\. \*\*(.*?)\*\* (.*?)(?=^\d+\. |\Z)", section)
    if [int(row[0]) for row in records] != list(range(1, 15)):
        raise ValueError("The documented 14-step assembly contract changed")
    return {int(number): {"title": title, "body": body.strip().replace("**", "").replace("`", "")}
            for number, title, body in records}


def make_guide(manifest: dict, access: dict) -> dict:
    ident, items = manifest["id"], manifest["instances"]
    named = {item["name"]: item for item in items}
    all_ids = set(named)
    reference = instructions()
    steps, assigned = [], set()

    def add(number, suffix, operation, members=(), *, hidden=(), preview=(), coupons=(), view="isometric",
            tools="2.5 / 3 mm六角棒レンチ・5.5 / 7 mm小型スパナ（実購入品で照合）", arrow=None):
        ids = [item["name"] if isinstance(item, dict) else item for item in members]
        if set(ids) & assigned or len(ids) != len(set(ids)) or not set(ids) <= all_ids:
            raise ValueError(f"{ident}: duplicate or unknown step assignment at {number}{suffix}")
        assigned.update(ids)
        text = reference.get(number, {"title": "部品を表示する前の状態", "body": ""})
        steps.append({"id": f"{number}{suffix}", "referenceStep": number, "title": text["title"],
                      "operation": operation, "cautions": text["body"], "tools": tools,
                      "add": ids, "hidden": sorted(set(hidden)), "preview": list(preview), "coupons": list(coupons),
                      "view": view, "arrow": arrow})

    add(0, "", "未配置です。次へ進むと、本体に組み込まないフィット試験片から確認します。", tools="まだ使用しません")
    add(1, "", "試験片二種類の実CAD形状です。本体の正規組立数量は0。表示用に横へ並べたもので、新しい機構部品ではありません。",
        coupons=["Q_BEARING_FIT", "Q_JOINT_FIT"], tools="ノギス、実購入の軸受・軸・ブッシュ", view="top")
    prepared = [i["name"] for i in items if i["part_id"].startswith(("H_shaft_", "H_sleeve_", "H_pivot_sleeve_",
                 "H_crank_sleeve_", "H_inner_spacer_", "H_tie_tube_")) or i["part_id"] in
                {"H_PIVOT_ROD6", "H_BODY_TIE", "H_CASE_TIE_LEFT", "H_CASE_TIE_RIGHT"}]
    add(2, "", "仕分け対象を完成位置で強調しています。まだ組み付け済みではありません。切断長さ・数量は部品表を参照し、実材料・工具の適合を確認します。",
        preview=prepared, tools="ノギス・切断／端面仕上げ／M4端部加工の適切な設備（原典の事前条件）")

    first_body = next(n for n, item in enumerate(items) if item["part_id"] == "H_PIVOT_ROD6")
    frame_items = items[:first_body]
    carriage, regular = [], []
    in_carriage = False
    for item in frame_items:
        if item["part_id"].startswith("P_FRAME_") or (item["part_id"] == "H_608" and item.get("axis") != "I"):
            in_carriage = False
        if item["part_id"].startswith("P_INPUT_CARRIAGE_"):
            in_carriage = True
        (carriage if in_carriage else regular).append(item)
    add(3, "", "各フレームのナット・軸受・外輪押さえを準備。ここでは取り付け先を完成位置で示しますが、主フレームを実際に閉じるのは手順8・9です。",
        regular, view="left", arrow={"instance": "H_608_001", "direction": [1, 0, 0], "label": "左支持への挿入方向（説明）"})
    if ident == "A":
        if len([i for i in carriage if i["part_id"].startswith("P_INPUT_CARRIAGE_")]) != 3:
            raise ValueError("A must have three canonical input carriages")
        add(4, "", "A固有：三つのキャリッジと軸受を準備し、長穴のM4固定は仮止め。張力をまだ確定しません。", carriage, view="left")
    elif carriage:
        raise ValueError(f"{ident}: unexpected input carriage")
    add(5, "", ("A/C固有：端板・一体フォーク・二つのカップを独立したサブアセンブリとして準備。"
                if ident in "AC" else "B固有：小径端板へ二つのカップを直接締結。フォークは使いません。")
        + "この段階の風車は完成位置での参照表示で、軸の組込みは手順9です。",
        [i for i in items if i["group"] == "rotor" and not i["part_id"].startswith("H_shaft_")],
        view="back")
    add(6, "", "六脚を非鏡映／鏡映で分けて準備。_R三角形と金属スリーブの積層を照合し、ねじで樹脂関節を固定しないことを確認します。",
        [i for i in items if i["group"] == "legs"], view="front")
    add(7, "", "三つの共有クランクとREX軸を準備。外側0°／中央180°／外側0°、ハブの対辺基準と反転ハブの90°インデックスを混同しません。",
        [i for i in items if i["group"] == "crank" and i["part_id"] != "H_COLLAR8"])

    tool_checks = [check for check in access["checks"] if check["check"] == "Window screw straight-tool path after carrier-first disassembly"]
    carrier_hidden = set()
    inspections = []
    for index, stage in enumerate(manifest["design"]["stages"]):
        window_items = [i for i in items if i["part_id"] == f"S_WINDOW_{index+1}"]
        window = window_items[0]
        screw_length = stage["window_screw_length_mm"]
        sign = -1 if stage["side"] == "left" else 1
        screw_x = window["transform"][0][3] + sign * 1.5
        screws = [i["name"] for i in items if i["group"] == "guard_lid"
                  and i["part_id"] == f"H_bolt_3_{screw_length}" and abs(i["transform"][0][3] - screw_x) < 0.01]
        checks = [check for check in tool_checks if check["screw"] in screws]
        if len(checks) != 4 or any(not check["passed"] for check in checks):
            raise ValueError(f"{ident}/{stage['id']}: expected four recorded window tool-path checks")
        removed = set(checks[0]["removed_parts"])
        if any(set(check["removed_parts"]) != removed for check in checks):
            raise ValueError("Window screw checks disagree on the partial assembly state")
        if stage["side_index"] == max(s["side_index"] for s in manifest["design"]["stages"] if s["side"] == stage["side"]):
            carrier_hidden.update(removed)
        inspections.append({"id": stage["id"], "title": f"14 · {stage['id']} 窓ねじの工具経路",
                            "hidden": sorted(removed), "highlight": screws, "view": stage["side"],
                            "operation": "入力を止め、回転体を別に支持した部分組立。前側キャリア・軸端止めを外し、同じ側の外段がある場合は窓・歯車・ハブ・ガードも先に外します。",
                            "cautions": checks[0]["assembly_state"], "tool": checks[0]["tool"],
                            "arrow": {"instance": screws[0], "direction": [-sign, 0, 0],
                                      "label": "窓ねじへ工具を入れる方向（記録済み部分組立）"}})
    if not carrier_hidden <= all_ids:
        raise ValueError("Access check references unknown instance IDs")
    first_crank = next(n for n, item in enumerate(items) if item["part_id"] == "P_CRANK_CHEEK")
    body = items[first_body:first_crank]
    add(8, "", "主左フレームから一湾ずつ、対向二脚と共有クランク、中間フレームの順に閉じます。準備済み部品は完成位置で淡色表示。32 mmハブを8 mm軸受穴へ通す説明ではありません。",
        body + [i for i in items if i["group"] == "pivot"], hidden=carrier_hidden,
        arrow={"instance": "P_FRAME_CORE_001", "direction": [-1, 0, 0],
               "label": "次のフレームを自由端側から戻す方向（説明）"})
    add(9, "", "風車・連絡軸を入れて最後の主フレームを閉じます。BはM2もあります。前側キャリアは窓ねじの操作のため外した状態を保ちます。",
        [i for i in items if i["part_id"].startswith("H_shaft_") and i["group"] in {"rotor", "drivetrain"}],
        hidden=carrier_hidden, tools="芯出し棒・ノギス・該当六角棒レンチ")
    add(10, "", "靴のピッチ関節を金属スリーブで支え、交換足裏を二本のタイで保持します。BのCEF軸方向位置・スペーサはA/Cと異なります。",
        [i for i in items if i["group"] == "feet"], hidden=carrier_hidden, view="front")

    case_start = next(n for n, item in enumerate(items) if item["part_id"] == "H_CASE_TIE_LEFT")
    case_items = items[case_start:]
    if any(item["group"] not in {"frame", "hardware"} or not (
            item["part_id"].startswith(("H_CASE_TIE_", "H_tie_tube_"))
            or item["part_id"] in {"H_washer_4_0p8", "H_locknut_4"}) for item in case_items):
        raise ValueError(f"{ident}: missing assembly-stage mapping for unrecognized case members")
    add(11, "-case", "左右ケースのロッドと指定チューブを準備。ガード背板・段・窓を主フレーム側から外側へ積み重ねます。前側キャリアはまだ戻しません。",
        case_items, hidden=carrier_hidden)
    starts = []
    for stage in manifest["design"]["stages"]:
        marker = "H_PULLEY24" if stage["type"] == "belt" else f"P_{stage['id']}_PINION"
        starts.append(next(n for n, item in enumerate(items) if item["part_id"] == marker))
    delayed_window = []
    for index, stage in enumerate(manifest["design"]["stages"]):
        block = items[starts[index]:starts[index+1] if index+1 < len(starts) else case_start]
        windows = [item for item in block if item["group"] == "guard_lid"]
        drive = [item for item in block if item["group"] != "guard_lid" and item["part_id"] != "H_BELT520"]
        withdrawal = next(check for check in access["checks"] if check["check"] == f"{stage['id']} gear/pulley and hub withdrawal")
        arrow = {"instance": withdrawal["moving"][0], "direction": [-withdrawal["direction"], 0, 0],
                 "label": "組付け側への方向（原典は逆方向の取外しを標本確認）"}
        add(11, f"-{stage['id']}", f"{stage['side']}側 {stage['id']}："
            + ("プーリーとハブはケース外で先に締結。ベルトは手順12で装着します。" if stage["type"] == "belt"
               else "歯車とハブはケース外で先に締結。背板を準備し、段を軸に取り付けます。")
            + (" B右側はS1窓を先に完成させ、後からS3を取り付けます。" if ident == "B" else ""),
            drive, hidden=carrier_hidden, view=stage["side"], arrow=arrow)
        if stage["type"] == "belt":
            delayed_window = windows
        else:
            add(11, f"-{stage['id']}-window", f"{stage['id']}の窓を締結。前側キャリアを先に閉じて工具経路を塞がないでください。",
                windows, hidden=carrier_hidden, view=stage["side"],
                arrow={"instance": windows[0]["name"], "direction": [1 if stage["side"] == "left" else -1, 0, 0],
                       "label": "窓を段へ戻す方向（説明）"})
    if ident == "A":
        add(12, "-belt", "520×9 mmベルトを装着。前側キャリアを仮組みして三つのキャリッジの芯・張力を合わせた後、ユニットごと再び外して窓を締めます。10 N/スパンは計算仮定です。",
            [i for i in items if i["part_id"] == "H_BELT520"], hidden=carrier_hidden, view="left",
            tools="芯出し棒・2.5 / 3 mm六角棒レンチ")
        add(12, "-window", "設定を保ったキャリアを外した状態でS1窓を締結。13 mm軸穴、M3×40、キャリッジねじ用8.4 mm追加孔を図面と照合します。",
            delayed_window, hidden=carrier_hidden, view="left")
    retaining = [i for i in items if i["name"] not in assigned and
                 (i["part_id"].startswith(("H_inner_spacer_", "H_endwasher_", "H_button_")) or i["part_id"] == "H_COLLAR8")]
    add(13, "", "位置決め側の内輪スペーサ・カラー・軸端止めを調整。窓を締めた後に前側キャリアを戻し、最後に軸端止め・ケース固定を完成します。全周手回しや実機試験は未実施です。",
        retaining, tools="ノギス・シム／すきまゲージ・メーカー指定の締付工具")
    if assigned != all_ids:
        raise ValueError(f"{ident}: missing assembly-stage mapping: {sorted(all_ids-assigned)}")
    for step in steps:
        if not set(step["hidden"]) <= all_ids or not set(step["preview"]) <= all_ids:
            raise ValueError(f"{ident}: invalid stage visibility IDs")
        if step["arrow"] and step["arrow"]["instance"] not in all_ids:
            raise ValueError(f"{ident}: invalid insertion-arrow reference")
    return {"steps": steps, "completeStep": len(steps)-1, "inspections": inspections,
            "disassembly": reference[14], "mapping": "Prepared subassemblies shown at final reference positions; not a motion/path simulation."}


def build_viewer(output: Path) -> tuple[dict, dict, dict]:
    source = read_source()
    guides, assets, entries = {}, {}, {}
    for ident in "ABC":
        manifest, library, bom, access = read_inputs(ident)
        model_path = output / "assets" / f"ver3-{ident}.glb"
        model = export_glb(manifest, library, model_path, source)
        guide = make_guide(manifest, access)
        guide.update(schemaVersion=1, design=ident, revision=source, model=model,
                     modelUrl=f"assets/ver3-{ident}.glb",
                     parts={part: {"name": part_name(part), "category": data["category"],
                                   "description": data["description"], "quantity": int(bom[part]["quantity"]),
                                   "vertices": model["parts"][part]["vertices"], "triangles": model["parts"][part]["triangles"]}
                            for part, data in manifest["parts"].items()},
                     instances={item["name"]: {"partId": item["part_id"], "group": item["group"]}
                                for item in manifest["instances"]},
                     links={key: source_url(path, source, raw) for key, path, raw in [
                         ("assembly", "docs/ver3/ASSEMBLY_ja.md", False),
                         ("bom", f"docs/ver3/BOM_{ident}.csv", True),
                         ("access", f"docs/ver3/assembly_access_{ident}.json", False),
                         ("canonical", f"docs/ver3/assembly_{ident}.json", False),
                         ("cad", f"FreeCAD/Ver.3/{ident}/Ver3_{ident}.step", True),
                         ("stl", f"STL/Ver.3/{ident}", False),
                         ("section", f"docs/ver3/drawings/crank_section_{ident}.svg", False)]},
                     limitations=manifest["limitations"])
        filename = f"assets/assembly-{ident}.json"
        (output / filename).write_text(json.dumps(guide, ensure_ascii=False, separators=(",", ":")) + "\n")
        guides[ident] = guide
        entries[ident] = {"guideUrl": filename, "modelUrl": guide["modelUrl"], "bytes": model["bytes"],
                          "instances": model["instanceCount"], "parts": len(guide["parts"])}
        for name, original in ((f"assets/ver3-{ident}.glb", manifest["cad_meshes"]),
                               (filename, f"docs/ver3/assembly_{ident}.json")):
            path = output / name
            assets[name] = {"source": original, "source_sha256": digest(ROOT / original),
                            "sha256": digest(path), "bytes": path.stat().st_size, "loading": "on-demand",
                            "engineering_revision": source["revisionId"]}
    index = {"schemaVersion": 1, "revision": source, "designs": entries}
    (output / "assets/viewer-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")
    path = output / "assets/viewer-index.json"
    assets["assets/viewer-index.json"] = {"source": "site/viewer-source.json", "source_sha256": digest(SOURCE),
                                        "sha256": digest(path), "bytes": path.stat().st_size, "loading": "on-demand"}
    if sum(item["bytes"] for item in assets.values()) > MAX_DISPLAY_BYTES:
        raise ValueError("All opt-in 3D data exceeded the 18 MB display budget")
    return guides, assets, source


def static_guides(guides: dict, source: dict) -> str:
    result = []
    for ident, guide in guides.items():
        parts = guide["parts"]
        rows = []
        for step in guide["steps"][1:]:
            quantities = Counter(guide["instances"][name]["partId"] for name in step["add"] or step["preview"])
            for part in step["coupons"]:
                quantities[part] = 0
            items = "".join(f"<tr><th scope=\"row\">{escape(part)}<small>{escape(parts[part]['name'])}</small></th>"
                            f"<td>{quantity}</td><td>{CATEGORIES[parts[part]['category']]}</td></tr>"
                            for part, quantity in sorted(quantities.items()))
            table = (f'<details class="step-bom"><summary>今回の部品ID・数量・区分（{len(quantities)}種類）</summary>'
                     '<p class="small-note">準備・仕分けは組付け済み数量ではありません。試験片は本体数量0です。</p>'
                     '<table><thead><tr><th scope="col">部品ID・名称</th><th scope="col">数量</th><th scope="col">区分</th></tr></thead>'
                     f'<tbody>{items}</tbody></table></details>') if quantities else ""
            rows.append(f'<article class="static-step" id="guide-{ident}-{step["id"]}">'
                        f'<h4>{step["id"]} · {escape(step["title"])}</h4><p>{escape(step["operation"])}</p>'
                        f'<p class="small-note">工具：{escape(step["tools"])}</p>{table}'
                        f'<details><summary>向き・締結・順序の注意（原典手順{step["referenceStep"]}）</summary>'
                        f'<p>{escape(step["cautions"])}</p></details></article>')
        rows.append(f'<article class="static-step"><h4>14 · {escape(guide["disassembly"]["title"])}</h4>'
                    f'<p>{escape(guide["disassembly"]["body"])}</p></article>')
        result.append(f'<section class="static-guide" id="guide-{ident}" aria-labelledby="guide-{ident}-title">'
                      f'<h3 id="guide-{ident}-title">Ver.3 {ident}案 · 具体的な組立手順</h3>'
                      f'<p>正規組立{guide["model"]["instanceCount"]}点。部品定義{len(parts)}種類には、本体数量0の試験片2種類を含みます。'
                      '表示上の準備と実物への組付けは区別してください。</p>'
                      f'<div class="document-strip"><a href="{guide["links"]["bom"]}">{ident}の正本BOM CSV</a>'
                      f'<a href="{guide["links"]["access"]}">{ident}の装着経路と部分組立前提</a>'
                      f'<a href="{guide["links"]["section"]}">{ident}の実CAD断面</a></div>'
                      + "".join(rows) + "</section>")
    return "\n".join(result)
