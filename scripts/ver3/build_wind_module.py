"""One100mm rotor module, using own frozenR4 parts and private vendor checks."""

import argparse
from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
import shutil
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib", required=True)
parser.add_argument("--vendor-dir", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, args.freecad_lib)

import FreeCAD as App
import Part
import MeshPart
import numpy as np

from cad_parts import capsule, cylinder, disk
# These two R4 helpers have no dependence on its dimensions or document state.
from build_input_cartridge import common_volume, normalize_vendor
from input_cartridge import cost, sha, stack_contract, write_json
from wind_module import BASE, CAD, INPUT, OUT, PRINT, ROOT, blade_profile, holder_graph, load, size_holders

CFG = load()
V = App.Vector
SOURCE = json.loads((BASE/"assembly.json").read_text())
LAYOUT = SOURCE["design"]["layout"]
HEIGHT = CFG["axisHeightMm"]


def pose(x=0, y=0, z=HEIGHT):
    return [[0, 0, 1, x], [1, 0, 0, y], [0, 1, 0, z], [0, 0, 0, 1]]


def placed(shape, matrix):
    result = shape.copy()
    result.Placement = App.Placement(App.Matrix(*np.array(matrix).ravel().tolist())).multiply(result.Placement)
    return result


def shifted(shape, delta):
    result = shape.copy()
    result.translate(V(*delta))
    return result


def rotated(shape, degrees):
    result = shape.copy()
    result.rotate(V(0, 0, HEIGHT), V(1, 0, 0), degrees)
    return result


def rectangle_beam(a, b, width, thickness, reference):
    a, b = np.array(a), np.array(b)
    ex = (b-a)/np.linalg.norm(b-a)
    ez = np.array(reference, float)-np.dot(reference, ex)*ex
    ez /= np.linalg.norm(ez)
    ey = np.cross(ez, ex)
    vertices = [V(*(a+s*ey*width/2+t*ez*thickness/2)) for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(V(*(b-a)))


def carrier(original, braced):
    # Reuse only our own original lower rails/pads, not any vendor CAD.
    base = original.common(Part.makeBox(130, 80, 4, V(-5, -40, 0)))
    pieces = [base]
    for side in ("fixed", "floating"):
        graph = holder_graph(CFG, side, braced)
        if side == "fixed":
            start, end = LAYOUT["fixedHolderStartMm"], LAYOUT["fixedHolderEndMm"]
        else:
            start, end = LAYOUT["floatHolderStartMm"], LAYOUT["floatHolderEndMm"]
        thickness = end-start
        profile = disk(12, thickness).fuse(capsule((-18, 0), (18, 0), 12, thickness))
        for sign in (-1, 1):
            profile = profile.fuse(capsule((sign*18, 4-HEIGHT), (sign*6, -10),
                                            CFG["holder"]["primaryLegWidthMm"], thickness))
        pieces.append(placed(profile, pose(start)))
        if braced:
            for member in graph["members"]:
                if member["kind"] == "axial_brace":
                    pieces.append(rectangle_beam(graph["nodes"][member["a"]], graph["nodes"][member["b"]],
                                                 member["width"], member["thickness"], member["reference"]))
    result = pieces[0].multiFuse(pieces[1:]).removeSplitter()
    bores = [
        (-1, 122, LAYOUT["retainerCentralBoreMm"]),
        (LAYOUT["fixedHolderStartMm"]-.1, LAYOUT["fixedFlangeShoulderMm"]-LAYOUT["fixedHolderStartMm"]+.1, LAYOUT["flangePocketDiameterMm"]),
        (LAYOUT["fixedFlangeShoulderMm"], LAYOUT["fixedBodyBoreEndMm"]-LAYOUT["fixedFlangeShoulderMm"], LAYOUT["bearingSeatDiameterMm"]),
        (LAYOUT["floatBodyBoreStartMm"], LAYOUT["floatFlangePocketStartMm"]-LAYOUT["floatBodyBoreStartMm"], LAYOUT["bearingSeatDiameterMm"]),
        (LAYOUT["floatFlangePocketStartMm"], LAYOUT["floatHolderEndMm"]-LAYOUT["floatFlangePocketStartMm"]+.1, LAYOUT["flangePocketDiameterMm"]),
    ]
    for start, length, diameter in bores:
        result = result.cut(Part.makeCylinder(diameter/2, length, V(start, 0, HEIGHT), V(1, 0, 0)))
    for y in (-18, 18):
        result = result.cut(Part.makeCylinder(2.25, 122, V(-1, y, HEIGHT), V(1, 0, 0)))
    return result.removeSplitter()


def rotor_parts():
    r = CFG["rotor"]
    root = disk(r["outerDiameterMm"]/2, r["rootPlateMm"], r["rootShaftBoreMm"])
    root = root.cut(cylinder(r["rootPilotBoreMm"]/2, r["rootPilotDepthMm"]))
    for x in (-8, 8):
        for y in (-8, 8):
            root = root.cut(cylinder(r["boltBoreMm"]/2, r["rootPlateMm"]+2, x, y, -1))
    end = shifted(disk(r["outerDiameterMm"]/2, r["endRingThicknessMm"], r["endRingBoreMm"]),
                  (0, 0, r["rootPlateMm"]+r["activeSpanMm"]))
    blades = []
    for index in range(r["bladeCount"]):
        wires = []
        for axial, thickness in zip(r["thicknessStationsActiveXmm"], r["thicknessStationsMm"]):
            points = [V(x, y, axial+r["rootPlateMm"]) for x, y in
                      blade_profile(CFG, index*360/r["bladeCount"], thickness)]
            wires.append(Part.Wire(Part.makePolygon(points+[points[0]]).Edges))
        blades.append(Part.makeLoft(wires, True, True))
    print("Fusing16 original tapered blades and two end plates", flush=True)
    shape = root.multiFuse([end, *blades]).removeSplitter()
    if not shape.isValid() or len(shape.Solids) != 1:
        raise RuntimeError("Rotor root/blades/end ring are not one valid connected solid")
    return shape, root, end, blades


def collect_original_parts(document):
    definitions = {}
    for instance in SOURCE["instances"]:
        pid = instance["part_id"]
        if pid in definitions:
            continue
        shape = document.getObject(instance["name"]).Shape.copy()
        inverse = App.Placement(App.Matrix(*np.array(instance["transform"]).ravel().tolist())).inverse()
        shape.Placement = inverse.multiply(shape.Placement)
        definitions[pid] = shape
    return definitions


def build():
    print("Sizing reinforced holder under fixed absolute loads", flush=True)
    sizing = size_holders(CFG)
    original = App.openDocument(str(ROOT/"FreeCAD/Ver.3/common_input_r4/CommonInputR4.FCStd"))
    shapes = collect_original_parts(original)
    new_carrier = carrier(shapes["P_CARRIER"], sizing["chosenBraces"])
    material_checks = 0
    for side in ("fixed", "floating"):
        graph = holder_graph(CFG, side, sizing["chosenBraces"])
        for member in graph["members"]:
            a, b = np.array(graph["nodes"][member["a"]]), np.array(graph["nodes"][member["b"]])
            for fraction in (.1, .3, .5, .7, .9):
                material_checks += 1
                if not new_carrier.isInside(V(*(a+(b-a)*fraction)), 1e-6, True):
                    raise RuntimeError("Frame surrogate centerline lies outside the actual carrier material")
    print("Carrier complete; generating rotor", flush=True)
    rotor, root, end, blades = rotor_parts()
    blade_gap = blades[0].distToShape(blades[1])[0]
    App.closeDocument(original.Name)
    shapes["P_CARRIER"] = new_carrier
    shapes.pop("P_FLANGE")
    shapes["P_ROTOR"] = rotor
    parts = deepcopy(SOURCE["parts"])
    parts.pop("P_FLANGE")
    parts["P_ROTOR"] = {"category": "printed", "description": "100mmODx38mm overall,32mm active;16 curved blades, tapered roots,4mm hub root,2mm end ring with40mm access bore; no validated aerodynamic performance"}
    for pid, shape in shapes.items():
        if not shape.isValid() or not shape.Solids:
            raise RuntimeError("Invalid part: "+pid)
        volume = sum(s.Volume for s in shape.Solids)
        center = sum((s.Volume*s.CenterOfMass for s in shape.Solids), V())/volume
        parts[pid].update({"solid_volume_mm3": volume, "solids": len(shape.Solids),
                          "local_center_of_mass_mm": list(center)})
        if parts[pid]["category"] == "printed":
            if len(shape.Solids) != 1:
                raise RuntimeError("Printable part has disconnected bodies: "+pid)
            parts[pid]["mass_g"] = volume*CFG["loadCases"]["printDensityGPerCm3Assumed"]/1000
            parts[pid]["mass_basis"] = "actual new solid CAD x assumed PETG density; not sliced/measured"
    parts["P_CARRIER"]["description"] = "55mm axis carrier; unchanged R4 bearing seats/axial stack; four6x6mm3D braces selected by absolute-load frame screening"
    instances = deepcopy(SOURCE["instances"])
    for item in instances:
        if item["part_id"] != "P_CARRIER":
            item["transform"][2][3] += HEIGHT-30
        if item["part_id"] == "P_FLANGE":
            item["part_id"], item["name"] = "P_ROTOR", "ROTOR"
        item["source_part_revision"] = CFG["revisionId"] if item["part_id"] in ("P_ROTOR", "P_CARRIER") else SOURCE["revisionId"]
    world = {i["name"]: placed(shapes[i["part_id"]], i["transform"]) for i in instances}
    vendor = normalize_vendor(args.vendor_dir)
    real = {i["name"]: placed(vendor[i["part_id"]], i["transform"]) if i["part_id"] in vendor else world[i["name"]]
            for i in instances}
    print("Checking real interfaces, rotor envelope and access", flush=True)
    access = check_access(instances, world, real, shapes, placed(root, pose(43)))
    for folder in (OUT, CAD, PRINT):
        folder.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument("WindModuleR6")
    groups = {k: doc.addObject("App::DocumentObjectGroup", k) for k in ("printed", "purchased")}
    for item in instances:
        pid = item["part_id"]
        feature = doc.addObject("Part::Feature", item["name"])
        feature.Shape = shapes[pid]
        feature.Placement = App.Placement(App.Matrix(*np.array(item["transform"]).ravel().tolist())).multiply(feature.Placement)
        for name, value in (("PartId", pid), ("RevisionId", CFG["revisionId"]), ("Category", parts[pid]["category"]),
                            ("SourcePartRevision", item["source_part_revision"]), ("Specification", parts[pid]["description"]),
                            ("MassBasis", parts[pid]["mass_basis"])):
            feature.addProperty("App::PropertyString", name, "WindModule")
            setattr(feature, name, value)
        feature.addProperty("App::PropertyFloat", "NominalMassGram", "WindModule")
        feature.NominalMassGram = parts[pid]["mass_g"]
        groups[parts[pid]["category"]].addObject(feature)
    doc.recompute()
    native = CAD/"WindModuleR6.FCStd"
    temporary = CAD/"WindModuleR6.new.FCStd"
    doc.saveAs(str(temporary))
    temporary.replace(native)
    features = [o for o in doc.Objects if o.TypeId == "Part::Feature"]
    step = CAD/"WindModuleR6.step"
    print("Saving native and STEP", flush=True)
    Part.export(features, str(step))
    step.write_text("\n".join(line.rstrip() for line in step.read_text().splitlines())+"\n")
    library = {}
    print("Tessellating exact solids for STL and previews", flush=True)
    for pid, shape in shapes.items():
        vertices, triangles = shape.tessellate(.12)
        library[pid] = {"vertices": [list(v) for v in vertices], "triangles": triangles, "category": parts[pid]["category"]}
        if parts[pid]["category"] == "printed":
            printable = shifted(shape, (0, 0, -shape.BoundBox.ZMin))
            mesh = MeshPart.meshFromShape(Shape=printable, LinearDeflection=.10, AngularDeflection=.15, Relative=False)
            mesh.write(str(PRINT/(pid+".stl")))
    with gzip.open(ROOT/SOURCE["cad_meshes"], "rt") as stream:
        old_library = json.load(stream)
    library["Q_BEARING_FIT"] = old_library["Q_BEARING_FIT"]
    shutil.copyfile(ROOT/"STL/Ver.3/common_input_r4/Q_BEARING_FIT.stl", PRINT/"Q_BEARING_FIT.stl")
    (CAD/"render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(library, separators=(",", ":")).encode(), mtime=0))
    printed_mass = sum(parts[i["part_id"]]["mass_g"] for i in instances if parts[i["part_id"]]["category"] == "printed")
    accounting = cost(SOURCE["design"], printed_mass, parts["Q_BEARING_FIT"]["mass_g"])
    accounting.update({"scope": "one rotor module, not three walking designs",
                       "moduleNominalMassG": accounting["wholeCartridgeNominalMassG"],
                       "r4TestFlangeRemovedMassG": SOURCE["parts"]["P_FLANGE"]["mass_g"],
                       "r4CarrierReplacedMassG": SOURCE["parts"]["P_CARRIER"]["mass_g"],
                       "newCarrierSolidMassG": parts["P_CARRIER"]["mass_g"],
                       "newRotorSolidMassG": parts["P_ROTOR"]["mass_g"]})
    procedure = deepcopy(SOURCE["assemblyStages"])
    for row in procedure:
        row["add"] = ["ROTOR" if name == "TEST_FLANGE" else name for name in row["add"]]
        if row["id"] == "01":
            row["title"] = "剛い取付面と4穴の固定を先に確認"
            row["cautions"] = ["Base mating structure/fasteners are not specified; powered operation remains forbidden. Base fixing access is verified before caps and rotor."]
        if row["id"] == "04":
            row["title"] = "Dハブと一体ローターの根元4ねじを先組み"
            row["cautions"] = ["4mm root+1mm washer+M4x12:7mm thread engagement. Insert3mm key through40mm end-ring opening; no blade strings or manual forcing."]
        if row["id"] in ("07", "08"):
            row["cautions"] = ["Stopped/supported only. Do not infer real spin or walking qualification. Release clamps and withdraw shaft before lifting rotor unit; foundation unqualified."]
    payload = {"revisionId": CFG["revisionId"], "id": "WIND_MODULE_R6", "units": "mm",
               "coordinates": SOURCE["coordinates"], "design": CFG, "parts": parts, "instances": instances,
               "assemblyStages": procedure, "cad_meshes": str((CAD/"render_geometry.json.gz").relative_to(ROOT)),
               "mass": accounting, "baseSourceManifestSha256": sha(BASE/"manifest.json"),
               "purchasedGeometry": "reuse of our own R4 dimensional envelopes; private vendor solids used only in access checks",
               "manufacturingRelease": False, "physicalStartingTorqueNm": None, "qualifiedWalkingPrototypeCount": 0}
    aux = {}
    for name, shape in (("root_plate", root), ("end_ring", end), ("one_blade", blades[0])):
        vertices, faces = shape.tessellate(.10)
        aux[name] = {"vertices": [list(v) for v in vertices], "triangles": faces,
                     "volume_mm3": shape.Volume, "center_of_mass_mm": list(shape.Solids[0].CenterOfMass)}
    (CAD/"analysis_geometry.json.gz").write_bytes(gzip.compress(json.dumps(aux, separators=(",", ":")).encode(), mtime=0))
    write_json(OUT/"assembly.json", payload)
    write_json(OUT/"holder_sizing.json", sizing)
    write_json(OUT/"assembly_access.json", access)
    write_json(OUT/"procurement.json", accounting)
    stock = {p["id"]: p for p in accounting["purchasedRows"]}
    with (OUT/"BOM.csv").open("w", newline="") as stream:
        w = csv.writer(stream, lineterminator="\n")
        w.writerow(["part_id", "category", "assembly_quantity", "sku", "purchase_pieces", "minimum_lot_usd",
                    "unit_nominal_mass_g", "total_nominal_mass_g", "basis", "description"])
        for pid, p in parts.items():
            quantity = sum(i["part_id"] == pid for i in instances)
            info = stock.get(pid, {})
            w.writerow([pid, p["category"], quantity, info.get("sku", ""), info.get("purchaseQuantity", ""),
                        info.get("subtotalUsd", ""), p["mass_g"], p["mass_g"]*quantity, p["mass_basis"], p["description"]])
    expected = sum(sum(s.Volume for s in shape.Solids) for shape in world.values())
    expected_solids = sum(len(s.Solids) for s in world.values())
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(native))
    features = [o for o in reopened.Objects if o.TypeId == "Part::Feature"]
    if len(features) != 36 or any(not o.Shape.isValid() for o in features):
        raise RuntimeError("Saved native failed validation")
    placement_error = max(abs(getattr(world[o.Name].BoundBox, key)-getattr(o.Shape.BoundBox, key))
                          for o in features for key in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"))
    exchanged = Part.read(str(step))
    volume_error = abs(sum(s.Volume for s in exchanged.Solids)-expected)/expected
    if len(exchanged.Solids) != expected_solids or volume_error > 1e-6 or placement_error > 1e-8:
        raise RuntimeError("Native/STEP/placement mismatch")
    App.closeDocument(reopened.Name)
    summary = {"revisionId": CFG["revisionId"], "nativeObjects": 36, "nativeSolids": expected_solids,
               "stepSolids": len(exchanged.Solids), "relativeVolumeError": volume_error,
               "placementErrorMm": placement_error, "rotorOverallMm": [38, 100, 100],
               "rotorActiveSpanMm": 32, "axisHeightMm": HEIGHT,
               "rotorActualSolidMassG": parts["P_ROTOR"]["mass_g"],
               "carrierActualSolidMassG": parts["P_CARRIER"]["mass_g"],
               "totalPrintedSolidMassG": printed_mass, "totalNominalModuleMassG": accounting["moduleNominalMassG"],
               "originalR4NominalMassG": SOURCE["mass"]["wholeCartridgeNominalMassG"],
               "rotorRadialCadEccentricityMm": float(np.linalg.norm(np.array(parts["P_ROTOR"]["local_center_of_mass_mm"])[:2])),
               "minimum_neighboring_blade_gap_mm": blade_gap,
               "rotorPolarMassInertiaKgM2": rotor.Solids[0].MatrixOfInertia.A33*CFG["loadCases"]["printDensityGPerCm3Assumed"]*1e-12,
               "frame_material_centerline_samples": material_checks,
               "physicalBalanceOrMassMeasured": False, "matingFoundationQualified": False}
    write_json(OUT/"cad_validation.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def check_access(instances, world, real, shapes, rotor_root):
    envelope = Part.makeCylinder(50, 38, V(43, 0, HEIGHT), V(1, 0, 0))
    moving = [i["name"] for i in instances if i["rotating"]]
    static = [i["name"] for i in instances if not i["rotating"]]
    for name in static:
        if common_volume(envelope, real[name]) > 1e-6:
            raise RuntimeError("Analytic circular rotor envelope meets a fixed part")
    axial_extrema = []
    for dx in (-.6, 0, .15):
        shifted_envelope = shifted(envelope, [dx, 0, 0])
        minimum = min(shifted_envelope.distToShape(real[name])[0] for name in static)
        if any(common_volume(shifted_envelope, real[name]) > 1e-6 for name in static):
            raise RuntimeError("Whole-rotor axial acceptance position intersects a fixed part")
        axial_extrema.append({"dx_mm": dx, "minimum_rigid_envelope_clearance_mm": minimum})

    def rotor_intersection(other):
        if common_volume(envelope, other) <= 1e-6:
            return 0.0
        box = other.BoundBox
        radial_bound = np.hypot(max(abs(box.YMin), abs(box.YMax)),
                                max(abs(box.ZMin-HEIGHT), abs(box.ZMax-HEIGHT)))
        if box.XMax <= 47+1e-7 or radial_bound < 20:
            return common_volume(rotor_root, other)
        return common_volume(real["ROTOR"], other)

    faults, allowed = [], []
    for i, item in enumerate(instances):
        a = item["name"]
        for other in instances[i+1:]:
            b = other["name"]
            volume = (rotor_intersection(real[b]) if a == "ROTOR" else
                      rotor_intersection(real[a]) if b == "ROTOR" else common_volume(real[a], real[b]))
            if volume <= 1e-6:
                continue
            intended = ({a, b} == {"SHAFT", "D_HUB"}
                        or (a.startswith("FLANGE_SCREW_") and b == "D_HUB")
                        or (b.startswith("FLANGE_SCREW_") and a == "D_HUB")
                        or (a.startswith("SCREW_") and b == "NUT_"+a[6:])
                        or (b.startswith("SCREW_") and a == "NUT_"+b[6:]))
            (allowed if intended else faults).append({"a": a, "b": b, "volume_mm3": volume})
    if faults:
        raise RuntimeError("Module assembly collision: "+json.dumps(faults))
    minimum = float("inf")
    pair_count = 0
    for angle in range(0, 360, 15):
        for name in moving:
            if name == "ROTOR":
                pair_count += len(static)
                continue
            shape = rotated(real[name], angle)
            for other in static:
                pair_count += 1
                if common_volume(shape, real[other]) > 1e-6:
                    raise RuntimeError(f"Rotating interference: {name}/{other}/{angle}")
    minimum = min(envelope.distToShape(real[name])[0] for name in static)
    tools = []
    for x in (6, 114):
        for y in (-18, 18):
            tool = Part.makeCylinder(4, 115, V(x, y, 4.1), V(0, 0, 1))
            volume = common_volume(tool, real["CARRIER"])
            if volume > 1e-6:
                raise RuntimeError("Base mounting-hole tool path obstructed by a brace")
            after_caps = [name for name in static if name != "CARRIER" and common_volume(tool, real[name]) > 1e-6]
            tools.append({"stage": "before_caps", "mounting_hole_xy_mm": [x, y], "tool": "8mm OD vertical access envelope",
                          "carrier_overlap_mm3": volume, "blocked_after_caps_by": after_caps,
                          "foundation_and_external_fasteners": "UNSPECIFIED; no powered-use approval"})
    for index in range(4):
        name = "FLANGE_SCREW_"+str(index)
        item = next(i for i in instances if i["name"] == name)
        y, z = item["transform"][1][3], item["transform"][2][3]
        straight = Part.makeCylinder(2, 35.7, V(52.1, y, z), V(1, 0, 0))
        handle = Part.makeCylinder(2, 65, V(87.8, y, z), V(0, 0, 1))
        tool = straight.fuse(handle)
        collision = [other for other in real if other != name and
                     (rotor_intersection(tool) if other == "ROTOR" else common_volume(tool, real[other])) > 1e-6]
        if collision:
            raise RuntimeError("Rotor fixing-key path blocked: "+str(collision))
        tools.append({"stage": "rotor_root_fastening", "fastener": name,
                      "tool": "4mm envelope for3mm L-key,35.7mm axial shank+65mm upper handle",
                      "through_end_ring_bore_mm": 40, "unexpected_overlap": collision})
    for side, direction, x in (("LOC", 1, 28.2), ("FLOAT", -1, 84.8)):
        for y in (-18, 18):
            tool = Part.makeCylinder(6, 28, V(x, y, HEIGHT), V(direction, 0, 0))
            obstacles = ["CARRIER", "CAP_LOC", "CAP_FLOAT", "BEARING_LOC", "BEARING_FLOAT"]
            collision = [n for n in obstacles if common_volume(tool, real[n]) > 1e-6]
            if collision:
                raise RuntimeError("Cap-nut tool path blocked before the rotor installation")
            tools.append({"stage": "caps_before_rotor_and_collars", "side": side, "y_mm": y,
                          "tool": "12mm OD x28mm nut-driver envelope", "unexpected_overlap": collision})
    for name in ("D_HUB", "COLLAR_OUT", "COLLAR_IN"):
        for index, screw in enumerate(real[name].Solids[1:], start=1):
            face = max((f for f in screw.Faces if isinstance(f.Surface, Part.Plane)), key=lambda f: f.Area)
            normal = face.normalAt(0, 0)
            tool = Part.makeCylinder(2, 28, face.CenterOfMass+normal*.1, normal)
            chosen = None
            for degree in range(0, 360, 15):
                if App.Rotation(V(1, 0, 0), degree).multVec(normal).z < .2:
                    continue
                moved = rotated(tool, degree)
                maximum = 0.0
                for other, solid in real.items():
                    if other == name:
                        continue
                    if other == "ROTOR":
                        volume = rotor_intersection(tool)
                    else:
                        volume = common_volume(moved, rotated(solid, degree) if other in moving else solid)
                    maximum = max(maximum, volume)
                for j, solid in enumerate(real[name].Solids):
                    if j != index:
                        maximum = max(maximum, common_volume(moved, rotated(solid, degree)))
                if maximum <= 1e-6:
                    chosen = {"stage": "stopped_supported_module", "purchased_assembly": name,
                              "included_screw_index": index, "shaft_angle_deg": degree,
                              "tool": "4mm OD x28mm clamp-key envelope into upper half-space",
                              "maximum_overlap_mm3": maximum}
                    break
            if chosen is None:
                raise RuntimeError(f"No clamp-key access after rotor installation:{name}/{index}")
            tools.append(chosen)
    paths = []

    def path(name, moving_ids, rest, vector, distances, exclusions=()):
        maximum = 0.0
        for distance in distances:
            for moving_name in moving_ids:
                shape = shifted(real[moving_name], [distance*v for v in vector])
                for fixed_name in rest:
                    if (moving_name, fixed_name) in exclusions:
                        continue
                    if moving_name == "ROTOR":
                        moved_envelope = shifted(envelope, [distance*v for v in vector])
                        volume = common_volume(moved_envelope, real[fixed_name])
                        if volume > 1e-6:
                            volume = common_volume(shape, real[fixed_name])
                    elif fixed_name == "ROTOR":
                        volume = rotor_intersection(shape)
                    else:
                        volume = common_volume(shape, real[fixed_name])
                    maximum = max(maximum, volume)
                    if volume > 1e-6:
                        raise RuntimeError(f"Access collision:{name}/{moving_name}/{fixed_name}/{distance}")
        paths.append({"id": name, "moving": moving_ids, "remaining": rest, "direction": vector,
                      "samples_mm": distances, "maximum_overlap_mm3": maximum,
                      "separate_vendor_fit_exclusions": [list(x) for x in exclusions]})

    path("shaft_with_clamps_released", ["SHAFT"], [n for n in real if n != "SHAFT"], [-1, 0, 0],
         [0, 1, 5, 12, 24, 48, 72, 100, 124], [("SHAFT", "D_HUB")])
    unit = [i["name"] for i in instances if i["group"] == "flange_unit"]
    path("whole_rotor_unit_after_shaft", unit, [n for n in real if n not in ["SHAFT", *unit]],
         [0, 0, 1], [0, 1, 5, 10, 25, 50, 110])
    for name, cap, vector in (("BEARING_LOC", "CAP_LOC", [-1, 0, 0]), ("BEARING_FLOAT", "CAP_FLOAT", [1, 0, 0])):
        path(name+"_before_cap", [name], ["CARRIER"], vector, [0, .5, 1, 2, 5, 15, 30])
    for name, values, obstacles in (("BEARING_LOC", [-.3, 0], ["CARRIER", "CAP_LOC"]),
                                     ("BEARING_FLOAT", [-1, 0, 1], ["CARRIER", "CAP_FLOAT"])):
        path(name+"_axial_freedom", [name], obstacles, [1, 0, 0], values)
    return {"revisionId": CFG["revisionId"], "static_pairs": 630, "intentional_reference_interfaces": allowed,
            "unintended_static_intersections": faults, "rotation_angles_deg": list(range(0, 360, 15)),
            "rotation_pair_checks": pair_count, "rotor_to_fixed_minimum_sampled_clearance_mm": minimum,
            "full_circular_envelope_clear_of_fixed_parts": True, "rotor_to_mounting_plane_mm": HEIGHT-50,
            "rotor_axial_acceptance_extrema": axial_extrema,
            "rotor_clearance_basis": "conservative100x38 full cylinder, valid for all angles; root holes checked separately. Active/end-ring center void radius20 verified by canonical profile, not a sampled visibility shortcut.",
            "tools": tools, "paths": paths,
            "vendorSourceHashes": {name+".step": sha(args.vendor_dir/(name+".step"))
                                  for name in ("shaft", "bearing", "collar", "hub", "spacer")},
            "supplierCadRedistributed": False, "manufacturerDClampFit": "specified compatible pair; physical fit/tolerance/state and torque remain unknown",
            "operatingBaseFixation": "UNQUALIFIED",
            "limitations": "Sampled paths/tools plus bounding rotor envelope; not all tools/continuous tolerances, physical spinning or strength certification"}


if __name__ == "__main__":
    build()
