"""Analytic/unit checks for the bounded study, not physical validation."""

import json
import math
from pathlib import Path
import unittest

import numpy as np

from beam import circle_section, d_section, rectangle_section, solve_beam, twist_bound
from study_r2 import GaitStudy, INPUT, coupled_startup, gear_check, phase_map, reflect_loads, rotor_mass_proxy, static_jet_proxy


class BeamTests(unittest.TestCase):
    def setUp(self):
        self.section = circle_section(6)
        self.length = 100.0
        self.modulus = 200000.0
        self.ei = self.modulus*self.section.inertia_min

    def test_simply_supported_center_load(self):
        force = -10
        result = solve_beam(self.length, self.modulus, self.section, [(50, force)],
                            [(0, "translation"), (100, "translation")], elements=10)
        self.assertAlmostEqual(result["max_deflection_mm"], abs(force)*100**3/(48*self.ei), places=10)
        self.assertAlmostEqual(result["max_rotation_rad"], abs(force)*100**2/(16*self.ei), places=10)
        self.assertLess(result["force_balance_error_n"], 1e-8)
        self.assertLess(result["moment_balance_error_nmm"], 1e-7)

    def test_cantilever_tip_load(self):
        force = -10
        result = solve_beam(100, self.modulus, self.section, [(100, force)],
                            [(0, "translation"), (0, "rotation")], elements=10)
        self.assertAlmostEqual(result["max_deflection_mm"], abs(force)*100**3/(3*self.ei), places=9)
        self.assertAlmostEqual(result["max_rotation_rad"], abs(force)*100**2/(2*self.ei), places=9)
        self.assertLess(result["moment_balance_error_nmm"], 1e-6)

    def test_uniform_load_and_refinement(self):
        expected = 5*0.1*100**4/(384*self.ei)
        for count in (2, 8, 24):
            result = solve_beam(100, self.modulus, self.section, [],
                                [(0, "translation"), (100, "translation")],
                                distributed_load=-0.1, elements=count)
            self.assertAlmostEqual(result["max_deflection_mm"], expected, places=9)
            expected_stress = 0.1*100**2/8*self.section.extreme_fiber/self.section.inertia_min
            self.assertAlmostEqual(result["max_bending_stress_mpa"], expected_stress, places=8)

    def test_invalid_model_is_not_a_success_fallback(self):
        with self.assertRaises(ValueError):
            solve_beam(100, self.modulus, self.section, [(101, 1)], [])
        with self.assertRaises(ValueError):
            solve_beam(100, self.modulus, self.section, [(50, 1)], [])

    def test_section_and_torsional_bounds(self):
        d = d_section(6, 0.5)
        outer = circle_section(6)
        self.assertLess(d.area, outer.area)
        self.assertLess(d.inertia_min, outer.inertia_min)
        self.assertLess(d.torsion_lower, d.torsion_upper)
        result = twist_bound(100, 100, 74000, d)
        self.assertGreater(result["upper_rad"], result["lower_rad"])
        self.assertIsNone(result["peak_shear_stress_mpa"])
        rectangle = rectangle_section(8, 3)
        self.assertLess(rectangle.torsion_upper, 8*3*(8**2+3**2)/12)


class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(INPUT.read_text())
        cls.common = cls.cfg["common"]

    def test_phase_path_and_exact_centers(self):
        legs = phase_map(self.common)
        self.assertEqual([leg["phase_deg"] for leg in legs], [0, 180, 180, 0, 0, 180])
        for candidate in self.cfg["candidates"]:
            checked = gear_check(candidate, self.common)
            self.assertEqual(checked["total_reduction"], math.prod(candidate["stageRatios"]))

    def test_linkage_closure_and_contact_not_overclaimed(self):
        study = GaitStudy(self.common, step_deg=5)
        result = study.summary()
        self.assertLess(result["closure_residual_mm"], 1e-6)
        self.assertGreater(result["target_cog_minimum_normal_fraction"], 0)
        self.assertEqual(result["physical_continuous_walk_status"], "UNKNOWN")
        self.assertIsNone(result["finite_sole_contact_audit_mm"])
        self.assertEqual(len(result["handoff_velocity_discontinuities"]), 2)
        self.assertGreater(result["advance_per_cycle_quadrature_mm"], 0)
        self.assertGreater(result["minimum_forward_rate_mm_per_rad"], 0)

    def test_reactions_and_virtual_work(self):
        study = GaitStudy(self.common, step_deg=10)
        profile, loads = study.torque_profile(0.55, 0.1, 0.015, opposing_wind_n=0.05)
        self.assertLess(loads["equilibrium_residual"], 1e-8)
        self.assertLess(loads["virtual_work_residual_nmm"], 1e-4)
        self.assertTrue(np.isfinite(profile).all())
        reflected, meta = reflect_loads(profile, self.cfg["candidates"][0], 0.9, 0.3)
        self.assertTrue(np.all(reflected >= meta["input_equivalent_bearing_drag_nm"]))
        self.assertEqual(meta["bearing_count"], 14)

    def test_resistance_opposes_actual_travel_not_assumed_axis(self):
        study = GaitStudy(self.common, step_deg=10)
        unloaded, _ = study.torque_profile(0.55, 0.1, 0.0)
        resisted, _ = study.torque_profile(0.55, 0.1, 0.03, opposing_wind_n=0.05)
        self.assertTrue(np.all(resisted[:, 1] >= unloaded[:, 1]))
        self.assertGreater((resisted[:, 1]-unloaded[:, 1]).min(), 0)

    def test_wind_moment_changes_normal_distribution(self):
        study = GaitStudy(self.common, step_deg=10)
        no_wind = study.pose(0.2, 0.55)
        wind = study.pose(0.2, 0.55, wind_y_n=0.1, wind_down_n=0.02,
                          wind_application_yz=(-50, 75))
        self.assertFalse(np.allclose(no_wind[3], wind[3]))
        self.assertAlmostEqual(float(wind[3].sum()), 1)
        _, loads = study.torque_profile(0.55, 0.1, 0.015, opposing_wind_n=0.1,
                                        wind_down_n=0.02, wind_application_yz=(-50, 75))
        self.assertLess(loads["virtual_work_residual_nmm"], 1e-4)

    def test_required_drive_couple_closes_support_balance(self):
        study = GaitStudy(self.common, step_deg=10)
        candidate = self.cfg["candidates"][1]
        profile, _, required, meta = coupled_startup(study, candidate, 1, self.common, 0.05, 0.01)
        self.assertLess(meta["support_drive_couple_residual_nm"], 1e-10)
        self.assertGreater(meta["support_drive_couple_iterations"], 1)
        check, _ = study.torque_profile(
            candidate["massCasesKg"][1], self.common["journalFrictionCases"][1],
            self.common["horizontalResistanceCases"][1], opposing_wind_n=0.05, wind_down_n=0.01,
            wind_application_yz=candidate["axisCentersYzMm"]["I"], input_couples_nmm=-required*1000)
        np.testing.assert_allclose(profile, check, rtol=1e-6, atol=1e-6)

    def test_hybrid_journals_match_supplier_bores(self):
        self.assertEqual(self.common["jointRadiiMm"]["A"], 3)
        self.assertEqual(self.common["jointRadiiMm"]["P"], 3)
        self.assertEqual(self.common["jointRadiiMm"]["B"], 2)
        self.assertLess(self.common["fixedPivotDiameterMm"], 3)
        sleeves = next(i for i in self.cfg["procurement"]["domesticOptions"]
                       if i["id"] == "H_SLEEVE_HYBRID_DOMESTIC")
        self.assertEqual(sum(sleeves["requiredQuantitiesBeforeFinalCAD"]), 36)
        self.assertEqual(round(sum(sleeves["unitPricesJpyExTax"])*50*1.1),
                         sleeves["threeMinimumLotsJpyTaxIncluded"])

    def test_static_proxy_energy_ceiling_and_velocity_scaling(self):
        options = (30, 48, self.common, self.cfg["fluidCases"], 12, 0, -0.75)
        slow = static_jet_proxy(*options, 4, 20, step_deg=10, rays=128)
        fast = static_jet_proxy(*options, 8, 20, step_deg=10, rays=128)
        first, second = np.array(slow["rows"]), np.array(fast["rows"])
        np.testing.assert_allclose(second[:, 1:5], 4*first[:, 1:5], rtol=1e-10, atol=1e-12)
        self.assertAlmostEqual(fast["whole_jet_kinetic_power_w"], 8*slow["whole_jet_kinetic_power_w"])
        self.assertLess(second[:, 1].max(), fast["ideal_intercepted_momentum_torque_ceiling_nm"])
        self.assertIsNone(fast["measured_supply_lower_bound_nm"])
        self.assertEqual(fast["actual_self_start_status"], "UNKNOWN")

    def test_centered_straight_vanes_have_zero_signed_torque(self):
        result = static_jet_proxy(45, 48, self.common, self.cfg["fluidCases"],
                                  12, 0, 0, 8, 20, step_deg=10, rays=256)
        self.assertLess(np.max(np.abs(np.array(result["rows"])[:, 1])), 1e-10)

    def test_rotor_mass_inertia_units_and_reflection(self):
        candidate = self.cfg["candidates"][0]
        result = rotor_mass_proxy(candidate, self.common, {"blades": 16, "sweep_deg": 20})
        inertia = result["polar_mass_inertia_about_rotor_axis_kg_m2_proxy"]
        mass = result["mass_kg_proxy"]
        radius_m = candidate["rotorDiameterMm"]/2000
        self.assertGreater(inertia, 0)
        self.assertLess(inertia, mass*(radius_m+0.001)**2)
        self.assertAlmostEqual(result["rotor_inertia_reflected_to_crank_kg_m2_proxy"],
                               inertia*math.prod(candidate["stageRatios"])**2)
        self.assertIsNone(result["angular_acceleration_rad_s2"])

    def test_invalid_flow_and_mass_inputs_stop_explicitly(self):
        with self.assertRaises(ValueError):
            static_jet_proxy(30, 48, self.common, self.cfg["fluidCases"], 12, 0, -0.5, 8, 0)
        with self.assertRaises(ValueError):
            GaitStudy(self.common, step_deg=0)
        with self.assertRaises(ValueError):
            GaitStudy(self.common, step_deg=10).pose(0, 0)


if __name__ == "__main__":
    unittest.main()
