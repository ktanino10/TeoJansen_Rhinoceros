import math
import unittest

import numpy as np

from beam import rectangle_section
from frame3d import solve_frame
from wind_module import blade_profile, holder_response, load


class FrameTests(unittest.TestCase):
    def test_cantilever_all_load_directions(self):
        nodes = {"root": [0, 0, 0], "tip": [100, 0, 0]}
        members = [dict(a="root", b="tip", width=8, thickness=4, reference=[0, 0, 1], kind="test")]
        e, g = 200000, 200000/(2*1.3)
        area, iy, iz = 32, 8*4**3/12, 4*8**3/12
        jt = rectangle_section(8, 4).torsion_lower
        for direction, expected in (
            (0, 10*100/(e*area)),
            (1, 10*100**3/(3*e*iz)),
            (2, 10*100**3/(3*e*iy)),
            (3, 10*100/(g*jt)),
        ):
            force = np.zeros(6)
            force[direction] = 10
            result = solve_frame(nodes, members, ["root"], {"tip": force.tolist()}, e, .3)
            self.assertAlmostEqual(result["displacements"]["tip"][direction], expected, places=10)
            self.assertLess(result["force_balance_error_n"], 1e-8)
            self.assertLess(result["moment_balance_error_nmm"], 1e-7)

    def test_rotated_frame_and_refinement(self):
        nodes = {"root": [0, 0, 0], "tip": [0, 100, 0]}
        members = [dict(a="root", b="tip", width=8, thickness=4, reference=[0, 0, 1], kind="test")]
        first = solve_frame(nodes, members, ["root"], {"tip": [0, 0, -10, 0, 0, 0]}, 200000, .3)
        second = solve_frame(nodes, members, ["root"], {"tip": [0, 0, -10, 0, 0, 0]}, 200000, .3, 4)
        np.testing.assert_allclose(first["displacements"]["tip"], second["displacements"]["tip"], atol=1e-10)
        self.assertLess(first["displacements"]["tip"][2], 0)

    def test_invalid_axis_not_silently_defaulted(self):
        with self.assertRaises(ValueError):
            solve_frame({"a": [0, 0, 0], "b": [0, 0, 100]},
                        [dict(a="a", b="b", width=8, thickness=4, reference=[0, 0, 1], kind="test")],
                        ["a"], {"b": [1, 0, 0, 0, 0, 0]})

    def test_blade_real_thickness_within_outside_diameter(self):
        cfg = load()
        for thickness in cfg["rotor"]["thicknessStationsMm"]:
            for angle in (0, 90, 137):
                points = blade_profile(cfg, angle, thickness)
                self.assertLessEqual(np.linalg.norm(points, axis=1).max(), 50)
                self.assertGreater(np.linalg.norm(points, axis=1).min(), 20)
        self.assertEqual(cfg["rotor"]["rootPlateMm"]+cfg["rotor"]["activeSpanMm"]+
                         cfg["rotor"]["endRingThicknessMm"], cfg["rotor"]["outerSpanMm"])

    def test_bracing_comparison_uses_same_force_and_absolute_result(self):
        cfg = load()
        bare = holder_response(cfg, "fixed", False, [1, 0, 0], 800)
        braced = holder_response(cfg, "fixed", True, [1, 0, 0], 800)
        self.assertLess(abs(braced["bearing_center_shift_mm"][0]), abs(bare["bearing_center_shift_mm"][0]))
        self.assertLess(braced["force_balance_error_n"], 1e-7)
        self.assertLess(braced["moment_balance_error_nmm"], 1e-6)
        self.assertIn("NOT solved", braced["boundary"])

    def test_bearing_offset_translation_is_work_conjugate(self):
        cfg = load()
        for side in ("fixed", "floating"):
            for force in ([0, 0, 1], [0, 1, 0], [1, -.3, .7]):
                result = holder_response(cfg, side, True, force, 800)
                offset = np.array(result["ring_to_bearing_offset_mm"])
                rotation = np.array(result["mean_ring_rotation_rad"])
                shift = np.array(result["bearing_center_shift_mm"])
                transported = np.array(result["ring_plane_translation_mm"])+np.cross(rotation, offset)
                np.testing.assert_allclose(shift, transported, atol=1e-12)
                nodal_work = sum(np.dot(result["loads"][n], result["displacements"][n])
                                 for n in result["bearing_ring_nodes"])
                self.assertAlmostEqual(nodal_work, np.dot(force, shift), places=12)
                self.assertLess(result["load_point_work_residual_nmm"], 1e-10)
                self.assertGreater(np.linalg.norm(result["bearing_offset_rotation_translation_mm"]), 1e-8)
        vertical = holder_response(cfg, "fixed", True, [0, 0, 1], 800)
        self.assertAlmostEqual(vertical["bearing_center_shift_mm"][2], .001028710, places=9)
        self.assertGreater(vertical["bearing_center_shift_mm"][2], vertical["ring_plane_translation_mm"][2])


if __name__ == "__main__":
    unittest.main()
