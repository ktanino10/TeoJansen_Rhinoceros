"""Canonical geometry and structural sizing for one100mm wind module."""

import json
import math
from pathlib import Path

import numpy as np

from frame3d import solve_frame
from input_cartridge import ROOT, sha, write_json

INPUT = Path(__file__).with_suffix(".json")
OUT = ROOT/"docs/ver3/wind_module_r6"
CAD = ROOT/"FreeCAD/Ver.3/wind_module_r6"
PRINT = ROOT/"STL/Ver.3/wind_module_r6"
BASE = ROOT/"docs/ver3/common_input_r4"


def load():
    return json.loads(INPUT.read_text())


def blade_profile(cfg, angle_deg=0, thickness=None):
    rotor = cfg["rotor"]
    radius = np.linspace(rotor["centrelineInnerRadiusMm"], rotor["centrelineOuterRadiusMm"],
                         rotor["centrelineSamples"])
    theta = np.linspace(0, math.radians(rotor["sweepAngleDeg"]), len(radius))+math.radians(angle_deg)
    points = np.column_stack([radius*np.cos(theta), radius*np.sin(theta)])
    if thickness is None:
        return points
    tangent = np.diff(points, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    edge_normals = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    normals = np.empty_like(points)
    normals[0], normals[-1] = edge_normals[0], edge_normals[-1]
    # Miter offsets keep every side segment exactly parallel as thickness
    # changes, so the root tapers have planar rather than twisted loft faces.
    normals[1:-1] = ((edge_normals[:-1]+edge_normals[1:])
                    / (1+np.sum(edge_normals[:-1]*edge_normals[1:], axis=1))[:, None])
    outline = np.vstack([points+normals*thickness/2, (points-normals*thickness/2)[::-1]])
    if np.linalg.norm(outline, axis=1).max() > rotor["outerDiameterMm"]/2+1e-9:
        raise ValueError("The blade's real wall, not only its centerline, exceeds the100mm envelope")
    return outline


def holder_graph(cfg, side, braced):
    layout = json.loads((BASE/"assembly.json").read_text())["design"]["layout"]
    height = cfg["axisHeightMm"]
    if side == "fixed":
        start, end = layout["fixedHolderStartMm"], layout["fixedHolderEndMm"]
        bearing_x = layout["fixedBearingStartMm"]+layout["bearingWidthMm"]/2
        foot_x = cfg["holder"]["fixedBraceFootXmm"]
    elif side == "floating":
        start, end = layout["floatHolderStartMm"], layout["floatHolderEndMm"]
        bearing_x = layout["floatingBearingStartMm"]+layout["bearingWidthMm"]/2
        foot_x = cfg["holder"]["floatingBraceFootXmm"]
    else:
        raise ValueError(side)
    center_x, thickness = (start+end)/2, end-start
    count = cfg["holder"]["frameRingSegments"]
    nodes, members, fixed, ring = {}, [], [], []

    def member(a, b, width, depth, reference, kind):
        members.append(dict(a=a, b=b, width=width, thickness=depth, reference=reference, kind=kind))

    for i in range(count):
        theta = 2*math.pi*i/count
        name = f"ring{i}"
        nodes[name] = [center_x, 10*math.cos(theta), height+10*math.sin(theta)]
        ring.append(name)
    for i in range(count):
        member(ring[i], ring[(i+1)%count], cfg["holder"]["frameRingSectionRadialWidthMm"],
               thickness, [1, 0, 0], "bearing_boss_ring")
    if count != 12:
        raise ValueError("This frozen sizing model has twelve material-contained ring chords")
    junction_z = height-cfg["holder"]["braceJunctionHeightBelowAxisMm"]
    junction_y = 18+(6-18)*(junction_z-4)/(height-10-4)
    for sign in (-1, 1):
        suffix = "n" if sign < 0 else "p"
        root, junction, top = f"root_{suffix}", f"junction_{suffix}", f"top_{suffix}"
        nodes[root] = [center_x, sign*18, 4]
        nodes[junction] = [center_x, sign*junction_y, junction_z]
        nodes[top] = [center_x, sign*6, height-10]
        fixed.append(root)
        for a, b in ((root, junction), (junction, top)):
            member(a, b, cfg["holder"]["primaryLegWidthMm"], thickness, [1, 0, 0], "primary_leg")
        member(top, "ring8" if sign < 0 else "ring10",
               cfg["holder"]["frameRingSectionRadialWidthMm"], thickness, [1, 0, 0], "ring_leg_junction")
        if braced:
            anchor = f"brace_root_{suffix}"
            nodes[anchor] = [foot_x, sign*18, 4]
            fixed.append(anchor)
            member(anchor, junction, cfg["holder"]["braceSquareMm"],
                   cfg["holder"]["braceSquareMm"], [0, 1, 0], "axial_brace")
    return {"nodes": nodes, "members": members, "fixed": fixed, "ring": ring,
            "bearing_x": bearing_x, "center_x": center_x}


def holder_response(cfg, side, braced, force, modulus, subdivisions=1):
    graph = holder_graph(cfg, side, braced)
    force = np.array(force, float)
    offset = np.array([graph["bearing_x"]-graph["center_x"], 0, 0])
    moment = np.cross(offset, force)
    nodal = np.r_[force, moment]/len(graph["ring"])
    loads = {n: nodal.tolist() for n in graph["ring"]}
    result = solve_frame(graph["nodes"], graph["members"], graph["fixed"], loads,
                         modulus=modulus, poisson=cfg["holder"]["poissonAssumed"], subdivisions=subdivisions)
    displacements = np.array([result["displacements"][n] for n in graph["ring"]])
    ring_shift = displacements[:, :3].mean(axis=0)
    ring_rotation = displacements[:, 3:].mean(axis=0)
    offset_shift = np.cross(ring_rotation, offset)
    center_shift = ring_shift+offset_shift
    nodal_work = float(sum(np.dot(loads[n], result["displacements"][n]) for n in graph["ring"]))
    center_work = float(force@center_shift)
    if abs(nodal_work-center_work) > 1e-10:
        raise RuntimeError("Bearing-center displacement is not work-conjugate to the applied eccentric load")
    diameters = []
    for i in range(6):
        a, b = graph["ring"][i], graph["ring"][i+6]
        before = np.array(graph["nodes"][a])-graph["nodes"][b]
        after = before+np.array(result["displacements"][a][:3])-result["displacements"][b][:3]
        diameters.append(abs(np.linalg.norm(after)-np.linalg.norm(before)))
    result.update({"side": side, "braced": braced, "bearing_ring_nodes": graph["ring"],
                   "ring_plane_center_mm": [graph["center_x"], 0, cfg["axisHeightMm"]],
                   "bearing_center_mm": [graph["bearing_x"], 0, cfg["axisHeightMm"]],
                   "ring_plane_translation_mm": ring_shift.tolist(),
                   "ring_to_bearing_offset_mm": offset.tolist(),
                   "bearing_offset_rotation_translation_mm": offset_shift.tolist(),
                   "bearing_center_shift_mm": center_shift.tolist(),
                   "mean_ring_rotation_rad": ring_rotation.tolist(),
                   "equivalent_nodal_work_nmm": nodal_work,
                   "bearing_center_work_nmm": center_work,
                   "load_point_work_residual_nmm": abs(nodal_work-center_work),
                   "maximum_material_ring_diameter_change_mm": float(max(diameters)),
                   "boundary": cfg["holder"]["boundary"],
                   "load_application": "equal equivalent forces and eccentricity moments on material-contained boss ring nodes; translation is transported to the bearing center using mean rotation cross axial offset; local ball/race pressure not modeled"})
    return result


def size_holders(cfg):
    trials = []
    for braced in (False, True):
        for modulus in cfg["holder"]["EcasesMpa"]:
            for loadcase in cfg["holder"]["comparisonLoads"]:
                results = [holder_response(cfg, side, braced, loadcase[key], modulus)
                           for side, key in (("fixed", "fixedN"), ("floating", "floatingN"))]
                shift = np.array(results[1]["bearing_center_shift_mm"])-results[0]["bearing_center_shift_mm"]
                axial = max(abs(r["bearing_center_shift_mm"][0]) for r in results)
                radial_relative = float(np.linalg.norm(shift[1:]))
                stress = max(r["max_normal_stress_mpa"] for r in results)
                passed = (axial <= cfg["holder"]["holderAxialDeflectionBudgetMm"]
                          and radial_relative <= cfg["holder"]["radialRelativeShiftBudgetMm"]
                          and stress <= cfg["holder"]["stressScreenMpa"])
                trials.append({"braced": braced, "E_mpa": modulus, "loadcase": loadcase,
                               "maximum_bearing_axial_shift_mm": axial,
                               "relative_bearing_radial_shift_mm": radial_relative,
                               "maximum_normal_stress_mpa": stress, "conditional_budget_pass": passed,
                               "frames": results})
    bare_ok = all(t["conditional_budget_pass"] for t in trials if not t["braced"])
    braced_ok = all(t["conditional_budget_pass"] for t in trials if t["braced"])
    if not (bare_ok or braced_ok):
        raise RuntimeError("The one proposed brace size does not meet the absolute structural budgets")
    selected = not bare_ok
    refinements = []
    for side, force in (("fixed", [1, 0, 0]), ("floating", [0, 0, -1.2625])):
        coarse = holder_response(cfg, side, selected, force, 800)
        fine = holder_response(cfg, side, selected, force, 800, subdivisions=2)
        error = float(np.max(np.abs(np.array(coarse["bearing_center_shift_mm"])-fine["bearing_center_shift_mm"])))
        if error > 1e-7:
            raise RuntimeError("Frame subdivision changed the response")
        refinements.append({"side": side, "shift_difference_mm": error})
    return {"revisionId": cfg["revisionId"], "chosenBraces": selected,
            "selection": "minimum of only bare and four6x6mm braces, under unchanged loads/directions and absolute budgets",
            "trials": trials, "refinement": refinements,
            "physicalStructuralQualification": "UNKNOWN",
            "scope": "beam-frame surrogate with backed/clamped roots; actual base fixation, contact, stress concentration and FDM properties not certified"}


if __name__ == "__main__":
    cfg = load()
    result = size_holders(cfg)
    write_json(OUT/"holder_sizing.json", result)
    for trial in result["trials"]:
        if trial["E_mpa"] == 800:
            print(trial["braced"], trial["loadcase"]["id"],
                  trial["maximum_bearing_axial_shift_mm"], trial["relative_bearing_radial_shift_mm"],
                  trial["maximum_normal_stress_mpa"], trial["conditional_budget_pass"])
