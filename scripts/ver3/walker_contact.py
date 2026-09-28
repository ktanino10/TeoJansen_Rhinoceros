"""Whole-walker linkage and unilateral compliant-toe screening in mm,N,rad.

No arbitrary body advance is imposed. Normal spring equilibrium establishes
height/tilt; tangential toe velocities determine an approximate rigid-body
advance/yaw and integrated no-slip residual. This is quasi-static, not impact
dynamics or a material-property certificate.
"""

from copy import deepcopy
import itertools
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

from commercial_r3 import LENGTH_KEYS
from walker_kinematics import points_many
from core import CONFIG

INPUT = Path(__file__).with_name("walker_r7.json")
ROOT = INPUT.parents[2]
OUT = ROOT/"docs/ver3/integrated_r7"


def load():
    return json.loads(INPUT.read_text())


def dimensions(which,common=None):
    if which == "reference":
        values={k: CONFIG["linkage"][k] for k in LENGTH_KEYS}
        if common:
            values.update({k:v/common["linkScale"] for k,v in common.get("linkDimensionOverridesMm",{}).items()})
        return values
    if which == "r3":
        return json.loads((ROOT/"docs/ver3/commercial_basis_r3/linkage_search.json").read_text())["selectedUnscaledMm"]
    raise ValueError(which)


def foot_total_rate(foot, rate_error=0):
    if foot["springRateNmm"] <= 0 or not -1 < rate_error:
        raise ValueError("Invalid catalogued coil rate or error")
    return foot.get("springCountPerFoot",1)*foot["springRateNmm"]*(1+rate_error)


def functional_swing_budget(common):
    # World-space flight clearance already contains body settling under
    # the other feet's spring compression. Do not subtract that twice.
    return 2*common["errors"]["floorHeightErrorMm"]+2*common["foot"]["footFreeGeometryToleranceMm"]


def normal_active_set(basis,baseline,stiffness,target,previous=None):
    count=len(baseline)
    if not 3<=count<=8:raise ValueError("Bounded contact solver requires3..8 modeled foot centers")
    scale=np.array([1,.01,.01]);b=basis*scale;load=target*scale
    candidates=[]
    if previous is not None:
        guessed=tuple(np.flatnonzero(baseline+basis@previous<0))
        if len(guessed)>=3:candidates.append(guessed)
    candidates.extend(group for n in range(3,count+1) for group in itertools.combinations(range(count),n)
                      if group not in candidates)
    for active in candidates:
        active=np.array(active)
        matrix=b[active].T@(stiffness[active,None]*b[active])
        eigenvalues=np.linalg.eigvalsh(matrix)
        if eigenvalues[0]<=1e-12*eigenvalues[-1]:continue
        rhs=-load-b[active].T@(stiffness[active]*baseline[active])
        body=np.linalg.solve(matrix,rhs)*scale
        gap=baseline+basis@body
        inactive=np.ones(count,dtype=bool);inactive[active]=False
        if np.any(gap[active]>1e-8) or np.any(gap[inactive]<-1e-8):continue
        force=-stiffness*np.minimum(gap,0)
        if np.linalg.norm((basis.T@force-target)*scale)>1e-7:
            raise RuntimeError("Active-set force/moment balance failed")
        return body
    raise ValueError("No equilibrated unilateral contact set for the load resultant")


class ContactGait:
    def __init__(self, common, dims, step_deg=.5):
        self.common, self.dims = common,dict(dims)
        self.dims.update({k:v/common["linkScale"] for k,v in common.get("linkDimensionOverridesMm",{}).items()})
        self.step_deg = step_deg
        self.angles = np.deg2rad(np.arange(0, 360, step_deg))
        count = len(common["legPhasesDeg"])
        stations = (np.arange(count)-(count-1)/2)*common["stationPitchMm"]
        self.legs = [(station, side, phase)
                     for station, pair in zip(stations, common["legPhasesDeg"])
                     for side, phase in zip((-1, 1), pair)]
        self.beta_ref = math.radians(common["foot"]["pitchReferenceBodyAngleDeg"])
        self.normal_offsets = [0] if common["foot"]["normalModelCenter"] else common["foot"]["toeLaneCentersMm"]
        self.lanes = len(self.normal_offsets)
        self.leg_count = len(self.legs)

    def neutral(self, errors=None):
        errors = errors or {}
        cloud, gammas = [], []
        for index, (station, side, phase) in enumerate(self.legs):
            values = dict(self.dims)
            for key, delta in errors.get("lengths", [{} for _ in range(self.leg_count)])[index].items():
                values[key] += delta/self.common["linkScale"]
            angle = self.angles+math.radians(phase+errors.get("phase_deg", [0]*self.leg_count)[index])
            points, _ = points_many(angle, values, self.common["linkScale"])
            ce = points["E"]-points["C"]
            gamma = np.unwrap(np.arctan2(ce[:, 1], ce[:, 0])-self.beta_ref)
            dy, dz = self.common["foot"]["toeOffsetFromFNeutralMm"]
            toe = points["F"]+np.column_stack([dy*np.cos(gamma)-dz*np.sin(gamma),
                                              dy*np.sin(gamma)+dz*np.cos(gamma)])
            # Foot width is a modeled contact feature, not an arbitrary COP patch.
            for lane in self.normal_offsets:
                x = side*self.common["foot"].get("centerAbsXmm",61.0)+lane
                cloud.append(np.column_stack([np.full(len(angle), x), toe[:, 0]+station,
                                              toe[:, 1]+errors.get("toe_z_mm", [0]*self.leg_count)[index]]))
                gammas.append(gamma)
        return np.stack(cloud, axis=1), np.stack(gammas, axis=1)

    def normal_equilibrium(self, feet, gamma, weight, cog_xy, stiffness, floor, previous=None, guide_mode=0):
        cosine, sine = np.cos(gamma), np.sin(gamma)
        if np.any(cosine < .1):
            raise ValueError("Guide axis is nearly horizontal; contact model invalid")
        foot = self.common["foot"]
        friction = foot["guideFrictionMuSensitivity"][-1]
        ground_mu = foot["groundFrictionCoefficientAssumed"]
        lever = (foot["movingBushingStartAboveFmm"]+foot["guideBearingLengthMm"]/2
                 -foot["toeOffsetFromFNeutralMm"][1])
        radial_force_factor = (2*lever/foot["guideBearingLengthMm"]*abs(sine)
            +ground_mu*(2*foot["toeRadiusMm"]/foot["guideBearingLengthMm"]
                        +2*lever/foot["guideBearingLengthMm"]*abs(cosine)))
        denominator = cosine*(cosine+guide_mode*(ground_mu*abs(sine)+friction*radial_force_factor))
        inadmissible = denominator <= 0
        # An unloaded airborne toe does not require a ground-load mobility law.
        # If such a provisional contact activates, fail explicitly below.
        effective = stiffness/np.where(inadmissible, cosine**2, denominator)
        target = np.r_[weight, weight*np.array(cog_xy)]
        positions = feet.copy()
        count = len(feet)
        for iteration in range(8):
            basis = np.column_stack([np.ones(count), positions[:, 0], positions[:, 1]])
            baseline = feet[:, 2]-self.common["foot"]["toeRadiusMm"]-floor
            body=normal_active_set(basis,baseline,effective,target,previous)
            gaps = baseline+basis@body
            force = -effective*np.minimum(gaps, 0)
            if np.any(force[inadmissible] > 1e-8):
                raise ValueError("A loaded toe enters the self-locking guide/friction envelope")
            local_deflection = np.where(force > 0, -gaps/cosine, 0)
            corrected = feet.copy()
            corrected[:, 1] -= local_deflection*np.sin(gamma)
            if np.max(np.abs(corrected[:, 1]-positions[:, 1])) < 1e-6:
                break
            positions = corrected
            previous = body
        else:
            raise ValueError("Toe-deflection/moment equilibrium did not converge")
        positions[:, 2] += local_deflection*np.cos(gamma)
        residual = basis.T@force-target
        if np.linalg.norm(residual) > 1e-5:
            raise RuntimeError("Ground reaction force/moment imbalance")
        return body, force, positions, local_deflection, body

    def evaluate(self, mass_kg, cog_xy=(0, -20), modulus=800, errors=None, wind_shift=(0, 0), guide_mode=0,
                 external_planar_load=(0,0,0)):
        feet, gamma = self.neutral(errors)
        errors = errors or {}
        stiffness = np.repeat([foot_total_rate(self.common["foot"], t)/self.lanes
                               for t in errors.get("spring_rate_error", [0]*self.leg_count)], self.lanes)
        floor = np.repeat(errors.get("floor_z_mm", [0]*self.leg_count), self.lanes)
        weight = mass_kg*9.80665
        external=np.asarray(external_planar_load,float)
        if external.shape!=(3,) or not np.all(np.isfinite(external)):
            raise ValueError("Expected finite external Fx,Fy,Mz in N,N,Nmm")
        ground_mu=self.common["foot"]["groundFrictionCoefficientAssumed"]
        if ground_mu<=0 or np.linalg.norm(external[:2])>=ground_mu*weight:
            raise ValueError("External force exceeds the available planar friction envelope")
        external_normalized=external/(ground_mu*weight)
        cog=np.asarray(cog_xy,float)+wind_shift
        if cog.shape==(2,):cog=np.broadcast_to(cog,(len(self.angles),2))
        if cog.shape!=(len(self.angles),2) or not np.all(np.isfinite(cog)):
            raise ValueError("Expected one COP or a finite angle-indexed COP trajectory")
        bodies, reactions, toes, compressions, support = [], [], [], [], []
        previous = None
        for f,g,center in zip(feet,gamma,cog):
            body, force, toe, compression, previous = self.normal_equilibrium(
                f, g, weight, center, stiffness, floor, previous, guide_mode=guide_mode)
            bodies.append(body)
            reactions.append(force)
            toes.append(toe)
            compressions.append(compression)
            active = force > self.common["criteria"]["loadFootFraction"]*weight/self.lanes
            xy = toe[active, :2]
            if len(xy) < 3:
                support.append(-100.)
            else:
                hull = ConvexHull(xy)
                margin = np.min(-(hull.equations[:, :2]@center+hull.equations[:, 2]))
                support.append(float(margin))
        bodies, reactions, toes, compressions = map(np.array, (bodies, reactions, toes, compressions))
        # Small-angle rigid-body coordinates; member lengths themselves are
        # unchanged. Validity is separately gated on body tilt.
        transformed = toes.copy()
        transformed[:, :, 0] -= bodies[:, None, 1]*toes[:, :, 2]
        transformed[:, :, 1] -= bodies[:, None, 2]*toes[:, :, 2]
        transformed[:, :, 2] += (bodies[:, None, 0]+bodies[:, None, 1]*toes[:, :, 0]
                                +bodies[:, None, 2]*toes[:, :, 1])
        dt = math.radians(self.step_deg)
        rate = (np.roll(transformed, -1, axis=0)-np.roll(transformed, 1, axis=0))/(2*dt)
        beta_rate = (np.roll(gamma, -1, axis=0)-np.roll(gamma, 1, axis=0))/(2*dt)
        body_pitch_rate = (np.roll(bodies[:, 2], -1)-np.roll(bodies[:, 2], 1))/(2*dt)
        rate[:, :, 1] += self.common["foot"]["toeRadiusMm"]*(beta_rate+body_pitch_rate[:, None])
        velocity, slips = [], []
        contact_count = len(self.legs)*self.lanes
        equilibrium_errors = []
        for i in range(len(self.angles)):
            weights = reactions[i]/weight
            a = np.zeros((2*contact_count, 3))
            rhs = -rate[i, :, :2].ravel()
            for j, (x, y) in enumerate(transformed[i, :, :2]):
                a[2*j] = [1, 0, -y]
                a[2*j+1] = [0, 1, x]
            w = np.repeat(np.sqrt(weights), 2)
            motion = np.linalg.lstsq(a*w[:, None], rhs*w, rcond=None)[0]
            # Minimum smooth Coulomb dissipation; regularization resolves a
            # sticking subgradient rather than prescribing body advance.
            for _ in range(60):
                residual = (a@motion-rhs).reshape(contact_count, 2)
                effective_weights = weights/np.sqrt(np.sum(residual**2, axis=1)+.01**2)
                w = np.repeat(np.sqrt(effective_weights), 2)
                matrix=(a*w[:,None]).T@(a*w[:,None])
                target=a.T@(rhs*w*w)+external_normalized
                updated = np.linalg.solve(matrix+np.diag([1e-12,1e-12,1e-8]),target)
                if np.linalg.norm(updated-motion) < 1e-7:
                    motion = updated
                    break
                motion = updated
            scaled_a = a@np.diag([1, 1, .01])
            q = motion*[1, 1, 100]
            for _ in range(30):
                residual = (scaled_a@q-rhs).reshape(contact_count, 2)
                norms = np.sqrt(np.sum(residual**2, axis=1)+.01**2)
                scaled_external=external_normalized*[1,1,.01]
                gradient = scaled_a.T@(weights[:, None]*residual/norms[:, None]).ravel()-scaled_external
                if np.linalg.norm(gradient) < 1e-8:
                    break
                hessian = np.zeros((3, 3))
                for j in range(contact_count):
                    b = scaled_a[2*j:2*j+2]
                    local = weights[j]*(np.eye(2)/norms[j]-np.outer(residual[j], residual[j])/norms[j]**3)
                    hessian += b.T@local@b
                step = np.linalg.solve(hessian+np.eye(3)*1e-10, -gradient)
                objective = float(weights@norms-scaled_external@q)
                fraction = 1.0
                for _ in range(30):
                    trial = (scaled_a@(q+fraction*step)-rhs).reshape(contact_count, 2)
                    value = float(weights@np.sqrt(np.sum(trial**2, axis=1)+.01**2)-scaled_external@(q+fraction*step))
                    if value <= objective+1e-4*fraction*gradient@step+1e-13:
                        break
                    fraction *= .5
                else:
                    raise ValueError("Friction dissipation line search failed")
                q += fraction*step
            motion = q*[1, 1, .01]
            velocity.append(motion)
            residual = (a@motion-rhs).reshape(contact_count, 2)
            slips.append(residual)
            resistance = weights[:, None]*residual/np.sqrt(np.sum(residual**2, axis=1)+.01**2)[:, None]
            equilibrium_errors.append(float(np.linalg.norm((a.T@resistance.ravel()-external_normalized)/[1, 1, 100])))
            if equilibrium_errors[-1] > 1e-6:
                raise ValueError("Contact tangential force/moment residual exceeds numerical allowance")
        velocity, slips = np.array(velocity), np.array(slips)
        maximum_episode = 0.
        lengths = np.zeros(contact_count)
        for i in range(3*len(self.angles)):
            step = i % len(self.angles)
            active = reactions[step] > self.common["criteria"]["loadFootFraction"]*weight/self.lanes
            lengths[~active] = 0
            lengths[active] += np.linalg.norm(slips[step, active], axis=1)*dt
            if i >= len(self.angles):
                maximum_episode = max(maximum_episode, float(lengths.max()))
        swing_gap = transformed[:, :, 2]-self.common["foot"]["toeRadiusMm"]-floor
        minimum_mid_swing = min(float(np.max(swing_gap[:, leg])) for leg in range(contact_count))
        criteria = self.common["criteria"]
        tilt = np.rad2deg(np.arctan(np.linalg.norm(bodies[:, 1:], axis=1)))
        spring_forces = compressions*stiffness
        leg_reactions = reactions.reshape(len(self.angles), self.leg_count, self.lanes).sum(axis=2)
        loaded_lanes = reactions > self.common["criteria"]["loadFootFraction"]*weight/self.lanes
        loaded_feet=leg_reactions>criteria["loadFootFraction"]*weight
        return {
            "mass_kg": mass_kg, "printed_root_E_mpa_not_coil_rate": modulus, "foot_k_nmm": stiffness.tolist(),
            "coil_rate_source": self.common["foot"]["springSku"],
            "guide_hysteresis_envelope_mode": guide_mode,
            "body_height_range_mm": [float(bodies[:, 0].min()), float(bodies[:, 0].max())],
            "maximum_body_tilt_deg": float(tilt.max()),
            "minimum_loaded_feet": int(loaded_feet.sum(axis=1).min()),
            "minimum_loaded_toe_lanes": int(loaded_lanes.sum(axis=1).min()),
            "legacy_loaded_three_legs_goal": bool(loaded_feet.sum(axis=1).min() >= 3),
            "minimum_support_margin_mm": min(support),
            "maximum_guide_compression_mm": float(np.abs(compressions).max()),
            "maximum_foot_force_n": float(leg_reactions.max()),
            "maximum_combined_spring_force_n": float(spring_forces.max()),
            "maximum_spring_force_n": float(spring_forces.max()/self.common["foot"].get("springCountPerFoot",1)),
            "maximum_required_rocker_angle_deg": float(np.rad2deg(np.abs(np.arctan(bodies[:, 1]))).max()
                +math.degrees(math.atan((2*self.common["foot"]["groundRoughnessMm"]
                                         +2*self.common["foot"]["footFreeGeometryToleranceMm"])
                                        /(2*self.common["foot"]["rockerHalfSpanMm"])))),
            "minimum_of_each_foot_maximum_swing_gap_mm": minimum_mid_swing,
            "world_swing_gap_already_includes_loaded_compliance":True,
            "maximum_predicted_loaded_episode_slip_mm": maximum_episode,
            "advance_per_cycle_mm": float(velocity[:, 1].sum()*dt),
            "lateral_per_cycle_mm": float(velocity[:, 0].sum()*dt),
            "yaw_per_cycle_rad": float(velocity[:, 2].sum()*dt),
            "legacy_8mm_swing_goal": minimum_mid_swing >= 8,
            "support_and_compliance_pass": bool(tilt.max() <= criteria["maximumBodyTiltDeg"]
                and loaded_feet.sum(axis=1).min() >= criteria["minimumLoadBearingFeet"]
                and min(support) >= criteria["minimumSupportMarginWithCogoErrorMm"]
                and np.abs(compressions).max() <= criteria["maximumCompressionMm"]
                and spring_forces.max()/self.common["foot"].get("springCountPerFoot",1)
                    <= self.common["foot"]["springRatedMaxLoadN"]),
            "slip_design_goal_pass": maximum_episode <= criteria["maxTangentialSlipPerLoadedEpisodeMm"],
            "tangential_force_moment_residual_normalized_max": max(equilibrium_errors),
            "external_planar_load_N_N_Nmm":external.tolist(),
            "method": f"{contact_count} stock-spring/guide foot centers with passive equalizing rockers; no support-polygon enlargement. Unilateral normal support with guide-friction envelopes; small-angle pose; smooth-Coulomb minimum dissipation. Not impact dynamics.",
            "data": {"theta_rad": self.angles.tolist(), "body_z_slopex_slopey": bodies.tolist(),
                     "normal_n": reactions.tolist(), "toes_body_mm": toes.tolist(),
                     "spring_compression_mm": compressions.tolist(),
                     "body_velocity_mm_per_rad": velocity.tolist(),
                     "toe_slip_velocity_mm_per_rad": slips.tolist()}
        }


def error_cases(common):
    e = common["errors"]
    rng = np.random.default_rng(e["seed"])
    count = 2*len(common["legPhasesDeg"])
    cases = [{"id": "nominal", "errors": {}}]
    length_names = list(LENGTH_KEYS)
    effective_length=e["linkPitchErrorMm"]+2*e["pinRadialPlayMm"]
    for i in range(e["randomAssemblies"]):
        cases.append({"id": f"sample{i:02}", "errors": {
            "lengths": [{n: float(rng.uniform(-effective_length,effective_length))
                         for n in length_names} for _ in range(count)],
            "phase_deg": rng.uniform(-e["stationCrankErrorDeg"], e["stationCrankErrorDeg"], count).tolist(),
            "toe_z_mm": rng.uniform(-common["foot"]["footFreeGeometryToleranceMm"],
                                    common["foot"]["footFreeGeometryToleranceMm"],count).tolist(),
            "floor_z_mm": rng.uniform(-e["floorHeightErrorMm"], e["floorHeightErrorMm"], count).tolist(),
            "spring_rate_error": rng.uniform(-e["springRateErrorFraction"], e["springRateErrorFraction"], count).tolist()
        }})
    for sign in (-1, 1):
        cases.append({"id": f"alternating_extremes_{sign}", "errors": {
            "toe_z_mm": [sign*(-1)**i*.3 for i in range(count)],
            "phase_deg": [sign*(-1)**i*e["stationCrankErrorDeg"] for i in range(count)],
            "floor_z_mm": [-sign*(-1)**i*e["floorHeightErrorMm"] for i in range(count)],
            "spring_rate_error": [sign*(-1)**i*e["springRateErrorFraction"] for i in range(count)]
        }})
    return cases


if __name__ == "__main__":
    cfg = load()
    for which in ("reference", "r3"):
        gait = ContactGait(cfg["common"], dimensions(which), step_deg=1)
        for mass in (.25, .4):
            for modulus in (800, 2600):
                result = gait.evaluate(mass, modulus=modulus)
                print(which, mass, modulus, json.dumps({k:v for k,v in result.items() if k != "data"}))
