"""Linear 3D Euler--Bernoulli frame elements, mm/N/MPa/radians.

This is a slender-member surrogate, not solid/laminated-plastic FEM. All root
constraints, section orientations and loads must be supplied by the caller.
"""

import math

import numpy as np

from beam import rectangle_section


def member_matrix(first, second, width, thickness, reference, modulus, poisson):
    delta = np.array(second, float)-first
    length = float(np.linalg.norm(delta))
    if length <= 0 or min(width, thickness, modulus) <= 0 or not -1 < poisson < .5:
        raise ValueError("Invalid beam geometry/material")
    ex = delta/length
    ez = np.array(reference, float)-np.dot(reference, ex)*ex
    if np.linalg.norm(ez) < 1e-8:
        raise ValueError("Beam section reference is parallel to its span")
    ez /= np.linalg.norm(ez)
    ey = np.cross(ez, ex)
    rotation = np.vstack([ex, ey, ez])
    transform = np.zeros((12, 12))
    for i in (0, 3, 6, 9):
        transform[i:i+3, i:i+3] = rotation
    area = width*thickness
    iy, iz = width*thickness**3/12, thickness*width**3/12
    jt = rectangle_section(width, thickness).torsion_lower
    shear = modulus/(2*(1+poisson))
    local = np.zeros((12, 12))
    for indices, factor in (([0, 6], modulus*area/length), ([3, 9], shear*jt/length)):
        local[np.ix_(indices, indices)] = factor*np.array([[1, -1], [-1, 1]])
    standard = np.array([[12, 6*length, -12, 6*length],
                         [6*length, 4*length**2, -6*length, 2*length**2],
                         [-12, -6*length, 12, -6*length],
                         [6*length, 2*length**2, -6*length, 4*length**2]])
    local[np.ix_([1, 5, 7, 11], [1, 5, 7, 11])] = modulus*iz/length**3*standard
    signs = np.diag([1, -1, 1, -1])
    local[np.ix_([2, 4, 8, 10], [2, 4, 8, 10])] = modulus*iy/length**3*signs@standard@signs
    return transform.T@local@transform, local, transform, length, (area, iy, iz, jt)


def solve_frame(nodes, members, fixed_nodes, loads, modulus=800, poisson=.35, subdivisions=1):
    if subdivisions < 1:
        raise ValueError("At least one subdivision required")
    coordinates = {key: np.array(point, float) for key, point in nodes.items()}
    elements = []
    for index, m in enumerate(members):
        a, b = coordinates[m["a"]], coordinates[m["b"]]
        parent_length = float(np.linalg.norm(b-a))
        previous = m["a"]
        for i in range(1, subdivisions+1):
            key = m["b"] if i == subdivisions else f"_m{index}_{i}"
            if i != subdivisions:
                coordinates[key] = a+(b-a)*i/subdivisions
            elements.append({**m, "a": previous, "b": key, "parent": index, "parentLength": parent_length})
            previous = key
    names = list(coordinates)
    lookup = {name: i for i, name in enumerate(names)}
    stiffness, force = np.zeros((6*len(names),)*2), np.zeros(6*len(names))
    records = []
    for m in elements:
        ia, ib = lookup[m["a"]], lookup[m["b"]]
        dofs = np.r_[np.arange(6*ia, 6*ia+6), np.arange(6*ib, 6*ib+6)]
        global_k, local_k, transform, length, section = member_matrix(
            coordinates[m["a"]], coordinates[m["b"]], m["width"], m["thickness"],
            m["reference"], modulus, poisson)
        stiffness[np.ix_(dofs, dofs)] += global_k
        records.append((m, dofs, local_k, transform, section))
    for name, values in loads.items():
        values = np.array(values, float)
        if values.shape != (6,):
            raise ValueError("Loads must be Fx,Fy,Fz,Mx,My,Mz")
        force[6*lookup[name]:6*lookup[name]+6] += values
    fixed = sorted({6*lookup[n]+i for n in fixed_nodes for i in range(6)})
    free = np.array([i for i in range(len(force)) if i not in fixed])
    displacement = np.zeros_like(force)
    displacement[free] = np.linalg.solve(stiffness[np.ix_(free, free)], force[free])
    residual = stiffness@displacement-force
    reactions = {n: residual[6*lookup[n]:6*lookup[n]+6].tolist() for n in fixed_nodes}
    force_error, moment_error = np.zeros(3), np.zeros(3)
    for name in names:
        vector = force[6*lookup[name]:6*lookup[name]+6]
        if name in reactions:
            vector = vector+reactions[name]
        force_error += vector[:3]
        moment_error += vector[3:]+np.cross(coordinates[name], vector[:3])
    stresses = []
    for m, dofs, local_k, transform, (area, iy, iz, jt) in records:
        internal = local_k@transform@displacement[dofs]
        axial = max(abs(internal[0]), abs(internal[6]))
        my = max(abs(internal[4]), abs(internal[10]))
        mz = max(abs(internal[5]), abs(internal[11]))
        stress = axial/area+my*m["thickness"]/2/iy+mz*m["width"]/2/iz
        compression = max(float(internal[0]), 0)
        euler = math.pi**2*modulus*min(iy, iz)/(2*m["parentLength"])**2
        stresses.append({"parent": m["parent"], "kind": m["kind"], "a": m["a"], "b": m["b"],
                         "normal_stress_screen_mpa": float(stress), "compression_n": compression,
                         "parent_span_euler_k2_n": euler, "torsion_peak_shear_mpa": None})
    return {
        "method": "3D linear Euler-Bernoulli frame surrogate; no solid FDM or bearing contact FEM",
        "units": "mm,N,MPa,rad", "modulus_mpa_assumed": modulus, "poisson_assumed": poisson,
        "coordinates": {k: v.tolist() for k, v in coordinates.items()}, "members": elements,
        "displacements": {n: displacement[6*lookup[n]:6*lookup[n]+6].tolist() for n in names},
        "loads": {k: list(v) for k, v in loads.items()}, "fixed_nodes": list(fixed_nodes),
        "reactions": reactions, "member_screens": stresses,
        "max_translation_mm": float(np.linalg.norm(displacement.reshape(-1, 6)[:, :3], axis=1).max()),
        "max_normal_stress_mpa": max(s["normal_stress_screen_mpa"] for s in stresses),
        "force_balance_error_n": float(np.linalg.norm(force_error)),
        "moment_balance_error_nmm": float(np.linalg.norm(moment_error)),
        "free_dof_residual": float(np.abs(residual[free]).max()),
    }
