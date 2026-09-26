"""Common quasi-static torque/friction scenarios along the prescribed gait."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math

import numpy as np

from core import CONFIG, LINKS, ROOT, OUT, axis_speeds, dump, gait, link_pose
from mechanics import MassModel

parser = argparse.ArgumentParser()
parser.add_argument("--only", choices=["A", "B", "C"], default="A")
args = parser.parse_args()
manifest_path = OUT/f"assembly_{args.only}.json"
manifest = json.loads(manifest_path.read_text())
design, parts = manifest["design"], manifest["parts"]
walk = json.loads((OUT/f"walk_{args.only}.json").read_text())
if walk["assembly_sha256"] != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
    raise RuntimeError("Walking load allocation is stale relative to the assembly")
with (OUT/f"walk_samples_{args.only}.csv").open() as stream:
    samples = list(csv.DictReader(stream))
if len(samples) != 4321:
    raise RuntimeError("Expected the common three-cycle0.25deg walking sample grid")
mass_model = MassModel(manifest)
mass_model.verify()
cfg, link_cfg = CONFIG["assumptions"], CONFIG["linkage"]
gravity = cfg["gravity_m_s2"]
weight = mass_model.mass_g/1000*gravity
step = 1e-5
shoe_mass = sum(parts[item["part_id"]]["mass_g"] for item in manifest["instances"]
                if item.get("motion", {}).get("type") == "joint"
                and item["motion"].get("node") == "F")/6000


def link_id(name, mirror):
    return name+"_R" if mirror and name in ("L_PBD", "L_CEF") else name


def leg_info(theta, mirror):
    points = gait(theta, mirror)
    centers, rates, masses = {}, {}, {}
    before, after = gait(theta-step, mirror), gait(theta+step, mirror)
    for name, nodes in LINKS.items():
        part_id = link_id(name, mirror)
        matrix = np.array(link_pose(part_id, 0, theta, mirror))
        centers[name] = (matrix@np.array(parts[part_id]["local_center_of_mass_mm"]+[1]))[1:3]-[0, link_cfg["crank_height"]]
        masses[name] = parts[part_id]["mass_g"]/1000
        a, b = before[nodes[1]]-before[nodes[0]], after[nodes[1]]-after[nodes[0]]
        rates[name] = math.atan2(a[0]*b[1]-a[1]*b[0], float(a@b))/(2*step)
    foot_rate = (after["F"]-before["F"])/(2*step)
    return points, centers, rates, masses, foot_rate


def reactions(info, external_force, normal):
    points, centers, rates, masses, _ = info
    bodies = list(LINKS)
    variables = ["A_AB", "A_AC", "B", "C_AC", "C_PC", "D", "E", "P_TRI", "P_PC"]
    incidence = {
        "L_AB": [("A_AB", "A", 1), ("B", "B", 1)],
        "L_AC": [("A_AC", "A", 1), ("C_AC", "C", 1)],
        "L_PC": [("P_PC", "P", 1), ("C_PC", "C", 1)],
        "L_PBD": [("P_TRI", "P", 1), ("B", "B", -1), ("D", "D", 1)],
        "L_DE": [("D", "D", -1), ("E", "E", 1)],
        "L_CEF": [("C_AC", "C", -1), ("C_PC", "C", -1), ("E", "E", -1)],
    }
    matrix, rhs = np.zeros((18, 18)), np.zeros(18)
    for body in bodies:
        row = 3*bodies.index(body)
        center = centers[body]
        rhs[row:row+2] = masses[body]*gravity*normal[1:]
        for variable, node, sign in incidence[body]:
            col = 2*variables.index(variable)
            arm = points[node]-center
            matrix[row, col] += sign
            matrix[row+1, col+1] += sign
            matrix[row+2, col] -= sign*arm[1]
            matrix[row+2, col+1] += sign*arm[0]
        if body == "L_CEF":
            arm = points["F"]-center
            rhs[row:row+2] -= external_force
            rhs[row+2] -= arm[0]*external_force[1]-arm[1]*external_force[0]
    solution = np.linalg.solve(matrix, rhs)
    residual = float(np.linalg.norm(matrix@solution-rhs))
    force = {name: solution[2*i:2*i+2] for i, name in enumerate(variables)}
    norm = {name: float(np.linalg.norm(value)) for name, value in force.items()}
    loss = 3*(norm["A_AB"]*abs(rates["L_AB"]-1)+norm["A_AC"]*abs(rates["L_AC"]-1))
    loss += CONFIG["hardware"]["pivot_rod_diameter"]/2*(
        norm["P_TRI"]*abs(rates["L_PBD"])+norm["P_PC"]*abs(rates["L_PC"]))
    loss += 2*(norm["B"]*abs(rates["L_AB"]-rates["L_PBD"])
               +norm["D"]*abs(rates["L_DE"]-rates["L_PBD"])
               +norm["E"]*abs(rates["L_DE"]-rates["L_CEF"]))
    c_loads = [norm["C_AC"], norm["C_PC"], float(np.linalg.norm(force["C_AC"]+force["C_PC"]))]
    c_rates = [rates[name] for name in ("L_AC", "L_PC", "L_CEF")]
    loss += 2*max(sum(f*abs(rate-pin) for f, rate in zip(c_loads, c_rates)) for pin in c_rates)
    # The F-shoe hinge is a real additional journal, not a free efficiency gain.
    loss += 2*float(np.linalg.norm(external_force))*abs(rates["L_CEF"])
    ac_axis = (points["C"]-points["A"])/np.linalg.norm(points["C"]-points["A"])
    compression = max(0, float(force["A_AC"]@ac_axis))
    return loss, max(norm.values()), compression, residual


bearings = Counter(item["axis"] for item in manifest["instances"] if item["part_id"] == "H_608")
speeds = axis_speeds(design)
upstream_efficiency = {"I": 1.0}
efficiency = 1.0
for stage in design["stages"]:
    efficiency *= stage["mesh_efficiency_assumed"]
    upstream_efficiency[stage["output_axis"]] = efficiency
profiles, cases = [], []
residual_max, joint_max, compression_max = 0, 0, 0
for label, mu, bearing_drag, horizontal_mu in zip(
        ("low", "nominal", "high"), cfg["static_friction_coefficients"],
        cfg["bearing_start_torque_nmm"], cfg["horizontal_resistance_coefficients"]):
    required, joint_friction, load_torque = [], [], []
    bearing_input = sum(bearing_drag*count*abs(speeds[axis]/speeds["I"])/upstream_efficiency[axis]
                        for axis, count in bearings.items())
    for degree in range(360):
        # Same resolution/phase window for all three designs; cycle2 avoids clip-start transients.
        sample = samples[1440+4*degree]
        theta = float(sample["theta"])
        normal = np.array([float(sample[f"normal_{axis}"]) for axis in ("x", "y", "z")])
        fractions = np.array([float(sample[f"normal_fraction_{i}"]) for i in range(6)])
        cg_rate = (mass_model.at(theta+step)-mass_model.at(theta-step))/(2*step)
        torque = weight*float(normal@cg_rate)
        tangent = np.array([0.0, 1.0, 0.0])-normal*normal[1]
        tangent /= np.linalg.norm(tangent)
        friction = 0
        for bay, phase in enumerate(link_cfg["phases"]):
            for mirror in (False, True):
                index = bay*2+int(mirror)
                info = leg_info(theta+math.radians(phase), mirror)
                foot_rate = np.array([0, *info[4]])
                n_force = max(0, fractions[index])*weight
                tangential = -horizontal_mu*n_force*math.copysign(1, float(foot_rate@tangent))
                ground_force = n_force*normal+tangential*tangent
                transmitted = ground_force-shoe_mass*gravity*normal
                loss, joint, compression, residual = reactions(info, transmitted[1:], normal)
                friction += mu*loss
                torque -= float(ground_force@foot_rate)
                residual_max = max(residual_max, residual)
                joint_max = max(joint_max, joint)
                compression_max = max(compression_max, compression)
        input_torque = (max(0, torque+friction)/(design["ratio"]*efficiency)+bearing_input)/1000
        required.append(input_torque)
        joint_friction.append(friction/1000)
        load_torque.append(torque/1000)
        profiles.append([args.only, label, degree, torque/1000, friction/1000, bearing_input/1000, input_torque])
    diameters = {str(speed): [
        2000*math.sqrt(max(required)/(cfg["air_density_kg_m3"]*design["rotor"]["span"]/1000*cq*speed**2))
        for cq in reversed(cfg["rotor_torque_coefficient_range"])]
        for speed in cfg["wind_speeds_m_s"]}
    cases.append(dict(case=label, journal_static_mu=mu, bearing_breakaway_nmm_each=bearing_drag,
                      effective_horizontal_resistance_coefficient=horizontal_mu,
                      peak_required_input_nm=max(required), peak_angle_deg=int(np.argmax(required)),
                      peak_joint_friction_at_crank_nm=max(joint_friction),
                      input_equivalent_bearing_breakaway_nm=bearing_input/1000,
                      load_torque_range_nm=[min(load_torque), max(load_torque)],
                      equivalent_rotor_diameter_mm_at_same_span=diameters))
rotor_input = {str(speed): [
    cfg["air_density_kg_m3"]*design["rotor"]["span"]/1000*(design["rotor"]["radius"]/1000)**2*cq*speed**2
    for cq in cfg["rotor_torque_coefficient_range"]]
    for speed in cfg["wind_speeds_m_s"]}
budget = []
for case in cases:
    for speed, values in rotor_input.items():
        for cq, available in zip(cfg["rotor_torque_coefficient_range"], values):
            budget.append(dict(case=case["case"], wind_m_s=float(speed), assumed_cq=cq,
                               available_input_nm=available, required_peak_nm=case["peak_required_input_nm"],
                               available_to_required_ratio=available/case["peak_required_input_nm"],
                               numerical_budget_closed=available >= case["peak_required_input_nm"]))
ac_length = link_cfg["AC"]*link_cfg["scale"]
ac_inertia = link_cfg["ac_link_width"]*link_cfg["link_thickness"]**3/12
euler_load = math.pi**2*CONFIG["structure"]["elastic_modulus_mpa"]*ac_inertia/ac_length**2
summary = dict(
    prototype=args.only,
    assembly_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    walking_sha256=hashlib.sha256((OUT/f"walk_{args.only}.json").read_bytes()).hexdigest(),
    mass_g_solid_cad_plus_catalog_assumptions=mass_model.mass_g,
    bearing_counts_by_axis=dict(bearings), upstream_efficiency_by_axis=upstream_efficiency,
    nominal_total_transmission_efficiency_assumed=efficiency,
    maximum_equilibrium_residual_n_nmm=residual_max, maximum_model_joint_force_n=joint_max,
    ac_compression_max_n=compression_max, ac_pinned_euler_proxy_n=euler_load,
    ac_euler_proxy_ratio=euler_load/compression_max if compression_max else None,
    scenarios=cases, rotor_input_nm_range=rotor_input, budget=budget,
    sampling="360 poses at1deg spacing from the second cycle of the common0.25deg prescribed walking/load-allocation model.",
    model="Six rigid planar bodies per leg; conditional nonnegative normal-load allocation; explicit journal and F-hinge friction; every bearing converted through actual upstream ratios/losses. A belt nominal efficiency0.95; spur stage0.90.",
    limitations=[
        "All material, static friction, bearing drag, aerodynamic coefficients and contact normal allocation are provisional.",
        "Walking load allocation is a kinematic support assumption, not validated passive-shoe/ground dynamics or a complete3D internal-force solution.",
        "The local leg solve omits small pin masses and out-of-plane reactions. Full CAD mass enters gravity and global support.",
        "Euler buckling is a pinned straight-member screening proxy, not an FEA or printed-link strength certificate.",
        "Belt10N/span pretension means about20N additional radial load; actual tension/drag must be measured. No lossless belt assumption.",
        "Static Cq may be zero/negative at an unfavorable angle. Positive-coefficient budget closure is not self-starting proof.",
        "No inertia, impacts, wind field, coasting-through-stalls or running-efficiency experiment was simulated.",
        "Equivalent diameters are scaling comparisons, not supplied larger interchangeable CAD.",
    ])
with (OUT/f"startup_profile_{args.only}.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["prototype", "scenario", "crank_deg", "load_torque_nm", "journal_friction_nm",
                     "input_equivalent_bearing_drag_nm", "required_input_nm"])
    writer.writerows(profiles)
dump(OUT/f"startup_{args.only}.json", summary)
print(json.dumps({key: value for key, value in summary.items() if key not in ("budget", "limitations")}, indent=2))
