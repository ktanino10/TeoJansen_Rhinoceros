"""Build one original cartridge CAD. Vendor STEP is read only for private checks.

Run in FreeCAD's bundled Python with --freecad-lib and --vendor-dir. The latter
contains bearing.step, collar.step, shaft.step, hub.step and spacer.step.
No manufacturer solid, drawing or tessellation is saved in the deliverables.
"""

import argparse
from collections import Counter
import csv
import gzip
import json
import math
from pathlib import Path
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

from cad_parts import cylinder, disk, capsule, polygon, hexagon, bolt
from input_cartridge import CAD, INPUT, OUT, PRINT, ROOT, cost, load, mechanics, sha, stack_contract, write_json

V = App.Vector
CFG = load()
L = CFG["layout"]
H = L["axisHeightMm"]


def transform(x=0, y=0, z=H, reverse=False, angle=0):
    c, s = math.cos(angle), math.sin(angle)
    sign = -1 if reverse else 1
    return [[0, 0, sign, x], [c, -sign*s, 0, y], [s, sign*c, 0, z], [0, 0, 0, 1]]


def placed(shape, matrix):
    result = shape.copy()
    result.Placement = App.Placement(App.Matrix(*[v for row in matrix for v in row])).multiply(result.Placement)
    return result


def shifted(shape, delta):
    result = shape.copy()
    result.translate(V(*delta))
    return result


def turn(shape, degrees):
    result = shape.copy()
    result.rotate(V(0, 0, H), V(1, 0, 0), degrees)
    return result


def d_shape(length, flat):
    result = cylinder(3, length).common(Part.makeBox(6, 3+flat, length, V(-3, -3, 0)))
    result.rotate(V(), V(0, 0, 1), -45)
    return result


def bore_x(shape, start, length, diameter):
    return shape.cut(Part.makeCylinder(diameter/2, length, V(start, 0, H), V(1, 0, 0)))


def support_blank(thickness):
    pitch, radius = L["coverBoltHalfPitchMm"], L["holderBossRadiusMm"]
    ring = disk(L["bearingBossRadiusMm"], thickness)
    bridge = capsule((-pitch, 0), (pitch, 0), 2*radius, thickness)
    legs = [capsule((sign*L["baseRailHalfPitchMm"], L["baseRailThicknessMm"]-H),
                    (sign*6, -10), L["holderLegWidthMm"], thickness)
            for sign in (-1, 1)]
    return ring.multiFuse([bridge, *legs]).removeSplitter()


def carrier():
    rails = [Part.makeBox(114, L["baseRailWidthMm"], 4, V(3, y-3, 0)) for y in (-18, 18)]
    pieces = rails[:]
    for x in L["mountingXmm"]:
        for y in L["mountingYmm"]:
            pieces.append(cylinder(6, 4, x, y, 0))
    for start, end in ((L["fixedHolderStartMm"], L["fixedHolderEndMm"]),
                       (L["floatHolderStartMm"], L["floatHolderEndMm"])):
        pieces.append(placed(support_blank(end-start), transform(start)))
        pieces.append(Part.makeBox(end-start, 36, 4, V(start, -18, 0)))
    result = pieces[0].multiFuse(pieces[1:]).removeSplitter()
    result = bore_x(result, -1, 122, L["retainerCentralBoreMm"])
    result = bore_x(result, L["fixedHolderStartMm"]-0.1,
                    L["fixedFlangeShoulderMm"]-L["fixedHolderStartMm"]+0.1, L["flangePocketDiameterMm"])
    result = bore_x(result, L["fixedFlangeShoulderMm"],
                    L["fixedBodyBoreEndMm"]-L["fixedFlangeShoulderMm"], L["bearingSeatDiameterMm"])
    result = bore_x(result, L["floatBodyBoreStartMm"],
                    L["floatFlangePocketStartMm"]-L["floatBodyBoreStartMm"], L["bearingSeatDiameterMm"])
    result = bore_x(result, L["floatFlangePocketStartMm"],
                    L["floatHolderEndMm"]-L["floatFlangePocketStartMm"]+0.1, L["flangePocketDiameterMm"])
    for y in (-L["coverBoltHalfPitchMm"], L["coverBoltHalfPitchMm"]):
        result = result.cut(Part.makeCylinder(L["coverBoltBoreMm"]/2, 122, V(-1, y, H), V(1, 0, 0)))
    for x in L["mountingXmm"]:
        for y in L["mountingYmm"]:
            result = result.cut(cylinder(L["mountingHoleDiameterMm"]/2, 6, x, y, -1))
    return result.removeSplitter()


def cap():
    pitch, thickness = L["coverBoltHalfPitchMm"], L["coverThicknessMm"]
    result = disk(L["bearingBossRadiusMm"], thickness).fuse(
        capsule((-pitch, 0), (pitch, 0), 2*L["holderBossRadiusMm"], thickness))
    result = result.cut(cylinder(L["retainerCentralBoreMm"]/2, thickness+2, z=-1))
    for x in (-pitch, pitch):
        result = result.cut(cylinder(L["coverBoltBoreMm"]/2, thickness+2, x, 0, -1))
    return result.removeSplitter()


def flange():
    result = disk(L["flangeDiameterMm"]/2, L["flangeThicknessMm"], L["flangeShaftBoreMm"])
    result = result.cut(cylinder(L["flangePilotBoreMm"]/2, L["flangePilotDepthMm"], z=0))
    half = L["hubHoleSquareMm"]/2
    for x in (-half, half):
        for y in (-half, half):
            result = result.cut(cylinder(L["flangeBoltBoreMm"]/2, L["flangeThicknessMm"]+2, x, y, -1))
    # One visible index flat; no string or load hook is provided by this flange.
    return result.cut(Part.makeBox(2, 4, 6, V(19, -2, -1))).removeSplitter()


def coupon():
    result = Part.makeBox(88, 24, 7)
    for x, diameter in zip((11, 33, 55, 77), CFG["acceptanceScenarios"]["fitCouponDiametersMm"]):
        result = result.cut(cylinder(diameter/2, 9, x, 12, -1))
        result = result.cut(cylinder(L["flangePocketDiameterMm"]/2, 1.3, x, 12, 5.7))
    return result.cut(Part.makeBox(2, 3, 9, V(0, 0, -1)))


def bearing_envelope():
    # Original dimensional ring envelopes; the manufacturer's joined internal
    # race model is deliberately not copied or used for mass.
    inner = disk(4.255, 5, 6)
    outer = disk(7, 4, 12.4).fuse(shifted(disk(7.5, 1, 12.4), (0, 0, 4)))
    shields = [shifted(disk(6.19, 0.12, 8.86), (0, 0, z)) for z in (0.3, 4.58)]
    return Part.makeCompound([inner, outer, *shields])


def collar_envelope():
    body = shifted(disk(9.5, 9, 6), (0, 0, -9.5))
    body = body.fuse(shifted(disk(4.5, 0.5, 6), (0, 0, -0.5)))
    body = body.cut(Part.makeBox(1.5, 8, 10, V(-0.75, 2.9, -9.5)))
    head = Part.makeCylinder(3.5, 4, V(-7.23, 5.44, -5), V(1, 0, 0))
    # Clamp screw shown as a separate assembly constituent; catalogue mass
    # already includes it. No second priced instance is added.
    return Part.makeCompound([body, head])


def hub_envelope():
    body = disk(16, 8).fuse(cylinder(7, 2, z=8))
    body = body.cut(shifted(d_shape(12, L["referenceClampedHubFlatFromCenterMm"]), (0, 0, -1)))
    for x in (-8, 8):
        for y in (-8, 8):
            body = body.cut(cylinder(1.65, 12, x, y, -1))
    # A bounding lip accounts for the supplied clamp-screw axial protrusion.
    lip = shifted(disk(15, 0.4, 24), (0, 0, -0.4))
    return body.fuse(lip).removeSplitter()


def nut_envelope():
    return hexagon(L["locknutAcrossFlatsMm"], L["locknutEnvelopeHeightMm"]).cut(
        cylinder(1.65, L["locknutEnvelopeHeightMm"]+2, z=-1))


class Model:
    def __init__(self):
        self.defs = {}
        self.instances = []
        self.world = {}
        self.doc = App.newDocument("CommonInputR4")
        self.counts = Counter()
        self.groups = {}
        for name in ("printed", "purchased"):
            self.groups[name] = self.doc.addObject("App::DocumentObjectGroup", name)

    def define(self, pid, shape, category, description, mass=None):
        if not shape.isValid() or not shape.Solids:
            raise RuntimeError(f"{pid}: invalid B-rep")
        if category == "printed" and len(shape.Solids) != 1:
            raise RuntimeError(f"{pid}: print is not a single connected solid")
        volume = sum(s.Volume for s in shape.Solids)
        center = sum((s.CenterOfMass*s.Volume for s in shape.Solids), V())/volume
        self.defs[pid] = {"shape": shape, "category": category, "description": description,
                          "mass_g": mass if mass is not None else volume*CFG["materials"]["printedDensityGPerCm3"]/1000,
                          "mass_basis": "catalogue purchased assembly" if mass is not None else "original CAD solid volume x assumed PETG density; not sliced/measured",
                          "solid_volume_mm3": volume, "solids": len(shape.Solids),
                          "local_center_of_mass_mm": list(center)}

    def add(self, pid, matrix, group, rotating=False, name=None):
        self.counts[pid] += 1
        name = name or f"{pid}_{self.counts[pid]:03}"
        d = self.defs[pid]
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = d["shape"]
        obj.Placement = App.Placement(App.Matrix(*[v for row in matrix for v in row])).multiply(obj.Placement)
        for prop, value in (("PartId", pid), ("RevisionId", CFG["revisionId"]),
                            ("Category", d["category"]), ("Specification", d["description"]),
                            ("AssemblyGroup", group), ("MassBasis", d["mass_basis"])):
            obj.addProperty("App::PropertyString", prop, "Cartridge")
            setattr(obj, prop, value)
        obj.addProperty("App::PropertyFloat", "NominalMassGram", "Cartridge")
        obj.NominalMassGram = d["mass_g"]
        self.groups[d["category"]].addObject(obj)
        self.instances.append({"name": name, "part_id": pid, "transform": matrix, "group": group,
                               "rotating": rotating})
        self.world[name] = placed(d["shape"], matrix)
        return name

    def ids(self, group):
        return [r["name"] for r in self.instances if r["group"] == group]


def construct():
    a = Model()
    for pid, shape, description in (
        ("P_CARRIER", carrier(), "One-piece rail carrier; locating flange clearance0.30mm and separate floating flange groove2mm travel. Horizontal bearing seats require fit coupon and inspection."),
        ("P_CAP", cap(), "3mm cover,central10.2 bore; bolts land on carrier,not bearing. No clamping contact with inner ring."),
        ("P_FLANGE", flange(), "Original40mm test flange4mm thick;14.3x2.15 pilot pocket,M4 four-hole16mm square. Index flat; no load hook or wind rotor."),
        ("Q_BEARING_FIT", coupon(), "Quantity0 coupon;14.0/14.15/14.3/14.45mm seats;100% scale only."),
    ):
        a.define(pid, shape, "printed", description)
    shapes = {"H_SHAFT": d_shape(L["shaftLengthMm"], L["shaftFlatFromCenterMm"]), "H_BEARING": bearing_envelope(),
              "H_COLLAR": collar_envelope(), "H_HUB": hub_envelope(),
              "H_SPACER": disk(L["spacerReferenceOuterDiameterMm"]/2, L["spacerLengthMm"], L["spacerReferenceInnerDiameterMm"]),
              "H_BOLT12": bolt(4, L["flangeScrewLengthMm"]), "H_BOLT20": bolt(4, L["capsScrewLengthMm"]),
              "H_WASHER": disk(L["washerOuterDiameterMm"]/2, L["washerThicknessMm"], L["washerInnerDiameterMm"]),
              "H_LOCKNUT": nut_envelope()}
    for p in CFG["parts"]:
        a.define(p["id"], shapes[p["id"]], "purchased", p["sku"]+": "+p["spec"], p["massG"])
    a.add("P_CARRIER", np.eye(4).tolist(), "carrier", name="CARRIER")
    cap_start = L["fixedHolderStartMm"]-L["coverThicknessMm"]
    a.add("H_BEARING", transform(L["fixedBearingStartMm"]+L["bearingWidthMm"], reverse=True),
          "locating_support", name="BEARING_LOC")
    a.add("H_BEARING", transform(L["floatingBearingStartMm"]), "floating_support", name="BEARING_FLOAT")
    a.add("P_CAP", transform(cap_start), "locating_support", name="CAP_LOC")
    a.add("P_CAP", transform(L["floatHolderEndMm"]), "floating_support", name="CAP_FLOAT")
    for side, group, underhead, back in (
        ("LOC", "locating_fasteners", cap_start-L["washerThicknessMm"], L["fixedHolderEndMm"]),
        ("FLOAT", "floating_fasteners", L["floatHolderEndMm"]+L["coverThicknessMm"]+L["washerThicknessMm"], L["floatHolderStartMm"])
    ):
        reverse = side == "FLOAT"
        for sign in (-1, 1):
            y = sign*L["coverBoltHalfPitchMm"]
            suffix = f"{side}_{'N' if sign < 0 else 'P'}"
            a.add("H_BOLT20", transform(underhead, y, reverse=reverse), group, name="SCREW_"+suffix)
            a.add("H_WASHER", transform(underhead, y, reverse=reverse), group, name="HEAD_WASHER_"+suffix)
            a.add("H_WASHER", transform(back, y, reverse=reverse), group, name="NUT_WASHER_"+suffix)
            a.add("H_LOCKNUT", transform(back+(-1 if reverse else 1)*L["washerThicknessMm"], y, reverse=reverse), group, name="NUT_"+suffix)
    a.add("H_SHAFT", transform(), "shaft", rotating=True, name="SHAFT")
    a.add("H_SPACER", transform(L["outerSpacerStartMm"]), "locating_rotating", rotating=True, name="SPACER_OUT")
    a.add("H_SPACER", transform(L["innerSpacerStartMm"]), "locating_rotating", rotating=True, name="SPACER_IN")
    a.add("H_COLLAR", transform(L["outerCollarBossFaceMm"]), "locating_rotating", rotating=True, name="COLLAR_OUT")
    a.add("H_COLLAR", transform(L["innerCollarBossFaceMm"], reverse=True), "locating_rotating", rotating=True, name="COLLAR_IN")
    a.add("H_HUB", transform(L["hubBodyStartMm"]), "flange_unit", rotating=True, name="D_HUB")
    flange_start = L["hubBodyStartMm"]+L["hubBodyWidthMm"]
    a.add("P_FLANGE", transform(flange_start), "flange_unit", rotating=True, name="TEST_FLANGE")
    half = L["hubHoleSquareMm"]/2
    for i, (y, z) in enumerate(((-half, -half), (-half, half), (half, -half), (half, half))):
        a.add("H_WASHER", transform(flange_start+L["flangeThicknessMm"], y, H+z),
              "flange_unit", True, "FLANGE_WASHER_"+str(i))
        a.add("H_BOLT12", transform(flange_start+L["flangeThicknessMm"]+L["washerThicknessMm"], y, H+z, reverse=True),
              "flange_unit", True, "FLANGE_SCREW_"+str(i))
    for p in CFG["parts"]:
        if a.counts[p["id"]] != p["quantity"]:
            raise RuntimeError(f"Bill of materials mismatch for {p['id']}")
    return a


def normalize_vendor(directory):
    raw = {name: Part.read(str(directory/f"{name}.step"))
           for name in ("bearing", "collar", "shaft", "hub", "spacer")}
    bearing = raw["bearing"].copy()
    bearing.rotate(V(), V(1, 0, 0), 90)
    collar = raw["collar"].copy()
    cb = collar.Solids[0]
    bore = next(f.Surface for f in cb.Faces if isinstance(f.Surface, Part.Cylinder)
                and abs(f.Surface.Radius-3) < 1e-6 and abs(f.Surface.Axis.y) > .999)
    collar.translate(V(-bore.Center.x, -cb.BoundBox.YMax, -bore.Center.z))
    collar.rotate(V(), V(1, 0, 0), 90)
    shaft = raw["shaft"].copy()
    shaft.rotate(V(), V(1, 0, 0), 90)
    shaft.rotate(V(), V(0, 0, 1), -45)
    hub = raw["hub"].copy()
    hs = hub.Solids[0]
    axis = next(f.Surface.Center for f in hs.Faces if isinstance(f.Surface, Part.Cylinder)
                and abs(f.Surface.Radius-3) < 1e-6 and abs(f.Surface.Axis.z) > .999)
    zbase = min(f.CenterOfMass.z for f in hs.Faces if isinstance(f.Surface, Part.Plane)
                and f.BoundBox.ZLength < 1e-6 and f.Area > 100)
    hub.translate(V(-axis.x, -axis.y, -zbase))
    spacer = raw["spacer"].copy()
    spacer.rotate(V(), V(1, 0, 0), 90)
    spacer.translate(V(0, 0, -spacer.BoundBox.ZMin))
    return {"H_BEARING": bearing, "H_COLLAR": collar, "H_SHAFT": shaft, "H_HUB": hub, "H_SPACER": spacer}


def common_volume(a, b):
    ba, bb = a.BoundBox, b.BoundBox
    if (ba.XMax < bb.XMin or bb.XMax < ba.XMin or ba.YMax < bb.YMin or bb.YMax < ba.YMin
            or ba.ZMax < bb.ZMin or bb.ZMax < ba.ZMin):
        return 0.0
    return float(a.common(b).Volume)


def validate(a, vendor):
    real = {r["name"]: placed(vendor[r["part_id"]], r["transform"]) if r["part_id"] in vendor
            else a.world[r["name"]] for r in a.instances}
    accepted, faults = [], []
    pairs = 0
    for i, left in enumerate(a.instances):
        for right in a.instances[i+1:]:
            first, second = left["name"], right["name"]
            volume = common_volume(real[first], real[second])
            pairs += 1
            if volume <= 1e-6:
                continue
            allowed = ({first, second} == {"SHAFT", "D_HUB"}
                       or (first.startswith("FLANGE_SCREW_") and second == "D_HUB")
                       or (second.startswith("FLANGE_SCREW_") and first == "D_HUB")
                       or (first.startswith("SCREW_") and second == "NUT_"+first[6:])
                       or (second.startswith("SCREW_") and first == "NUT_"+second[6:]))
            row = {"first": first, "second": second, "volume_mm3": volume}
            (accepted if allowed else faults).append(row)
    if faults:
        raise RuntimeError("Unexpected assembled intersections: "+json.dumps(faults))
    static_names = [r["name"] for r in a.instances if not r["rotating"]]
    rotating_names = [r["name"] for r in a.instances if r["rotating"]]
    sweep_count = 0
    closest = {"mm": float("inf")}
    for degree in range(0, 360, 15):
        for name in rotating_names:
            moving = turn(real[name], degree)
            for other in static_names:
                sweep_count += 1
                if common_volume(moving, real[other]) > 1e-6:
                    raise RuntimeError(f"Rotation collision: {name}/{other}/{degree}deg")
                if other in ("CARRIER", "CAP_LOC", "CAP_FLOAT"):
                    gap = moving.distToShape(real[other])[0]
                    if gap < closest["mm"]:
                        closest = {"mm": gap, "moving": name, "fixed": other, "angle_deg": degree}
    # The flange groove, not an axial clamp, captures the floating outer ring.
    extrema = []
    for dx in (-1, -0.5, 0, 0.5, 1):
        moving = shifted(real["BEARING_FLOAT"], (dx, 0, 0))
        overlap = sum(common_volume(moving, real[n]) for n in ("CARRIER", "CAP_FLOAT"))
        if overlap > 1e-6:
            raise RuntimeError("Floating outer ring path interferes")
        extrema.append({"bearing_dx_mm": dx, "overlap_mm3": overlap})
    fixed_positions = []
    for dx in (-0.3, -0.15, 0):
        moving = shifted(real["BEARING_LOC"], (dx, 0, 0))
        overlap = sum(common_volume(moving, real[n]) for n in ("CARRIER", "CAP_LOC"))
        if overlap > 1e-6:
            raise RuntimeError("Fixed outer-ring capture path clamps the flange")
        fixed_positions.append({"bearing_dx_mm": dx, "overlap_mm3": overlap})
    paths = []

    def path(name, moving_ids, remaining_ids, direction, offsets, exceptions=()):
        maximum = 0.0
        for distance in offsets:
            for moving_id in moving_ids:
                moved = shifted(real[moving_id], tuple(distance*x for x in direction))
                for other in remaining_ids:
                    if (moving_id, other) in exceptions:
                        continue
                    overlap = common_volume(moved, real[other])
                    maximum = max(maximum, overlap)
                    if overlap > 1e-6:
                        raise RuntimeError(f"Path collision {name}/{moving_id}/{other}/{distance}: {overlap}")
        paths.append({"id": name, "moving": moving_ids, "remaining": remaining_ids,
                      "direction": direction, "offsets_mm": offsets, "maximum_unintended_overlap_mm3": maximum,
                      "excluded_manufacturer_fit_interfaces": [list(x) for x in exceptions],
                      "method": "sampled rigid insertion/removal using actual vendor B-rep where available"})

    sample = [0, 0.5, 1, 2, 4, 8, 16, 32, 64, 128]
    path("fixed_bearing_before_cap", ["BEARING_LOC"], ["CARRIER"], [-1, 0, 0], sample)
    path("floating_bearing_before_cap", ["BEARING_FLOAT"], ["CARRIER"], [1, 0, 0], sample)
    path("fixed_cap_before_shaft_stack", ["CAP_LOC"], ["CARRIER", "BEARING_LOC"], [-1, 0, 0], sample[:8])
    path("float_cap_before_shaft", ["CAP_FLOAT"], ["CARRIER", "BEARING_FLOAT"], [1, 0, 0], sample[:8])
    rest = [r["name"] for r in a.instances if r["name"] != "SHAFT"]
    path("shaft_left_with_clamps_released", ["SHAFT"], rest, [-1, 0, 0], [0, 2, 5, 10, 20, 40, 60, 90, 122],
         [("SHAFT", "D_HUB")])
    flange_ids = a.ids("flange_unit")
    without_shaft = [r["name"] for r in a.instances if r["name"] not in ["SHAFT", *flange_ids]]
    path("preassembled_flange_unit_up_after_shaft_removal", flange_ids, without_shaft, [0, 0, 1], sample)
    # Cover nuts are tightened before the flange unit and collars are inserted.
    tools = []
    for side, sign, x, exclude_group in (("LOC", 1, 28.2, "locating_fasteners"),
                                        ("FLOAT", -1, 84.8, "floating_fasteners")):
        obstacles = ["CARRIER", "CAP_LOC", "CAP_FLOAT", "BEARING_LOC", "BEARING_FLOAT"]
        for y in (-18, 18):
            tool = Part.makeCylinder(6, 28, V(x, y, H), V(sign, 0, 0))
            overlap = sum(common_volume(tool, real[name]) for name in obstacles)
            if overlap > 1e-6:
                raise RuntimeError("7mm nut-driver access blocked before rotor installation")
            tools.append({"stage": "caps_before_rotating_stack", "side": side, "y_mm": y,
                          "tool": "12mm OD x28mm axial nut-driver clearance envelope",
                          "overlap_mm3": overlap})
    for i in range(4):
        item = next(r for r in a.instances if r["name"] == "FLANGE_SCREW_"+str(i))
        y, z = item["transform"][1][3], item["transform"][2][3]
        tool = Part.makeCylinder(2, 26, V(52.1, y, z), V(1, 0, 0))
        overlaps = [common_volume(tool, s) for name, s in real.items() if name != item["name"]]
        if max(overlaps) > 1e-6:
            raise RuntimeError("Flange3mm hex-key path is blocked")
        tools.append({"stage": "assembled_flange", "fastener": item["name"],
                      "tool": "4mm diameter x26mm axial key-shank envelope", "overlap_mm3": max(overlaps)})
    for name in ("D_HUB", "COLLAR_OUT", "COLLAR_IN"):
        for screw_index, screw in enumerate(real[name].Solids[1:], start=1):
            planes = [f for f in screw.Faces if isinstance(f.Surface, Part.Plane)]
            face = max(planes, key=lambda f: f.Area)
            normal = face.normalAt(0, 0)
            start = face.CenterOfMass+normal*0.1
            tool = Part.makeCylinder(2, 28, start, normal)
            chosen = None
            for degree in range(0, 360, 15):
                rotation = App.Rotation(V(1, 0, 0), degree)
                if rotation.multVec(normal).z < 0.2:
                    continue
                moved_tool = turn(tool, degree)
                obstacles = [turn(s, degree) if other in rotating_names else s
                             for other, s in real.items() if other != name]
                obstacles += [turn(s, degree) for j, s in enumerate(real[name].Solids) if j != screw_index]
                maximum = max(common_volume(moved_tool, s) for s in obstacles)
                if maximum <= 1e-6:
                    chosen = {"stage": "supported_stopped_shaft", "purchased_assembly": name,
                              "included_screw_index": screw_index, "shaft_angle_deg": degree,
                              "tool": "4mm diameter x28mm key-shank envelope toward upper half-space",
                              "overlap_mm3": maximum, "requires_all_rotating_parts_turned_together": True}
                    break
            if chosen is None:
                raise RuntimeError(f"No upper-access clamp-key pose: {name}/{screw_index}")
            tools.append(chosen)
    axial_sweep = []
    for dx in (-0.6, 0, 0.15):
        minimum = float("inf")
        for degree in range(0, 360, 30):
            for name in rotating_names:
                moved = shifted(turn(real[name], degree), (dx, 0, 0))
                for other in ("CARRIER", "CAP_LOC", "CAP_FLOAT"):
                    if common_volume(moved, real[other]) > 1e-6:
                        raise RuntimeError("Axial tolerance position produces printed-part rubbing")
                    minimum = min(minimum, moved.distToShape(real[other])[0])
        axial_sweep.append({"whole_rotating_stack_dx_mm": dx, "angle_step_deg": 30,
                            "minimum_printed_clearance_mm": minimum})
    contacts = []
    for name, end in (("SPACER_OUT", 14), ("SPACER_IN", 19)):
        b = real["BEARING_LOC"]
        inner = [f for f in b.Faces if isinstance(f.Surface, Part.Plane)
                 and abs(f.CenterOfMass.x-end) < 1e-6 and f.BoundBox.XLength < 1e-6
                 and 15 < f.Area < 25 and f.BoundBox.YLength < 10]
        if len(inner) != 1:
            raise RuntimeError("Unable to identify unique real inner-ring end face")
        contact = real[name].common(inner[0]).Area
        if contact < 10:
            raise RuntimeError("Stock spacer lacks the intended inner-ring contact")
        other_planes = [f for f in b.Faces if isinstance(f.Surface, Part.Plane)
                        and f.BoundBox.XLength < 1e-6 and f.BoundBox.YLength > 10]
        other_clearance = min(real[name].distToShape(f)[0] for f in other_planes)
        if other_clearance < 0.15:
            raise RuntimeError("Stock spacer lacks clearance to non-inner axial faces")
        contacts.append({"spacer": name, "bearing_end_x_mm": end, "inner_end_contact_area_mm2": contact,
                         "minimum_to_non_inner_axial_faces_mm": other_clearance})
    return {
        "revisionId": CFG["revisionId"], "static_pairs_checked": pairs,
        "documented_nominal_interface_overlaps": accepted, "unexpected_intersections": faults,
        "rotation_samples_deg": list(range(0, 360, 15)), "rotation_pair_checks": sweep_count,
        "minimum_rotating_to_printed_clearance": closest,
        "floating_ring_positions": extrema, "locating_ring_positions": fixed_positions,
        "insertion_paths": paths, "tool_access": tools, "spacer_inner_contacts": contacts,
        "rotating_axial_extrema": axial_sweep,
        "fit": {"manufacturer_designated_d_pair": True, "d_hub_geometry_rescaled": False,
                "reference_state_or_tolerances_published": None,
                "physical_hub_fit": "UNKNOWN", "clamp_screws_released_for_removal": True},
        "vendorSourceHashes": {name+".step": sha(args.vendor_dir/(name+".step"))
                              for name in ("bearing", "shaft", "collar", "hub", "spacer")},
        "supplierCadRedistributed": False,
        "limits": ["Samples are not continuous collision proof.", "Tool envelopes are acceptance sizes, not every tool.",
                   "Thread engagement and the manufacturer-specified D clamp interface are not validated as slip fits by nominal overlap.",
                   "No physical preload, printed-seat fit, drag, strength, rotor or walking qualification."]
    }


def stages(a):
    def step(sid, title, kind, added, note, direction):
        fasteners = Counter(r["part_id"] for r in a.instances if r["name"] in added
                            and r["part_id"] in ("H_BOLT12", "H_BOLT20", "H_WASHER", "H_LOCKNUT"))
        tools = ["3mm hex key", "7mm nut driver/wrench"] if "fasteners" in kind else []
        if sid == "04":
            tools = ["3mm hex key"]
        if sid in ("06", "07", "08"):
            tools = ["2.5mm hub clamp key", "3mm collar clamp key"]
        return {"id": sid, "title": title, "kind": kind, "add": added, "temporarily_removed": [],
                "reinserted": [], "tools": tools,
                "approachFromDirection": direction,
                "direction": [-v for v in direction] if direction else None,
                "directionMeaning": "travel toward the final assembly position; access JSON separately records reverse/removal travel",
                "externalFastenersAdded": dict(fasteners), "cautions": [note]}
    return [
        step("01", "試験片とキャリア確認", "fixture", a.ids("carrier"),
             "Quantity0 fit coupon first. Mounting holes are not a bench fixation authorization.", None),
        step("02", "固定側軸受と押さえ", "fasteners", a.ids("locating_support")+a.ids("locating_fasteners"),
             "Bearing first from-X, cap next. Cap contacts carrier lands, not the inner ring. Bolt torque is not a bearing-preload setting.", [-1, 0, 0]),
        step("03", "浮動側軸受と押さえ", "fasteners", a.ids("floating_support")+a.ids("floating_fasteners"),
             "Bearing from+X; flange stays free in its longer groove. Verify float rather than tightening away the gap.", [1, 0, 0]),
        step("04", "ハブと試験フランジを先組み", "bench_subassembly_at_final_pose", a.ids("flange_unit"),
             "FourM4x12 and washers before placing between supports. Shown at final position, not pre-attached to shaft.", [0, 0, 1]),
        step("05", "固定側だけへ2スペーサーと2カラー", "loose_subassembly", a.ids("locating_rotating"),
             "Do not put the second collar at the floating bearing. Pieces are supported while the shaft is absent.", None),
        step("06", "左から軸を挿入", "shaft_insertion", a.ids("shaft"),
             "Release both hub pinch screws and collars. Follow the vendor D-profile index; do not force or resize the supplied hub.", [-1, 0, 0]),
        step("07", "すきまと工具経路を確認", "inspection", [],
             "Set0.10–0.30mm total locating inner-stack play and confirm outer-ring float after tightening. No powered or string-load test authorized.", None),
        step("08", "逆順で脱着", "removal_reference", [],
             "Release clamps, withdraw shaft toward-X, then lift flange unit+Z. Never try to pass the32mm hub through a6mm bearing.", None),
    ]


def export(a, report):
    for path in (OUT, CAD, PRINT):
        path.mkdir(parents=True, exist_ok=True)
    a.doc.recompute()
    native = CAD/"CommonInputR4.FCStd"
    temporary = CAD/"CommonInputR4.new.FCStd"
    a.doc.saveAs(str(temporary))
    temporary.replace(native)
    features = [o for o in a.doc.Objects if o.TypeId == "Part::Feature"]
    step_path = CAD/"CommonInputR4.step"
    Part.export(features, str(step_path))
    step_path.write_text("\n".join(line.rstrip() for line in step_path.read_text().splitlines())+"\n")
    meshes, definitions, printed_mass = {}, {}, 0.0
    for pid, d in a.defs.items():
        vertices, faces = d["shape"].tessellate(0.10)
        meshes[pid] = {"vertices": [list(v) for v in vertices], "triangles": faces,
                       "category": d["category"]}
        definitions[pid] = {k: v for k, v in d.items() if k != "shape"}
        if d["category"] == "printed":
            shape = d["shape"].copy()
            shape.translate(V(0, 0, -shape.BoundBox.ZMin))
            mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.08,
                                         AngularDeflection=0.12, Relative=False)
            mesh.write(str(PRINT/(pid+".stl")))
            printed_mass += a.counts[pid]*d["mass_g"]
    payload = json.dumps(meshes, separators=(",", ":"), allow_nan=False).encode()
    with (CAD/"render_geometry.json.gz").open("wb") as stream:
        stream.write(gzip.compress(payload, mtime=0))
    accounting = cost(CFG, printed_mass, a.defs["Q_BEARING_FIT"]["mass_g"])
    procedure = stages(a)
    membership = [name for step in procedure for name in step["add"]]
    if sorted(membership) != sorted(a.world) or len(membership) != len(set(membership)):
        raise RuntimeError("Assembly stages do not add every instance exactly once")
    manifest = {
        "revisionId": CFG["revisionId"], "id": "COMMON_INPUT_R4", "units": "mm",
        "coordinates": "X shaft, Y lateral, Z up; row-major rigid transforms, no scale",
        "design": CFG, "parts": definitions, "instances": a.instances,
        "cad_meshes": str((CAD/"render_geometry.json.gz").relative_to(ROOT)),
        "assemblyStages": procedure, "printCoupons": ["Q_BEARING_FIT"],
        "mass": accounting, "geometryOrigin": "original procedural solids and dimensional envelopes; no vendor B-rep copied",
        "qualifiedWalkingPrototypeCount": 0, "physicalLowDragCertification": False,
    }
    write_json(OUT/"assembly.json", manifest)
    write_json(OUT/"assembly_access.json", report)
    write_json(OUT/"tolerance_stack.json", stack_contract(CFG))
    write_json(OUT/"shaft_mechanics.json", mechanics(CFG))
    write_json(OUT/"procurement.json", accounting)
    stock = {p["id"]: p for p in accounting["purchasedRows"]}
    with (OUT/"BOM.csv").open("w", newline="") as stream:
        w = csv.writer(stream, lineterminator="\n")
        w.writerow(["part_id", "category", "assembly_qty", "sku", "purchase_packs", "purchase_pieces",
                    "minimum_lot_usd", "unit_mass_g", "assembly_mass_g", "mass_basis", "spec", "source"])
        for pid, d in definitions.items():
            q, p = a.counts[pid], stock.get(pid, {})
            w.writerow([pid, d["category"], q, p.get("sku", ""), p.get("purchasePacks", ""),
                        p.get("purchaseQuantity", ""), p.get("subtotalUsd", ""), d["mass_g"], q*d["mass_g"],
                        d["mass_basis"], d["description"], p.get("url", "")])
    expected = sum(sum(s.Volume for s in shape.Solids) for shape in a.world.values())
    count = sum(len(s.Solids) for s in a.world.values())
    App.closeDocument(a.doc.Name)
    reopened = App.openDocument(str(native))
    actual_objects = [o for o in reopened.Objects if o.TypeId == "Part::Feature"]
    if len(actual_objects) != len(a.instances) or any(not o.Shape.isValid() for o in actual_objects):
        raise RuntimeError("Native document reopen failed")
    placement_error = 0.0
    for obj in actual_objects:
        expected_box, actual_box = a.world[obj.Name].BoundBox, obj.Shape.BoundBox
        placement_error = max(placement_error, max(abs(getattr(expected_box, key)-getattr(actual_box, key))
                                                   for key in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax")))
    if placement_error > 1e-8:
        raise RuntimeError("Reopened native placements differ from the checked world solids")
    exchange = Part.read(str(CAD/"CommonInputR4.step"))
    error = abs(sum(s.Volume for s in exchange.Solids)-expected)/expected
    if len(exchange.Solids) != count or error > 1e-6 or not exchange.isValid():
        raise RuntimeError("STEP does not match the original native solids")
    App.closeDocument(reopened.Name)
    summary = {"revisionId": CFG["revisionId"], "nativeObjectCount": len(actual_objects),
               "nativeSolidCount": count, "stepSolidCount": len(exchange.Solids),
               "stepRelativeVolumeError": error, "parts": len(definitions), "instances": len(a.instances),
               "nativePlacementMaxBoundErrorMm": placement_error,
               "printedBodyCount": sum(a.counts[p] for p, d in definitions.items() if d["category"] == "printed"),
               "printedSolidMassG": printed_mass, "purchasedCatalogueMassG": accounting["purchasedCatalogueMassG"],
               "totalNominalMassG": accounting["wholeCartridgeNominalMassG"],
               "originalFourSkuReferenceMassG": 59, "purchasedMinimumLotUsd": accounting["purchasedMinimumLotUsd"],
               "isManufacturingRelease": False, "measuredDragNmm": None}
    write_json(OUT/"cad_validation.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return manifest


if __name__ == "__main__":
    stack_contract(CFG)
    model = construct()
    vendor_shapes = normalize_vendor(args.vendor_dir)
    validation = validate(model, vendor_shapes)
    export(model, validation)
