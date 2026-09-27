"""Draw the actual cartridge mesh and seal/verify its separate release contract."""

import argparse
import csv
import gzip
import html
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import trimesh

from input_cartridge import CAD, INPUT, OUT, PRINT, ROOT, cost, load, sha, stack_contract, write_json

COLORS = {
    "P_CARRIER": "#4876a0", "P_CAP": "#d9a24d", "P_FLANGE": "#59b493",
    "H_HUB": "#aebcca", "H_SHAFT": "#c3cad1", "H_COLLAR": "#8695a4",
    "H_BEARING": "#667b90", "H_SPACER": "#c4b07c",
}


def txt(x, y, value, size=15, color="#e0e9f3"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="sans-serif" font-size="{size}">{html.escape(str(value))}</text>'


def svg(path, body, width=1200, height=850):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                    f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#111925"/>'
                    + "".join(body)+"</svg>\n")


def world_meshes(manifest):
    with gzip.open(ROOT/manifest["cad_meshes"], "rt") as stream:
        library = json.load(stream)
    result = []
    for item in manifest["instances"]:
        mesh = library[item["part_id"]]
        matrix = np.array(item["transform"])
        vertices = np.array(mesh["vertices"])@matrix[:3, :3].T+matrix[:3, 3]
        result.append({**item, "vertices": vertices, "triangles": np.array(mesh["triangles"])})
    return result


def hex_rgb(value):
    return np.array([int(value[i:i+2], 16) for i in (1, 3, 5)])


def preview(path, manifest, meshes, exploded=False):
    direction = np.array([100.0, -210.0, 126.0])
    direction /= np.linalg.norm(direction)
    horizontal = np.cross([0, 0, 1], direction)
    horizontal /= np.linalg.norm(horizontal)
    vertical = np.cross(direction, horizontal)
    records = []
    for item in meshes:
        points = item["vertices"].copy()
        if exploded:
            if item["name"] == "SHAFT":
                points[:, 0] -= 124
            elif item["group"] == "flange_unit":
                points[:, 2] += 50
            elif item["group"] == "locating_rotating":
                points[:, 1] -= 48
        projected = np.column_stack([points@horizontal, points@vertical, points@direction])
        records.append((item, points, projected))
    cloud = np.vstack([p for _, _, p in records])
    bounds = np.array([cloud[:, :2].min(axis=0), cloud[:, :2].max(axis=0)])
    scale = min(1080/(bounds[1, 0]-bounds[0, 0]), 490/(bounds[1, 1]-bounds[0, 1]))
    offset = np.array([600, 365])
    center = bounds.mean(axis=0)
    faces = []
    for item, points, projected in records:
        rgb = hex_rgb(COLORS.get(item["part_id"], "#c1c5cc"))
        for tri in item["triangles"]:
            vertices = points[tri]
            normal = np.cross(vertices[1]-vertices[0], vertices[2]-vertices[0])
            length = np.linalg.norm(normal)
            if length < 1e-12:
                continue
            normal /= length
            facing = float(normal@direction)
            if facing <= 0:
                continue
            shade = 0.45+0.5*facing
            color = "rgb("+",".join(str(int(v*shade)) for v in rgb)+")"
            xy = (projected[tri, :2]-center)*[scale, -scale]+offset
            polygon = " ".join(f"{x:.2f},{y:.2f}" for x, y in xy)
            faces.append((float(projected[tri, 2].mean()),
                          f'<polygon points="{polygon}" fill="{color}" stroke="{color}" stroke-width="0.3"/>'))
    summary = json.loads((OUT/"cad_validation.json").read_text())
    body = [txt(40, 38, "共通入力カートリッジ / "+("脱着順序の説明配置" if exploded else "実CAD由来の形状"), 23),
            txt(40, 66, manifest["revisionId"]+" / 購入部は寸法モデル。実測・低抵抗認証・風力完成機ではありません。", 15, "#f3c471")]
    body += [drawing for _, drawing in sorted(faces)]
    labels = [("キャリア", "#4876a0"), ("外輪押さえ", "#d9a24d"),
              ("試験フランジ", "#59b493"), ("購入D軸・ハブ・軸受", "#bac5d0")]
    for i, (label, color) in enumerate(labels):
        body += [f'<rect x="{45+i*285}" y="664" width="16" height="16" fill="{color}"/>',
                 txt(69+i*285, 678, label, 16)]
    body += [txt(40, 725, f'36組立インスタンス / 印刷4個 / 名目 {summary["totalNominalMassG"]:.2f}g '
                 f'= CAD印刷体積 {summary["printedSolidMassG"]:.2f}g + 購入カタログ {summary["purchasedCatalogueMassG"]:.2f}g', 16),
             txt(40, 754, "固定側の前後2カラー + 4mm鋼スペーサー2個。右外輪は軸方向に浮動。切断・端面タップなし。", 15)]
    body.append(txt(40, 787, "脱着：クランプ解放→軸を-Xへ→ハブ/フランジを+Zへ。各部品の同時移動や貫通を意味しない。" if exploded
                    else "試験片は本体数量0。支持台への固定、実はめあい、締付後のすきま/始動抵抗は現物確認が必要。", 14))
    svg(path, body)


def clip_segment(a, b, low, high):
    delta = b-a
    first, last = 0.0, 1.0
    for dim in range(2):
        if abs(delta[dim]) < 1e-12:
            if not low[dim] <= a[dim] <= high[dim]:
                return None
        else:
            begin, end = sorted(((low[dim]-a[dim])/delta[dim], (high[dim]-a[dim])/delta[dim]))
            first, last = max(first, begin), min(last, end)
    return None if first > last else (a+first*delta, a+last*delta)


def mesh_section_segments(meshes, xmin, xmax, zmin, zmax):
    segments = []
    for item in meshes:
        points = item["vertices"]
        for face in item["triangles"]:
            tri = points[face]
            if tri[:, 1].min() > 1e-9 or tri[:, 1].max() < -1e-9:
                continue
            hits = []
            for first, last in zip(tri, np.roll(tri, -1, axis=0)):
                if abs(first[1]) < 1e-9:
                    hits.append(first[[0, 2]])
                if first[1]*last[1] < 0:
                    t = -first[1]/(last[1]-first[1])
                    hits.append((first+t*(last-first))[[0, 2]])
            if len(hits) < 2:
                continue
            pair = np.unique(np.round(hits, 7), axis=0)
            if len(pair) != 2:
                continue
            a, b = pair
            clipped = clip_segment(a, b, (xmin, zmin), (xmax, zmax))
            if clipped is not None:
                segments.append((item["part_id"], *clipped))
    return segments


def section_drawing(path, manifest, meshes):
    body = [txt(35, 37, "固定／浮動側の実CAD断面・荷重経路", 24),
            txt(35, 66, manifest["revisionId"]+" / X-Z断面（Y=0）。寸法は名目。購入部内部は説明用簡略形状。", 15, "#f3c471")]
    panels = [(0, 40, 45, 210, 12, "固定側：内輪と外輪の保持経路を分離"),
              (86, 106, 700, 210, 15, "浮動側：外輪フランジの長い溝")]
    for xmin, xmax, x0, y0, scale, title in panels:
        body.append(txt(x0, 115, title, 18))
        for pid, a, b in mesh_section_segments(meshes, xmin, xmax, 14, 42):
            x1, y1 = x0+(a[0]-xmin)*scale, y0+(40-a[1])*scale
            x2, y2 = x0+(b[0]-xmin)*scale, y0+(40-b[1])*scale
            body.append(f'<path d="M{x1:.3f} {y1:.3f}L{x2:.3f} {y2:.3f}" fill="none" '
                        f'stroke="{COLORS.get(pid, "#a3acb5")}" stroke-width="1.4"/>')
        axis_y = y0+10*scale
        body.append(f'<path d="M{x0} {axis_y}h{(xmax-xmin)*scale}" stroke="#8193a5" stroke-dasharray="4 4"/>')
    body += [txt(45, 595, "左：外輪溝1.30mm − フランジ1.00mm = 0.30mm", 16),
             txt(45, 623, "内輪：4mmスペーサー＋軸受5mm＋4mmスペーサー", 16),
             txt(45, 651, "カラーの向かい合うボス面間13.20mm → 全すきま0.20mm", 15),
             txt(700, 595, "右：外輪溝3.00mm − フランジ1.00mm", 16),
             txt(700, 623, "全2.00mm（名目±1.00mm）を逃がす", 16),
             txt(700, 651, "右側にカラーを追加して締め込まない", 15),
             txt(40, 700, "キャップは軸受面でなくキャリア両脇の受け面に着座。締付けで意図的な軸受予圧を作らない。", 16),
             txt(40, 730, "寸法受入シナリオ：左すきま最小0.10mm、浮動の残余0.05mm。これは実公差保証ではない。", 15),
             txt(40, 758, "締付後のキャップ沈み/変形が0.05mmを超える場合、想定を満たさず再調整・再設計。過締めで解決しない。", 14),
             txt(40, 790, "断面の縮尺：左12px/mm、右15px/mm。0.3mm/0.2mmの隙間を大きく描き替えてはいない。", 14)]
    svg(path, body)


def validate_meshes(manifest):
    rows = []
    for pid, part in manifest["parts"].items():
        if part["category"] != "printed":
            continue
        path = PRINT/(pid+".stl")
        mesh = trimesh.load(path, force="mesh")
        relative = abs(mesh.volume-part["solid_volume_mm3"])/part["solid_volume_mm3"]
        if not mesh.is_volume or len(mesh.split()) != 1 or relative > 0.01:
            raise RuntimeError(f"Invalid or inaccurate printed STL: {pid}")
        if np.any(mesh.extents > 230) or abs(mesh.bounds[0, 2]) > 1e-5:
            raise RuntimeError(f"Print pose/envelope problem: {pid}")
        rows.append({"partId": pid, "singleClosedSolid": True, "extentsMm": mesh.extents.tolist(),
                     "meshToBrepVolumeRelativeError": float(relative),
                     "assemblyQuantity": sum(r["part_id"] == pid for r in manifest["instances"])})
    return rows


def seal():
    cfg = load()
    manifest = json.loads((OUT/"assembly.json").read_text())
    meshes = world_meshes(manifest)
    preview(OUT/"cad_preview.svg", manifest, meshes)
    preview(OUT/"removal_sequence.svg", manifest, meshes, exploded=True)
    section_drawing(OUT/"bearing_sections.svg", manifest, meshes)
    write_json(OUT/"stl_validation.json", validate_meshes(manifest))
    sources = [INPUT, Path(__file__), Path(__file__).with_name("build_input_cartridge.py"),
               Path(__file__).with_name("input_cartridge.py"), Path(__file__).with_name("test_input_cartridge.py"),
               Path(__file__).with_name("cad_parts.py"), Path(__file__).with_name("core.py"),
               Path(__file__).with_name("design.json"), Path(__file__).with_name("beam.py")]
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    contained = True
    for p in sources:
        result = subprocess.run(["git", "show", f"{commit}:{p.relative_to(ROOT)}"], cwd=ROOT,
                                capture_output=True, check=False)
        contained = contained and result.returncode == 0 and result.stdout == p.read_bytes()
    artifacts = [p for folder in (OUT, CAD, PRINT) for p in sorted(folder.iterdir())
                 if p.is_file() and p.name != "manifest.json"]
    write_json(OUT/"manifest.json", {
        "revisionId": cfg["revisionId"], "sourceCommit": commit, "sourceCommitContainsInputs": contained,
        "sourceHashes": source_hashes, "artifactHashes": {str(p.relative_to(ROOT)): sha(p) for p in artifacts},
        "geometryStatus": "original actual cartridge CAD, purchased dimensional envelopes",
        "cadNative": str((CAD/"CommonInputR4.FCStd").relative_to(ROOT)),
        "cadStep": str((CAD/"CommonInputR4.step").relative_to(ROOT)),
        "assembly": str((OUT/"assembly.json").relative_to(ROOT)), "bom": str((OUT/"BOM.csv").relative_to(ROOT)),
        "access": str((OUT/"assembly_access.json").relative_to(ROOT)),
        "cadMeshes": manifest["cad_meshes"],
        "figures": [{"file": str((OUT/name).relative_to(ROOT)), "revisionId": cfg["revisionId"],
                     "sourceGeometryRevision": cfg["revisionId"], "method": method, "units": "mm",
                     "displayAmplification": 1, "isCartridgeCadGeometry": True, "isWalkingPrototypeGeometry": False,
                     "sourceHashes": {"assembly.json": sha(OUT/"assembly.json"),
                                      "render_geometry.json.gz": sha(CAD/"render_geometry.json.gz")}}
                    for name, method in (("cad_preview.svg", "actual mesh orthographic projection"),
                                         ("removal_sequence.svg", "same mesh in labelled sequential-removal explanation poses"),
                                         ("bearing_sections.svg", "actual triangulated-CAD section, dimensioned nominal stack"))],
        "supplierCadRedistributed": False, "manufacturingRelease": False,
        "qualifiedWalkingPrototypeCount": 0, "measuredStartingTorqueNmm": None,
    })
    verify()


def verify():
    cfg = load()
    manifest = json.loads((OUT/"manifest.json").read_text())
    if manifest["revisionId"] != cfg["revisionId"] or manifest["qualifiedWalkingPrototypeCount"] != 0:
        raise ValueError("Unexpected cartridge revision or walking qualification")
    for relative, expected in {**manifest["sourceHashes"], **manifest["artifactHashes"]}.items():
        path = (ROOT/relative).resolve()
        path.relative_to(ROOT)
        if sha(path) != expected:
            raise ValueError(f"Changed input/artifact: {relative}")
    assembly = json.loads((OUT/"assembly.json").read_text())
    names = [item["name"] for item in assembly["instances"]]
    adds = [name for step in assembly["assemblyStages"] for name in step["add"]]
    if len(names) != 36 or sorted(names) != sorted(adds) or len(set(names)) != len(names):
        raise ValueError("Assembly membership inconsistency")
    for item in assembly["instances"]:
        r = np.array(item["transform"])[:3, :3]
        if not np.allclose(r.T@r, np.eye(3)) or abs(np.linalg.det(r)-1) > 1e-10:
            raise ValueError("Scaled/non-rigid assembly pose")
    expected_cost = cost(cfg, assembly["mass"]["printedSolidMassG"], assembly["mass"]["couponSolidMassG"])
    if expected_cost != json.loads((OUT/"procurement.json").read_text()):
        raise ValueError("Cost, quantities or catalogue mass inconsistent")
    if stack_contract(cfg) != json.loads((OUT/"tolerance_stack.json").read_text()):
        raise ValueError("Tolerance stack changed")
    validate_meshes(assembly)
    for figure in manifest["figures"]:
        ET.parse(ROOT/figure["file"])
    report = json.loads((OUT/"assembly_access.json").read_text())
    if report["unexpected_intersections"]:
        raise ValueError("Known unintended cartridge collisions")
    if min(r["minimum_printed_clearance_mm"] for r in report["rotating_axial_extrema"]) < .15:
        raise ValueError("Axial position loses the declared printed-part clearance")
    print(json.dumps({"revisionId": cfg["revisionId"], "instances": len(names),
                      "filesChecked": len(manifest["artifactHashes"]), "sourcePinned": manifest["sourceCommitContainsInputs"],
                      "cadPackage": "CONSISTENT", "physicalLowDrag": "UNKNOWN",
                      "qualifiedWalkingPrototypes": 0}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    opts = parser.parse_args()
    verify() if opts.verify else seal()
