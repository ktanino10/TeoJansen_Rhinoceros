from copy import deepcopy
import json
import math
import unittest

import numpy as np

from analyze_wind_module import proxy, rotor_screens
from input_cartridge import ROOT
from wind_module import blade_profile, holder_graph, load


class WindModuleTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load()

    def test_proxy_speed_scaling_and_no_forced_positive_torque(self):
        base = proxy(self.cfg, rays=128)
        changed = deepcopy(self.cfg)
        changed["loadCases"]["air"]["peakMS"] *= 2
        doubled = proxy(changed, rays=128)
        np.testing.assert_allclose(doubled[:, 1:], 4*base[:, 1:], atol=1e-13)
        centered = deepcopy(self.cfg)
        centered["loadCases"]["air"]["aimRadiusFraction"] = 0
        centered["rotor"]["sweepAngleDeg"] = 0
        self.assertLess(np.max(np.abs(proxy(centered, rays=128)[:, 1])), 1e-11)

    def test_root_cup_span_and_wall_definition(self):
        r = self.cfg["rotor"]
        self.assertEqual(r["rootPlateMm"]+r["activeSpanMm"]+r["endRingThicknessMm"], 38)
        self.assertEqual(r["thicknessStationsActiveXmm"][-1], 32)
        self.assertEqual(min(r["thicknessStationsMm"]), 1.2)
        for thickness in r["thicknessStationsMm"]:
            p = blade_profile(self.cfg, 0, thickness)
            self.assertLessEqual(np.linalg.norm(p, axis=1).max(), 50)
            # Both endpoints of each outer edge have the same normal offset.
            center = blade_profile(self.cfg)
            delta = np.diff(center, axis=0)
            normal = np.column_stack([-delta[:, 1], delta[:, 0]])/np.linalg.norm(delta, axis=1)[:, None]
            side = p[:len(center)]
            np.testing.assert_allclose(np.sum((side[:-1]-center[:-1])*normal, axis=1), thickness/2, atol=1e-11)

    def test_all_primary_material_paths_avoid_the_bearing_void(self):
        for side in ("fixed", "floating"):
            graph = holder_graph(self.cfg, side, True)
            for m in graph["members"]:
                if m["kind"] == "bearing_boss_ring":
                    a, b = np.array(graph["nodes"][m["a"]]), np.array(graph["nodes"][m["b"]])
                    midpoint = (a+b)/2
                    self.assertGreater(np.linalg.norm(midpoint[1:]-[0, 55])-m["width"]/2, 7.6)

    def test_bearing_resistance_stays_an_assumption(self):
        self.assertEqual(self.cfg["loadCases"]["bearingPairBreakawayNmmSensitivity"], [.2, .6, 2.0])
        self.assertFalse(self.cfg["holder"]["baseMounting"]["poweredOperationPermitted"])
        self.assertFalse(self.cfg["holder"]["baseMounting"]["matingStructureSpecified"])


if __name__ == "__main__":
    unittest.main()
