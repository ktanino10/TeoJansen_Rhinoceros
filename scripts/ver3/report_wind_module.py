"""Small static drawings and checks for the single module; no videos/WebGL."""

import argparse
import base64
import gzip
import io
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw
import trimesh

from cartridge_report import hex_rgb, svg, txt, world_meshes
from input_cartridge import sha, write_json
from wind_module import BASE, CAD, INPUT, OUT, PRINT, ROOT, load


def raster_meshes(assembly, exploded=False):
    records = world_meshes(assembly)
    eye = np.array([120., -200., 100.])
    eye /= np.linalg.norm(eye)
    u = np.cross([0, 0, 1], eye)
    u /= np.linalg.norm(u)
    v = np.cross(eye, u)
    all_projected, data = [], []
    colors = {"P_CARRIER": "#4b789a", "P_CAP": "#dcac59", "P_ROTOR": "#64b897",
              "H_HUB": "#bec7d1", "H_BEARING": "#697f91"}
    for item in records:
        points = item["vertices"].copy()
        if exploded:
            if item["name"] == "SHAFT":
                points[:, 0] -= 124
            elif item["group"] == "flange_unit":
                points[:, 2] += 70
            elif item["group"] == "locating_rotating":
                points[:, 1] -= 48
        projected = np.column_stack([points@u, points@v, points@eye])
        all_projected.append(projected)
        data.append((item, points, projected))
    cloud = np.vstack(all_projected)
    low, high = cloud[:, :2].min(axis=0), cloud[:, :2].max(axis=0)
    scale = min(1080/(high[0]-low[0]), 530/(high[1]-low[1]))
    center = (low+high)/2
    polygons = []
    for item, points, projected in data:
        triangles = item["triangles"]
        tri = points[triangles]
        normals = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        good = lengths > 1e-12
        normals[good] /= lengths[good, None]
        facing = normals@eye
        color = hex_rgb(colors.get(item["part_id"], "#b8c2cd"))
        for index in np.flatnonzero(good & (facing > 0)):
            f = triangles[index]
            xy = (projected[f, :2]-center)*[scale, -scale]+[575, 285]
            rgb = tuple(int(c*(.43+.55*facing[index])) for c in color)
            polygons.append((float(projected[f, 2].mean()), xy, rgb))
    image = Image.new("RGB", (2300, 1140), "#111925")
    draw = ImageDraw.Draw(image)
    for _, xy, color in sorted(polygons, key=lambda p: p[0]):
        draw.polygon([tuple(2*p) for p in xy], fill=color)
    image = image.resize((1150, 570), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")


def module_preview(path, assembly, exploded=False):
    cfg = load()
    mass = assembly["mass"]
    image = raster_meshes(assembly, exploded)
    body = [txt(35, 35, "裸16羽根ローター＋共通入力軸 / "+("分離説明配置" if exploded else "実CAD"), 23),
            txt(35, 64, cfg["revisionId"]+" / 径100mm・外形38mm・受風32mm・軸高55mm", 16, "#f3c471"),
            f'<image x="25" y="83" width="1150" height="570" href="data:image/png;base64,{image}"/>',
            txt(35, 685, f'ローター {mass["newRotorSolidMassG"]:.2f}g / キャリア {mass["newCarrierSolidMassG"]:.2f}g / '
                f'全体 {mass["moduleNominalMassG"]:.2f}g（実CAD密度＋購入カタログの名目値）', 16),
            txt(35, 718, "機械的Dハブ・根元4本M4・端リングの40mm開口。低抵抗／自己始動／歩行の認証ではありません。", 15),
            txt(35, 750, "軸を-Xへ完全に抜いてからローターユニットを+Zへ。図の各移動を同時に行う指示ではありません。" if exploded
                else "4本の6×6mm斜材は同じ荷重の絶対変位予算から採用。基台の相手・固定剛性は未確認で運転不可。", 15),
            txt(35, 786, "図は保存済みメッシュの静的投影。購入部はR4の独自寸法モデルを継承し、メーカーCADは再配布しない。", 14)]
    svg(path, body)


def frame_preview(path):
    cfg = load()
    sizing = json.loads((OUT/"holder_sizing.json").read_text())
    body = [txt(35, 35, "補剛は倍率でなく、同じ1Nの絶対変位で選ぶ", 23),
            txt(35, 65, "3D梁フレーム近似 / E=800MPa / 固定側Fx=1N / 根元固定 / 変形表示100倍", 16, "#f3c471")]
    eye = np.array([1., -1.5, .5])
    eye /= np.linalg.norm(eye)
    u = np.cross([0, 0, 1], eye)
    u /= np.linalg.norm(u)
    v = np.cross(eye, u)
    for braced, x0, color, label in ((False, 285, "#ef9679", "斜材なし"), (True, 865, "#69bea4", "6×6mm斜材あり")):
        trial = next(t for t in sizing["trials"] if t["braced"] == braced and t["E_mpa"] == 800
                     and t["loadcase"]["id"] == "AXIAL_FIXED_1N")
        frame = trial["frames"][0]
        nodes = {n: np.array(p) for n, p in frame["coordinates"].items()}
        disp = {n: np.array(d[:3]) for n, d in frame["displacements"].items()}
        center = np.array([24, 0, 28])

        def project(point):
            return np.array([x0+4*(point-center)@u, 350-4*(point-center)@v])

        for member in frame["members"]:
            for factor, stroke in ((0, "#647285"), (100, color)):
                a, b = [project(nodes[n]+factor*disp[n]) for n in (member["a"], member["b"])]
                body.append(f'<path d="M{a[0]:.2f} {a[1]:.2f}L{b[0]:.2f} {b[1]:.2f}" stroke="{stroke}" stroke-width="2" fill="none"/>')
        for node in frame["fixed_nodes"]:
            p = project(nodes[node])
            body.append(f'<path d="M{p[0]} {p[1]}l-6 11h12z" fill="#b8c4d1"/>')
        point = np.mean([nodes[n] for n in frame["bearing_ring_nodes"]], axis=0)
        start, end = project(point-[14, 0, 0]), project(point)
        direction = (end-start)/np.linalg.norm(end-start)
        normal = np.array([-direction[1], direction[0]])
        head = [end, end-8*direction+4*normal, end-8*direction-4*normal]
        body += [f'<path d="M{start[0]} {start[1]}L{end[0]} {end[1]}" stroke="#f3c471" stroke-width="2"/>',
                 '<polygon points="'+" ".join(f"{p[0]},{p[1]}" for p in head)+'" fill="#f3c471"/>',
                 txt(start[0]-25, start[1]-10, "Fx 1N", 14, "#f3c471")]
        body += [txt(x0-140, 128, label, 20, color),
                 txt(x0-220, 565, f'軸受中心の軸方向移動 {trial["maximum_bearing_axial_shift_mm"]:.5f} mm', 17, color),
                 txt(x0-220, 594, f'部材の軸力＋曲げ応力代理最大 {trial["maximum_normal_stress_mpa"]:.3f} MPa', 16)]
    body += [txt(35, 655, "ホルダー差動変形に0.025mm、熱等の未モデル量に0.025mmを配分（R4の0.05mm予算内）。", 16),
             txt(35, 687, "実質量の重力／風とFx±1Nの結果では、共通移動・左右差・軸の伸び／傾きを別に記録。", 15),
             txt(35, 719, "キャップの荷重時変形、取付面／固定ボルト、実軸受内部すきまは未確定。全浮動余白を保証しない。", 15),
             txt(35, 754, "根元は剛い相手材で裏打ちされる境界仮定。線はCAD内の部材中心線を標本確認した梁モデルで、solid FEMではない。", 14)]
    svg(path, body)


def blade_preview(path):
    cfg = load()
    result = json.loads((OUT/"rotor_strength_screens.json").read_text())
    body = [txt(35, 35, "羽根・根元の曲げスクリーニング", 23),
            txt(35, 65, "最小板厚1.2mmの片持ち＋根元板ストリップ / E=800MPa / 変形表示10倍", 16, "#f3c471")]
    length, scale = 32, 28
    body.append('<path d="M105 145H1001" stroke="#768494" stroke-width="2"/>')
    body += ['<path d="M1001 80V143l-5 -9m5 9l5 -9" stroke="#f3c471" stroke-width="2" fill="none"/>',
             txt(875, 108, "計算横荷重", 15, "#f3c471")]
    for rpm, color in ((0, "#65b797"), (600, "#ee9476")):
        row = next(s for s in result["scenarios"] if s["E_mpa"] == 800 and s["rpm_prescribed_not_predicted"] == rpm)
        points = []
        for fraction in np.linspace(0, 1, 65):
            deflection = row["blade_tip_deflection_mm"]*(fraction*fraction*(3-fraction)/2)
            deflection += row["root_strip_rotation_rad"]*length*fraction
            points.append((105+fraction*length*scale, 145+deflection*scale*10))
        coords = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
        body.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"/>')
        body.append(txt(80, 610+35*(rpm == 600),
                        f'{rpm} rpm（指定感度、到達予測ではない）：先端＋根元回転 {row["blade_tip_with_root_rotation_mm"]:.3f}mm、'
                        f'羽根曲げ {row["blade_bending_stress_mpa"]:.3f}MPa', 16, color))
    body += [txt(35, 712, "荷重は1枚の風上限＋自重＋指定回転数の遠心力を同一方向へ置いた保守的な比較。", 15),
             txt(35, 744, "端リングによる羽根拘束と根元2.4mmテーパーの剛性効果は羽根側の式に加点していない。", 15),
             txt(35, 778, "600rpmの安全保証・運転指示ではない。積層接着、クリープ、疲労、局所応力集中、実材料は未検証。", 14)]
    svg(path, body)


def mesh_checks(assembly):
    rows = []
    for pid, p in assembly["parts"].items():
        if p["category"] != "printed":
            continue
        mesh = trimesh.load(PRINT/(pid+".stl"), force="mesh")
        error = abs(mesh.volume-p["solid_volume_mm3"])/p["solid_volume_mm3"]
        if not mesh.is_volume or len(mesh.split()) != 1 or np.any(mesh.extents > 230) or error > .01:
            raise ValueError("Invalid printed STL: "+pid)
        rows.append({"part": pid, "singleClosedSolid": True, "dimensionsMm": mesh.extents.tolist(),
                     "volumeRelativeError": float(error),
                     "assemblyQuantity": sum(i["part_id"] == pid for i in assembly["instances"])})
    return rows


def seal():
    cfg = load()
    assembly = json.loads((OUT/"assembly.json").read_text())
    module_preview(OUT/"cad_preview.svg", assembly)
    module_preview(OUT/"assembly_separation.svg", assembly, True)
    frame_preview(OUT/"holder_deflection.svg")
    blade_preview(OUT/"blade_deflection.svg")
    write_json(OUT/"stl_validation.json", mesh_checks(assembly))
    files = [INPUT, Path(__file__), ROOT/"scripts/ver3/build_wind_module.py",
             ROOT/"scripts/ver3/wind_module.py", ROOT/"scripts/ver3/frame3d.py",
             ROOT/"scripts/ver3/analyze_wind_module.py", ROOT/"scripts/ver3/test_frame3d.py",
             ROOT/"scripts/ver3/test_wind_module.py", ROOT/"scripts/ver3/beam.py",
             ROOT/"scripts/ver3/cad_parts.py", ROOT/"scripts/ver3/input_cartridge.py",
             ROOT/"scripts/ver3/build_input_cartridge.py", ROOT/"scripts/ver3/cartridge_report.py",
             ROOT/"scripts/ver3/commercial_r3.py", ROOT/"scripts/ver3/study_r2.py",
             ROOT/"scripts/ver3/study_r2.json", ROOT/"scripts/ver3/core.py", ROOT/"scripts/ver3/design.json"]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in files}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    pinned = True
    for path in files:
        stored = subprocess.run(["git", "show", f"{commit}:{path.relative_to(ROOT)}"], cwd=ROOT, capture_output=True, check=False)
        pinned = pinned and stored.returncode == 0 and stored.stdout == path.read_bytes()
    artifacts = sorted(p for directory in (OUT, CAD, PRINT) for p in directory.iterdir()
                       if p.is_file() and p.name != "manifest.json")
    figures = [
        ("cad_preview.svg", "actual CAD mesh static projection", 1, "assembly.json", "mm,g", "ASSEMBLED"),
        ("assembly_separation.svg", "actual CAD in sequential removal explanation positions", 1, "assembly.json", "mm,g", "REMOVAL_EXPLANATION"),
        ("holder_deflection.svg", "3D beam-frame surrogate, not solid FEM", 100, "holder_sizing.json", "mm,N,MPa", "AXIAL_FIXED_1N_E800"),
        ("blade_deflection.svg", "beam/plate-strip screening, not solid FEM", 10, "rotor_strength_screens.json", "mm,N,MPa,rpm", "BLADE_WIND_GRAVITY_0_600RPM_E800")
    ]
    write_json(OUT/"manifest.json", {
        "revisionId": cfg["revisionId"], "sourceCommit": commit, "sourceCommitContainsInputs": pinned,
        "sourceHashes": hashes, "artifactHashes": {str(p.relative_to(ROOT)): sha(p) for p in artifacts},
        "baseCartridgeManifestHash": sha(BASE/"manifest.json"),
        "baseConditionalMachineManifestHash": sha(ROOT/"docs/ver3/commercial_basis_r3/manifest.json"),
        "figures": [{"file": str((OUT/name).relative_to(ROOT)), "revisionId": cfg["revisionId"],
                     "sourceGeometryRevision": cfg["revisionId"], "method": method, "displayAmplification": factor,
                     "units": units, "figureUnits": units, "dataFile": str((OUT/data).relative_to(ROOT)),
                     "loadcaseId": case, "resultStatus": "UNKNOWN",
                     "isRotorModuleCadGeometry": factor == 1, "isQualifiedWalkingGeometry": False,
                     "sourceHashes": {data: sha(OUT/data), "assembly.json": sha(OUT/"assembly.json"),
                                      "render_geometry.json.gz": sha(CAD/"render_geometry.json.gz")}}
                    for name, method, factor, data, units, case in figures],
        "native": str((CAD/"WindModuleR6.FCStd").relative_to(ROOT)),
        "step": str((CAD/"WindModuleR6.step").relative_to(ROOT)),
        "cadMesh": assembly["cad_meshes"], "assembly": str((OUT/"assembly.json").relative_to(ROOT)),
        "bom": str((OUT/"BOM.csv").relative_to(ROOT)),
        "manufacturingRelease": False, "qualifiedWalkingPrototypeCount": 0,
        "matingFoundationQualified": False, "airModelCalibrated": False, "realBearingDragMeasured": False,
        "supplierCadRedistributed": False,
    })
    verify()


def verify():
    cfg = load()
    m = json.loads((OUT/"manifest.json").read_text())
    if m["revisionId"] != cfg["revisionId"] or m["qualifiedWalkingPrototypeCount"] != 0:
        raise ValueError("Unexpected module revision or qualification")
    for relative, expected in {**m["sourceHashes"], **m["artifactHashes"]}.items():
        path = (ROOT/relative).resolve()
        path.relative_to(ROOT)
        if sha(path) != expected:
            raise ValueError("Changed input/artifact: "+relative)
    if sha(BASE/"manifest.json") != m["baseCartridgeManifestHash"]:
        raise ValueError("Frozen R4 changed")
    assembly = json.loads((OUT/"assembly.json").read_text())
    names = [i["name"] for i in assembly["instances"]]
    added = [n for s in assembly["assemblyStages"] for n in s["add"]]
    if len(names) != 36 or sorted(names) != sorted(added) or len(set(added)) != len(added):
        raise ValueError("Bad assembly stage membership")
    mesh_checks(assembly)
    for f in m["figures"]:
        ET.parse(ROOT/f["file"])
    structural = json.loads((OUT/"actual_mass_support.json").read_text())
    for case in structural["holder_cases"]:
        if not case["conditional_budget_pass"]:
            raise ValueError("Frame allowance failed")
        shifts = np.array([f["bearing_center_shift_mm"] for f in case["frames"]])
        np.testing.assert_allclose(shifts[1]-shifts[0], case["differential_bearing_translation_mm"], atol=1e-12)
        np.testing.assert_allclose(shifts.mean(axis=0), case["common_mode_bearing_translation_mm"], atol=1e-12)
        for frame in case["frames"]:
            rotation = np.array(frame["mean_ring_rotation_rad"])
            offset = np.array(frame["ring_to_bearing_offset_mm"])
            corrected = np.array(frame["ring_plane_translation_mm"])+np.cross(rotation, offset)
            np.testing.assert_allclose(corrected, frame["bearing_center_shift_mm"], atol=1e-12)
            if frame["load_point_work_residual_nmm"] > 1e-10:
                raise ValueError("Eccentric force and bearing-center displacement are not work-conjugate")
        if case["full_assembled_float_margin_status"] != "UNKNOWN":
            raise ValueError("Unresolved cap/base/bearing compliance must not be certified")
    print(json.dumps({"revisionId": cfg["revisionId"], "sourcePinned": m["sourceCommitContainsInputs"],
                      "artifacts": len(m["artifactHashes"]), "instances": 36,
                      "moduleCadAndData": "CONSISTENT", "physicalStartingAndWalking": "UNKNOWN"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify() if args.verify else seal()
