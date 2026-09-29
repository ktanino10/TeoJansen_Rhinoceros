"""Versioned rigid/contact visualization extension; never rewrites canonical r7 data."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import root
from scipy.spatial import ConvexHull

from r7_data import Snapshot
from r7_motion_diagnostic import canonical_functions
from r7_floor_gate import source_floor_api

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/ver3/r7_walking_v1"
REVISION = "r7-floor2-walking-kinematic-v1"
TAU = 2 * math.pi
ASSUMPTIONS = {
    "normalReconciliation": (
        "Retain the saved normal resultant and its source small-map world XY center of pressure. "
        "Solve height and two polar-orthogonalized slopes with exact guide projection, "
        "unilateral compression and the original combined catalog spring rate. "
        "This is a new geometric/quasi-static display equilibrium, not a new wind or tangential solver."
    ),
    "loadedRocker": (
        "Equalize the heights of the two real cylindrical pad axes about the real guide-pitch "
        "rocker axis. Keep the unique solution inside the accepted +/-5 degree travel."
    ),
    "airborneRocker": (
        "VISUAL_REST_V1: in flight, smoothly return toward zero relative rocker angle "
        "using smoothstep(clearance/3mm). At touchdown the equal-height contact angle is recovered. "
        "This is a declared visualization rest law, not a solved gravity, damping or impact response."
    ),
    "spring": (
        "PROCEDURAL_COIL_V1: keep the actual bottom/top seats, 0.6mm wire diameter, "
        "3.2mm mean radius and 6.8 turns; change helix pitch with guide travel. "
        "The same twelve spring instance IDs remain, with declared procedural geometry instead "
        "of the undeformed CAD coil. No stress, fatigue or solid-FEM assertion."
    ),
    "planar": (
        "Interpolate the 73 saved integrated components inside a cycle; compose whole cycles "
        "as SE(2) transforms, transporting translation by accumulated yaw. "
        "No arbitrary v*t advance and no new tangential friction solve. Source slip remains."
    ),
    "timing": (
        "Prescribed absolute input 120rpm, not achieved speed. Signed input angle is calculated "
        "from continuous time/crank angle and the actual signed gear ratio, never wrapped-frame interpolation."
    ),
}


def polar_rotation(sx, sy):
    skew = np.array([[0., 0., -sx], [0., 0., -sy], [sx, sy, 0.]])
    length = math.sqrt(1 + sx * sx + sy * sy)
    return np.eye(3) + skew / length + skew @ skew / (length * (length + 1))


def sample_periodic(rows, phase):
    position = phase / TAU * (len(rows) - 1)
    index = min(int(position), len(rows) - 2)
    fraction = position - index
    return np.asarray(rows[index]) * (1 - fraction) + np.asarray(rows[index + 1]) * fraction


def planar_pose(rows, theta):
    cycle = math.floor(theta / TAU)
    phase = theta - cycle * TAU
    local = sample_periodic(rows, phase)
    end = np.asarray(rows[-1])
    yaw = cycle * end[2]
    # Geometric series, including negative cycles, without accumulating per-frame drift.
    if abs(end[2]) < 1e-12:
        offset = cycle * end[:2]
    else:
        series = np.expm1(1j * yaw) / np.expm1(1j * end[2])
        offset_complex = complex(*end[:2]) * series
        offset = np.array([offset_complex.real, offset_complex.imag])
    c, s = math.cos(yaw), math.sin(yaw)
    xy = offset + np.array([[c, -s], [s, c]]) @ local[:2]
    return np.r_[xy, yaw + local[2]]


class WalkModel:
    def __init__(self, design, packet=None):
        self.snapshot = Snapshot(use_git=False)
        self.design = design
        self.entry = next(d for d in self.snapshot.contract["designs"] if d["id"] == design)
        self.assembly = json.loads(self.snapshot.verify(self.entry["assembly"]))
        self.source = json.loads(self.snapshot.verify(self.entry["contactFrames"]))
        if any(f["independentRockerAngleRad"] is not None for f in self.source["frames"]):
            raise ValueError("A changed canonical rocker contract requires explicit review")
        self.api, self.provenance = canonical_functions(self.snapshot)
        self.common = self.assembly["parameters"]["common"]
        self.foot = self.common["foot"]
        self.reference_z = self.assembly["bodyOriginZMm"]
        self.dims = self.api["dimensions"]("reference", self.common)
        self.order = self.source["footOrder"]
        self.foot_indices = {(f["stationYmm"], f["side"]): i for i, f in enumerate(self.order)}
        self.reference = self.points(0)
        self.groups, self.group_items, lookup = [], [], {}
        self.instance_groups = {}
        for item in self.assembly["instances"]:
            key = json.dumps(item["motion"], sort_keys=True)
            if key not in lookup:
                lookup[key] = len(self.groups)
                self.groups.append(item["motion"])
                self.group_items.append(item)
            self.instance_groups[item["name"]] = lookup[key]
        self.keys = {(m["station"], m["side"], m["phase"]) for m in self.groups if "phase" in m}
        self.initial = {key: self.points(key[2]) for key in self.keys}
        self.source_bodies = np.asarray([f["bodyHeightAndSlopes"] for f in self.source["frames"]])
        self.source_compressions = np.asarray([f["springCompressionMm"] for f in self.source["frames"]])
        self.planar = [f["integratedPlanarComponents"] for f in self.source["frames"]]
        self.targets = []
        for frame in self.source["frames"]:
            h, sx, sy = frame["bodyHeightAndSlopes"]
            small = np.array([[1, 0, -sx], [0, 1, -sy], [sx, sy, 1]])
            centers = np.asarray(frame["toesBodyMm"]) @ small.T + [0, 0, h]
            force = np.asarray(frame["normalN"])
            self.targets.append(np.r_[force.sum(), force @ centers[:, :2] / force.sum()].tolist())
        self.packet = packet

    def points(self, theta):
        return self.api["points_many"](np.array(theta), self.dims, self.common["linkScale"])[0]

    def neutral(self, theta):
        feet, guides, gammas = [], [], []
        frames = {key: (self.points(theta + key[2]), self.initial[key], self.reference) for key in self.keys}
        for foot in self.order:
            key = (foot["stationYmm"], foot["side"], math.radians(foot["phaseDeg"]))
            p = frames[key][0]
            gamma = math.atan2(*(p["E"] - p["C"])[::-1]) - math.radians(self.foot["pitchReferenceBodyAngleDeg"])
            c, s = math.cos(gamma), math.sin(gamma)
            dy, dz = self.foot["toeOffsetFromFNeutralMm"]
            feet.append([foot["side"] * self.foot["centerAbsXmm"],
                         foot["stationYmm"] + p["F"][0] + dy * c - dz * s,
                         p["F"][1] + dy * s + dz * c])
            guides.append([0, -s, c])
            gammas.append(gamma)
        return np.array(feet), np.array(guides), np.array(gammas), frames

    def contacts(self, body, neutral):
        h, sx, sy = body
        r = polar_rotation(sx, sy)
        feet, guides, gamma, _ = neutral
        world = feet @ r.T + [0, 0, h]
        axes = guides @ r.T
        if axes[:, 2].min() < .25:
            raise ValueError("Invalid near-horizontal guide")
        gap = world[:, 2] - self.foot["toeRadiusMm"]
        compression = np.maximum(0, -gap / axes[:, 2])
        world += compression[:, None] * axes
        normal = compression * self.foot["springCountPerFoot"] * self.foot["springRateNmm"] / axes[:, 2]
        rocker, pad_minimum = [], []
        for i in range(6):
            axis = r @ np.array([0, math.cos(gamma[i]), math.sin(gamma[i])])
            lane = r[:, 0]
            angle = math.atan2(-lane[2], np.cross(axis, lane)[2])
            angle = (angle + math.pi / 2) % math.pi - math.pi / 2
            if abs(angle) > math.radians(self.foot["rockerTravelDeg"]):
                raise ValueError("Equal-height rocker exceeds actual stops")
            t = min(max(gap[i] / 3, 0), 1)
            angle *= 1 - t * t * (3 - 2 * t)
            u = lane * math.cos(angle) + np.cross(axis, lane) * math.sin(angle)
            u += axis * (axis @ lane) * (1 - math.cos(angle))
            low = (world[i, 2] - self.foot["toeRadiusMm"] * math.sqrt(max(0, 1 - u[2] ** 2))
                   - (self.foot["rockerHalfSpanMm"] + self.foot["toeLaneWidthMm"] / 2) * abs(u[2]))
            rocker.append(angle)
            pad_minimum.append(low)
        return {"rotation": r, "centers": world, "compression": compression, "normal": normal,
                "rocker": np.array(rocker), "padMinimum": np.array(pad_minimum), "gamma": gamma}

    def equilibrium_error(self, body, neutral, target):
        state = self.contacts(body, neutral)
        normal, centers = state["normal"], state["centers"]
        return np.r_[normal.sum() - target[0],
                     (normal @ centers[:, :2] - target[0] * target[1:]) / 100]

    def generate(self, step_deg=.125):
        count = round(360 / step_deg)
        if count < 72 or abs(count * step_deg - 360) > 1e-9:
            raise ValueError("Use an exact cycle divisor of at most 5deg")
        bodies, corrections = [], []
        maximum_error = 0
        for index in range(count):
            theta = index * TAU / count
            initial = sample_periodic(self.source_bodies, theta)
            target = sample_periodic(self.targets, theta)
            neutral = self.neutral(theta)
            solution = root(self.equilibrium_error, initial, args=(neutral, target), tol=1e-10)
            error = float(np.max(np.abs(self.equilibrium_error(solution.x, neutral, target))))
            if error > 1e-8:
                raise ValueError(f"{self.design} {math.degrees(theta)}deg: contact reconciliation failed ({error})")
            maximum_error = max(maximum_error, error)
            bodies.append(solution.x.tolist())
            contact = self.contacts(solution.x, neutral)
            corrections.append([abs(solution.x[0] - initial[0]),
                                math.degrees(np.linalg.norm(solution.x[1:] - initial[1:])),
                                float(np.max(np.abs(contact["compression"] - sample_periodic(self.source_compressions, theta))))])
        bodies.append(bodies[0])
        packet = {
            "schemaVersion": 1, "revisionId": REVISION, "designId": self.design,
            "source": {
                "geometryRevision": self.snapshot.source["revisionId"],
                "artifactCommit": self.snapshot.commit, "inputCommit": self.snapshot.source["inputCommit"],
                "sourceHash": self.snapshot.source["sourceHash"],
                "contractSha256": self.snapshot.source["contractSha256"],
                "assemblySha256": self.entry["assembly"]["sha256"],
                "contactFramesSha256": self.entry["contactFrames"]["sha256"],
                "meshSha256": self.entry["mesh"]["sha256"], "canonicalFunctions": self.provenance,
            },
            "units": {"length": "mm", "angle": "rad", "force": "N", "time": "s"},
            "conventions": "Right-handed CAD X=shaft, Y=station, Z=up; row-major rigid matrices. Forward is -Y.",
            "assumptions": ASSUMPTIONS, "manufacturingRelease": False, "physicalQualifiedCount": 0,
            "canonicalIndependentRockerAngleRad": None, "physicalTestsPerformed": False,
            "bodyReferenceZMm": self.reference_z,
            "lengthsMm": {k: v * self.common["linkScale"] for k, v in self.dims.items()},
            "rigids": {k: list(v) for k, v in self.api["rigids"]().items()},
            "foot": {k: self.foot[k] for k in (
                "centerAbsXmm", "toeOffsetFromFNeutralMm", "pitchReferenceBodyAngleDeg", "toeRadiusMm",
                "rockerTravelDeg", "rockerHalfSpanMm", "toeLaneWidthMm", "springCountPerFoot", "springRateNmm",
                "springFreeLengthMm", "springOuterDiameterMm", "springWireMm", "springTotalTurns",
                "springRatedTravelMm", "workingCompressionLimitMm", "springBottomSeatAboveFmm", "springTopSeatAboveFmm")},
            "airborneRestClearanceMm": 3, "footOrder": self.order, "motionGroups": self.groups,
            "instances": {i["name"]: [i["part_id"], self.instance_groups[i["name"]]] for i in self.assembly["instances"]},
            "instanceCount": len(self.assembly["instances"]), "reducer": self.assembly["reduction"],
            "prescribedInputRpm": 120,
            "inputTurnsPerCrank": self.source["prescribedTiming"]["signedInputTurnsPerCrank"],
            "bodySampleStepDeg": step_deg, "bodySamples": bodies, "normalTargets": self.targets,
            "planarSamples": self.planar, "forwardPerCycleMm": -self.planar[-1][1],
            "sourceSlipMaximumMm": self.snapshot.json(f"docs/ver3/integrated_r7/{self.design}/work_budget.json")["contact"]["maximum_predicted_loaded_episode_slip_mm"],
            "reconciliation": {
                "maximumSolvedScaledBalanceError": maximum_error,
                "maximumHeightCorrectionMm": float(np.max(corrections, axis=0)[0]),
                "maximumSlopeCorrectionDegreesApprox": float(np.max(corrections, axis=0)[1]),
                "maximumGuideCompressionCorrectionMm": float(np.max(corrections, axis=0)[2]),
                "scope": "Compared with interpolated saved source states; no translation of the floor or modification of geometry.",
            },
        }
        self.packet = packet
        return packet

    def pose(self, theta):
        if self.packet is None:
            raise ValueError("Generate or load the versioned motion packet first")
        phase = theta % TAU
        body = sample_periodic(self.packet["bodySamples"], phase)
        neutral = self.neutral(phase)
        state = self.contacts(body, neutral)
        planar = planar_pose(self.planar, theta)
        c, s = math.cos(planar[2]), math.sin(planar[2])
        rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        rotation = rz @ state["rotation"]
        world = np.eye(4)
        world[:3, :3] = rotation
        world[:3, 3] = np.r_[planar[:2], body[0]] - rotation @ [0, 0, self.reference_z]
        deltas = []
        for item in self.group_items:
            motion = item["motion"]
            index = self.foot_indices[(motion["station"], motion["side"])] if motion["kind"] == "foot" else None
            delta = self.api["transform"](item, theta, self.common, self.reference_z,
                                          state["compression"][index] if index is not None else 0,
                                          state["rocker"][index] if index is not None else 0, neutral[3])
            deltas.append(delta)
        return {**state, "body": world, "groups": deltas, "planar": planar, "neutral": neutral,
                "bodyParameters": body, "theta": theta, "target": sample_periodic(self.targets, phase)}

    def validate(self, step_deg=.0625, check_floor=True, floor_step_deg=.5):
        floor_api = source_floor_api(self.snapshot, self.api)
        envelopes = json.loads(self.snapshot.verify(self.entry["nativeFloorEnvelopes"])) if check_floor else None
        lows, supports = [], []
        maximum_gram, maximum_balance, maximum_compression, maximum_rocker = 0., 0., 0., 0.
        maximum_link_error, maximum_anchor_error, floor_samples = 0., 0., 0
        minimum_pad, minimum_loaded = math.inf, 6
        worst_floor = None
        for degrees in np.arange(0, 360, step_deg):
            pose = self.pose(math.radians(degrees))
            state = pose
            for points, _, _ in pose["neutral"][3].values():
                for a, b, length in (("O", "A", "OA"), ("A", "B", "AB"), ("B", "P", "BP"),
                                     ("A", "C", "AC"), ("P", "C", "PC"), ("B", "D", "BD"),
                                     ("P", "D", "PD"), ("C", "E", "CE"), ("D", "E", "DE"),
                                     ("C", "F", "CF"), ("E", "F", "EF")):
                    maximum_link_error = max(maximum_link_error, abs(float(np.linalg.norm(points[a] - points[b]))
                                                                     - self.packet["lengthsMm"][length]))
            minimum_pad = min(minimum_pad, float(state["padMinimum"].min()))
            maximum_compression = max(maximum_compression, float(state["compression"].max()))
            maximum_rocker = max(maximum_rocker, float(np.abs(state["rocker"]).max()))
            force = state["normal"]
            active = force > .02 * state["target"][0]
            minimum_loaded = min(minimum_loaded, int(active.sum()))
            if active.sum() < 3:
                raise ValueError("Fewer than three display load-bearing feet")
            hull = ConvexHull(state["centers"][active, :2])
            margin = float(np.min(-(hull.equations[:, :2] @ state["target"][1:] + hull.equations[:, 2])))
            supports.append(margin)
            error = self.equilibrium_error(pose["bodyParameters"], pose["neutral"], pose["target"])
            maximum_balance = max(maximum_balance, float(np.max(np.abs(error))))
            for matrix in [pose["body"], *pose["groups"]]:
                maximum_gram = max(maximum_gram, float(np.max(np.abs(matrix[:3, :3].T @ matrix[:3, :3] - np.eye(3)))))
            for item in self.assembly["instances"]:
                if item["motion"].get("piece") != "SPRING":
                    continue
                m = item["motion"]
                i = self.foot_indices[(m["station"], m["side"])]
                base = np.asarray(item["transform"])
                free_delta = self.api["transform"](item, math.radians(degrees), self.common, self.reference_z, 0, 0, pose["neutral"][3])
                moving_delta = pose["groups"][self.instance_groups[item["name"]]]
                top = moving_delta @ base @ [0, 0, self.foot["springFreeLengthMm"] - pose["compression"][i], 1]
                fixed = free_delta @ base @ [0, 0, self.foot["springFreeLengthMm"], 1]
                maximum_anchor_error = max(maximum_anchor_error, float(np.linalg.norm(top - fixed)))
            if envelopes is not None and abs(degrees / floor_step_deg - round(degrees / floor_step_deg)) < 1e-8:
                floor_samples += 1
                for item in self.assembly["instances"]:
                    part = envelopes["parts"][item["part_id"]]
                    matrix = pose["body"] @ pose["groups"][self.instance_groups[item["name"]]] @ np.asarray(item["transform"])
                    low = float(floor_api["minimum_cloud"](part["points"], part.get("circles", []), matrix[2:3, :3])[0] + matrix[2, 3])
                    if not lows or low < lows[0]:
                        lows[:] = [low]
                        worst_floor = {"crankDeg": float(degrees), "instanceId": item["name"]}
        first, end = self.pose(0), self.pose(TAU)
        closure = max(float(np.abs(a - b).max()) for a, b in zip(first["groups"], end["groups"]))
        report = {
            "designId": self.design, "revisionId": REVISION, "samples": len(supports),
            "sampleStepDeg": step_deg, "instanceCount": len(self.assembly["instances"]),
            "maximumRotationGramError": maximum_gram, "maximumCycleLocalMatrixDifference": closure,
            "maximumLinkLengthErrorMm": maximum_link_error, "maximumSpringTopAnchorErrorMm": maximum_anchor_error,
            "nativeNoncontactFloorSamples": floor_samples, "nativeNoncontactFloorStepDeg": floor_step_deg,
            "minimumAnalyticalPadZMm": minimum_pad,
            "minimumNativeNoncontactEnvelopeZMm": lows[0] if lows else None, "lowestNoncontact": worst_floor,
            "maximumGuideCompressionMm": maximum_compression, "maximumRockerAngleDeg": math.degrees(maximum_rocker),
            "minimumLoadedFeet": minimum_loaded, "minimumSupportMarginMm": min(supports),
            "maximumInterpolatedBalanceErrorNAndNmmPer100": maximum_balance,
            "minimumSpringLengthMm": self.foot["springFreeLengthMm"] - maximum_compression,
            "springSolidLengthMm": self.foot["springWireMm"] * self.foot["springTotalTurns"],
            "sourceCanonicalRockerNullPreserved": True, "sourceGeometryUnchanged": True,
            "floorTranslationMm": 0, "newTangentialDynamicsSolved": False, "manufacturingRelease": False,
            "scope": "Finite rigid/contact checks, not swept-volume collision proof, CFD, dynamics, manufacturing or hardware qualification.",
        }
        checks = {
            "rigid": maximum_gram < 1e-9, "closure": closure < 1e-8,
            "padFloor": minimum_pad >= -1e-8, "noncontactFloor": bool(lows) and lows[0] >= -1e-8,
            "stroke": maximum_compression < self.foot["workingCompressionLimitMm"],
            "rockerStops": maximum_rocker <= math.radians(self.foot["rockerTravelDeg"]),
            "support": min(supports) >= 3, "balance": maximum_balance < .01,
            "pinDistances": maximum_link_error < 1e-8, "springAnchors": maximum_anchor_error < 1e-8,
            "boundedReconciliation": self.packet["reconciliation"]["maximumHeightCorrectionMm"] < .1
                and self.packet["reconciliation"]["maximumSlopeCorrectionDegreesApprox"] < .06
                and self.packet["reconciliation"]["maximumGuideCompressionCorrectionMm"] < .15,
        }
        report["checks"] = checks
        report["status"] = "PASS" if all(checks.values()) else "FAIL"
        return report


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", choices=list("ABC"), default="C")
    parser.add_argument("--step-deg", type=float, default=.125)
    parser.add_argument("--validation-step-deg", type=float, default=.0625)
    parser.add_argument("--skip-floor", action="store_true")
    args = parser.parse_args()
    model = WalkModel(args.design)
    packet = model.generate(args.step_deg)
    report = model.validate(args.validation_step_deg, not args.skip_floor)
    write_json(OUTPUT / f"motion_{args.design}.json", packet)
    write_json(OUTPUT / f"validation_{args.design}.json", report)
    fixtures = []
    for degrees in (0, .125, 37.3, 120, 179.875, 240, 359.875, 360, 793.4):
        pose = model.pose(math.radians(degrees))
        fixtures.append({"crankDegUnwrapped": degrees, "body": pose["body"].tolist(),
                         "groups": [m.tolist() for m in pose["groups"]],
                         "compression": pose["compression"].tolist(), "rocker": pose["rocker"].tolist(),
                         "padMinimum": pose["padMinimum"].tolist(), "normal": pose["normal"].tolist()})
    write_json(OUTPUT / f"reference_{args.design}.json", fixtures)
    print(json.dumps({"reconciliation": packet["reconciliation"], "validation": report}, indent=2), flush=True)
    if report["status"] != "PASS":
        raise SystemExit("Continuous walking constraints failed; do not publish this motion packet")


if __name__ == "__main__":
    main()
