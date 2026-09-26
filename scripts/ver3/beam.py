"""Small Euler--Bernoulli beam solver; mm, N, MPa and radians throughout."""

from dataclasses import dataclass
import math

import numpy as np
from scipy.integrate import quad


@dataclass(frozen=True)
class Section:
    area: float
    inertia_min: float
    extreme_fiber: float
    torsion_lower: float
    torsion_upper: float
    description: str


def circle_section(diameter):
    if diameter <= 0:
        raise ValueError("The diameter must be positive")
    radius = diameter / 2
    inertia = math.pi * radius**4 / 4
    return Section(math.pi * radius**2, inertia, radius, 2 * inertia,
                   2 * inertia, "solid circular section")


def d_section(diameter, flat_depth):
    """Exact area integrals; domain-monotonic torsional rigidity bounds, not Ip."""
    radius = diameter / 2
    if not 0 < flat_depth < radius:
        raise ValueError("Expected a single flat between the center and circumference")
    top = radius - flat_depth
    width = lambda y: 2 * math.sqrt(max(0, radius**2 - y**2))
    integrate = lambda fn: quad(fn, -radius, top, epsabs=1e-10)[0]
    area = integrate(width)
    centroid = integrate(lambda y: y * width(y)) / area
    ix = integrate(lambda y: (y - centroid)**2 * width(y))
    iy = integrate(lambda y: width(y)**3 / 12)
    # A circle of radius r-depth/2, shifted toward the round side, lies inside D.
    inner_radius = radius - flat_depth / 2
    return Section(area, min(ix, iy), radius + abs(centroid),
                   math.pi * inner_radius**4 / 2, math.pi * radius**4 / 2,
                   "single-flat D; weakest bending axis; Jt between inscribed/enclosing circles")


def rectangle_section(width, thickness):
    if min(width, thickness) <= 0:
        raise ValueError("The rectangle dimensions must be positive")
    thin, wide = sorted((width, thickness))
    inertia = wide * thin**3 / 12
    # The convergent Saint-Venant rectangle series is distinct from polar inertia.
    factor = sum(math.tanh(n * math.pi * wide / (2 * thin)) / n**5
                 for n in range(1, 202, 2))
    torsion = wide * thin**3 / 3 * (1 - 192 * thin * factor / (math.pi**5 * wide))
    return Section(width * thickness, inertia, thin / 2, torsion, torsion,
                   "solid rectangle; weak-axis bending; Saint-Venant rectangle series")


def solve_beam(length, elastic_modulus, section, loads, supports,
               distributed_load=0.0, elements=24, samples_per_element=9):
    """Point loads (x,F), constraints (x,translation|rotation); no hidden clamps."""
    if length <= 0 or elastic_modulus <= 0 or elements < 1:
        raise ValueError("Positive length, modulus and mesh count are required")
    for x, _ in [*loads, *supports]:
        if not 0 <= x <= length:
            raise ValueError(f"Position {x} lies outside beam length {length}")
    if any(kind not in ("translation", "rotation") for _, kind in supports):
        raise ValueError("Unknown support kind")
    xs = np.array(sorted(set(np.linspace(0, length, elements + 1).tolist()
                             + [float(x) for x, _ in loads]
                             + [float(x) for x, _ in supports])))
    size = 2 * len(xs)
    stiffness = np.zeros((size, size))
    force = np.zeros(size)
    ei = elastic_modulus * section.inertia_min
    for i, span in enumerate(np.diff(xs)):
        local = ei / span**3 * np.array([
            [12, 6*span, -12, 6*span],
            [6*span, 4*span**2, -6*span, 2*span**2],
            [-12, -6*span, 12, -6*span],
            [6*span, 2*span**2, -6*span, 4*span**2],
        ])
        dofs = np.arange(2*i, 2*i + 4)
        stiffness[np.ix_(dofs, dofs)] += local
        force[dofs] += distributed_load * np.array(
            [span/2, span**2/12, span/2, -span**2/12])
    for position, magnitude in loads:
        force[2 * int(np.where(xs == position)[0][0])] += magnitude
    constrained = sorted(set(
        2 * int(np.where(xs == position)[0][0]) + int(kind == "rotation")
        for position, kind in supports))
    free = np.array([i for i in range(size) if i not in constrained])
    displacement = np.zeros(size)
    reduced = stiffness[np.ix_(free, free)]
    if np.linalg.matrix_rank(reduced) != len(free):
        raise ValueError("Unrestrained or numerically singular beam")
    displacement[free] = np.linalg.solve(reduced, force[free])
    residual = stiffness @ displacement - force
    reactions = [{"x_mm": float(xs[dof//2]),
                  "kind": "moment" if dof % 2 else "force",
                  "value_n_or_nmm": float(residual[dof])}
                 for dof in constrained]
    fields = []
    for i, span in enumerate(np.diff(xs)):
        nodal = displacement[2*i:2*i + 4]
        for t in np.linspace(0, 1, samples_per_element):
            shape = np.array([1-3*t*t+2*t**3, span*(t-2*t*t+t**3),
                              3*t*t-2*t**3, span*(-t*t+t**3)])
            first = np.array([(-6*t+6*t*t)/span, 1-4*t+3*t*t,
                              (6*t-6*t*t)/span, -2*t+3*t*t])
            second = np.array([(-6+12*t)/span**2, (-4+6*t)/span,
                               (6-12*t)/span**2, (-2+6*t)/span])
            # The quartic bubble makes a uniform element load exact between nodes.
            q = distributed_load
            bubble = q * span**4 / (24*ei) * t*t*(1-t)**2
            bubble_first = q * span**3 / (24*ei) * (2*t-6*t*t+4*t**3)
            bubble_second = q * span**2 / (24*ei) * (2-12*t+12*t*t)
            moment = ei * (second @ nodal + bubble_second)
            fields.append([float(xs[i] + span*t), float(shape @ nodal + bubble),
                           float(first @ nodal + bubble_first), float(moment),
                           float(moment * section.extreme_fiber / section.inertia_min)])
    field = np.array(fields)
    vertical_balance = sum(f for _, f in loads) + distributed_load * length
    moment_balance = sum(x*f for x, f in loads) + distributed_load * length**2 / 2
    for item in reactions:
        value = item["value_n_or_nmm"]
        if item["kind"] == "force":
            vertical_balance += value
            moment_balance += item["x_mm"] * value
        else:
            moment_balance += value
    return {
        "method": "Euler-Bernoulli 1D beam finite elements; not solid FEM",
        "units": "mm,N,MPa,rad", "nodes": len(xs), "elements": len(xs)-1,
        "max_deflection_mm": float(np.abs(field[:, 1]).max()),
        "max_deflection_x_mm": float(field[np.argmax(np.abs(field[:, 1])), 0]),
        "max_rotation_rad": float(np.abs(field[:, 2]).max()),
        "max_bending_stress_mpa": float(np.abs(field[:, 4]).max()),
        "force_balance_error_n": float(abs(vertical_balance)),
        "moment_balance_error_nmm": float(abs(moment_balance)),
        "free_dof_residual_max": float(np.abs(residual[free]).max()),
        "reactions": reactions,
        "field_columns": ["x_mm", "displacement_mm", "rotation_rad", "moment_nmm", "stress_mpa"],
        "field": field.tolist(),
    }


def twist_bound(torque_nmm, length_mm, shear_modulus_mpa, section):
    if length_mm < 0 or shear_modulus_mpa <= 0:
        raise ValueError("Invalid torsion length or shear modulus")
    numerator = abs(torque_nmm) * length_mm / shear_modulus_mpa
    return {"lower_rad": numerator / section.torsion_upper,
            "upper_rad": numerator / section.torsion_lower,
            "peak_shear_stress_mpa": None,
            "note": "Rigidity bound only; D-section peak shear/yield not inferred from polar inertia"}
