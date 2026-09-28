"""Actual-mass/load screens for the one R6 module; no CFD or operating approval."""

from copy import deepcopy
import csv
import gzip
import json
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy.special import erf

from beam import d_section, rectangle_section, solve_beam, twist_bound
from commercial_r3 import RedesignedGait, rod_startup, torque_decomposition
from input_cartridge import write_json
from wind_module import BASE, CAD, OUT, ROOT, blade_profile, holder_response, load


def read_inputs():
    assembly = json.loads((OUT/"assembly.json").read_text())
    with gzip.open(ROOT/assembly["cad_meshes"], "rt") as stream:
        meshes = json.load(stream)
    with gzip.open(CAD/"analysis_geometry.json.gz", "rt") as stream:
        aux = json.load(stream)
    return assembly, meshes, aux


def proxy(cfg, rays=512):
    r, air = cfg["rotor"], cfg["loadCases"]["air"]
    centerline = blade_profile(cfg)/1000
    radius, span = r["centrelineOuterRadiusMm"]/1000, r["activeSpanMm"]/1000
    sigma, aim = air["sigmaMm"]/1000, air["aimRadiusFraction"]*r["outerDiameterMm"]/2000
    z = np.linspace(-radius, radius, rays, endpoint=False)+radius/rays
    q_area = (0.5*air["rhoKgM3"]*air["peakMS"]**2*sigma*math.sqrt(math.pi)
              * erf(span/(2*sigma))*2*radius/rays*np.exp(-((z-aim)/sigma)**2))
    rows = []
    for angle_deg in np.arange(0, 360, .5):
        angle = np.deg2rad(angle_deg+np.arange(r["bladeCount"])*360/r["bladeCount"])
        c, s = np.cos(angle), np.sin(angle)
        y = c[:, None]*centerline[None, :, 0]-s[:, None]*centerline[None, :, 1]
        zz = s[:, None]*centerline[None, :, 0]+c[:, None]*centerline[None, :, 1]
        points = np.stack([y, zz], axis=-1)
        start, delta = points[:, :-1].reshape(-1, 2), np.diff(points, axis=1).reshape(-1, 2)
        usable = np.abs(delta[:, 1]) > 1e-12
        fraction = np.zeros((len(start), len(z)))
        np.divide(z[None, :]-start[:, 1, None], delta[:, 1, None], out=fraction, where=usable[:, None])
        hit_y = np.where(usable[:, None] & (fraction >= 0) & (fraction < 1),
                         start[:, 0, None]+fraction*delta[:, 0, None], np.inf)
        index = np.argmin(hit_y, axis=0)
        hit_y = hit_y[index, np.arange(len(z))]
        hit = np.isfinite(hit_y)
        hit_y = np.where(hit, hit_y, 0)
        normal = np.column_stack([-delta[index, 1], delta[index, 0]])
        normal /= np.linalg.norm(normal, axis=1)[:, None]
        fy = air["panelCoefficientAssumed"]*q_area*normal[:, 0]**2*hit
        fz = air["panelCoefficientAssumed"]*q_area*normal[:, 0]*normal[:, 1]*hit
        torque = hit_y*fz-z*fy
        rows.append([float(angle_deg), float(torque.sum()), float(fy.sum()), float(fz.sum())])
    return np.array(rows)


def global_vertices(item, mesh):
    matrix = np.array(item["transform"])
    return np.array(mesh["vertices"])@matrix[:3, :3].T+matrix[:3, 3]


def extra_projected_drag(assembly, meshes, aux, cfg, pixel_mm=.5):
    """Prescribed-q silhouette upper load only; no extra driving torque credit."""
    xmin, zmin, xmax, zmax = -2, -2, 122, cfg["axisHeightMm"]+cfg["rotor"]["outerDiameterMm"]/2+2
    width, height = math.ceil((xmax-xmin)/pixel_mm), math.ceil((zmax-zmin)/pixel_mm)
    images = {key: Image.new("1", (width, height), 0) for key in ("rotating_extra", "fixed")}
    draws = {key: ImageDraw.Draw(image) for key, image in images.items()}
    h = cfg["axisHeightMm"]

    def project(points):
        return np.column_stack([(points[:, 0]-xmin)/pixel_mm, (points[:, 2]-zmin)/pixel_mm])

    def polygons(draw, vertices, triangles):
        xy = project(vertices)
        for triangle in triangles:
            draw.polygon([tuple(p) for p in xy[triangle]], fill=1)

    for item in assembly["instances"]:
        if item["name"] == "ROTOR":
            continue
        vertices = global_vertices(item, meshes[item["part_id"]])
        if item["rotating"]:
            # Swept circular envelope bounds all orientations of included
            # clamp screws. It is conservative silhouette drag, not actual Cp.
            radius = np.linalg.norm(vertices[:, 1:]-[0, h], axis=1).max()
            rect = project(np.array([[vertices[:, 0].min(), 0, h-radius],
                                     [vertices[:, 0].max(), 0, h+radius]]))
            draws["rotating_extra"].rectangle([tuple(rect[0]), tuple(rect[1])], fill=1)
        else:
            polygons(draws["fixed"], vertices, meshes[item["part_id"]]["triangles"])
    rotor_item = next(i for i in assembly["instances"] if i["name"] == "ROTOR")
    for key in ("root_plate", "end_ring"):
        polygons(draws["rotating_extra"], global_vertices(rotor_item, aux[key]), aux[key]["triangles"])
    xx = xmin+(np.arange(width)+.5)*pixel_mm
    zz = zmin+(np.arange(height)+.5)*pixel_mm
    x0 = cfg["rotor"]["startXmm"]+cfg["rotor"]["rootPlateMm"]+cfg["rotor"]["activeSpanMm"]/2
    z0 = h+cfg["loadCases"]["air"]["aimRadiusFraction"]*cfg["rotor"]["outerDiameterMm"]/2
    air = cfg["loadCases"]["air"]
    squared_velocity = air["peakMS"]**2*np.exp(-((xx[None, :]-x0)**2+(zz[:, None]-z0)**2)/air["sigmaMm"]**2)
    q_cells = .5*air["rhoKgM3"]*squared_velocity*(pixel_mm/1000)**2*air["panelCoefficientAssumed"]
    result = {}
    for key, image in images.items():
        force = q_cells*np.asarray(image, dtype=bool)
        total = float(force.sum())
        result[key] = {"side_force_n": total, "cop_x_mm": float((force*xx).sum()/total),
                       "cop_z_mm": float((force*zz[:, None]).sum()/total),
                       "silhouette_area_mm2": int(np.asarray(image, dtype=bool).sum())*pixel_mm**2}
    return {"method": "rasterized CAD/swept-part projected area under the same prescribed Gaussian q; flat-drag upper load proxy",
            "pixel_mm": pixel_mm, "loads": result,
            "not_credited_to_drive_torque": True,
            "limitations": "No solved airflow/pressure. Adding to vane proxy can double count shadowed flow; intentionally conservative support load, not additional captured power."}


def shaft_and_holders(assembly, cfg, rows, extra):
    supports = [(16.5, "translation"), (96.5, "translation")]
    gravity = cfg["loadCases"]["gravity"]
    zloads, static_mass = [], 0.0
    for item in assembly["instances"]:
        part = assembly["parts"][item["part_id"]]
        if item["rotating"] and item["name"] != "SHAFT":
            matrix = np.array(item["transform"])
            point = matrix@np.r_[part["local_center_of_mass_mm"], 1]
            zloads.append((float(point[0]), -part["mass_g"]/1000*gravity))
        elif not item["rotating"]:
            static_mass += part["mass_g"]/1000
    rotor_cop_x = cfg["rotor"]["startXmm"]+cfg["rotor"]["rootPlateMm"]+cfg["rotor"]["activeSpanMm"]/2
    zloads.append((rotor_cop_x, -float(np.abs(rows[:, 3]).max())))
    yloads = [(rotor_cop_x, float(rows[:, 2].max())),
              (extra["loads"]["rotating_extra"]["cop_x_mm"], extra["loads"]["rotating_extra"]["side_force_n"])]
    section = d_section(6, .5)
    zresult = solve_beam(120, 193000, section, zloads, supports,
                         distributed_load=-assembly["parts"]["H_SHAFT"]["mass_g"]/1000*gravity/120)
    yresult = solve_beam(120, 193000, section, yloads, supports)
    if len(zresult["reactions"]) != 2 or len(yresult["reactions"]) != 2:
        raise RuntimeError("Unexpected shaft reactions")
    static_wind = extra["loads"]["fixed"]
    beta = (static_wind["cop_x_mm"]-16.5)/80
    loads = []
    for i, side in enumerate(("fixed", "floating")):
        fy = -yresult["reactions"][i]["value_n_or_nmm"]+static_wind["side_force_n"]*(1-beta if i == 0 else beta)
        fz = -zresult["reactions"][i]["value_n_or_nmm"]-static_mass*gravity/2
        loads.append([0, fy, fz])
    cases = []
    for modulus in cfg["holder"]["EcasesMpa"]:
        for axial in (-1, 0, 1):
            applied = deepcopy(loads)
            applied[0][0] = axial
            frames = [holder_response(cfg, side, True, force, modulus)
                      for side, force in zip(("fixed", "floating"), applied)]
            shifts = np.array([r["bearing_center_shift_mm"] for r in frames])
            common_shift = shifts.mean(axis=0)
            differential = shifts[1]-shifts[0]
            max_axial = float(np.abs(shifts[:, 0]).max())
            shaft_axial_bound = abs(axial)*80/(193000*section.area)
            axial_differential_bound = abs(float(differential[0]))+shaft_axial_bound
            radial = float(np.linalg.norm(differential[1:]))
            relative_with_shaft = radial+math.hypot(zresult["max_deflection_mm"], yresult["max_deflection_mm"])
            alignment = []
            line_slopes = differential[1:]/(80+differential[0])
            for i, x in enumerate((16.5, 96.5)):
                y_field, z_field = np.array(yresult["field"]), np.array(zresult["field"])
                dy = float(y_field[np.argmin(np.abs(y_field[:, 0]-x)), 2])
                dz = float(z_field[np.argmin(np.abs(z_field[:, 0]-x)), 2])
                rotation = np.array(frames[i]["mean_ring_rotation_rad"])
                mismatch = line_slopes+[dy, dz]-np.array([rotation[2], -rotation[1]])
                alignment.append({"side": frames[i]["side"], "shaft_elastic_slopes_rad": [dy, dz],
                                  "support_line_slopes_rad": line_slopes.tolist(),
                                  "carrier_bore_rotation_rad": rotation.tolist(),
                                  "relative_axis_misalignment_rad": float(np.linalg.norm(mismatch)),
                                  "manufacturer_allowable_misalignment_rad": None,
                                  "qualification": "UNKNOWN; ring/bearing contact and supplier limit unavailable"})
            r4 = json.loads((BASE/"assembly.json").read_text())["design"]
            limits, layout = r4["acceptanceScenarios"], r4["layout"]
            fixed_allowance = (layout["fixedFlangeShoulderMm"]-layout["fixedHolderStartMm"]-1
                               +max(limits["fixedPocketDepthErrorMm"])-min(limits["flangeThicknessErrorMm"]))
            float_range = (layout["floatHolderEndMm"]-layout["floatFlangePocketStartMm"]-1
                           +min(limits["floatingPocketLengthErrorMm"])-max(limits["flangeThicknessErrorMm"])
                           -limits["capCompressionAllowanceMm"])
            required_float = (fixed_allowance+max(limits["collarGapTotalMm"])/2
                              +max(abs(v) for v in limits["supportSpacingErrorMm"])
                              +axial_differential_bound+cfg["holder"]["remainingThermalAndUnmodeledAxialBudgetMm"])
            partial_float_margin = float_range/2-required_float
            passes = (axial_differential_bound <= cfg["holder"]["holderAxialDeflectionBudgetMm"]
                      and relative_with_shaft <= cfg["holder"]["radialRelativeShiftBudgetMm"]
                      and max(r["max_normal_stress_mpa"] for r in frames) <= cfg["holder"]["stressScreenMpa"])
            cases.append({"E_mpa": modulus, "additional_fixed_axial_n": axial, "applied_ring_forces_n": applied,
                          "maximum_axial_shift_mm": max_axial,
                          "common_mode_bearing_translation_mm": common_shift.tolist(),
                          "differential_bearing_translation_mm": differential.tolist(),
                          "shaft_axial_extension_upper_mm": shaft_axial_bound,
                          "differential_axial_movement_plus_shaft_upper_mm": axial_differential_bound,
                          "relative_radial_shift_plus_shaft_upper_mm": relative_with_shaft,
                          "alignment": alignment,
                          "partial_float_stack_margin_mm": partial_float_margin,
                          "full_assembled_float_margin_status": "UNKNOWN",
                          "unquantified_stack_terms": ["load-dependent cap bending/separation and joint settlement",
                                                      "real bearing internal axial clearance and contact compliance",
                                                      "mating structure/fixing bolt movement",
                                                      "actual printed/purchased tolerances and thermal change"],
                          "conditional_budget_pass": passes, "frames": frames})
    if not all(c["conditional_budget_pass"] for c in cases):
        raise RuntimeError("The actual-mass wind/gravity cases exceed the selected brace/fit budget")
    return {"shaft_vertical": zresult, "shaft_lateral": yresult, "holder_cases": cases,
            "shaft_torsion": twist_bound(cfg["loadCases"]["shaftTorqueScreenNmm"], 80, 74000, section),
            "static_mass_applied_at_rings_kg": static_mass,
            "method_note": "actual nominal rotating mass on shaft; nonrotating mass conservatively applied half at each high ring, rather than at lower real attachment. Backed roots and fits remain assumptions."}


def rotor_screens(assembly, cfg, aux):
    r, loads = cfg["rotor"], cfg["loadCases"]
    density = loads["printDensityGPerCm3Assumed"]/1000
    blade_mass_kg = aux["one_blade"]["volume_mm3"]*density/1000
    blade_com = np.array(aux["one_blade"]["center_of_mass_mm"])
    com_radius_m = float(np.linalg.norm(blade_com[:2]))/1000
    arc_length = float(np.linalg.norm(np.diff(blade_profile(cfg), axis=0), axis=1).sum())
    chord = float(np.linalg.norm(blade_profile(cfg)[-1]-blade_profile(cfg)[0]))
    pressure = .5*loads["air"]["rhoKgM3"]*loads["air"]["peakMS"]**2
    one_blade_force = loads["air"]["panelCoefficientAssumed"]*pressure*arc_length*r["activeSpanMm"]/1e6
    root_span = r["outerDiameterMm"]/2-r["boltHoleSquareMm"]/math.sqrt(2)
    root_width = 6.0
    root_i = root_width*r["rootPlateMm"]**3/12
    blade_section = rectangle_section(chord, min(r["thicknessStationsMm"]))
    ring_span = math.pi*r["outerDiameterMm"]/r["bladeCount"]
    ring_section = rectangle_section((r["outerDiameterMm"]-r["endRingBoreMm"])/2, r["endRingThicknessMm"])
    scenarios = []
    for modulus in cfg["holder"]["EcasesMpa"]:
        for rpm in loads["speedRpmSensitivity"]:
            omega = rpm*2*math.pi/60
            centrifugal = blade_mass_kg*com_radius_m*omega**2
            force = one_blade_force+blade_mass_kg*loads["gravity"]+centrifugal
            span = r["activeSpanMm"]
            blade = solve_beam(span, modulus, blade_section, [(span, force)],
                               [(0, "translation"), (0, "rotation")])
            moment = force*span
            root_shift = moment*root_span**2/(2*modulus*root_i)
            root_rotation = moment*root_span/(modulus*root_i)
            root_stress = moment*r["rootPlateMm"]/2/root_i
            combined = blade["max_deflection_mm"]+root_rotation*span
            ring = solve_beam(ring_span, modulus, ring_section, [(ring_span/2, loads["axialScreenN"])],
                              [(0, "translation"), (ring_span, "translation")])
            hoop_proxy = loads["printDensityGPerCm3Assumed"]*1000*omega**2*(r["outerDiameterMm"]/2000)**2/1e6
            scenarios.append({"E_mpa": modulus, "rpm_prescribed_not_predicted": rpm,
                              "wind_force_one_blade_upper_n": one_blade_force,
                              "blade_gravity_n": blade_mass_kg*loads["gravity"],
                              "centrifugal_force_one_blade_n": centrifugal,
                              "blade_tip_deflection_mm": blade["max_deflection_mm"],
                              "blade_bending_stress_mpa": blade["max_bending_stress_mpa"],
                              "root_strip_shift_mm": root_shift, "root_strip_rotation_rad": root_rotation,
                              "root_strip_bending_stress_mpa": root_stress,
                              "blade_tip_with_root_rotation_mm": combined,
                              "end_ring_axial_point_load_deflection_mm": ring["max_deflection_mm"],
                              "end_ring_bending_stress_mpa": ring["max_bending_stress_mpa"],
                              "end_ring_self_hoop_stress_proxy_mpa": hoop_proxy,
                              "physical_strength_status": "UNKNOWN"})
    bolt_radius = r["boltHoleSquareMm"]/math.sqrt(2)
    bolt_force = loads["shaftTorqueScreenNmm"]/(4*bolt_radius)
    return {"scenarios": scenarios, "root_strip_width_mm_assumed": root_width, "root_strip_span_mm": root_span,
            "one_blade_nominal_mass_g_from_cad": blade_mass_kg*1000,
            "fixing_bolt_torque_load_n_each": bolt_force,
            "printed_hole_nominal_bearing_stress_mpa": bolt_force/(4*r["rootPlateMm"]),
            "method": "slender blade at minimum1.2mm thickness, free-tip point load;6mm root tributary strip clamped at bolt circle;end-ring span simply supported. Root/far-ring restraint ignored for blade stiffness. NOT solid FDM FEM.",
            "limits": ["Root strip/support distribution is an engineering screening idealization, not a measured hub/plate contact.",
                       "Peak q is used only for a per-blade strength load, never as uniform-rotor available power.",
                       "Tapered2.4mm roots are in CAD but the thin1.2mm blade screen conservatively ignores their stiffness benefit.",
                       "No fatigue,creep,layer adhesion,local notch or safe/achievable RPM certification."]}


def budgets(assembly, cfg, rows, extra):
    rotating_mass = sum(assembly["parts"][i["part_id"]]["mass_g"] for i in assembly["instances"] if i["rotating"])/1000
    air = cfg["loadCases"]["air"]
    bare = []
    for bearing_nmm in cfg["loadCases"]["bearingPairBreakawayNmmSensitivity"]:
        for eccentric in cfg["loadCases"]["rotatingSystemEccentricityMmSensitivity"]:
            gravity = rotating_mass*cfg["loadCases"]["gravity"]*eccentric/1000*np.cos(np.deg2rad(rows[:, 0]))
            required = bearing_nmm/1000+gravity
            bare.append({"bearing_pair_nmm_assumed": bearing_nmm,
                         "rotating_system_cog_eccentricity_mm_assumed": eccentric,
                         "rotating_nominal_mass_kg": rotating_mass,
                         "raw_minimum_difference_nm": float((rows[:, 1]-required).min()),
                         "derated_minimum_difference_nm": float((air["deratingAssumed"]*rows[:, 1]-required).min()),
                         "gravity_unbalance_amplitude_nm": float(np.max(np.abs(gravity))),
                         "downstream_torque_nm": 0, "physical_start_status": "UNKNOWN"})
    r3 = json.loads((ROOT/"docs/ver3/commercial_basis_r3/candidate_C.json").read_text())
    r4 = json.loads((BASE/"assembly.json").read_text())
    old_input_without_flange = (r4["mass"]["wholeCartridgeNominalMassG"]-r4["parts"]["P_FLANGE"]["mass_g"])/1000
    residuals = [m-old_input_without_flange-r3["rotor_mass_proxy"]["mass_kg_proxy"] for m in r3["candidate"]["massCasesKg"]]
    design = deepcopy(r3["candidate"])
    design["massCasesKg"] = [m+assembly["mass"]["moduleNominalMassG"]/1000 for m in residuals]
    common = deepcopy(json.loads((ROOT/"scripts/ver3/study_r2.json").read_text())["common"])
    study = RedesignedGait(common, r3["linkage"], step_deg=.25)
    fy = float(rows[:, 2].max())+sum(x["side_force_n"] for x in extra["loads"].values())
    fz = float(np.abs(rows[:, 3]).max())
    loaded = []
    for case, label in enumerate(("low", "nominal", "high")):
        profile, reaction, required, metadata = rod_startup(study, design, common, case, fy, fz)
        decomposition = torque_decomposition(profile, required, design, common, case, metadata)
        crank = np.unique(np.r_[np.arange(0, 360, .5/25), profile[:, 0], 360])
        demand = np.interp(crank, np.r_[profile[:, 0], 360], np.r_[required, required[0]])
        supply = np.interp((25*crank) % 360, np.r_[rows[:, 0], 360], np.r_[rows[:, 1], rows[0, 1]])
        pair = common["bearingDragNmmCases"][case]*2/1000
        target = 2*(demand-pair)+pair
        loaded.append({"case": label, "whole_machine_mass_kg_assumed": design["massCasesKg"][case],
                       "decomposition_at_peak": decomposition,
                       "phase_relation": "input_deg=25*crank_deg,zero mounting index;16-blade90deg indices are equivalent",
                       "phase_samples": len(crank), "raw_one_times_minimum_difference_nm": float((supply-demand).min()),
                       "raw_design_target_minimum_difference_nm": float((supply-target).min()),
                       "derated_design_target_minimum_difference_nm": float((.5*supply-target).min()),
                       "physical_walking_status": "UNKNOWN"})
    return {"bare_module": bare, "conditional_C_downstream": loaded,
            "balance_scope": "Eccentricity is a prescribed sensitivity of the ENTIRE rotating mass, including purchased hardware. Ideal geometric rotor symmetry does not establish real assembled balance. Loaded C rows use ideal balance.",
            "mass_ledger": {"r4_input_without_test_flange_kg": old_input_without_flange,
                            "r3_rotor_proxy_removed_kg": r3["rotor_mass_proxy"]["mass_kg_proxy"],
                            "unbuilt_remaining_assembly_allowance_kg": residuals,
                            "actual_nominal_module_inserted_once_kg": assembly["mass"]["moduleNominalMassG"]/1000},
            "load_coupling_limits": "R3 link,gear ratio,target COM and friction assumptions retained; no actual downstreamCAD, gear alignment or ground-contact proof. Additional wind is a support-load envelope, not phase-resolved full airflow."}


def main():
    cfg = load()
    assembly, meshes, aux = read_inputs()
    rows = proxy(cfg)
    refined = proxy(cfg, rays=1024)
    ray_change = abs(refined[:, 1].min()/rows[:, 1].min()-1)
    if ray_change > .02:
        raise RuntimeError("Rotating-load quadrature needs refinement")
    extra = extra_projected_drag(assembly, meshes, aux, cfg)
    fine_extra = extra_projected_drag(assembly, meshes, aux, cfg, pixel_mm=.25)
    for key in extra["loads"]:
        relative = abs(fine_extra["loads"][key]["side_force_n"]/extra["loads"][key]["side_force_n"]-1)
        if relative > .08:
            raise RuntimeError("CAD projected-load raster is not sufficiently resolved")
    structure = shaft_and_holders(assembly, cfg, rows, fine_extra)
    screens = rotor_screens(assembly, cfg, aux)
    geometry = json.loads((OUT/"cad_validation.json").read_text())
    access = json.loads((OUT/"assembly_access.json").read_text())
    tip = max(row["blade_tip_with_root_rotation_mm"] for row in screens["scenarios"])
    axial_root = max(row["root_strip_shift_mm"] for row in screens["scenarios"])
    end_ring = max(row["end_ring_axial_point_load_deflection_mm"] for row in screens["scenarios"])
    axial_frame = max(c["differential_axial_movement_plus_shaft_upper_mm"] for c in structure["holder_cases"])
    tilt = max(a["relative_axis_misalignment_rad"] for c in structure["holder_cases"] for a in c["alignment"])
    axial_geometric = min(c["minimum_rigid_envelope_clearance_mm"] for c in access["rotor_axial_acceptance_extrema"])
    screens["partial_clearance_screen"] = {
        "undeformed_neighbor_gap_mm": geometry["minimum_neighboring_blade_gap_mm"],
        "two_opposite_blade_deflections_mm": 2*tip,
        "remaining_neighbor_gap_mm": geometry["minimum_neighboring_blade_gap_mm"]-2*tip,
        "rigid_axial_clearance_at_acceptance_extremes_mm": axial_geometric,
        "root_plate_axial_shift_mm": axial_root, "end_ring_deflection_mm": end_ring,
        "frame_differential_plus_shaft_mm": axial_frame, "tilt_times_outer_radius_mm": tilt*50,
        "remaining_partial_axial_clearance_mm": axial_geometric-axial_root-end_ring-axial_frame-tilt*50,
        "scope": "conservative sum of maxima from different prescribed screens; not one simultaneous equilibrium or complete manufacturing/operating clearance certificate"
    }
    if min(screens["partial_clearance_screen"]["remaining_neighbor_gap_mm"],
           screens["partial_clearance_screen"]["remaining_partial_axial_clearance_mm"]) < cfg["loadCases"]["smallestMovingClearanceMm"]:
        raise RuntimeError("The prescribed deformation screens consume the moving clearance allowance")
    budget = budgets(assembly, cfg, rows, fine_extra)
    with (OUT/"rotor_torque.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["rotor_deg", "raw_proxy_nm", "raw_rotor_fy_n", "raw_rotor_fz_n"])
        writer.writerows(rows)
    write_json(OUT/"wind_loads.json", {"revisionId": cfg["revisionId"], "rawMinimumNm": float(rows[:, 1].min()),
        "rawMaximumNm": float(rows[:, 1].max()), "angularStepDeg": .5, "rays": 512,
        "refinementMinTorqueRelativeChange": float(ray_change), "additionalDrag": fine_extra,
        "source": cfg["loadCases"]["air"],
        "method": "same uncalibrated first-hit normal panel drag, now using the canonical33-segment blade centerline. Taper thickness,pressure recovery,endplate torque and running flow not solved.",
        "measuredOrCertifiedLowerBoundNm": None})
    write_json(OUT/"actual_mass_support.json", {"revisionId": cfg["revisionId"], **structure})
    write_json(OUT/"rotor_strength_screens.json", {"revisionId": cfg["revisionId"], **screens})
    write_json(OUT/"supply_required.json", {"revisionId": cfg["revisionId"], **budget})
    print("raw supply min/max mNm", rows[:, 1].min()*1000, rows[:, 1].max()*1000)
    print("extra CAD silhouette loads", fine_extra["loads"])
    print("actual-mass maximum holder axial shift mm", max(c["maximum_axial_shift_mm"] for c in structure["holder_cases"]))
    print("C loaded nominal", budget["conditional_C_downstream"][1])


if __name__ == "__main__":
    main()
