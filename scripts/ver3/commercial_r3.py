"""A bounded common-dryer redesign; preserves every frozen R2 input/artifact."""

import argparse
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
from scipy.optimize import differential_evolution

from core import CONFIG, ROOT, dump
from study_r2 import (GaitStudy, beam_image, coupled_startup, gear_check, plot, svg, text,
                      reflect_loads, rib_section_screen, rotor_mass_proxy,
                      static_jet_proxy, structures, write_csv)

INPUT = Path(__file__).with_suffix(".json")
OUT = ROOT / "docs/ver3/commercial_basis_r3"
R2 = ROOT / "docs/ver3/feasibility_r2"
LENGTH_KEYS = ("QP", "OQ", "OA", "AB", "BP", "AC", "PC", "BD", "PD", "CE", "DE", "CF", "EF")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def circle_many(p, radius, q, other, branch):
    delta = q-p
    distance = np.linalg.norm(delta, axis=-1)
    margin = np.minimum(distance-abs(radius-other), radius+other-distance)
    if np.any(margin <= 0):
        raise ValueError("Non-closing or tangent linkage candidate")
    along = (radius**2-other**2+distance**2)/(2*distance)
    height = np.sqrt(radius**2-along**2)
    middle = p+along[..., None]*delta/distance[..., None]
    normal = np.stack([-delta[..., 1], delta[..., 0]], axis=-1)/distance[..., None]
    first, second = middle+height[..., None]*normal, middle-height[..., None]*normal
    axis = 0 if branch == "left" else 1
    choice = first[..., axis] < second[..., axis] if branch != "top" else first[..., axis] > second[..., axis]
    return np.where(choice[..., None], first, second), float(margin.min())


def points_many(theta, dimensions, scale):
    c = {key: dimensions[key]*scale for key in LENGTH_KEYS}
    theta = np.asarray(theta)
    p = np.broadcast_to([-c["QP"], -c["OQ"]], theta.shape+(2,))
    a = c["OA"]*np.stack([np.cos(theta), np.sin(theta)], axis=-1)
    b, mb = circle_many(a, c["AB"], p, c["BP"], "top")
    cc, mc = circle_many(a, c["AC"], p, c["PC"], "bottom")
    d, md = circle_many(b, c["BD"], p, c["PD"], "left")
    e, me = circle_many(cc, c["CE"], d, c["DE"], "bottom")
    f, mf = circle_many(cc, c["CF"], e, c["EF"], "bottom")
    return dict(O=np.zeros_like(a), P=p, A=a, B=b, C=cc, D=d, E=e, F=f), min(mb, mc, md, me, mf)


def fast_gait_metrics(dimensions, common, samples):
    theta = np.arange(samples)*2*math.pi/samples
    points, margin = points_many(theta, dimensions, common["linkageScale"])
    foot = points["F"]
    rates = (np.roll(foot, -1, axis=0)-np.roll(foot, 1, axis=0))/(4*math.pi/samples)
    ce = points["E"]-points["C"]
    angles = np.arctan2(ce[:, 1], ce[:, 0])
    delta_angles = np.angle(np.exp(1j*(np.roll(angles, -1)-np.roll(angles, 1))))
    beta_rate = delta_angles/(4*math.pi/samples)
    other = np.roll(foot, samples//2, axis=0)
    choose = foot[:, 1] <= other[:, 1]
    active = np.where(choose[:, None], foot, other)
    active_rates = np.where(choose[:, None], rates, np.roll(rates, samples//2, axis=0))
    beta = np.where(choose, beta_rate, np.roll(beta_rate, samples//2))
    forward = active_rates[:, 0]+common["footRadiusMm"]*beta
    switches = choose != np.roll(choose, 1)
    return {
        "samples": samples, "peak_stance_vertical_rate_mm_per_rad": float(np.abs(active_rates[:, 1]).max()),
        "rms_stance_vertical_rate_mm_per_rad": float(np.sqrt(np.mean(active_rates[:, 1]**2))),
        "body_bounce_mm": float(np.ptp(active[:, 1])),
        "swing_gap_max_mm": float(np.abs(foot[:, 1]-other[:, 1]).max()),
        "stance_stride_mm": float(np.ptp(active[:, 0])),
        "minimum_forward_rate_mm_per_rad": float(forward.min()),
        "horizontal_handoff_jump_mm_per_rad": float(np.abs(forward-np.roll(forward, 1))[switches].max()),
        "stance_switch_count": int(switches.sum()),
        "circle_tangency_margin_mm": margin,
    }


def optimize_linkage(cfg, common):
    setup = cfg["boundedLinkageSearch"]
    base = {key: CONFIG["linkage"][key] for key in LENGTH_KEYS}
    variables = list(setup["variableBoundsUnscaledMm"])
    rejected = {"closure": 0, "lift_stride_direction_clearance": 0}
    trials = []

    def objective(values):
        dimensions = {**base, **dict(zip(variables, map(float, values)))}
        try:
            result = fast_gait_metrics(dimensions, common, setup["angleSamples"])
        except ValueError:
            rejected["closure"] += 1
            return 1e6
        deficit = (max(0, setup["minimumSwingGapMm"]-result["swing_gap_max_mm"])
                   + max(0, setup["minimumStrideMm"]-result["stance_stride_mm"])
                   + max(0, setup["minimumForwardRateMmPerRad"]-result["minimum_forward_rate_mm_per_rad"])
                   + 10*max(0, setup["minimumCircleTangencyMarginMm"]-result["circle_tangency_margin_mm"]))
        score = (result["peak_stance_vertical_rate_mm_per_rad"]
                 + 0.3*result["rms_stance_vertical_rate_mm_per_rad"]
                 + 0.08*result["horizontal_handoff_jump_mm_per_rad"]+100*deficit)
        if deficit:
            rejected["lift_stride_direction_clearance"] += 1
        trials.append([*map(float, values), score, deficit])
        return score

    original = fast_gait_metrics(base, common, setup["refinedAngleSamples"])
    fit = differential_evolution(objective, list(setup["variableBoundsUnscaledMm"].values()),
                                 seed=setup["seed"], popsize=setup["populationMultiplier"],
                                 maxiter=setup["maximumIterations"], polish=False, workers=1)
    continuous = {**base, **dict(zip(variables, map(float, fit.x)))}
    rounding_candidates = {}
    scale = common["linkageScale"]
    for trial in trials:
        rounded = tuple(round(value*scale, 1)/scale for value in trial[:len(variables)])
        if rounded in rounding_candidates:
            continue
        dimensions = {**base, **dict(zip(variables, rounded))}
        try:
            result = fast_gait_metrics(dimensions, common, setup["refinedAngleSamples"])
        except ValueError:
            continue
        if (result["swing_gap_max_mm"] < setup["minimumSwingGapMm"]
                or result["stance_stride_mm"] < setup["minimumStrideMm"]
                or result["minimum_forward_rate_mm_per_rad"] < setup["minimumForwardRateMmPerRad"]
                or result["circle_tangency_margin_mm"] < setup["minimumCircleTangencyMarginMm"]
                or result["stance_switch_count"] != 2):
            continue
        score = (result["peak_stance_vertical_rate_mm_per_rad"]
                 + 0.3*result["rms_stance_vertical_rate_mm_per_rad"]
                 + 0.08*result["horizontal_handoff_jump_mm_per_rad"])
        rounding_candidates[rounded] = (score, result)
    if not rounding_candidates:
        raise RuntimeError("No already-explored candidate survives 0.1mm physical pitch rounding")
    rounded, (_, fine) = min(rounding_candidates.items(), key=lambda item: item[1][0])
    chosen = {**base, **dict(zip(variables, rounded))}
    admissible = (fine["swing_gap_max_mm"] >= setup["minimumSwingGapMm"]
                  and fine["stance_stride_mm"] >= setup["minimumStrideMm"]
                  and fine["minimum_forward_rate_mm_per_rad"] >= setup["minimumForwardRateMmPerRad"]
                  and fine["circle_tangency_margin_mm"] >= setup["minimumCircleTangencyMarginMm"])
    improvement = fine["peak_stance_vertical_rate_mm_per_rad"] < original["peak_stance_vertical_rate_mm_per_rad"]
    if not admissible or not improvement:
        raise RuntimeError("The bounded kinematic redesign did not improve an admissible candidate; do not substitute it")
    return {
        "revisionId": cfg["revisionId"], "method": "bounded five-length differential-evolution kinematic search, not commercial generative design",
        "bounds": setup, "functionEvaluations": fit.nfev, "rejectedCounts": rejected,
        "optimizerConverged": bool(fit.success), "optimizerTermination": str(fit.message),
        "originalUnscaledMm": base, "continuousBestUnscaledMm": continuous,
        "selectedUnscaledMm": chosen, "physicalPitchRoundingMm": 0.1,
        "roundingAdmissibleCandidates": len(rounding_candidates),
        "originalMetrics": original, "selectedMetrics": fine,
        "geometryScreen": "PASS", "completeMechanicalStatus": "UNKNOWN",
        "trialColumns": variables+["objective", "constraint_deficit"],
        "trials": trials,
        "limitations": ["No CAD clearance or manufactured link strength is inferred from foot-curve improvement.",
                        "No mass reduction, independent phase assignment, body-translation offset or leg stretching was used."]
    }


class RedesignedGait(GaitStudy):
    def __init__(self, common, dimensions, step_deg=0.5):
        self.dimensions = dimensions
        super().__init__(common, step_deg)

    @lru_cache(maxsize=16384)
    def points(self, theta):
        return points_many(np.array(theta), self.dimensions, self.common["linkageScale"])[0]

    def summary(self):
        result = super().summary()
        closure = 0.0
        for theta in self.angles:
            points = self.points(theta)
            for a, b, key in (("A", "B", "AB"), ("A", "C", "AC"), ("P", "C", "PC"),
                              ("P", "B", "BP"), ("P", "D", "PD"), ("B", "D", "BD"),
                              ("C", "E", "CE"), ("D", "E", "DE"), ("C", "F", "CF"), ("E", "F", "EF")):
                closure = max(closure, abs(np.linalg.norm(points[a]-points[b])
                                          - self.dimensions[key]*self.common["linkageScale"]))
        result.update({"closure_residual_mm": float(closure),
                       "unscaled_dimensions_mm": self.dimensions,
                       "method": "same mechanically phased tripod with dimensioned optimized links"})
        return result


def rod_reflection(profile, design, common, case):
    """Reuse R2's one quartered-rod alternative, with no new mechanism search."""
    alt = common["synchronizationAlternative"]
    eta = common["meshEfficiencyCases"][case]
    mu = common["journalFrictionCases"][case]
    drag = common["bearingDragNmmCases"][case]
    feedback = 2*math.sqrt(2)*mu*alt["couplingJournalRadiusMm"]/alt["crankRadiusMm"]
    if feedback >= 1:
        raise ValueError("Quartered-rod friction bound is infeasible")
    ratio, efficiency, bearing_input = 1.0, 1.0, 2*drag
    for i, stage in enumerate(design["stageRatios"]):
        ratio *= stage
        efficiency *= eta
        count = alt["mainBearingCount"] if i == len(design["stageRatios"])-1 else 2
        bearing_input += count*drag/(ratio*efficiency*((1-feedback) if i == len(design["stageRatios"])-1 else 1))
    rod_volume = 4*alt["stationPitchMm"]*alt["rodWidthMm"]*alt["rodThicknessMm"]
    rod_weight = rod_volume*common["plasticDensityGPerCm3"]/1e6*common["gravity"]
    extra = mu*alt["couplingJournalRadiusMm"]*(
        alt["jointCount"]*alt["preloadPerJointCasesN"][case]+rod_weight)
    required = ((profile[:, 3]+extra)/(ratio*efficiency*(1-feedback))+bearing_input)/1000
    return required, {
        "method": "same R2 quartered-rod force/friction feedback upper-loss bound",
        "input_equivalent_bearing_drag_nm": bearing_input/1000,
        "bearing_count": 2*(len(design["stageRatios"])+1)+4,
        "coupling_efficiency_bound_assumed": 1-feedback, "extra_rod_friction_nmm": extra,
        "preload_each_n_assumed": alt["preloadPerJointCasesN"][case],
        "full_mechanism_qualification": "UNKNOWN"
    }


def rod_startup(study, design, common, case, force_y, force_down):
    previous = np.zeros(len(study.angles))
    direction = (-1)**len(design["stageRatios"])
    for iteration in range(16):
        profile, maxima = study.torque_profile(
            design["massCasesKg"][case], common["journalFrictionCases"][case],
            common["horizontalResistanceCases"][case], opposing_wind_n=force_y, wind_down_n=force_down,
            wind_application_yz=design["axisCentersYzMm"]["I"], input_couples_nmm=direction*previous*1000)
        required, meta = rod_reflection(profile, design, common, case)
        error = float(np.abs(required-previous).max())
        if error < 1e-10:
            meta.update({"support_drive_couple_iterations": iteration+1, "support_drive_couple_residual_nm": error})
            return profile, maxima, required, meta
        previous = required
    raise RuntimeError("Quartered-rod load/support fixed point failed")


def torque_decomposition(profile, required, design, common, case, meta):
    index = int(np.argmax(required))
    ratio = math.prod(design["stageRatios"])
    reducer_eta = common["meshEfficiencyCases"][case]**len(design["stageRatios"])
    coupling_eta = meta["coupling_efficiency_bound_assumed"]
    ideal = profile[index, 3]/ratio/1000
    gear_loss = ideal*(1/reducer_eta-1)
    rod_loss = (ideal+gear_loss)*(1/coupling_eta-1)
    extra = meta["extra_rod_friction_nmm"]/(ratio*reducer_eta*coupling_eta)/1000
    input_pair = 2*common["bearingDragNmmCases"][case]/1000
    downstream_bearings = meta["input_equivalent_bearing_drag_nm"]-input_pair
    total = ideal+gear_loss+rod_loss+extra+downstream_bearings+input_pair
    if abs(total-required[index]) > 1e-12:
        raise RuntimeError("Peak-angle torque decomposition does not sum to the same required sample")
    return {
        "same_resistance_case": ("low", "nominal", "high")[case],
        "same_peak_crank_angle_deg": float(profile[index, 0]),
        "crank_load_nmm": float(profile[index, 1]),
        "crank_joint_friction_nmm": float(profile[index, 2]),
        "positive_crank_demand_nmm": float(profile[index, 3]),
        "ideal_input_after_ratio_nm": float(ideal),
        "reducer_mesh_loss_input_nm": float(gear_loss),
        "coupling_load_friction_input_nm": float(rod_loss),
        "coupling_preload_selfweight_loss_input_nm": float(extra),
        "downstream_bearing_loss_input_nm": float(downstream_bearings),
        "input_two_bearing_loss_nm": float(input_pair),
        "total_required_input_nm": float(total),
        "downstream_required_after_input_bearings_nm": float(total-input_pair),
        "designer_downstream_margin_multiplier": 2.0,
        "net_output_target_nm": float(2*(total-input_pair)),
        "gross_aerodynamic_target_nm": float(2*(total-input_pair)+input_pair),
        "definition": "2x is applied ONLY to downstream demand after the same two input bearings; input-bearing resistance is added once, not doubled or subtracted from measured output again.",
    }


def field(design, common, cfg, speed_multiplier=1, sigma=20, aim=0, samples=256):
    assumptions = cfg["modelAssumptions"]
    fluid = {"airDensityKgM3": assumptions["airDensityKgM3"],
             "airKinematicViscosityM2S": assumptions["airKinematicViscosityM2S"]}
    radius = design["rotorDiameterMm"]/2
    return static_jet_proxy(radius, common["rotor"]["spanMm"], common, fluid, 16, 20,
                            -0.5+aim/radius, assumptions["nominalGaussianPeakMS"]*speed_multiplier,
                            sigma, step_deg=1, rays=samples)


def receiver_probe(design, common, cfg):
    assumptions = cfg["modelAssumptions"]
    fluid = {"airDensityKgM3": assumptions["airDensityKgM3"],
             "airKinematicViscosityM2S": assumptions["airKinematicViscosityM2S"]}
    rows = []
    for blades in (12, 16):
        for angle in (20, 40, 60):
            for offset in (-0.5, -0.65, -0.8):
                jet = static_jet_proxy(design["rotorDiameterMm"]/2, common["rotor"]["spanMm"],
                                       common, fluid, blades, angle, offset,
                                       assumptions["nominalGaussianPeakMS"], 20, step_deg=2, rays=128)
                rows.append({"blades": blades, "sweep_deg": angle, "offset_radius_fraction": offset,
                             "minimum_raw_proxy_nm": min(r[1] for r in jet["rows"])})
    selected = max(rows, key=lambda row: row["minimum_raw_proxy_nm"])
    return {
        "method": "one fixed 18-case receiver extension at nominal field, 2deg/128 rays; uncalibrated proxy",
        "cases": rows, "best_nominal_proxy": selected,
        "adopted": {"blades": 16, "sweep_deg": 20, "offset_radius_fraction": -0.5},
        "decision": "retain prior geometry/aim; the small single-cell gain does not close the budget and is not a validated receiver improvement",
        "applied_supply_gain": 0
    }


def sensitivity(design, dimensions, common, cfg):
    study = RedesignedGait(common, dimensions, step_deg=2)
    assumptions = cfg["modelAssumptions"]
    cells = []
    for multiplier in assumptions["velocityMultipliers"]:
        for sigma in assumptions["velocitySigmaMmCases"]:
            for aim in assumptions["aimErrorMmCases"]:
                jet = field(design, common, cfg, multiplier, sigma, aim)
                rows = np.array(jet["rows"])
                fy, fz = float(rows[:, 2].max()), float(np.abs(rows[:, 3]).max())
                cases = []
                for index in (1, 2):
                    profile, loads, required, meta = rod_startup(study, design, common, index, fy, fz)
                    input_pair = 2*common["bearingDragNmmCases"][index]/1000
                    target = 2*(required.max()-input_pair)+input_pair
                    available_proxy = float(rows[:, 1].min())*0.5
                    cases.append({
                        "resistance": ("low", "nominal", "high")[index],
                        "required_input_nm": float(required.max()),
                        "gross_design_target_nm": float(target),
                        "conditional_half_capture_margin": available_proxy/target,
                        "conditional_half_capture_status": "PASS" if available_proxy >= target else "FAIL",
                        "ideal_momentum_ceiling_status": "FAIL" if jet["ideal_intercepted_momentum_torque_ceiling_nm"] < required.max() else "UNKNOWN",
                        "minimum_support_margin_at_target_cog_mm": float(profile[:, 4].min()),
                        "peak_joint_force_n": loads["joint_n"],
                        "fixed_point_residual_nm": meta["support_drive_couple_residual_nm"],
                    })
                cells.append({
                    "peak_speed_m_s_assumed": multiplier*assumptions["nominalGaussianPeakMS"],
                    "velocity_sigma_mm_assumed": sigma, "aim_error_mm_assumed": aim,
                    "minimum_proxy_nm": float(rows[:, 1].min()), "maximum_opposing_force_n": fy,
                    "downward_force_envelope_n": fz,
                    "jet_power_ceiling_w": jet["whole_jet_kinetic_power_w"],
                    "momentum_torque_ceiling_nm": jet["ideal_intercepted_momentum_torque_ceiling_nm"],
                    "cases": cases,
                    "physical_status": "UNKNOWN",
                })
    return {"crank_sampling_deg": 2, "extra_samples": "both sides of exact contact switches",
            "wind_angle_sampling_deg": 1, "rays": 256, "cells": cells,
            "sampling_warning": "27 scenario samples, not continuous uncertainty bounds or a measured dryer envelope"}


def tolerance_screen(dimensions, common, cfg):
    variables = list(cfg["boundedLinkageSearch"]["variableBoundsUnscaledMm"])
    rows = []
    for key in variables:
        for delta_mm in (-0.1, 0.1):
            altered = {**dimensions, key: dimensions[key]+delta_mm/common["linkageScale"]}
            metrics = fast_gait_metrics(altered, common, 1440)
            rows.append({"dimension": key, "physical_pitch_error_mm": delta_mm, "metrics": metrics})
    return {"method": "one-at-a-time +/-0.1mm pitch perturbations; not a worst-case tolerance stack",
            "cases": rows, "all_combined_errors_status": "UNKNOWN",
            "maximum_bounce_mm": max(row["metrics"]["body_bounce_mm"] for row in rows),
            "minimum_swing_gap_mm": min(row["metrics"]["swing_gap_max_mm"] for row in rows),
            "maximum_handoff_rate_jump_mm_per_rad": max(row["metrics"]["horizontal_handoff_jump_mm_per_rad"] for row in rows),
            "more_than_two_handoffs_cases": [row["dimension"]+str(row["physical_pitch_error_mm"])
                                             for row in rows if row["metrics"]["stance_switch_count"] != 2]}


def gait_figure(path, dimensions, common, cfg):
    theta = np.linspace(0, 2*math.pi, 721)
    series = []
    for label, lengths, color in (
        ("R2: 標準リンク・同方向三脚", {key: CONFIG["linkage"][key] for key in LENGTH_KEYS}, "#ff9977"),
        ("R3: 5寸法のみ改訂・実ピッチ0.1mmへ丸め", dimensions, "#6ad6a2"),
    ):
        points, _ = points_many(theta, lengths, common["linkageScale"])
        other, _ = points_many(theta+math.pi, lengths, common["linkageScale"])
        height = -np.minimum(points["F"][:, 1], other["F"][:, 1])
        series.append((label, np.column_stack([np.rad2deg(theta), height-height.min()]).tolist(), color))
    plot(path, "接地幾何を改訂し、重心を持ち上げる仕事を減らす", series,
         "クランク角 [deg]", "最も低い姿勢からの本体上下量 [mm]",
         [cfg["revisionId"]+" / 同一の位相・尺度。グラフの縦原点だけ各曲線の最低姿勢とする。",
          "画像の任意移動や部材伸縮ではなく、QP/OQ/DE/CF/EFの実寸法を変更。上昇量は重力項へそのまま渡す。",
          "接地衝撃・誤差・摩擦は別。歩行を観測した図や実物の無滑り証明ではない。"])


def linkage_drawing(path, dimensions, common, cfg):
    body = [text(40, 35, "同じ位相・尺度で、5つのピン間寸法を改訂", 23),
            text(40, 63, cfg["revisionId"]+" / 2D運動学模式図。製作済みCADではない。", 15, "#f7c66f")]
    panels = [("R2", {k: CONFIG["linkage"][k] for k in LENGTH_KEYS}, 325, "#ff9977"),
              ("R3", dimensions, 850, "#6ad6a2")]
    scale, origin_y = 5, 265
    for label, lengths, x0, color in panels:
        points, _ = points_many(np.array(0.0), lengths, common["linkageScale"])
        body.append(text(x0-70, 119, label+" / クランク0°", 18, color))
        for names in (("O", "A"), ("A", "B"), ("A", "C"), ("P", "C"),
                      ("P", "B", "D", "P"), ("D", "E"), ("C", "E", "F", "C")):
            coords = " ".join(f"{x0+scale*points[name][0]:.3f},{origin_y-scale*points[name][1]:.3f}" for name in names)
            body.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"/>')
        trajectory, _ = points_many(np.linspace(0, 2*math.pi, 361), lengths, common["linkageScale"])
        coords = " ".join(f"{x0+scale*y:.3f},{origin_y-scale*z:.3f}" for y, z in trajectory["F"])
        body.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1" stroke-dasharray="4 3"/>')
        for name, point in points.items():
            x, y = x0+scale*point[0], origin_y-scale*point[1]
            if not 40 < x < 1150 or not 135 < y < 680:
                raise RuntimeError("Linkage diagram overlaps the heading or dimension table")
            body += [f'<circle cx="{x:.3f}" cy="{y:.3f}" r="4" fill="#eaf0f7"/>',
                     text(x+7, y-5, name, 13)]
    body.append(text(40, 710, "ピン間実寸法 [mm]    R2 → R3", 18))
    for i, key in enumerate(cfg["boundedLinkageSearch"]["variableBoundsUnscaledMm"]):
        old = CONFIG["linkage"][key]*common["linkageScale"]
        new = dimensions[key]*common["linkageScale"]
        body.append(text(40+(i%3)*385, 748+(i//3)*30, f"{key}: {old:.2f} → {new:.1f}", 17))
    body += [text(40, 850, "図の座標スケール5px/mm、変形拡大なし。点Fの軌跡が実寸法から変わる。", 14),
             text(40, 874, "足上げの低下と±0.1mm誤差感度を別表に残す。軸方向層・工具・干渉は未検証。", 14)]
    svg(path, body, height=920)


def bearing_figure(path, cfg):
    body = [text(40, 40, "内輪接触を寸法で確認し、不適合スペーサーを除外", 23),
            text(40, 74, cfg["revisionId"]+" / メーカー寸法の模式図。実部品断面CADではない。", 15, "#f7c66f")]
    center = (285, 310)
    for diameter, color, label, dashed in (
        (13, "#7b8ea4", "外輪13mm", False),
        (8, "#ff9977", "候補スペーサー外径8mm：不適合", False),
        (7.4, "#6ad6a2", "686AZZ1 軸肩上限7.4mm", True),
        (6, "#eaf0f7", "軸穴6mm", False),
    ):
        body.append(f'<circle cx="{center[0]}" cy="{center[1]}" r="{diameter*16}" fill="none" '
                    f'stroke="{color}" stroke-width="3" stroke-dasharray="{"5 4" if dashed else "none"}"/>')
        body.append(text(570, 190+[(13), 8, 7.4, 6].index(diameter)*44, label, 19, color))
    body += [text(570, 405, "径の超過0.6mm、片側0.3mm。", 18, "#ff9977"),
             text(570, 442, "15mmカラー全面を直接当てる案も採らない。", 17),
             text(40, 560, "メーカー表: 686A開放 / 686AZZ1シールド。小売の『ISC 686ZZ』と同一とは未確認。", 16),
             text(40, 599, "別案: NSK 626ZZ + IWATA SC0607CB2（ボス9.2mm、適合欄626ZZ）。", 16),
             text(40, 633, "19mm外輪用の設計変更とNSK実当たり面の照合が未完。新しい組合せを計算へ黙って代入しない。", 15),
             text(40, 708, "32px/mmで外径を表示。隙間はメーカー軸肩寸法との照合であり、玉/溝/シールド形状の再現ではない。", 14)]
    svg(path, body, height=760)


def run(output, optimize_only=False):
    cfg = json.loads(INPUT.read_text())
    old_cfg = json.loads(Path(__file__).with_name("study_r2.json").read_text())
    common = deepcopy(old_cfg["common"])
    output.mkdir(parents=True, exist_ok=True)
    search = optimize_linkage(cfg, common)
    write_csv(output/"linkage_search.csv", search["trialColumns"], search.pop("trials"))
    dump(output/"linkage_search.json", search)
    print("Kinematic improvement", json.dumps(search["selectedMetrics"]), flush=True)
    if optimize_only:
        return
    revised = RedesignedGait(common, search["selectedUnscaledMm"])
    original = GaitStudy(common)
    dump(output/"gait.json", revised.summary())
    tolerance = tolerance_screen(search["selectedUnscaledMm"], common, cfg)
    tolerance["conditional_swing_clearance_status"] = "PASS" if tolerance["minimum_swing_gap_mm"] >= cfg["boundedLinkageSearch"]["minimumSwingGapMm"] else "FAIL"
    tolerance["handoff_no_worse_than_r2_nominal_status"] = "PASS" if tolerance["maximum_handoff_rate_jump_mm_per_rad"] <= search["originalMetrics"]["horizontal_handoff_jump_mm_per_rad"] else "FAIL"
    dump(output/"linkage_tolerance.json", tolerance)
    gait_figure(output/"gait_improvement.svg", search["selectedUnscaledMm"], common, cfg)
    linkage_drawing(output/"linkage_layout.svg", search["selectedUnscaledMm"], common, cfg)
    bearing_figure(output/"bearing_interface.svg", cfg)
    write_csv(output/"v2_observations.template.csv",
              ["record_status", "apparatus", "video_reference", "viewpoint", "start_angle_description",
               "start_angle_deg_if_known", "mode", "nozzle_condition", "distance_mm_if_known",
               "distance_reference", "flow_direction", "rotor_motion", "shaft_motion", "gear_motion",
               "leg_motion", "relative_mark_shift", "vibration_or_axial_escape", "notes"],
              [["NOT_PERFORMED", "USER_OWNED_V2_WITH_ROTOR"]+[""]*16])
    dump(output/"optional_v2_check.json", {
        "revisionId": cfg["revisionId"], "apparatusId": "USER_OWNED_V2_WITH_ROTOR",
        "apparatusExistence": "user-confirmed", "actualPhotosReviewed": False,
        "reportedWindStrength": {"statement": "stronger than an ordinary commercial hair dryer",
                                "evidenceClass": "user qualitative report", "velocityMS": None},
        "anemometerAvailable": False, "purchaseNewMeasurementTools": False,
        "requiredForDesignContinuation": False,
        "firstStep": "optional stopped photos and non-invasive motion observation, not a new load",
        "loadFixtureMountVerified": None, "permittedTestMassG": None,
        "loadTestStatus": "BLOCKED_UNTIL_ACTUAL_MOUNT_RETENTION_AND_CAPACITY_REVIEW",
        "torqueObservations": [], "measuredNetTorqueLowerBoundNm": None,
        "coinMassSource": cfg["referenceData"]["coinReference"],
        "outputTransferToRevisedRotors": "not permitted without an explicit measured/model transfer",
        "rotationSpeedAloneIsTorqueEvidence": False,
    })
    # Avoid a favorable mass assumption: charge larger rotor proxy mass to the
    # already hypothetical R2 whole-machine mass range, never credit a smaller frame.
    records, summary_rows = [], []
    for i, requested in enumerate(cfg["candidates"]):
        ident = requested["id"]
        old = deepcopy(old_cfg["candidates"][i])
        design = {**old, **requested}
        shape = {"blades": 16, "sweep_deg": 20}
        old_mass = rotor_mass_proxy(old, common, shape)
        new_mass = rotor_mass_proxy(design, common, shape)
        added_mass = max(0, new_mass["mass_kg_proxy"]-old_mass["mass_kg_proxy"])
        design["massCasesKg"] = [m+added_mass for m in old["massCasesKg"]]
        jet = field(design, common, cfg, sigma=cfg["modelAssumptions"]["nominalVelocitySigmaMm"], samples=512)
        jet_rows = np.array(jet["rows"])
        force_y, force_down = float(jet_rows[:, 2].max()), float(np.abs(jet_rows[:, 3]).max())
        cases, plot_series = [], []
        for case, name in enumerate(("low", "nominal", "high")):
            _, _, old_required, _ = coupled_startup(original, old, case, common, force_y, force_down)
            ratio_only = {**old, "stageRatios": design["stageRatios"]}
            _, _, ratio_required, _ = coupled_startup(original, ratio_only, case, common, force_y, force_down)
            profile, maxima, gear_required, gear_meta = coupled_startup(revised, design, case, common, force_y, force_down)
            rod_profile, rod_loads, rod_required, rod_meta = rod_startup(revised, design, common, case, force_y, force_down)
            write_csv(output/f"startup_{ident}_{name}.csv",
                      ["crank_deg", "load_nmm", "joint_friction_nmm", "required_crank_nmm",
                       "support_margin_mm", "gear_bus_input_nm", "rod_bus_input_nm"],
                      np.column_stack([profile, gear_required, rod_required]))
            input_bearing_pair = 2*common["bearingDragNmmCases"][case]/1000
            target = 2*(rod_required.max()-input_bearing_pair)+input_bearing_pair
            proxy_minimum = float(jet_rows[:, 1].min())
            cases.append({
                "id": name, "mass_kg_assumed": design["massCasesKg"][case],
                "journal_mu_assumed": common["journalFrictionCases"][case],
                "bearing_drag_nmm_each_assumed": common["bearingDragNmmCases"][case],
                "old_geometry_ratio_gearbus_peak_nm_at_same_force": float(old_required.max()),
                "new_ratio_only_peak_nm": float(ratio_required.max()),
                "ratio_only_definition": "same R2 mass, wind-application position and link geometry; change the numeric ratio only",
                "optimized_linkage_gearbus_peak_nm": float(gear_required.max()),
                "optimized_linkage_rod_bus_peak_nm": float(rod_required.max()),
                "proposed_rod_peak_reduction_fraction": float(1-rod_required.max()/old_required.max()),
                "gross_aero_design_target_nm": float(target),
                "net_after_same_two_input_bearings_target_nm": float(target-input_bearing_pair),
                "proxy_min_raw_nm": proxy_minimum,
                "conditional_budget_by_retained_fraction": [
                    {"retained_fraction_assumed": f, "minimum_proxy_nm": f*proxy_minimum,
                     "margin_to_design_target": f*proxy_minimum/target,
                     "status": "PASS" if f*proxy_minimum >= target else "FAIL"}
                    for f in cfg["modelAssumptions"]["retainedProxyForceFractions"]],
                "required_input_profile_peak_phase_deg": float(np.rad2deg(revised.angles[np.argmax(rod_required)])),
                "minimum_support_margin_mm_at_target_cog": float(rod_profile[:, 4].min()),
                "gear_bus": gear_meta, "rod_bus": rod_meta, "loads": rod_loads,
                "torque_decomposition_at_same_peak": torque_decomposition(rod_profile, rod_required, design, common, case, rod_meta),
                "load_components_nmm_at_crank": {
                    "gravity_plus_external_peak": float(profile[:, 1].max()),
                    "gravity_plus_external_min": float(profile[:, 1].min()),
                    "joint_friction_peak": float(profile[:, 2].max()),
                    "peak_total": float(profile[:, 3].max()),
                    "note": "individual maxima need not occur at the same angle; do not add peaks to reproduce peak_total"},
                "actual_self_start_status": "UNKNOWN",
            })
            plot_series.append((f"{name}: 更新リンク・同じ摩擦／質量感度",
                                np.column_stack([profile[:, 0], rod_required*1000]).tolist(),
                                ("#6ad6a2", "#72baf4", "#ff9977")[case]))
        structure_cfg = {**old_cfg, "revisionId": cfg["revisionId"], "common": common}
        structural = structures(design, structure_cfg, cases[-1]["loads"],
                                cases[-1]["optimized_linkage_rod_bus_peak_nm"],
                                force_y+force_down, new_mass["mass_kg_proxy"])
        structural["loadcaseId"] = f"{ident}_COMMERCIAL_COLD_150MM_HIGH_RESISTANCE"
        structural["method"] += "; reducer shaft loads use a conservative torque envelope; coupling-rod sweep/frame compliance not certified"
        record = {
            "revisionId": cfg["revisionId"], "designId": ident, "candidate": design,
            "sourceGeometryStatus": "dimensioned kinematic skeleton, not final CAD",
            "previousRevisionId": cfg["previousRevisionId"], "same_reference_plane_and_forces_for_isolated_improvements": True,
            "gears": gear_check(design, common), "linkage": search["selectedUnscaledMm"],
            "rotor_mass_proxy": new_mass, "additional_rotor_mass_charged_kg": added_mass,
            "startup": cases, "jet": jet, "structure": structural,
            "physicalStatus": "UNKNOWN", "qualifiedPrototype": False,
            "massStatus": "R2 assumption range plus actual geometric rotor-volume proxy difference, NOT a completed CAD or measured mass",
            "procurementStatus": "UNKNOWN; R2 subset reused, extra/larger gears and final fasteners remain unpriced",
            "ring_contact_update": cfg["bearingInterfaceUpdate"],
            "documented_support_fallback_not_applied": cfg["documentedSupportFallback"],
            "receiver_probe": receiver_probe(design, common, cfg),
        }
        decomposition = cases[1]["torque_decomposition_at_same_peak"]
        bearing_total = decomposition["input_two_bearing_loss_nm"]+decomposition["downstream_bearing_loss_input_nm"]
        fixed_load_no_bearings = decomposition["total_required_input_nm"]-bearing_total
        record["dominant_terms"] = {
            "case": "nominal, same peak angle as torque_decomposition",
            "all_bearing_fraction_of_total": bearing_total/decomposition["total_required_input_nm"],
            "fixed_peak_zero_bearing_loss_input_nm": fixed_load_no_bearings,
            "fixed_peak_zero_bearing_loss_2x_target_nm": 2*fixed_load_no_bearings,
            "half_capture_proxy_minimum_nm": cases[1]["proxy_min_raw_nm"]*0.5,
            "bearing_only_improvement_can_close_at_this_fixed_peak": cases[1]["proxy_min_raw_nm"]*0.5 >= 2*fixed_load_no_bearings,
            "warning": "algebraic diagnostic at the existing peak/load, not a new zero-friction simulation or proposed bearing specification",
        }
        sweep = sensitivity(design, search["selectedUnscaledMm"], common, cfg)
        record["sensitivity"] = sweep
        record["matrix"] = [
            {"criterion": "丸めたリンクの閉路・尺度・交互三脚", "status": "PASS", "scope": "kinematic skeleton"},
            {"criterion": "上下動と必要入力の低減", "status": "PASS",
             "scope": "same unmeasured mass/friction inputs; comparison not physical validation"},
            {"criterion": "±0.1mm単独寸法誤差で足上げ8mm", "status": tolerance["conditional_swing_clearance_status"],
             "scope": "one-at-a-time hypothetical manufacturing errors, not measured print tolerance"},
            {"criterion": "±0.1mm単独誤差で切替速度差をR2名目以下に維持",
             "status": tolerance["handoff_no_worse_than_r2_nominal_status"],
             "scope": "kinematic robustness diagnostic, not impact dynamics"},
            {"criterion": "名目風・名目抵抗・保持係数0.5のトルク予算",
             "status": cases[1]["conditional_budget_by_retained_fraction"][1]["status"],
             "scope": "defined uncalibrated static proxy, not all-angle measured supply"},
            {"criterion": "高抵抗・全感度ケースでの成立",
             "status": "PASS" if all(c["cases"][-1]["conditional_half_capture_status"] == "PASS" for c in sweep["cells"]) else "FAIL",
             "scope": "27 hypothetical samples only"},
            {"criterion": "実自己始動・30cm歩行", "status": "UNKNOWN"},
            {"criterion": "最終フレーム／ロッドの全周干渉・工具・組立", "status": "UNKNOWN"},
            {"criterion": "購入軸受・内輪スペーサの適合と全2万円BOM", "status": "UNKNOWN"},
        ]
        dump(output/f"candidate_{ident}.json", record)
        beam_image(output/f"deflection_{ident}.svg", ident, structural, cfg["revisionId"])
        plot(output/f"startup_{ident}.svg", f"{ident} / 共通市販冷風基準・限定改訂の必要入力",
             plot_series, "クランク角 [deg]", "必要入力 [mN·m]",
             [f'{cfg["revisionId"]} / 位相拘束は直交2ロッド案。実組立・実機自己始動はUNKNOWN。',
              "文献の測定点6.4m/sを分布ピークに置くことは設計仮定。幅・照準・支持の不確かさを別途扱う。"])
        curves = [(f"局所パネル抗力の未校正保持係数 {f:g}",
                   np.column_stack([jet_rows[:, 0], f*jet_rows[:, 1]*1000]).tolist(), color)
                  for f, color in zip(cfg["modelAssumptions"]["retainedProxyForceFractions"],
                                      ("#6ad6a2", "#72baf4", "#c094ef"))]
        curves.append(("名目抵抗の設計目標（総トルク）",
                       [[0, cases[1]["gross_aero_design_target_nm"]*1000],
                        [360, cases[1]["gross_aero_design_target_nm"]*1000]], "#ff9977"))
        plot(output/f"torque_budget_{ident}.svg", f"{ident} / 風車角別の供給代理値と必要値", curves,
             "風車角 [deg] / 進行に必要な回転へ正規化", "トルク [mN·m]",
             ["COLD・150mmを採用した設計基準。Gaussian peak=6.4m/s, sigma=20mmはいずれも機種実測ではない。",
              "抗力モデルはCFDでも保証された下限でもない。平均・運動量上限から自己始動を合格にしない。"])
        stages = [("R2形状/比", "old_geometry_ratio_gearbus_peak_nm_at_same_force"),
                  ("比のみ", "new_ratio_only_peak_nm"),
                  ("リンク+ローター質量", "optimized_linkage_gearbus_peak_nm"),
                  ("直交2ロッド", "optimized_linkage_rod_bus_peak_nm")]
        plot(output/f"improvement_{ident}.svg", f"{ident} / 必要入力を下げた要因と残る不足",
             [(name, [[j, c[key]*1000] for j, (_, key) in enumerate(stages)], color)
              for c, name, color in zip(cases, ("low", "nominal", "high"), ("#6ad6a2", "#72baf4", "#ff9977"))],
             "0=R2 / 1=比のみ / 2=リンク改訂+ローター増量 / 3=既比較ロッド",
             "入力軸ピークトルク [mN·m]",
             ["全点は同一の冷風基準からの風力包絡。旧8m/sの値と新6.4m/sを混ぜた改善ではない。",
              "部材軽量化を仮想の質量減として使わず、大きくなった風車の代理質量は上乗せする。",
              "ローター径変更による供給側の変化は別の角度別トルク図で確認する。"])
        summary_rows.append([ident, design["rotorDiameterMm"], math.prod(design["stageRatios"]),
                             added_mass, *[c["optimized_linkage_rod_bus_peak_nm"] for c in cases],
                             cases[1]["proposed_rod_peak_reduction_fraction"],
                             cases[1]["conditional_budget_by_retained_fraction"][1]["status"], "UNKNOWN"])
        records.append(record)
        print(ident, "input Nm", [c["optimized_linkage_rod_bus_peak_nm"] for c in cases], flush=True)
    write_csv(output/"comparison.csv",
              ["design", "rotor_diameter_mm", "reduction", "extra_rotor_mass_kg",
               "low_input_nm", "nominal_input_nm", "high_input_nm",
               "nominal_input_reduction_fraction_same_forces", "proxy_nominal_half_capture_budget", "physical_status"],
              summary_rows)
    write_csv(output/"torque_decomposition.csv",
              ["design", "case", "peak_crank_deg", "ideal_ratio_nm", "gear_loss_nm", "coupling_load_loss_nm",
               "coupling_preload_loss_nm", "other_bearing_loss_nm", "input_bearing_pair_nm",
               "total_required_nm", "net_2x_target_nm", "gross_target_nm"],
              [[r["designId"], c["id"], *[c["torque_decomposition_at_same_peak"][key] for key in (
                  "same_peak_crank_angle_deg", "ideal_input_after_ratio_nm", "reducer_mesh_loss_input_nm",
                  "coupling_load_friction_input_nm", "coupling_preload_selfweight_loss_input_nm",
                  "downstream_bearing_loss_input_nm", "input_two_bearing_loss_nm", "total_required_input_nm",
                  "net_output_target_nm", "gross_aerodynamic_target_nm")]]
               for r in records for c in r["startup"]])
    # R2's material/beam helper is reused, but all output and revision IDs are R3.
    rib_section_screen(structure_cfg, output)
    source_paths = [INPUT, Path(__file__), Path(__file__).with_name("study_r2.py"),
                    Path(__file__).with_name("study_r2.json"), Path(__file__).with_name("core.py"),
                    Path(__file__).with_name("design.json"), Path(__file__).with_name("beam.py"),
                    Path(__file__).with_name("test_commercial_r3.py")]
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    dump(output/"comparison.json", {
        "revisionId": cfg["revisionId"], "referenceData": cfg["referenceData"],
        "modelAssumptions": cfg["modelAssumptions"], "requirements": cfg["requirements"],
        "boundedSearch": {key: search[key] for key in ("functionEvaluations", "originalMetrics", "selectedMetrics")},
        "linkageTolerance": {k: v for k, v in tolerance.items() if k != "cases"},
        "bearingInterfaceUpdate": cfg["bearingInterfaceUpdate"],
        "documentedSupportFallback": cfg["documentedSupportFallback"],
        "candidates": [{"designId": r["designId"], "candidate": r["candidate"],
                        "startup": r["startup"], "gears": r["gears"], "matrix": r["matrix"],
                        "dominantTerms": r["dominant_terms"],
                        "physicalStatus": "UNKNOWN", "qualifiedPrototype": False} for r in records],
        "sourceHashes": source_hashes, "qualifiedPrototypeCount": 0,
        "requiresUserMeasurementToContinueDesign": False,
        "reasonForNotReleasing": "conditional static torque budget, complete assembly/interfaces/procurement and contact dynamics must qualify; not blocked solely on ReFa measurements",
    })
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    contained = True
    for path in source_paths:
        stored = subprocess.run(["git", "show", f"{commit}:{path.relative_to(ROOT)}"],
                                cwd=ROOT, capture_output=True, check=False)
        contained = contained and stored.returncode == 0 and stored.stdout == path.read_bytes()
    figures = []
    for record in records:
        ident = record["designId"]
        for kind, method, pointer in (
            ("deflection", "1D beam/column; no final assembly FEM", "/structure"),
            ("startup", "quasi-static coupled load and explicit losses", "/startup"),
            ("torque_budget", "uncalibrated static panel proxy and designer margin", "/jet"),
            ("improvement", "same-field scenario comparison; no measured performance", "/startup"),
        ):
            figures.append({
                "revisionId": cfg["revisionId"], "sourceGeometryRevision": cfg["revisionId"], "designId": ident,
                "loadcaseId": record["structure"]["loadcaseId"],
                "file": str((OUT/f"{kind}_{ident}.svg").relative_to(ROOT)),
                "dataFile": str((OUT/f"candidate_{ident}.json").relative_to(ROOT)),
                "dataPointer": pointer, "method": method,
                "units": "mm,N,MPa,rad" if kind == "deflection" else "Nm,deg",
                "figureUnits": "mm,N,MPa" if kind == "deflection" else "mN*m,deg_or_scenario_index",
                "displayAmplification": ({m["partId"]: m["displayAmplification"] for m in record["structure"]["members"]}
                                         if kind == "deflection" else 1),
                "resultStatus": "UNKNOWN", "isFinalCadGeometry": False,
                "sourceHashes": {**source_hashes, f"candidate_{ident}.json": sha(output/f"candidate_{ident}.json")},
            })
    for name, data, method, units in (
        ("gait_improvement", "linkage_search.json", "rigid co-oriented linkage geometry", "deg,mm"),
        ("linkage_layout", "linkage_search.json", "dimensioned 2D mechanism schematic; 5px/mm", "mm"),
        ("bearing_interface", "comparison.json", "manufacturer-dimension schematic, not vendor CAD; 32px/mm", "mm"),
        ("rib_section_screen_C", "rib_section_screen_C.json", "16-section beam coupon screen, not full frame GD", "mm,N,MPa"),
    ):
        figures.append({
            "revisionId": cfg["revisionId"], "sourceGeometryRevision": cfg["revisionId"], "designId": "C" if name.endswith("_C") else None,
            "loadcaseId": "C_COMMERCIAL_COLD_150MM_HIGH_RESISTANCE" if name.endswith("_C") else name,
            "file": str((OUT/f"{name}.svg").relative_to(ROOT)), "dataFile": str((OUT/data).relative_to(ROOT)),
            "method": method, "units": units, "figureUnits": units, "displayAmplification": 1,
            "resultStatus": "UNKNOWN", "isFinalCadGeometry": False,
            "sourceHashes": {**source_hashes, data: sha(output/data)},
        })
    dump(output/"manifest.json", {
        "revisionId": cfg["revisionId"], "previousRevisionId": cfg["previousRevisionId"],
        "sourceCommit": commit, "sourceCommitContainsInputs": contained,
        "sourceHashes": source_hashes,
        "previousManifestSha256": sha(R2/"manifest.json"),
        "artifactHashes": {str((OUT/p.name).relative_to(ROOT)): sha(p) for p in sorted(output.iterdir())
                           if p.is_file() and p.name != "manifest.json"},
        "geometryStatus": "skeleton_and_member_calculation_only", "qualifiedPrototypeCount": 0,
        "siteMappingToFirstCutCadPermitted": False, "figures": figures,
        "finalCadMeshHashes": None, "finalAssemblyHashes": None, "finalBomHashes": None,
        "requiresUserMeasurementToContinueDesign": False,
    })


def verify(output):
    manifest = json.loads((output/"manifest.json").read_text())
    cfg = json.loads(INPUT.read_text())
    if manifest["revisionId"] != cfg["revisionId"] or manifest["qualifiedPrototypeCount"] != 0:
        raise ValueError("Unexpected revision/qualification status")
    if sha(R2/"manifest.json") != manifest["previousManifestSha256"]:
        raise ValueError("Frozen R2 manifest changed")
    for relative, expected in manifest["sourceHashes"].items():
        path = (ROOT/relative).resolve()
        path.relative_to(ROOT)
        if sha(path) != expected:
            raise ValueError(f"Stale source: {relative}")
    for relative, expected in manifest["artifactHashes"].items():
        name = Path(relative).relative_to(OUT.relative_to(ROOT))
        if len(name.parts) != 1 or sha(output/name) != expected:
            raise ValueError(f"Changed artifact: {relative}")
    for figure in manifest["figures"]:
        ET.parse(output/Path(figure["file"]).name)
        if figure["isFinalCadGeometry"] or not figure["figureUnits"]:
            raise ValueError("Invalid figure scope or units")
    for ident in "ABC":
        record = json.loads((output/f"candidate_{ident}.json").read_text())
        if record["qualifiedPrototype"] or record["physicalStatus"] != "UNKNOWN":
            raise ValueError("A study candidate was incorrectly qualified")
        if len(record["sensitivity"]["cells"]) != 27:
            raise ValueError("Expected the exact 27 field/aim cells")
        for case in record["startup"]:
            d = case["torque_decomposition_at_same_peak"]
            if abs(d["total_required_input_nm"]-case["optimized_linkage_rod_bus_peak_nm"]) > 1e-12:
                raise ValueError("Decomposition peak mismatch")
            if abs(d["gross_aerodynamic_target_nm"]-(2*d["total_required_input_nm"]-d["input_two_bearing_loss_nm"])) > 1e-12:
                raise ValueError("Designer margin applied to the wrong load")
            if case["rod_bus"]["support_drive_couple_residual_nm"] > 1e-10:
                raise ValueError("Input/support coupling not converged")
        for member in record["structure"]["members"]:
            if member["force_balance_error_n"] > 1e-6 or member["moment_balance_error_nmm"] > 1e-5:
                raise ValueError("Unbalanced structural case")
    print(json.dumps({"revisionId": cfg["revisionId"], "figures": len(manifest["figures"]),
                      "caseCount": 81, "sourceCommitContainsInputs": manifest["sourceCommitContainsInputs"],
                      "numericalPackage": "CONSISTENT", "qualifiedPrototypeCount": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--optimize-only", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        run(args.output, args.optimize_only)
