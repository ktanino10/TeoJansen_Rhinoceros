"""Bounded V3 follow-up study. Never overwrites the first-cut CAD or site.

This is a feasibility gate, not a generator for three qualified prototypes.
ReFa measurements, a complete priced BOM and final collision/access CAD remain
explicitly absent. Run with Python already providing the Ver.3 dependencies.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from functools import lru_cache
import hashlib
import html
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy.integrate import trapezoid
from scipy.optimize import brentq
from scipy.special import erf

from beam import circle_section, d_section, rectangle_section, solve_beam, twist_bound
from core import CONFIG, LINKS, ROOT, dump, gait, gear_metrics

INPUT = Path(__file__).with_suffix(".json")
DEFAULT_OUTPUT = ROOT / "docs/ver3/feasibility_r2"
VARIABLES = ["A_AB", "A_AC", "B", "C_AC", "C_PC", "D", "E", "P_TRI", "P_PC"]
INCIDENCE = {
    "L_AB": [("A_AB", "A", 1), ("B", "B", 1)],
    "L_AC": [("A_AC", "A", 1), ("C_AC", "C", 1)],
    "L_PC": [("P_PC", "P", 1), ("C_PC", "C", 1)],
    "L_PBD": [("P_TRI", "P", 1), ("B", "B", -1), ("D", "D", 1)],
    "L_DE": [("D", "D", -1), ("E", "E", 1)],
    "L_CEF": [("C_AC", "C", -1), ("C_PC", "C", -1), ("E", "E", -1)],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(passed):
    return "PASS" if passed else "FAIL"


def write_csv(path, columns, rows):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def phase_map(common):
    bus = common["bus"]
    speeds = bus["signedSpeedFromCenter"]
    if any(speeds[index] != 1 for index in bus["mainAxisIndices"]):
        raise ValueError("Main cranks must have the same mechanically derived direction")
    expected_pitch = bus["moduleMm"] * bus["teeth"]
    if not np.allclose(np.diff(bus["centersYmm"]), expected_pitch, atol=1e-9):
        raise ValueError("The actual bus gear centers do not mesh")
    result = []
    for i, station in enumerate((-common["stationPitchMm"], 0, common["stationPitchMm"])):
        for side, sign in (("left", -1), ("right", 1)):
            angle = bus[f"{side}CrankIndicesDeg"][i]
            if angle not in (0, 180):
                raise ValueError("No manufactured crank indexing variant for this angle")
            result.append({"id": f"LEG_{i}_{side.upper()}", "shaft": f"MAIN_{i}",
                           "crankPartId": f"P_CRANK_INDEX_{angle}",
                           "phase_deg": angle, "x_mm": sign*common["footHalfTrackMm"],
                           "y_mm": station, "orientation": "same sagittal direction"})
    return result


class GaitStudy:
    def __init__(self, common, step_deg=0.5):
        if not 0 < step_deg <= 180:
            raise ValueError("Crank sampling interval must be in (0,180] degrees")
        self.common = common
        self.scale = common["linkageScale"] / CONFIG["linkage"]["scale"]
        self.legs = phase_map(common)
        self.step_deg = step_deg
        self.epsilon = 1e-5
        self.gravity = common["gravity"]
        self.radius = common["footRadiusMm"]
        self.names = list(LINKS)
        self.forward_sign = -1
        switch = lambda theta: self.points(theta)["F"][1]-self.points(theta+math.pi)["F"][1]
        boundaries = np.linspace(0, 2*math.pi, 73)
        self.switches = [brentq(switch, a, b) for a, b in zip(boundaries[:-1], boundaries[1:])
                         if switch(a)*switch(b) < 0]
        events = [angle+offset for angle in self.switches for offset in (-1e-7, 1e-7)]
        self.angles = np.unique(np.r_[np.deg2rad(np.arange(0, 360, step_deg)), events])
        self.reference_moment = self.moving_mass_moment(0)

    @lru_cache(maxsize=16384)
    def points(self, theta):
        return {key: point*self.scale for key, point in gait(theta).items()}

    def mass_geometry(self, points):
        centers, masses = {}, {}
        c = self.common
        for name, labels in LINKS.items():
            positions = [points[label] for label in labels]
            pairs = (list(zip(positions, positions[1:]+positions[:1]))
                     if len(positions) == 3 else [(positions[0], positions[1])])
            lengths = np.array([np.linalg.norm(b-a) for a, b in pairs])
            # Additive capsules, no infill credit or claim of CAD/slicer mass.
            areas = lengths*c["linkWidthMm"] + math.pi*c["linkWidthMm"]**2/4
            centers[name] = np.average([(a+b)/2 for a, b in pairs], axis=0, weights=areas)
            volume = float(areas.sum())
            masses[name] = volume*c["linkThicknessMm"]*c["plasticDensityGPerCm3"]/1e6
        return centers, masses

    @lru_cache(maxsize=16384)
    def moving_mass_moment(self, theta):
        moment = np.zeros(2)
        for leg in self.legs:
            points = self.points(theta + math.radians(leg["phase_deg"]))
            centers, masses = self.mass_geometry(points)
            moment += sum(masses[name]*centers[name] for name in self.names)
        return moment

    @lru_cache(maxsize=8192)
    def leg_info(self, theta):
        points = self.points(theta)
        centers, masses = self.mass_geometry(points)
        before, after = self.points(theta-self.epsilon), self.points(theta+self.epsilon)
        rates = {}
        for name, labels in LINKS.items():
            a, b = before[labels[1]]-before[labels[0]], after[labels[1]]-after[labels[0]]
            rates[name] = math.atan2(a[0]*b[1]-a[1]*b[0], float(a@b))/(2*self.epsilon)
        matrix, rhs = np.zeros((18, 18)), np.zeros((18, 3))
        for i, name in enumerate(self.names):
            row, center = 3*i, centers[name]
            rhs[row+1, 2] = masses[name]*self.gravity
            for variable, node, sign in INCIDENCE[name]:
                column = 2*VARIABLES.index(variable)
                arm = points[node]-center
                matrix[row, column] += sign
                matrix[row+1, column+1] += sign
                matrix[row+2, column] -= sign*arm[1]
                matrix[row+2, column+1] += sign*arm[0]
            if name == "L_CEF":
                # A circular sole's ground force acts below F, not at its center.
                arm = points["F"] + [0, -self.radius] - center
                rhs[row, 0] -= 1
                rhs[row+1, 1] -= 1
                rhs[row+2, 0] += arm[1]
                rhs[row+2, 1] -= arm[0]
        response = np.linalg.solve(matrix, rhs)
        residual = np.max(np.abs(matrix@response-rhs))
        return points, centers, masses, rates, response, float(residual)

    def pose(self, theta, mass_kg, center_offset=(0.0, 0.0),
             wind_y_n=0.0, wind_down_n=0.0, wind_application_yz=(0.0, 0.0),
             input_couple_nmm=0.0):
        if mass_kg <= 0:
            raise ValueError("Whole-machine mass must be positive")
        info = [self.leg_info(theta), self.leg_info(theta+math.pi)]
        active_phase = int(info[1][0]["F"][1] < info[0][0]["F"][1])
        foot = info[active_phase][0]["F"]
        active = [i for i, leg in enumerate(self.legs) if leg["phase_deg"] == active_phase*180]
        triangle = np.array([[self.legs[i]["x_mm"], self.legs[i]["y_mm"]+foot[0]]
                             for i in active])
        moment_delta = (self.moving_mass_moment(theta)-self.reference_moment)/mass_kg
        center = np.array(self.common["candidateCenterOfMassMm"][:2], float)
        center[1] += moment_delta[0]
        center += center_offset
        weight = mass_kg*self.gravity
        normal_total = weight+wind_down_n
        if normal_total <= 0:
            raise ValueError("Wind envelope removes the normal support load")
        wind_height = -foot[1]+self.radius+wind_application_yz[1]
        center[0] *= weight/normal_total
        center[1] = (weight*center[1]+wind_down_n*wind_application_yz[0]
                     + wind_y_n*wind_height-input_couple_nmm)/normal_total
        weights = np.linalg.solve(np.vstack([np.ones(3), triangle.T]), np.r_[1, center])
        margins = []
        for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
            edge = b-a
            arm = center-a
            value = abs(float(edge[0]*arm[1]-edge[1]*arm[0]))/np.linalg.norm(edge)
            margins.append(value)
        margin = min(margins) * (1 if weights.min() >= 0 else -1)
        dfoot = (self.points(theta+active_phase*math.pi+self.epsilon)["F"]
                 - self.points(theta+active_phase*math.pi-self.epsilon)["F"])/(2*self.epsilon)
        beta_rate = info[active_phase][3]["L_CEF"]
        velocity = np.array([-dfoot[0]-self.radius*beta_rate, -dfoot[1]])
        return info, active, triangle, weights, float(margin), velocity

    def summary(self):
        height, margin, gap, speed, minimum_fraction = [], [], [], [], []
        closure = 0.0
        constraints = (("A", "B", "AB"), ("A", "C", "AC"), ("P", "C", "PC"),
                       ("P", "B", "BP"), ("B", "D", "BD"), ("P", "D", "PD"),
                       ("D", "E", "DE"), ("C", "E", "CE"), ("C", "F", "CF"),
                       ("E", "F", "EF"))
        target_mass = 0.55
        for theta in self.angles:
            info, active, triangle, weights, support, velocity = self.pose(theta, target_mass)
            low = min(item[0]["F"][1] for item in info)
            height.append(-low+self.radius)
            margin.append(support)
            minimum_fraction.append(float(weights.min()))
            gap.append(abs(info[0][0]["F"][1]-info[1][0]["F"][1]))
            speed.append(self.forward_sign*velocity[0])
            for first, second, key in constraints:
                measured = np.linalg.norm(info[0][0][first]-info[0][0][second])
                expected = CONFIG["linkage"][key]*self.common["linkageScale"]
                closure = max(closure, abs(measured-expected))
        switch = lambda theta: self.points(theta)["F"][1]-self.points(theta+math.pi)["F"][1]
        crossings = []
        boundaries = np.linspace(0, 2*math.pi, 721)
        for a, b in zip(boundaries[:-1], boundaries[1:]):
            if switch(a)*switch(b) < 0:
                crossings.append(brentq(switch, a, b))
        jumps = []
        for theta in crossings:
            before = self.pose(theta-1e-7, target_mass)[-1]
            after = self.pose(theta+1e-7, target_mass)[-1]
            jumps.append({"crank_deg": math.degrees(theta),
                          "horizontal_velocity_jump_mm_per_rad": float(after[0]-before[0]),
                          "vertical_velocity_jump_mm_per_rad": float(after[1]-before[1])})
        return {
            "method": "co-oriented Jansen legs, mechanically phased 0/180, rigid circular-sole rolling constraints",
            "samples": len(self.angles), "step_deg": self.step_deg,
            "switch_one_sided_angles_deg": [math.degrees(angle+offset)
                                           for angle in self.switches for offset in (-1e-7, 1e-7)],
            "phase_map": self.legs, "closure_residual_mm": float(closure),
            "body_height_range_mm": [float(min(height)), float(max(height))],
            "body_bounce_mm": float(np.ptp(height)),
            "target_cog_minimum_support_margin_mm": min(margin),
            "target_cog_minimum_normal_fraction": min(minimum_fraction),
            "minimum_forward_rate_mm_per_rad": min(speed),
            "forward_axis": [0, self.forward_sign, 0],
            "advance_per_cycle_quadrature_mm": float(trapezoid(
                np.r_[speed, speed[0]], np.r_[self.angles, 2*math.pi])),
            "handoff_velocity_discontinuities": jumps,
            "within_tripod_constraint_mismatch_mm": 0.0,
            "within_tripod_mismatch_basis": "identical orientation/phase/geometry; an algebraic compatibility, NOT measured slip",
            "finite_sole_contact_audit_mm": None,
            "physical_continuous_walk_status": "UNKNOWN",
            "limitations": [
                "The required CG target is not a new CAD mass measurement.",
                "Zero within-tripod mismatch does not prove passive contact, floor friction or the inherited 3mm material-point target.",
                "Velocity jumps need compliance/impact validation; there is no dynamic or no-slip success claim.",
                "Outboard crank geometry, drive-bus backlash and swept parts still need final CAD."
            ],
        }

    def torque_profile(self, mass, journal_mu, resistance_mu, opposing_wind_n=0.0,
                       wind_down_n=0.0, wind_application_yz=(0.0, 0.0),
                       input_couples_nmm=None):
        rows = []
        maxima = dict(joint_n=0.0, crank_pin_n=0.0, fixed_pivot_n=0.0, ac_compression_n=0.0,
                      crank_pin_force_sum_n=0.0, fixed_pivot_force_sum_n=0.0,
                      equilibrium_residual=0.0, virtual_work_residual_nmm=0.0)
        gravity = self.gravity
        weight = mass*gravity
        normal_total = weight+wind_down_n
        ground_horizontal = self.forward_sign*(resistance_mu*normal_total+opposing_wind_n)
        if input_couples_nmm is None:
            input_couples_nmm = np.zeros(len(self.angles))
        if len(input_couples_nmm) != len(self.angles):
            raise ValueError("Drive-couple profile must use the same crank-angle grid")
        for index, theta in enumerate(self.angles):
            info, active, _, weights, margin, body_rate = self.pose(
                theta, mass, wind_y_n=opposing_wind_n, wind_down_n=wind_down_n,
                wind_application_yz=wind_application_yz, input_couple_nmm=input_couples_nmm[index])
            if weights.min() < -1e-9:
                raise ValueError("Target CG is outside the selected stance tripod")
            moving_rate = (self.moving_mass_moment(theta+self.epsilon)
                           - self.moving_mass_moment(theta-self.epsilon))/(2*self.epsilon)
            conservative_torque = normal_total*body_rate[1] + gravity*moving_rate[1]
            conservative_torque += ground_horizontal*body_rate[0]
            friction, reaction_torque = 0.0, 0.0
            for i, leg in enumerate(self.legs):
                local = info[leg["phase_deg"]//180]
                points, centers, masses, rates, response, residual = local
                fraction = weights[active.index(i)] if i in active else 0.0
                force = response @ np.array([fraction*ground_horizontal, fraction*normal_total, 1])
                forces = {name: force[2*j:2*j+2] for j, name in enumerate(VARIABLES)}
                norms = {name: float(np.linalg.norm(v)) for name, v in forces.items()}
                radii = self.common["jointRadiiMm"]
                loss = radii["A"]*(norms["A_AB"]*abs(rates["L_AB"]-1)
                                   + norms["A_AC"]*abs(rates["L_AC"]-1))
                loss += radii["P"]*(norms["P_TRI"]*abs(rates["L_PBD"])
                                    + norms["P_PC"]*abs(rates["L_PC"]))
                for pin, first, second in (("B", "L_AB", "L_PBD"),
                                           ("D", "L_DE", "L_PBD"),
                                           ("E", "L_DE", "L_CEF")):
                    loss += radii[pin]*norms[pin]*abs(rates[first]-rates[second])
                c_forces = [norms["C_AC"], norms["C_PC"],
                            np.linalg.norm(forces["C_AC"]+forces["C_PC"])]
                c_rates = [rates[name] for name in ("L_AC", "L_PC", "L_CEF")]
                loss += radii["C"]*max(sum(f*abs(rate-pin) for f, rate in zip(c_forces, c_rates))
                                       for pin in c_rates)
                friction += journal_mu*loss
                crank = forces["A_AB"]+forces["A_AC"]
                reaction_torque += points["A"][0]*crank[1]-points["A"][1]*crank[0]
                ac_axis = (points["C"]-points["A"])/np.linalg.norm(points["C"]-points["A"])
                maxima["joint_n"] = max(maxima["joint_n"], max(norms.values()))
                maxima["crank_pin_n"] = max(maxima["crank_pin_n"], float(np.linalg.norm(crank)))
                maxima["fixed_pivot_n"] = max(maxima["fixed_pivot_n"],
                                             float(np.linalg.norm(forces["P_TRI"]+forces["P_PC"])))
                maxima["crank_pin_force_sum_n"] = max(maxima["crank_pin_force_sum_n"],
                                                      norms["A_AB"]+norms["A_AC"])
                maxima["fixed_pivot_force_sum_n"] = max(maxima["fixed_pivot_force_sum_n"],
                                                        norms["P_TRI"]+norms["P_PC"])
                maxima["ac_compression_n"] = max(maxima["ac_compression_n"],
                                                 float(forces["A_AC"]@ac_axis), 0)
                maxima["equilibrium_residual"] = max(maxima["equilibrium_residual"], residual)
            error = abs(reaction_torque-conservative_torque)
            maxima["virtual_work_residual_nmm"] = max(maxima["virtual_work_residual_nmm"], error)
            rows.append([math.degrees(theta), conservative_torque, friction,
                         max(0.0, conservative_torque+friction), margin])
        if maxima["virtual_work_residual_nmm"] > 1e-4:
            raise RuntimeError(f"Leg reaction torque disagrees with virtual work: {maxima}")
        return np.array(rows), maxima


def rotor_outline(radius_m, common, blades, sweep_deg, angle_deg):
    cfg = common["rotor"]
    r = np.linspace(radius_m*cfg["innerRadiusFraction"], radius_m, 21)
    curved = math.radians(sweep_deg)*np.linspace(0, 1, len(r))
    offsets = np.deg2rad(angle_deg+np.arange(blades)*360/blades)
    angles = offsets[:, None]+curved
    return np.stack([r*np.cos(angles), r*np.sin(angles)], axis=-1)


def static_jet_proxy(radius_mm, span_mm, common, fluid, blades, sweep_deg,
                     offset_fraction, velocity, sigma_mm, step_deg=2.0, rays=256):
    """First-hit ray shadowing and local panel-normal drag; no solved fluid field."""
    if (min(radius_mm, span_mm, sigma_mm, fluid["airDensityKgM3"], fluid["airKinematicViscosityM2S"]) <= 0
            or velocity < 0 or blades < 1 or rays < 32 or not 0 < step_deg <= 360):
        raise ValueError("Invalid static-jet dimensions, material/flow values, or sampling grid")
    radius, span, sigma = radius_mm/1000, span_mm/1000, sigma_mm/1000
    z = np.linspace(-radius, radius, rays, endpoint=False)+radius/rays
    dz = 2*radius/rays
    axial_integral = sigma*math.sqrt(math.pi)*erf(span/(2*sigma))
    dynamic_pressure_area = (0.5*fluid["airDensityKgM3"]*velocity**2*axial_integral*dz
                             * np.exp(-((z-offset_fraction*radius)/sigma)**2))
    coefficient = common["rotor"]["proxyPanelDragCoefficient"]
    result = []
    for angle in np.arange(0, 360, step_deg):
        panels = rotor_outline(radius, common, blades, sweep_deg, angle)
        start = panels[:, :-1].reshape(-1, 2)
        delta = (panels[:, 1:]-panels[:, :-1]).reshape(-1, 2)
        dz_panel = delta[:, 1]
        usable = np.abs(dz_panel) > 1e-12
        t = np.zeros((len(start), len(z)))
        np.divide(z[None, :]-start[:, 1, None], dz_panel[:, None],
                  out=t, where=usable[:, None])
        intersects = usable[:, None] & (t >= 0) & (t < 1)
        y = start[:, 0, None]+t*delta[:, 0, None]
        distances = np.where(intersects, y, np.inf)
        first = np.argmin(distances, axis=0)
        hit_y = distances[first, np.arange(len(z))]
        hit = np.isfinite(hit_y)
        hit_y = np.where(hit, hit_y, 0)
        segment = delta[first]
        normal = np.column_stack([-segment[:, 1], segment[:, 0]])
        normal /= np.linalg.norm(normal, axis=1)[:, None]
        force_y = coefficient*dynamic_pressure_area*normal[:, 0]**2*hit
        force_z = coefficient*dynamic_pressure_area*normal[:, 0]*normal[:, 1]*hit
        torque_terms = hit_y*force_z-z*force_y
        result.append([float(angle), float(torque_terms.sum()), float(force_y.sum()),
                       float(force_z.sum()), float(torque_terms[torque_terms < 0].sum()),
                       float(dynamic_pressure_area[hit].sum()/dynamic_pressure_area.sum())])
    rho = fluid["airDensityKgM3"]
    whole_momentum = rho*velocity**2*math.pi*sigma**2
    whole_power = rho*velocity**3*math.pi*sigma**2/3
    axial_fraction = erf(span/(2*sigma))
    vertical_fraction = 0.5*(erf((radius-offset_fraction*radius)/sigma)
                             - erf((-radius-offset_fraction*radius)/sigma))
    return {
        "method": "uncalibrated first-hit local panel-normal drag; static only; NOT CFD",
        "angle_step_deg": step_deg, "rays": rays, "blade_count": blades,
        "sweep_deg": sweep_deg, "jet_offset_radius_fraction": offset_fraction,
        "peak_velocity_m_s": velocity, "velocity_sigma_mm": sigma_mm,
        "velocity_fwhm_diameter_mm": 2*math.sqrt(2*math.log(2))*sigma_mm,
        "measured_supply_lower_bound_nm": None,
        "ideal_intercepted_momentum_torque_ceiling_nm": 2*whole_momentum*radius*axial_fraction*vertical_fraction,
        "whole_jet_kinetic_power_w": whole_power,
        "rotor_diameter_reynolds_number": velocity*(2*radius)/fluid["airKinematicViscosityM2S"],
        "rows": result,
        "columns": ["rotor_deg", "proxy_torque_nm", "proxy_force_y_n", "proxy_force_z_n",
                    "negative_panel_torque_nm", "first_hit_projected_fraction"],
        "actual_self_start_status": "UNKNOWN",
    }


def gear_check(candidate, common):
    gear = common["gear"]
    if (gear["pressureAngleDeg"] != CONFIG["gears"]["pressure_angle"]
            or gear["backlashMm"] != CONFIG["gears"]["total_tangential_backlash"]):
        raise ValueError("Shared involute helper assumptions differ from the study")
    stages = []
    for ratio, (upstream, downstream) in zip(candidate["stageRatios"], candidate["stages"]):
        metrics = gear_metrics(gear["moduleMm"], gear["pinionTeeth"], gear["pinionTeeth"]*ratio)
        actual = float(np.linalg.norm(np.array(candidate["axisCentersYzMm"][upstream])
                                      - candidate["axisCentersYzMm"][downstream]))
        if not math.isclose(actual, metrics["center_distance_mm"], abs_tol=1e-8):
            raise ValueError(f"{candidate['id']} stage center mismatch")
        # The reused first-cut metric's hub-web radius is not applicable to new D bores.
        metrics.pop("root_web_mm")
        metrics["root_web_to_provisional_12mm_boss_mm"] = min(metrics["root_diameters_mm"])/2-6
        metrics["face_width_mm"] = gear["faceWidthMm"]
        stages.append({"axes": [upstream, downstream], **metrics})
    return {"stages": stages, "total_reduction": math.prod(candidate["stageRatios"]),
            "input_speed_sign_for_positive_crank": (-1)**len(stages),
            "full_mesh_collision_status": "UNKNOWN",
            "bearing_and_frame_relative_displacement_status": "UNKNOWN"}


def reflect_loads(profile, candidate, mesh_efficiency, bearing_drag_nmm):
    ratios = candidate["stageRatios"]
    reduction = math.prod(ratios)
    efficiency = mesh_efficiency**len(ratios)
    # Two meshes to each outer crank. All useful output conservatively traverses
    # two bus meshes, rather than claiming the center-crank fraction is known.
    bus_efficiency = mesh_efficiency**2
    bus_bearings = 10
    loss = 2*bearing_drag_nmm
    upstream_ratio, upstream_eff = 1.0, 1.0
    for i, ratio in enumerate(ratios):
        upstream_ratio *= ratio
        upstream_eff *= mesh_efficiency
        count = bus_bearings if i == len(ratios)-1 else 2
        loss += count*bearing_drag_nmm/(upstream_ratio*upstream_eff*(
            bus_efficiency if i == len(ratios)-1 else 1))
    reflected = profile[:, 3]/(reduction*efficiency*bus_efficiency)+loss
    return reflected/1000, {
        "total_reduction": reduction, "reducer_efficiency_assumption": efficiency,
        "bus_efficiency_upper_loss_model": bus_efficiency,
        "input_equivalent_bearing_drag_nm": loss/1000,
        "bearing_count": 2*(len(ratios)+1)+8,
        "note": "Every reducer and bus bearing counted; two extra bus meshes included. No lossless synchronization."
    }


def coupled_startup(study, candidate, index, common, force_y, force_down):
    required = np.zeros(len(study.angles))
    direction = (-1)**len(candidate["stageRatios"])
    for iteration in range(16):
        profile, maxima = study.torque_profile(
            candidate["massCasesKg"][index], common["journalFrictionCases"][index],
            common["horizontalResistanceCases"][index], opposing_wind_n=force_y,
            wind_down_n=force_down, wind_application_yz=candidate["axisCentersYzMm"]["I"],
            input_couples_nmm=direction*required*1000)
        updated, transmission = reflect_loads(profile, candidate,
                                              common["meshEfficiencyCases"][index],
                                              common["bearingDragNmmCases"][index])
        error = float(np.abs(updated-required).max())
        if error <= 1e-10:
            transmission.update({
                "support_drive_couple_iterations": iteration+1,
                "support_drive_couple_residual_nm": error,
                "support_drive_couple_definition": "required signed external input torque enters whole-body moment balance; fixed point with reaction/friction calculation, not the uncalibrated available wind torque",
            })
            return profile, maxima, updated, transmission
        required = updated
    raise RuntimeError(f"{candidate['id']}: support/required-input torque fixed point did not converge")


def compare_synchronization(cfg, output):
    common = cfg["common"]
    alt = common["synchronizationAlternative"]
    radius = alt["crankRadiusMm"]
    pitch = alt["stationPitchMm"]
    closure_error, minimum_singular = 0.0, float("inf")
    rows = []
    for degree in np.arange(0, 360, 0.25):
        theta = math.radians(degree)
        for phase in (0, math.pi/2):
            pins = np.array([[station+radius*math.cos(theta+phase),
                              radius*math.sin(theta+phase)] for station in (-pitch, 0, pitch)])
            closure_error = max(closure_error, float(np.abs(np.linalg.norm(np.diff(pins, axis=0), axis=1)-pitch).max()))
        jacobian = radius*np.array([[-math.sin(theta), 0], [0, math.sin(theta)],
                                    [-math.cos(theta), 0], [0, math.cos(theta)]])
        singular = float(np.linalg.svd(jacobian, compute_uv=False).min())
        minimum_singular = min(minimum_singular, singular)
        rows.append([degree, singular])
    comparison = []
    for candidate in cfg["candidates"]:
        case_data = []
        ratios = candidate["stageRatios"]
        total_ratio = math.prod(ratios)
        for i, label in enumerate(("low", "nominal", "high")):
            data = np.loadtxt(output/f"startup_{candidate['id']}_{label}.csv", delimiter=",", skiprows=1)
            mu = common["journalFrictionCases"][i]
            eta = common["meshEfficiencyCases"][i]
            bearing_drag = common["bearingDragNmmCases"][i]
            # The force norm bound covers both quartered rods and the driving
            # middle pin. Friction feedback is solved, not dropped as first order.
            feedback = 2*math.sqrt(2)*mu*alt["couplingJournalRadiusMm"]/radius
            if feedback >= 1:
                raise ValueError("Coupling-rod friction bound cannot transmit a positive useful load")
            rod_efficiency = 1-feedback
            upstream_ratio = upstream_eta = 1.0
            bearing_input = 2*bearing_drag
            for stage_index, ratio in enumerate(ratios):
                upstream_ratio *= ratio
                upstream_eta *= eta
                count = alt["mainBearingCount"] if stage_index == len(ratios)-1 else 2
                bearing_input += count*bearing_drag/(upstream_ratio*upstream_eta*(
                    rod_efficiency if stage_index == len(ratios)-1 else 1))
            preload = alt["preloadPerJointCasesN"][i]
            rod_volume = 2*(2*pitch)*alt["rodWidthMm"]*alt["rodThicknessMm"]
            rod_weight = rod_volume*common["plasticDensityGPerCm3"]/1e6*common["gravity"]
            extra_loss = mu*alt["couplingJournalRadiusMm"]*(alt["jointCount"]*preload+rod_weight)
            required = ((data[:, 3]+extra_loss)/(total_ratio*eta**len(ratios)*rod_efficiency)
                        + bearing_input)/1000
            force_bound = float((data[:, 3].max()+extra_loss)/(radius*rod_efficiency))
            section = rectangle_section(alt["rodWidthMm"], alt["rodThicknessMm"])
            critical = (math.pi**2*min(common["linkElasticModulusMpaCases"])
                        * section.inertia_min/pitch**2)
            case_data.append({
                "id": label, "same_mass_and_leg_loads_as_gear_bus": True,
                "gear_bus_peak_input_nm": float(data[:, 5].max()),
                "rod_bus_peak_input_nm": float(required.max()),
                "reduction_fraction": float(1-required.max()/data[:, 5].max()),
                "coupling_pin_journal_radius_mm": alt["couplingJournalRadiusMm"],
                "journal_mu": mu, "unmeasured_preload_each_n": preload,
                "friction_feedback_bound": feedback, "rod_bus_efficiency_bound": rod_efficiency,
                "rod_pin_force_upper_n": force_bound,
                "rod_segment_euler_screen_n": critical,
                "rod_segment_euler_ratio": critical/force_bound,
                "resultStatus": "UNKNOWN",
            })
        comparison.append({"designId": candidate["id"], "cases": case_data,
                           "gear_bus_bearings": 2*(len(ratios)+1)+8,
                           "rod_bus_bearings": 2*(len(ratios)+1)+4,
                           "domestic_bearing_cost_reduction_jpy": 4*187,
                           "new_parts": "2 rods, 6 indexed coupling cranks, 6 sleeve/pin joints and their fasteners; not fewer total interfaces by definition"})
    result = {
        "revisionId": cfg["revisionId"], "loadcaseId": "SYNC_SAME_LOADS_QUARTERED_RODS",
        "method": "closed-loop geometry/Jacobian plus conservative quasi-static friction bound; not complete assembly dynamics",
        "geometry": alt, "closure_residual_mm": closure_error,
        "minimum_relative_phase_constraint_singular_value_mm_per_rad": minimum_singular,
        "single_rod_dead_centers": [0, 180],
        "quartering_rationale": "orthogonal sine/cosine lever arms cannot both vanish; all three shafts are physically coupled in phase",
        "comparisons": comparison,
        "retained_baseline": "five-gear bus remains the common plotted baseline; the new rod option is not substituted into already generated figures",
        "decision": "carry the two-rod option to a small fit/drag coupon before selecting a production bus",
        "unresolved": [
            "Two three-hole rods overconstrain unequal printed station pitches; zero preload is not assumed.",
            "4mm OD stock journal selection and tolerances remain unresolved; the verified M3 Hirosugi OD6 sleeve is not interchangeable.",
            "Swept rod/rotor/gearbox keepouts, coupling-disc D-datum and assembly tool access need final solids.",
            "A lower predicted load alone does not qualify the alternate bus; extra bushings/fastener purchase lots can erase the JPY748 bearing saving."
        ],
        "resultStatus": "UNKNOWN",
    }
    dump(output/"synchronization_comparison.json", result)
    curves = []
    for record, color in zip(comparison, ("#6ad6a2", "#72baf4", "#c094ef")):
        curves.append((f'{record["designId"]}: 5歯車バス',
                       [[i, item["gear_bus_peak_input_nm"]*1000] for i, item in enumerate(record["cases"])], color))
        curves.append((f'{record["designId"]}: 直交2ロッド（予荷重も仮定）',
                       [[i, item["rod_bus_peak_input_nm"]*1000] for i, item in enumerate(record["cases"])],
                       {"#6ad6a2": "#2b9162", "#72baf4": "#3279ac", "#c094ef": "#77508f"}[color]))
    plot(output/"synchronization_comparison.svg", "同期機構を一度だけ限定比較",
         curves, "0=low / 1=nominal / 2=high（同じ質量・脚反力）", "必要入力 [mN·m]",
         ["直交した2ロッドで単一ロッドの死点を回避。3軸は独立駆動ではない。",
          "予荷重0/1/3Nは未測定感度。4個の玉軸受を減らす代わりに6個の摺動関節と組立公差が増える。",
          "既存の各案グラフは5歯車バスのまま。別モデルの有利な値を混ぜない。"])
    return result


def reference_beam_comparison(cfg, output):
    modulus = cfg["common"]["shaftElasticModulusMpa"]
    sets = [
        ("REFERENCE_ROUND_3", circle_section(3), "#ff9977"),
        ("REFERENCE_ROUND_4", circle_section(4), "#72baf4"),
        ("CANDIDATE_6D", d_section(6, 0.5), "#6ad6a2"),
    ]
    records, curves = [], []
    for name, section, color in sets:
        rows = []
        for length in (50, 75, 100, 125, 150, 175, 200):
            result = solve_beam(length, modulus, section, [(length/2, -1)],
                                [(0, "translation"), (length, "translation")])
            rows.append([length, result["max_deflection_mm"]])
        records.append({"partId": name, "section": asdict(section),
                        "columns": ["support_span_mm", "deflection_mm"], "values": rows})
        curves.append((name, rows, color))
    dump(output/"reference_support_span.json", {
        "revisionId": cfg["revisionId"], "loadcaseId": "REFERENCE_1N_SIMPLY_SUPPORTED",
        "method": "Euler-Bernoulli beam; identical 1N center load and simple supports",
        "elastic_modulus_mpa": modulus, "records": records, "resultStatus": "UNKNOWN",
        "isMeasuredV2": False,
        "warning": "Reference old-style thin/long rod only. Actual V2 spans, section, supports and loads were not established."
    })
    plot(output/"reference_support_span.svg", "棒径・支持間隔の効果（V2実測の比較ではありません）",
         curves, "両支持の支点間隔 [mm]", "最大たわみ [mm]",
         ["全曲線：中央1N・単純支持・E=193000MPa。短縮/太径化の影響を同一条件で比較。",
          "3mm/4mm丸棒は参考模式モデル。V2の実寸や実荷重を推定して埋めたものではない。",
          "6mmDは弱軸Iを使用。軸受/フレームのたわみと軸の回転姿勢は別途必要。"])


def procurement_report(cfg, output):
    domestic = {item["id"]: item for item in cfg["procurement"]["domesticOptions"]}
    bearing = domestic["H_BEARING_686ZZ_DOMESTIC"]
    collar = domestic["H_COLLAR_6_DOMESTIC"]
    sleeves = domestic["H_SLEEVE_HYBRID_DOMESTIC"]
    source_items = {item["id"]: item for item in cfg["procurement"]["verifiedItems"]}
    output_rows, comparisons = [], []
    for candidate in cfg["candidates"]:
        ident = candidate["id"]
        bearings = 2*(len(candidate["stageRatios"])+1)+8
        collars = 2*(candidate["shafts140mm"]+candidate["shafts120mm"])
        lines = [
            {"sku": "686ZZ", "required": bearings, "buy": bearings, "currency": "JPY",
             "subtotal": bearings*bearing["unitPriceJpyTaxIncluded"], "tax": "included",
             "source": bearing["source"]},
            {"sku": "SC0606C", "required": collars, "buy": collars, "currency": "JPY",
             "subtotal": collars*collar["unitPriceJpyTaxIncluded"], "tax": "included",
             "source": collar["source"]},
        ]
        for sku, needed, unit in zip(sleeves["skus"], sleeves["requiredQuantitiesBeforeFinalCAD"],
                                     sleeves["unitPricesJpyExTax"]):
            count = max(needed, sleeves["minimumOrderEachSku"])
            lines.append({"sku": sku, "required": needed, "buy": count, "currency": "JPY",
                          "subtotal": round(count*unit*1.1), "tax": "10% added to ex-tax list price",
                          "source": sleeves["sources"][0]})
        for item_id, quantity in (("SHAFT_6D_140", candidate["shafts140mm"]),
                                  ("SHAFT_6D_120", candidate["shafts120mm"])):
            item = source_items[item_id]
            lines.append({"sku": item["sku"], "required": quantity, "buy": quantity,
                          "currency": "USD", "subtotal": round(quantity*item["unitPrice"], 2),
                          "tax": "Japan landed tax unknown", "source": item["source"]})
        domestic_subtotal = sum(item["subtotal"] for item in lines if item["currency"] == "JPY")
        usd_subtotal = sum(item["subtotal"] for item in lines if item["currency"] == "USD")
        fx_cases = []
        for rate in cfg["budget"]["foreignExchangeJpyPerUsdSensitivity"]:
            subtotal = round(domestic_subtotal+usd_subtotal*rate)
            fx_cases.append({"jpy_per_usd_assumption": rate,
                             "quoted_subset_jpy": subtotal,
                             "remaining_to_20000_before_unpriced_items_jpy": 20000-subtotal,
                             "complete_budget_status": "FAIL" if subtotal > 20000 else "UNKNOWN"})
        comparisons.append({
            "designId": ident, "quoted_lines": lines, "domestic_subset_jpy": domestic_subtotal,
            "import_shaft_subset_usd": usd_subtotal, "fx_cases": fx_cases,
            "unpriced": ["M2/M3 bolts and locknuts by real sizes/grades and purchase lots",
                         "thrust washers and inner-ring-only spacers",
                         "printed/sliced material, guards, toe material",
                         "import tax, exchange/payment fees and separately stated shipping"],
            "interface_gates": ["13mm nonflanged bearing seats instead of 14mm flanged seats",
                                "15mm collar face isolated from shield/outer ring",
                                "hybrid OD6/M3 A-P joints and OD4/M2 free joints",
                                "M3 root/core strength and actual clamp-stack clearance",
                                "printed D-bore coupon, shaft fit and axial retention"],
            "complete_cost_jpy": None, "resultStatus": "UNKNOWN",
        })
        for line in lines:
            output_rows.append([ident, line["sku"], line["required"], line["buy"], line["currency"],
                                line["subtotal"], line["tax"], line["source"]])
    write_csv(output/"procurement_subset.csv",
              ["design", "sku", "assembly_quantity_provisional", "purchase_quantity", "currency",
               "subtotal", "tax_basis", "source"], output_rows)
    dump(output/"procurement.json", {
        "revisionId": cfg["revisionId"], "checkedDateJst": cfg["procurement"]["checkedDateJst"],
        "resultStatus": "UNKNOWN", "records": comparisons,
        "sources_and_terms": cfg["procurement"],
        "not_a_release_bom": True,
        "note": "Domestic options replace expensive import bearings/collars only after interface redesign. No full-price, in-stock, or complete assembly PASS."
    })


def rib_section_screen(cfg, output):
    candidate = json.loads((output/"candidate_C.json").read_text())
    shaft = next(item for item in candidate["structure"]["members"] if item["partId"] == "S_INTERMEDIATE")
    load = max(abs(item["value_n_or_nmm"]) for item in shaft["reactions"] if item["kind"] == "force")
    options = cfg["common"]["ribSectionScreen"]
    length = options["preserveStationsMm"][-1]-options["preserveStationsMm"][0]
    modulus = min(cfg["common"]["linkElasticModulusMpaCases"])
    alpha = math.radians(cfg["common"]["gear"]["pressureAngleDeg"])
    available = (candidate["structure"]["shaft_only_backlash_budget_mm"]
                 - candidate["structure"]["equivalent_backlash_consumption_upper_mm"])
    trials = []
    for width in options["widthsMm"]:
        for thickness in options["thicknessesMm"]:
            section = rectangle_section(width, thickness)
            result = solve_beam(length, modulus, section, [(length/2, -load)],
                                [(0, "translation"), (length, "translation")])
            budget_used = (4*math.tan(alpha)*result["max_deflection_mm"]
                           + 2*cfg["common"]["gear"]["faceWidthMm"]*result["max_rotation_rad"])
            passed = (budget_used <= available
                      and result["max_bending_stress_mpa"] <= cfg["criteria"]["printedCouponStrengthScreenMpa"])
            trials.append({
                "width_mm": width, "thickness_mm": thickness, "volume_proxy_mm3": width*thickness*length,
                "deflection_mm": result["max_deflection_mm"],
                "bending_stress_mpa": result["max_bending_stress_mpa"],
                "two_rib_equivalent_backlash_consumption_mm": budget_used,
                "conditional_screen": status(passed),
            })
    passed = [item for item in trials if item["conditional_screen"] == "PASS"]
    selected = min(passed, key=lambda item: item["volume_proxy_mm3"]) if passed else None
    dump(output/"rib_section_screen_C.json", {
        "revisionId": cfg["revisionId"], "designId": "C",
        "loadcaseId": candidate["structure"]["loadcaseId"],
        "sourcePartId": shaft["partId"], "sourceInstanceId": shaft["instanceId"],
        "method": "bounded 16-section linear beam coupon search, not topology optimization or full frame FEM",
        "preserve_stations_mm": options["preserveStationsMm"], "load_position_mm": length/2,
        "transverse_load_n": load, "load_source": "maximum intermediate-shaft bearing reaction in the same high-load envelope",
        "elastic_modulus_mpa_assumed": modulus, "remaining_backlash_budget_mm": available,
        "trials": trials, "selected_coupon_only": selected, "resultStatus": "UNKNOWN",
        "full_frame_status": "UNKNOWN",
        "missing": ["actual frame preserve bosses and connections", "moving and assembly/tool keepouts",
                    "3D loads and frame torsion", "print anisotropy/creep/strength data"],
    })
    series = []
    for thickness, color in zip(options["thicknessesMm"], ("#ff9977", "#c094ef", "#72baf4", "#6ad6a2")):
        series.append((f"厚さ {thickness:g}mm",
                       [[row["width_mm"], row["two_rib_equivalent_backlash_consumption_mm"]]
                        for row in trials if row["thickness_mm"] == thickness], color))
    series.append(("軸の変形を差し引いた残余予算",
                   [[min(options["widthsMm"]), available], [max(options["widthsMm"]), available]], "#eeeeee"))
    plot(output/"rib_section_screen_C.svg", "C / 保存点間リブの断面探索（全フレーム未検証）",
         series, "リブ幅 [mm]", "中心ずれ・傾きのバックラッシ換算 [mm]",
         [f"単純支持 {length:g}mm / 中央 {load:.3g}N / E={modulus:g}MPa / 16候補を実計算。",
          "2部材の最大変位・角度を保守的に加算。これは部材クーポンで、実際のフレーム剛性ではない。",
          "Cを生成設計済みの完成機とはしない。保存ボス・工具空間・可動域を備えた全体形状は次のゲート。"])


def rotor_mass_proxy(candidate, common, selected):
    radius = candidate["rotorDiameterMm"]/2
    section = rotor_outline(radius, common, selected["blades"], selected["sweep_deg"], 0)
    segment_lengths = np.linalg.norm(np.diff(section, axis=1), axis=2)
    segment_centers = (section[:, :-1]+section[:, 1:])/2
    length = segment_lengths.sum()
    rotor = common["rotor"]
    blades_volume = length*rotor["spanMm"]*rotor["wallMm"]
    plate_volume = 2*math.pi*(radius**2-(common["shaftDiameterMm"]/2)**2)*rotor["endplateThicknessMm"]
    density = common["plasticDensityGPerCm3"]/1e6
    segment_masses = segment_lengths*rotor["spanMm"]*rotor["wallMm"]*density
    blade_inertia = np.sum(segment_masses*(np.sum(segment_centers**2, axis=2)
                                          +(segment_lengths**2+rotor["wallMm"]**2)/12))
    plate_inertia = plate_volume*density*(radius**2+(common["shaftDiameterMm"]/2)**2)/2
    inertia = float(blade_inertia+plate_inertia)*1e-6
    return {"blade_volume_proxy_mm3": float(blades_volume),
            "endplate_volume_proxy_mm3": plate_volume,
            "mass_kg_proxy": (float(blades_volume)+plate_volume)*density,
            "polar_mass_inertia_about_rotor_axis_kg_m2_proxy": inertia,
            "rotor_inertia_reflected_to_crank_kg_m2_proxy": inertia*math.prod(candidate["stageRatios"])**2,
            "additional_rotor_input_torque_nm_per_rad_s2": inertia,
            "angular_acceleration_rad_s2": None,
            "dynamic_start_status": "UNKNOWN; static breakaway excludes acceleration, drivetrain/link inertia and impacts; inertia cannot prove start from a dead angle",
            "method": "additive thin walls plus full annular endplates; overlap, bosses, holes and slice settings not resolved"}


def structures(candidate, cfg, maxima, required_input_nm, force_wind_n, rotor_mass):
    common, criteria = cfg["common"], cfg["criteria"]
    section = d_section(common["shaftDiameterMm"], common["shaftFlatDepthMm"])
    e, g = common["shaftElasticModulusMpa"], common["shaftShearModulusMpa"]
    output_torque = required_input_nm*1000*math.prod(candidate["stageRatios"])
    pinion_radius = common["gear"]["moduleMm"]*common["gear"]["pinionTeeth"]/2
    alpha = math.radians(common["gear"]["pressureAngleDeg"])
    input_gear_force = required_input_nm*1000/pinion_radius/math.cos(alpha)
    final_wheel_radius = pinion_radius*candidate["stageRatios"][-1]
    output_gear_force = output_torque/final_wheel_radius/math.cos(alpha)
    loads = [
        ("S_INPUT", "input / rotor", 140, [20, 120],
         [(70, -(force_wind_n+rotor_mass*common["gravity"])),
          (27, -input_gear_force)], required_input_nm*1000),
        ("S_INTERMEDIATE", "intermediate upper load envelope", 120, [20, 100],
         [(27, -(input_gear_force+output_gear_force))], output_torque),
        ("S_MAIN", "crank / drive bus upper load envelope", 140, [20, 120],
         [(7, -maxima["crank_pin_n"]), (133, -maxima["crank_pin_n"]),
          (27, -output_gear_force)], output_torque),
    ]
    results = []
    for part, label, length, support_positions, points, torque in loads:
        bearing_constraints = [(x, "translation") for x in support_positions]
        weight_per_mm = section.area*7.85e-6*common["gravity"]
        result = solve_beam(length, e, section, points, bearing_constraints,
                            distributed_load=-weight_per_mm)
        refined = solve_beam(length, e, section, points, bearing_constraints,
                             distributed_load=-weight_per_mm, elements=48)
        result.update({
            "partId": part, "instanceId": f"{candidate['id']}_{part}_STUDY",
            "label": label, "section": asdict(section), "length_mm": length,
            "elastic_modulus_mpa": e, "supports": bearing_constraints, "loads_n": points,
            "distributed_load_n_per_mm": -weight_per_mm,
            "torsion": twist_bound(torque, support_positions[-1]-support_positions[0], g, section),
            "refinement_deflection_change_mm": abs(result["max_deflection_mm"]-refined["max_deflection_mm"]),
            "displayAmplification": 1000, "resultStatus": "UNKNOWN",
            "boundary_note": "Radial simple supports; rotations free; frame and bearing compliance excluded.",
            "scope": "candidate dimensions, not final CAD; loads deliberately aligned for a bending upper envelope",
        })
        results.append(result)
    pivot_section = circle_section(common["fixedPivotDiameterMm"])
    pivot_force = maxima["fixed_pivot_force_sum_n"]
    pivot = solve_beam(common["fixedPivotCantileverMm"], e, pivot_section,
                       [(common["fixedPivotCantileverMm"], -pivot_force)],
                       [(0, "translation"), (0, "rotation")])
    pivot.update({"partId": "S_FIXED_PIVOT", "instanceId": f"{candidate['id']}_PIVOT_STUDY",
                  "section": asdict(pivot_section), "length_mm": common["fixedPivotCantileverMm"],
                  "elastic_modulus_mpa": e, "supports": [(0, "translation"), (0, "rotation")],
                  "loads_n": [(common["fixedPivotCantileverMm"], -pivot_force)],
                  "displayAmplification": 20, "resultStatus": "UNKNOWN",
                  "boundary_note": "M3 bolt core screening only; OD6 sleeve stiffness ignored. Sum of separate pivot force magnitudes at full overhang bounds their bending. Printed boss/root flexibility and thread notch are not validated.",
                  "section_acceptance": common["fixedPivotSectionStatus"],
                  "torsion": None})
    results.append(pivot)
    ac_length = CONFIG["linkage"]["AC"]*common["linkageScale"]
    compression = maxima["ac_compression_n"]
    link_section = rectangle_section(common["linkWidthMm"], common["linkThicknessMm"])
    links = []
    for modulus in common["linkElasticModulusMpaCases"]:
        critical = math.pi**2*modulus*link_section.inertia_min/ac_length**2
        ratio = critical/compression if compression > 0 else None
        if compression >= critical:
            ecc_deflection = stress = None
        else:
            eccentricity = common["jointEccentricityMm"]
            secant = 1/math.cos(ac_length/2*math.sqrt(compression/(modulus*link_section.inertia_min)))
            ecc_deflection = eccentricity*(secant-1)
            stress = compression/link_section.area + (
                compression*(eccentricity+ecc_deflection)*link_section.extreme_fiber/link_section.inertia_min)
        bending = solve_beam(ac_length, modulus, link_section,
                             [(ac_length/2, -common["linkOutOfPlaneForceFraction"]*maxima["joint_n"])],
                             [(0, "translation"), (ac_length, "translation")])
        combined = None if stress is None else stress+bending["max_bending_stress_mpa"]
        displacement = None if ecc_deflection is None else ecc_deflection+bending["max_deflection_mm"]
        links.append({
            "elastic_modulus_mpa": modulus, "compression_n": compression,
            "euler_critical_load_n": critical, "euler_ratio": ratio,
            "secant_eccentric_deflection_mm": ecc_deflection,
            "combined_deflection_upper_mm": displacement,
            "combined_stress_screen_mpa": combined,
            "conditional_stress_screen": status(combined is not None and combined <= criteria["printedCouponStrengthScreenMpa"]),
            "conditional_buckling_screen": status(ratio is not None and ratio >= criteria["bucklingScreenRatio"]),
            "beam": bending,
        })
    link = links[0]["beam"].copy()
    link.update({"partId": "L_AC", "instanceId": f"{candidate['id']}_L_AC_STUDY",
                 "length_mm": ac_length, "section": asdict(link_section),
                 "elastic_modulus_mpa": common["linkElasticModulusMpaCases"][0],
                 "supports": [(0, "translation"), (ac_length, "translation")],
                 "loads_n": [(ac_length/2, -common["linkOutOfPlaneForceFraction"]*maxima["joint_n"])],
                 "displayAmplification": 20, "resultStatus": "UNKNOWN",
                 "torsion": None, "scenarios": links,
                 "boundary_note": "Pin-ended weak-axis bending. Eccentric compression is separate secant-column screening; no FDM strength certificate."})
    results.append(link)
    # Center motion and shaft-angle errors consume an explicit gear backlash budget.
    center_motion = results[0]["max_deflection_mm"]+results[1]["max_deflection_mm"]
    tilt_motion = common["gear"]["faceWidthMm"]*(
        results[0]["max_rotation_rad"]+results[1]["max_rotation_rad"])
    equivalent_backlash = 2*math.tan(alpha)*center_motion+tilt_motion
    limit = criteria["gearTangentialBacklashMm"]*criteria["maximumBacklashConsumptionFraction"]
    return {
        "method": "beam and eccentric-column screening, with weak-axis D bounds; not assembly FEM",
        "loadcaseId": f"{candidate['id']}_START_HIGH_OPPOSING_JET_HYP_8_20",
        "members": results,
        "gear_center_motion_upper_mm": center_motion,
        "shaft_tilt_across_face_upper_mm": tilt_motion,
        "equivalent_backlash_consumption_upper_mm": equivalent_backlash,
        "shaft_only_backlash_budget_mm": limit,
        "shaft_only_conditional_screen": status(equivalent_backlash <= limit),
        "assembly_mesh_alignment_status": "UNKNOWN",
        "missing": ["exact supplier fits and ring faces", "housing/frame compliance",
                    "D profile clocking", "actual printed properties", "full collision sweep"],
    }


def text(x, y, value, size=15, color="#dce5f2"):
    return (f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="{size}" '
            f'fill="{color}">{html.escape(str(value))}</text>')


def svg(path, body, width=1200, height=800):
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                    f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#101722"/>'
                    + "".join(body) + "</svg>\n")


def plot(path, title, series, xlabel, ylabel, footer, x_range=None):
    body = [text(45, 42, title, 23), text(45, 72, "条件付き計算 / CFD・実測・実機合格ではありません", 16, "#f7c66f")]
    points = [np.array(values) for _, values, _ in series]
    xmin = min(p[:, 0].min() for p in points) if x_range is None else x_range[0]
    xmax = max(p[:, 0].max() for p in points) if x_range is None else x_range[1]
    ymin = min(0.0, min(p[:, 1].min() for p in points))
    ymax = max(p[:, 1].max() for p in points)
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Degenerate plot range")
    lo, hi = ymin-(ymax-ymin)*0.05, ymax+(ymax-ymin)*0.08
    sx = lambda x: 95+(x-xmin)/(xmax-xmin)*1020
    sy = lambda y: 540-(y-lo)/(hi-lo)*405
    for fraction in np.linspace(0, 1, 6):
        value = lo+fraction*(hi-lo)
        y = sy(value)
        body += [f'<path d="M95 {y}H1115" stroke="#304052"/>', text(12, y+5, f"{value:.3g}", 13)]
    ticks = sorted(set(x for _, values, _ in series for x, _ in values)) if xmax-xmin <= 3 else np.linspace(xmin, xmax, 5)
    for value in ticks:
        x = sx(value)
        body += [f'<path d="M{x} 135V548" stroke="#263545"/>',
                 text(x-12, 563, f"{value:g}", 13)]
    body += [text(490, 584, xlabel, 16), text(95, 113, ylabel, 16)]
    for i, (label, values, color) in enumerate(series):
        coords = " ".join(f"{sx(x):.3f},{sy(y):.3f}" for x, y in values)
        body += [f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>',
                 text(100+(i%2)*535, 620+(i//2)*24, label, 14, color)]
        if len(values) <= 20:
            body += [f'<circle cx="{sx(x):.3f}" cy="{sy(y):.3f}" r="3" fill="{color}"/>'
                     for x, y in values]
    for i, line in enumerate(footer):
        body.append(text(45, 720+i*22, line, 13))
    svg(path, body, height=max(800, 755+len(footer)*22))


def beam_image(path, ident, report, revision):
    member = report["members"]
    body = [text(40, 36, f"{ident} / 部材たわみの限定計算 / {revision}", 22),
            text(40, 65, report["loadcaseId"], 14, "#f7c66f"),
            text(40, 87, "候補寸法の梁モデル。最終CAD/FEM・実測ではない。灰=原形、色=計算変形（倍率表示）。", 14)]
    for i, item in enumerate(member):
        y0 = 175+i*158
        length = item["length_mm"]
        field = np.array(item["field"])
        scale_x = 750/length
        amplification = item["displayAmplification"]
        maximum = max(item["max_deflection_mm"], 1e-12)
        body += [text(40, y0-65, f'{item["partId"]} | E={item["elastic_modulus_mpa"]:g} MPa | '
                     f'{amplification}× | UNKNOWN', 16),
                 f'<path d="M95 {y0} H845" stroke="#8191a4" stroke-width="2"/>']
        for first, second in zip(field[:-1], field[1:]):
            ratio = abs((first[1]+second[1])/2)/maximum
            color = f"rgb({int(70+185*ratio)},{int(185-70*ratio)},{int(235-140*ratio)})"
            body.append(f'<path d="M{95+first[0]*scale_x:.3f} {y0-first[1]*scale_x*amplification:.3f} '
                        f'L{95+second[0]*scale_x:.3f} {y0-second[1]*scale_x*amplification:.3f}" '
                        f'stroke="{color}" stroke-width="3"/>')
        for position, kind in item["supports"]:
            x = 95+position*scale_x
            if kind == "translation":
                body.append(f'<path d="M{x} {y0} l-7 12 h14 z" fill="#96abbe"/>')
            else:
                body.append(f'<path d="M{x} {y0-18}v36" stroke="#96abbe" stroke-width="5"/>')
        for position, load in item["loads_n"]:
            x = 95+position*scale_x
            body += [f'<path d="M{x} {y0-44}v35 l-4 -7 m4 7 l4 -7" stroke="#f7c66f" fill="none"/>',
                     text(x+7, y0-39, f"{abs(load):.3g} N", 12, "#f7c66f")]
        body += [text(875, y0-5, f'最大 {maximum:.4g} mm', 15),
                 text(875, y0+18, f'位置 {item["max_deflection_x_mm"]:.2f} mm', 14),
                 text(875, y0+41, f'曲げ {item["max_bending_stress_mpa"]:.3g} MPa', 14),
                 text(95, y0+68, f'L={length:g} mm / 梁支点・力はJSONと共通 / ハウジング・はめあいの変形は未加算', 13)]
    body += [text(40, 955, "色は各部材の変位0→その最大値。共通応力尺度ではない。L_AC図は横荷重分のみ。", 14),
             text(40, 978, "偏心圧縮・座屈の別計算は同JSON。D断面ねじりはJtの上下界で扱い、極断面二次モーメントを代用しない。", 13)]
    svg(path, body, height=1010)


def run(cfg, output):
    output.mkdir(parents=True, exist_ok=True)
    common, fluid, criteria = cfg["common"], cfg["fluidCases"], cfg["criteria"]
    gait_study = GaitStudy(common)
    gait_summary = gait_study.summary()
    dump(output/"gait.json", gait_summary)
    summaries = []
    for candidate in cfg["candidates"]:
        ident = candidate["id"]
        radius = candidate["rotorDiameterMm"]/2
        trials = []
        for blades in common["rotor"]["bladeCountCandidates"]:
            for sweep in common["rotor"]["sweepAngleCandidatesDeg"]:
                for offset in common["rotor"]["jetOffsetRadiusFractions"]:
                    result = static_jet_proxy(radius, common["rotor"]["spanMm"], common, fluid,
                                              blades, sweep, offset,
                                              fluid["referencePeakVelocityMS"],
                                              fluid["referenceVelocitySigmaMm"], step_deg=5, rays=128)
                    values = np.array(result["rows"])
                    trials.append({"blades": blades, "sweep_deg": sweep, "offset": offset,
                                   "minimum_proxy_nm": float(values[:, 1].min()),
                                   "mean_proxy_nm": float(values[:, 1].mean())})
        selected = max(trials, key=lambda trial: trial["minimum_proxy_nm"])
        jet = static_jet_proxy(radius, common["rotor"]["spanMm"], common, fluid,
                               selected["blades"], selected["sweep_deg"], selected["offset"],
                               fluid["referencePeakVelocityMS"], fluid["referenceVelocitySigmaMm"],
                               step_deg=0.5, rays=512)
        jet_array = np.array(jet["rows"])
        force_wind = float(jet_array[:, 2].max())
        force_down = float(np.abs(jet_array[:, 3]).max())
        cases, curves, high_maxima = [], [], None
        for i, name in enumerate(("low", "nominal", "high")):
            profile, maxima, required, transmission = coupled_startup(
                gait_study, candidate, i, common, force_wind, force_down)
            rows = np.column_stack([profile, required])
            write_csv(output/f"startup_{ident}_{name}.csv",
                      ["crank_deg", "gravity_and_external_nmm", "journal_nmm", "required_crank_nmm",
                       "target_cog_support_margin_mm", "required_input_nm"], rows)
            cases.append({
                "id": name, "mass_kg_assumption": candidate["massCasesKg"][i],
                "journal_mu_assumption": common["journalFrictionCases"][i],
                "horizontal_resistance_mu_assumption": common["horizontalResistanceCases"][i],
                "opposing_force_n_from_hypothetical_jet": force_wind,
                "downward_force_n_envelope_from_hypothetical_jet": force_down,
                "wind_application_body_yz_mm": candidate["axisCentersYzMm"]["I"],
                "normal_loads": "force/moment balance uses wind force, required signed input couple and mg+downward force; separate aerodynamic component maxima form a conservative envelope",
                "peak_input_nm": float(required.max()), "peak_crank_nmm": float(profile[:, 3].max()),
                "positive_crank_work_per_revolution_j": float(trapezoid(
                    np.r_[profile[:, 3], profile[0, 3]], np.r_[gait_study.angles, 2*math.pi])/1000),
                "transmission": transmission, "loads": maxima,
            })
            curves.append((f'{name}: 未測定の質量・摩擦を仮定',
                           np.column_stack([profile[:, 0], required*1000]).tolist(),
                           ("#6ad6a2", "#72baf4", "#ff9977")[i]))
            if name == "high":
                high_maxima = maxima
        assert high_maxima is not None
        rotor_mass = rotor_mass_proxy(candidate, common, selected)
        structural = structures(candidate, cfg, high_maxima, cases[-1]["peak_input_nm"],
                                force_wind+force_down, rotor_mass["mass_kg_proxy"])
        downstream_high = max(0.0, cases[-1]["peak_input_nm"]-2*common["bearingDragNmmCases"][-1]/1000)
        net_measurement_target = criteria["measuredTorqueMarginTarget"]*downstream_high
        required_factor = net_measurement_target+2*common["bearingDragNmmCases"][-1]/1000
        margin_under_wind = []
        for sign_y in (-1, 1):
            for sign_z in (-1, 1):
                for dx in (-5, 5):
                    for dy in (-5, 5):
                        for sample_index, theta in enumerate(gait_study.angles[::4]):
                            nominal_mass = candidate["massCasesKg"][1]
                            margin_under_wind.append(gait_study.pose(
                                theta, nominal_mass, (dx, dy), wind_y_n=sign_y*force_wind,
                                wind_down_n=sign_z*force_down,
                                wind_application_yz=candidate["axisCentersYzMm"]["I"],
                                input_couple_nmm=(-1)**len(candidate["stageRatios"])*required[sample_index*4]*1000)[4])
        # Necessary energy bounds never become sufficient torque claims.
        proxy_scenarios = []
        for sigma in fluid["velocitySigmaMm"]:
            for velocity in fluid["peakVelocityMS"]:
                check = static_jet_proxy(radius, common["rotor"]["spanMm"], common, fluid,
                                         selected["blades"], selected["sweep_deg"], selected["offset"],
                                         velocity, sigma, step_deg=2, rays=256)
                values = np.array(check.pop("rows"))
                cell_force_y = float(values[:, 2].max())
                cell_force_down = float(np.abs(values[:, 3]).max())
                cell_profile, cell_loads, cell_required, cell_transmission = coupled_startup(
                    gait_study, candidate, -1, common, cell_force_y, cell_force_down)
                check.update({"minimum_proxy_nm": float(values[:, 1].min()),
                              "maximum_proxy_nm": float(values[:, 1].max()),
                              "opposing_force_n": cell_force_y, "downward_envelope_n": cell_force_down,
                              "recomputed_high_required_input_nm": float(cell_required.max()),
                              "recomputed_high_loads": cell_loads,
                              "recomputed_transmission": cell_transmission,
                              "recomputed_support_margin_min_mm": float(cell_profile[:, 4].min()),
                              "ideal_ceiling_cannot_cover_high_input": bool(check[
                                  "ideal_intercepted_momentum_torque_ceiling_nm"] < float(cell_required.max())),
                              "actual_resultStatus": "UNKNOWN"})
                proxy_scenarios.append(check)
        quantities = {
            "printed_link_bodies": 36, "printed_cranks": 6, "printed_main_bus_gears": 5,
            "printed_reducer_gears": 2*len(candidate["stageRatios"]),
            "printed_rotor_subassembly_target": 2, "frame_panels_target": 2,
            "frame_cross_ties_target": 4, "guards_target": 2,
            "joint_pivot_sleeves_target": 6*6, "joint_bolts_target": 6*6,
            "joint_locknuts_target": 6*6, "shaft_bearings": 2*(len(candidate["stageRatios"])+1)+8,
            "d_shafts": candidate["shafts140mm"]+candidate["shafts120mm"],
            "axial_collars_target": 2*(candidate["shafts140mm"]+candidate["shafts120mm"]),
        }
        shaft_usd = candidate["shafts140mm"]*5.09+candidate["shafts120mm"]*4.69
        summary = {
            "revisionId": cfg["revisionId"], "designId": ident, "resultStatus": "UNKNOWN",
            "qualifiedPrototype": False, "candidate": candidate,
            "geometryStatus": cfg["geometryStatus"], "gears": gear_check(candidate, common),
            "part_count_architecture_lower_bound": sum(quantities.values()),
            "part_count_decomposition": quantities,
            "part_count_note": "Missing frame/guard fasteners, shims, fitted sleeves and retention details. Not final BOM/instance count.",
            "actual_mass_kg": None, "mass_assumption_range_kg": candidate["massCasesKg"],
            "rotor_mass_proxy": rotor_mass,
            "verified_shaft_subtotal_usd": shaft_usd,
            "shaft_subtotal_jpy_fx_sensitivity": {str(rate): round(shaft_usd*rate)
                                                 for rate in cfg["budget"]["foreignExchangeJpyPerUsdSensitivity"]},
            "complete_purchased_plus_printed_cost_jpy": None, "procurementStatus": "UNKNOWN",
            "rotor_proxy_search": {"candidates": trials, "selected_for_study": selected,
                                   "selection": "minimum signed torque in HYP_8_20 only; not a measured optimum or release selection"},
            "jet": jet, "fluid_sensitivity": proxy_scenarios, "startup": cases,
            "measured_supply_lower_bound_nm": None,
            "measurement_target_gross_aerodynamic_nm": required_factor,
            "measurement_target_static_net_input_nm": net_measurement_target,
            "measurement_net_definition": "After the SAME two input bearings. Compared to downstream demand excluding those two bearings, so drag is not counted twice.",
            "uncalibrated_proxy_peak_speed_for_target_m_s": None,
            "proxy_speed_warning": "No fixed-load velocity extrapolation: wind force, COP, reactions and friction change with velocity. Each saved sensitivity cell recomputes those loads. No mapping from catalogue flow or distance.",
            "structure": structural,
            "target_cog_wind_and_5mm_margin_min_mm": min(margin_under_wind),
            "matrix": [
                {"criterion": "剛リンク閉路", "resultStatus": status(gait_summary["closure_residual_mm"] <= criteria["closureResidualMm"]),
                 "scope": "candidate skeleton only"},
                {"criterion": "機械的な位相経路", "resultStatus": "UNKNOWN",
                 "evidence": "5-gear 1:1 bus and indexed D-cranks defined; complete CAD sweep pending"},
                {"criterion": "接地・30cm連続歩行", "resultStatus": "UNKNOWN",
                 "evidence": "kinematic tripod compatibility only; handoff impacts and friction unknown"},
                {"criterion": "全角度自己始動", "resultStatus": "UNKNOWN",
                 "evidence": "measured supply lower bound is null"},
                {"criterion": "仮の噴流HYP_8_20・高抵抗ケース", "resultStatus":
                 "FAIL" if jet["ideal_intercepted_momentum_torque_ceiling_nm"] < cases[-1]["peak_input_nm"] else "UNKNOWN",
                 "scope": "hypothetical cell only; momentum ceiling is necessary, not a measured ReFa result"},
                {"criterion": "軸のみの噛合い変形予算", "resultStatus": structural["shaft_only_conditional_screen"],
                 "scope": "assumed sections/loads; excludes frame, bearing fits and print tolerances"},
                {"criterion": "印刷材・構造全体", "resultStatus": "UNKNOWN",
                 "evidence": "beam/column screens not final assembly or measured FDM properties"},
                {"criterion": "全周干渉・工具・組立", "resultStatus": "UNKNOWN"},
                {"criterion": "調達・税込2万円", "resultStatus": "UNKNOWN",
                 "evidence": "only shaft list-price subtotal verified; complete BOM not priced"}
            ],
        }
        dump(output/f"candidate_{ident}.json", summary)
        beam_image(output/f"deflection_{ident}.svg", ident, structural, cfg["revisionId"])
        plot(output/f"startup_{ident}.svg", f"{ident} / 全クランク角の必要入力トルク", curves,
             "クランク角 [deg]", "風車軸の必要トルク [mN m]",
             [f'{cfg["revisionId"]} / {structural["loadcaseId"]}',
              "規定した質量・摩擦・部材モデルの条件値。実ReFaの供給はUNKNOWN。風の力は逆風側の包絡。"])
        proxy_lines = []
        for fraction, color in zip(common["rotor"]["retainedForceFractionSensitivity"],
                                   ("#6ad6a2", "#72baf4", "#c094ef")):
            proxy_lines.append((f"局所抗力モデル × 未校正保持係数 {fraction:g}",
                                np.column_stack([jet_array[:, 0], jet_array[:, 1]*fraction*1000]).tolist(), color))
        proxy_lines.append(("正味余裕2倍に相当する総トルク",
                            [[0, required_factor*1000], [360, required_factor*1000]], "#ff9977"))
        plot(output/f"jet_torque_{ident}.svg", f"{ident} / 局所噴流の静止角トルク推定と必要入力",
             proxy_lines, "風車角 [deg] / 正方向へ正規化", "トルク [mN m]",
             ["HYP_8_20: 仮のピーク8m/s・速度σ20mm。メーカー風速でも均一な全面風でもない。",
              "保持係数は実験値・下限ではない。上部戻り側の負トルクと第一面遮蔽を計算。回転中性能は未解析。",
              "測定供給下限=null。距離への換算なし。Bは奇数減速のため噴流/羽根の上下反転が必要。"])
        summaries.append({key: summary[key] for key in (
            "revisionId", "designId", "resultStatus", "qualifiedPrototype", "part_count_architecture_lower_bound",
            "actual_mass_kg", "mass_assumption_range_kg", "verified_shaft_subtotal_usd",
            "complete_purchased_plus_printed_cost_jpy", "measurement_target_static_net_input_nm",
            "uncalibrated_proxy_peak_speed_for_target_m_s", "target_cog_wind_and_5mm_margin_min_mm", "matrix")})
        print(ident, json.dumps(summaries[-1], ensure_ascii=False))
    compare_synchronization(cfg, output)
    reference_beam_comparison(cfg, output)
    procurement_report(cfg, output)
    rib_section_screen(cfg, output)
    source_paths = [INPUT, Path(__file__), Path(__file__).with_name("beam.py"),
                    Path(__file__).with_name("core.py"), Path(__file__).with_name("design.json"),
                    Path(__file__).with_name("test_study_r2.py")]
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in source_paths}
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    commit_contains_sources = True
    for path in source_paths:
        stored = subprocess.run(["git", "show", f"{source_commit}:{path.relative_to(ROOT)}"],
                                cwd=ROOT, capture_output=True, check=False)
        if stored.returncode or stored.stdout != path.read_bytes():
            commit_contains_sources = False
    if not commit_contains_sources:
        print("PRELIMINARY: sourceCommit does not yet contain these input/source hashes", file=sys.stderr)
    dump(output/"comparison.json", {
        "revisionId": cfg["revisionId"], "sourceCommit": source_commit,
        "sourceCommitContainsInputs": commit_contains_sources,
        "sourceHashes": hashes, "resultStatus": "UNKNOWN", "qualifiedPrototypeCount": 0,
        "operatingEnvelope": cfg["operatingEnvelope"], "budget": cfg["budget"],
        "criteria": criteria, "candidates": summaries,
        "releaseDecision": "STOP_BEFORE_FULL_CAD_RENDER; complete measurable input and mechanical/procurement gates first",
        "oldFirstCut": "Preserved in docs/ver3, FreeCAD/Ver.3, STL/Ver.3 and Blender/Ver.3; not superseded by this study",
    })
    figure_entries = []
    for ident in "ABC":
        record = json.loads((output/f"candidate_{ident}.json").read_text())
        for kind, method, units, pointer in (
            ("deflection", "Euler-Bernoulli beam and separate column screening", "mm,N,MPa,rad", "/structure/members"),
            ("startup", "quasi-static reactions and explicit joint/bearing/mesh resistance", "deg,Nm,N", "/startup"),
            ("jet_torque", "uncalibrated static ray-shadowed panel-normal drag; NOT CFD", "deg,Nm,N,m/s", "/jet"),
        ):
            figure_entries.append({
                "revisionId": cfg["revisionId"], "sourceGeometryRevision": cfg["revisionId"],
                "designId": ident, "loadcaseId": record["structure"]["loadcaseId"],
                "file": str(DEFAULT_OUTPUT.relative_to(ROOT)/f"{kind}_{ident}.svg"),
                "dataFile": str(DEFAULT_OUTPUT.relative_to(ROOT)/f"candidate_{ident}.json"),
                "dataPointer": pointer, "method": method, "units": units,
                "figureUnits": "mm,N,MPa" if kind == "deflection" else "deg,mN*m",
                "displayAmplification": ({m["partId"]: m["displayAmplification"] for m in record["structure"]["members"]}
                                         if kind == "deflection" else 1),
                "resultStatus": "UNKNOWN", "isFinalCadGeometry": False,
                "sourceHashes": {**hashes, f"candidate_{ident}.json": digest(output/f"candidate_{ident}.json")},
            })
    for name, design, method, case in (
        ("synchronization_comparison", None, "closed-loop/Jacobian/friction bound, not physical validation", "SYNC_SAME_LOADS_QUARTERED_RODS"),
        ("reference_support_span", None, "reference beam only, NOT measured V2", "REFERENCE_1N_SIMPLY_SUPPORTED"),
        ("rib_section_screen_C", "C", "16-section beam coupon search, NOT full-frame generative design",
         "C_START_HIGH_OPPOSING_JET_HYP_8_20"),
    ):
        figure_entries.append({
            "revisionId": cfg["revisionId"], "sourceGeometryRevision": cfg["revisionId"],
            "designId": design, "loadcaseId": case,
            "file": str(DEFAULT_OUTPUT.relative_to(ROOT)/f"{name}.svg"),
            "dataFile": str(DEFAULT_OUTPUT.relative_to(ROOT)/f"{name}.json"),
            "method": method, "units": "see labelled axes and JSON", "displayAmplification": 1,
            "resultStatus": "UNKNOWN", "isFinalCadGeometry": False,
            "sourceHashes": {**hashes, f"{name}.json": digest(output/f"{name}.json")},
        })
    artifacts = {str(DEFAULT_OUTPUT.relative_to(ROOT)/path.name): digest(path) for path in sorted(output.iterdir())
                 if path.is_file() and path.name != "manifest.json"}
    dump(output/"manifest.json", {
        "revisionId": cfg["revisionId"], "sourceCommit": source_commit, "sourceHashes": hashes,
        "sourceCommitContainsInputs": commit_contains_sources, "figures": figure_entries,
        "artifactHashes": artifacts, "geometryStatus": cfg["geometryStatus"],
        "finalCadMeshHashes": None, "finalAssemblyHashes": None, "finalBomHashes": None,
        "qualifiedPrototypeCount": 0, "resultStatus": "UNKNOWN",
        "method": ["rigid kinematics", "quasi-static leg reactions", "1D beam/column",
                   "uncalibrated static ray-shadowed normal-drag proxy"],
        "notPerformed": ["CFD", "solid assembly FEM", "physical testing", "purchasing", "printing"],
    })


def verify(output):
    cfg = json.loads(INPUT.read_text())
    manifest = json.loads((output/"manifest.json").read_text())
    if manifest["revisionId"] != cfg["revisionId"] or manifest["qualifiedPrototypeCount"] != 0:
        raise ValueError("Revision or qualification status differs from this study")
    for relative, expected in manifest["sourceHashes"].items():
        path = (ROOT/relative).resolve()
        path.relative_to(ROOT)
        if digest(path) != expected:
            raise ValueError(f"Stale source: {relative}")
    for relative, expected in manifest["artifactHashes"].items():
        relative_path = Path(relative).relative_to(DEFAULT_OUTPUT.relative_to(ROOT))
        if len(relative_path.parts) != 1:
            raise ValueError(f"Unexpected artifact path: {relative}")
        if digest(output/relative_path) != expected:
            raise ValueError(f"Stale artifact: {relative}")
    for figure in manifest["figures"]:
        ET.parse(output/Path(figure["file"]).name)
        if figure["resultStatus"] != "UNKNOWN" or figure["isFinalCadGeometry"]:
            raise ValueError("Study figure must not claim a final prototype")
    for ident in "ABC":
        record = json.loads((output/f"candidate_{ident}.json").read_text())
        if record["measured_supply_lower_bound_nm"] is not None or record["qualifiedPrototype"]:
            raise ValueError("A measurement or qualification was invented")
        for case in record["startup"]:
            if case["loads"]["virtual_work_residual_nmm"] > 1e-4:
                raise ValueError("Virtual work and force equilibrium differ")
            if case["transmission"]["support_drive_couple_residual_nm"] > 1e-10:
                raise ValueError("Support and drive torque are not self-consistent")
        for member in record["structure"]["members"]:
            if member["force_balance_error_n"] > 1e-6 or member["moment_balance_error_nmm"] > 1e-5:
                raise ValueError("Unbalanced beam loads")
            if member.get("refinement_deflection_change_mm", 0) > 5e-6:
                raise ValueError("Beam sampling refinement changed the peak too much")
        for cell in record["fluid_sensitivity"]:
            expected = (cell["ideal_intercepted_momentum_torque_ceiling_nm"]
                        < cell["recomputed_high_required_input_nm"])
            if bool(expected) != cell["ideal_ceiling_cannot_cover_high_input"]:
                raise ValueError("Fluid gate does not use its own recomputed load")
        high = record["startup"][-1]["peak_input_nm"]
        loss = 2*cfg["common"]["bearingDragNmmCases"][-1]/1000
        target = cfg["criteria"]["measuredTorqueMarginTarget"]*(high-loss)
        if abs(target-record["measurement_target_static_net_input_nm"]) > 1e-12:
            raise ValueError("Input-bearing drag counted twice in the measurement target")
    print(json.dumps({"revisionId": cfg["revisionId"], "artifactHashesChecked": len(manifest["artifactHashes"]),
                      "figureEntriesChecked": len(manifest["figures"]),
                      "sourceCommitContainsInputs": manifest["sourceCommitContainsInputs"],
                      "qualifiedPrototypeCount": 0, "numericalPackageStatus": "CONSISTENT",
                      "physicalFeasibility": "UNKNOWN"}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true", help="check hashes, fields, units and equilibrium without regenerating")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
        return
    cfg = json.loads(INPUT.read_text())
    run(cfg, args.output)


if __name__ == "__main__":
    main()
