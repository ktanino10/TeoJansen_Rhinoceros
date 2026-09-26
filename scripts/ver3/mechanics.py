"""Shared mass and rigid-ground helpers for numerical checks and walking."""

import gzip
import itertools
import json
import math

import numpy as np
from scipy.optimize import minimize, nnls
from scipy.spatial import ConvexHull, QhullError

from core import CONFIG, LINKS, ROOT, animated_transform, foot_centers, gait


class MassModel:
    """Exact aggregation of the canonical rigid-part mass transformations."""

    def __init__(self, manifest):
        self.manifest = manifest
        self.design = manifest["design"]
        self.mass_g = 0.0
        self.fixed = np.zeros(3)
        self.rotating = {}
        self.translating = {}
        self.links = {}
        for instance in manifest["instances"]:
            part = manifest["parts"][instance["part_id"]]
            mass = part["mass_g"]
            local = np.array(part["local_center_of_mass_mm"])
            initial = (np.array(instance["transform"]) @ np.append(local, 1))[:3]
            self.mass_g += mass
            motion = instance.get("motion")
            if not motion:
                self.fixed += mass*initial
                continue
            kind = motion["type"]
            if kind in ("shaft", "crank"):
                center = motion.get("center", [0, 0])
                key = (motion.get("speed", 1), center[0], center[1])
                old_mass, moment = self.rotating.get(key, (0.0, np.zeros(3)))
                self.rotating[key] = (old_mass+mass, moment+mass*initial)
            elif kind == "joint":
                key = (motion["node"], motion["phase"], motion.get("mirrored", False))
                old_mass, moment = self.translating.get(key, (0.0, np.zeros(3)))
                self.translating[key] = (old_mass+mass, moment+mass*initial)
            elif kind == "link":
                key = (motion["part_id"], motion["phase"], motion["mirrored"])
                old_mass, x_moment, _ = self.links.get(key, (0.0, 0.0, local))
                self.links[key] = (old_mass+mass, x_moment+mass*initial[0], local)
            else:
                raise ValueError(kind)

    def at(self, theta):
        result = self.fixed.copy()
        height = CONFIG["linkage"]["crank_height"]
        for (speed, y, z), (mass, moment) in self.rotating.items():
            center = np.array([0, y, z+height])
            vector = moment-mass*center
            co, si = math.cos(speed*theta), math.sin(speed*theta)
            rotated = np.array([vector[0], co*vector[1]-si*vector[2],
                                si*vector[1]+co*vector[2]])
            result += rotated+mass*center
        for (node, phase, mirror), (mass, moment) in self.translating.items():
            delta = gait(theta+phase, mirror)[node]-gait(phase, mirror)[node]
            result += moment+mass*np.array([0, *delta])
        for (part_id, phase, mirror), (mass, x_moment, local) in self.links.items():
            points = gait(theta+phase, mirror)
            names = LINKS[part_id.removesuffix("_R")]
            origin, end = points[names[0]], points[names[1]]
            direction = (end-origin)/np.linalg.norm(end-origin)
            yz = origin+np.array([direction[0]*local[0]-direction[1]*local[1],
                                  direction[1]*local[0]+direction[0]*local[1]])
            result += [x_moment, mass*yz[0], mass*(yz[1]+height)]
        return result/self.mass_g

    def verify(self):
        maximum = 0.0
        for theta in (0, 0.41, 1.9, 3.4, 2*math.pi):
            moment = np.zeros(3)
            for instance in self.manifest["instances"]:
                part = self.manifest["parts"][instance["part_id"]]
                matrix = np.array(animated_transform(instance, theta, self.design))
                point = matrix @ np.array(part["local_center_of_mass_mm"]+[1])
                moment += part["mass_g"]*point[:3]
            maximum = max(maximum, float(np.abs(moment/self.mass_g-self.at(theta)).max()))
        if maximum > 1e-8:
            raise RuntimeError(f"Mass aggregation differs from native assembly transforms by {maximum} mm")
        return maximum


def foot_rates(design, theta, epsilon=1e-5):
    return (foot_centers(design, theta+epsilon)-foot_centers(design, theta-epsilon))/(2*epsilon)


def ground_candidates(design, theta, center, tilt_limit=10):
    """Lower-hull point-foot triangles; no dynamic ground-contact claim."""
    feet = foot_centers(design, theta)
    rates = foot_rates(design, theta)
    candidates = []
    for indices in itertools.combinations(range(6), 3):
        triangle = feet[list(indices)]
        u, v = triangle[1]-triangle[0], triangle[2]-triangle[0]
        normal = np.cross(u, v)
        length = float(np.linalg.norm(normal))
        if length < 1e-9:
            continue
        normal /= length
        if normal[2] < 0:
            normal *= -1
        tilt = math.degrees(math.acos(float(np.clip(normal[2], -1, 1))))
        if tilt > tilt_limit or ((feet-triangle[0])@normal).min() < -1e-6:
            continue
        projection = center-np.dot(center-triangle[0], normal)*normal
        coordinates = np.linalg.lstsq(np.column_stack([u, v]), projection-triangle[0], rcond=None)[0]
        barycentric = np.array([1-coordinates.sum(), *coordinates])
        if barycentric.min() < -1e-8:
            continue
        margins = []
        for i in range(3):
            edge = triangle[(i+1)%3]-triangle[i]
            margins.append(float(np.linalg.norm(np.cross(edge, projection-triangle[i]))/np.linalg.norm(edge)))
        tangent = np.array([0.0, 1.0, 0.0])
        tangent -= normal*np.dot(normal, tangent)
        tangent /= np.linalg.norm(tangent)
        speeds = rates[list(indices)]@tangent
        same_direction = bool(np.all(speeds > 0) or np.all(speeds < 0))
        candidates.append(dict(contacts=list(indices), normal=normal, tilt_deg=tilt,
                               barycentric=barycentric, margin_mm=min(margins),
                               same_direction=same_direction, foot_velocities_mm_per_rad=speeds))
    return candidates


def level_rotation(normal):
    """Rotate the support-plane normal to world +Z, without inventing yaw."""
    z = np.array([0.0, 0.0, 1.0])
    axis = np.cross(normal, z)
    sine = np.linalg.norm(axis)
    cosine = float(normal@z)
    if sine < 1e-12:
        return np.eye(3)
    cross = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3)+cross+cross@cross*((1-cosine)/(sine*sine))


class FootGeometry:
    """Contact geometry tessellated from the actual shoe, sole and F-pin CAD."""

    def __init__(self, manifest):
        self.manifest = manifest
        self.design = manifest["design"]
        with gzip.open(ROOT/manifest["cad_meshes"], "rt") as stream:
            self.meshes = json.load(stream)
        initial_foot = foot_centers(self.design, 0)[0]
        points = []
        for instance in manifest["instances"]:
            motion = instance.get("motion", {})
            if (motion.get("type") == "joint" and motion.get("node") == "F"
                    and motion["bay"] == 0 and motion["phase"] == 0 and not motion.get("mirrored", False)):
                vertices = np.array(self.meshes[instance["part_id"]]["vertices"])
                matrix = np.array(instance["transform"])
                world = vertices@matrix[:3, :3].T+matrix[:3, 3]
                points.extend(world-initial_foot)
        if not points:
            raise ValueError("No canonical F-joint shoe geometry in assembly")
        cloud = np.unique(np.round(np.array(points), 9), axis=0)
        self.vertices = cloud[ConvexHull(cloud).vertices]
        self.reject_counts = {"degenerate_contact_polygon": 0}

    def options(self, theta, center, previous_normal=None, tolerance=0.25, max_tilt=10):
        centers = foot_centers(self.design, theta)
        cloud = (centers[:, None, :]+self.vertices[None, :, :]).reshape(-1, 3)
        foot_ids = np.repeat(np.arange(6), len(self.vertices))
        hull = ConvexHull(cloud)
        normals = [np.array([0.0, 0.0, 1.0])]
        if previous_normal is not None:
            normals.append(previous_normal)
        for equation in hull.equations:
            normal = -equation[:3]
            if normal[2] >= math.cos(math.radians(max_tilt)):
                if all(np.linalg.norm(normal-old) > 1e-6 for old in normals):
                    normals.append(normal)
        rates = foot_rates(self.design, theta)
        solutions = []
        for normal in normals:
            height = cloud@normal
            minimum = float(height.min())
            near = height <= minimum+tolerance
            contacts = sorted(set(foot_ids[near].tolist()))
            if len(contacts) < 2:
                continue
            rotation = level_rotation(normal)
            contact_xy = (cloud[near]@rotation.T)[:, :2]
            try:
                support = ConvexHull(contact_xy)
            except QhullError:
                self.reject_counts["degenerate_contact_polygon"] += 1
                continue
            cog_xy = (rotation@center)[:2]
            margin = float((-(support.equations[:, :2]@cog_xy+support.equations[:, 2])).min())
            if margin < -1e-7:
                continue
            tangent = rotation[1]
            velocities = rates[contacts]@tangent
            same = bool(np.all(velocities > 0) or np.all(velocities < 0))
            local_contacts = {}
            for index in contacts:
                selected = near & (foot_ids == index)
                local_contacts[index] = (cloud[selected]-centers[index]).mean(axis=0)
            solutions.append(dict(normal=normal, rotation=rotation, contacts=contacts,
                                  min_height=minimum, support_margin_mm=margin,
                                  same_direction=same, local_contacts=local_contacts,
                                  contact_points=cloud[near], contact_foot_ids=foot_ids[near],
                                  support_equations=support.equations,
                                  max_contact_gap_mm=max(float(height[foot_ids == index].min()-minimum) for index in contacts),
                                  tilt_deg=math.degrees(math.acos(float(np.clip(normal[2], -1, 1))))))
        return solutions

    def normal_loads(self, solution, center, foot_points):
        rotation = solution["rotation"]
        points = solution["contact_points"]
        identities = solution["contact_foot_ids"]
        xy = (points@rotation.T)[:, :2]/100
        balance = np.vstack([np.ones(len(points)), xy.T])
        target = np.r_[1, (rotation@center)[:2]/100]
        initial, residual = nnls(balance, target)
        if residual > 1e-6:
            raise RuntimeError(f"Contact force/moment balance is infeasible: {residual}")
        aggregation = np.array([identities == i for i in range(6)], float)
        objective = aggregation.T@aggregation+np.eye(len(points))*0.001
        fit = minimize(lambda w: float(w@objective@w), initial,
                       jac=lambda w: 2*objective@w, method="SLSQP",
                       bounds=[(0, None)]*len(points),
                       constraints=[{"type": "eq", "fun": lambda w: balance@w-target,
                                     "jac": lambda w: balance}],
                       options={"ftol": 1e-11, "maxiter": 80})
        if not fit.success or np.linalg.norm(balance@fit.x-target) > 1e-6:
            raise RuntimeError(f"Normal-load distribution failed: {fit.message}")
        weights = aggregation@fit.x
        local_centers = {}
        for i in np.flatnonzero(weights > 0.02):
            mask = identities == i
            local_centers[int(i)] = ((points[mask]-foot_points[i])*fit.x[mask, None]).sum(axis=0)/weights[i]
        return weights, local_centers
