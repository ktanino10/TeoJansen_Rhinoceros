"""Tests of the single-cartridge dimensional and accounting contract."""

from copy import deepcopy
import unittest

import numpy as np

from cartridge_report import clip_segment
from input_cartridge import cost, load, mechanics, stack_contract


class InputCartridgeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load()

    def test_locating_and_floating_clearance_are_not_preload(self):
        result = stack_contract(self.cfg)
        self.assertAlmostEqual(result["fixed_outer_ring_axial_play_nominal_mm"], .3)
        self.assertAlmostEqual(result["collar_inner_ring_stack_play_nominal_mm"], .2)
        self.assertAlmostEqual(result["floating_outer_ring_total_travel_nominal_mm"], 2)
        self.assertGreaterEqual(min(s["fixed_outer_clearance_min_mm"] for s in result["scenarios"]), .0999999)
        self.assertGreaterEqual(min(s["one_sided_float_remaining_mm"] for s in result["scenarios"]), .0499999)
        self.assertEqual(result["physicalPreloadStatus"], "UNKNOWN")

    def test_clearance_failure_is_not_silently_ignored(self):
        cfg = deepcopy(self.cfg)
        cfg["acceptanceScenarios"]["capCompressionAllowanceMm"] = .5
        with self.assertRaises(ValueError):
            stack_contract(cfg)

    def test_float_must_cover_the_whole_declared_stack(self):
        cfg = deepcopy(self.cfg)
        cfg["layout"]["floatFlangePocketStartMm"] = 98
        with self.assertRaises(ValueError):
            stack_contract(cfg)

    def test_fasteners_engage_nut_and_hub_without_bottoming(self):
        result = stack_contract(self.cfg)
        self.assertAlmostEqual(result["hub_flange_thread_engagement_mm"], 7)
        self.assertAlmostEqual(result["hub_flange_remaining_to_back_face_mm"], 1)
        self.assertGreaterEqual(result["floating_screw_projection_mm"], .7)

    def test_short_cap_screws_rejected(self):
        cfg = deepcopy(self.cfg)
        cfg["layout"]["capsScrewLengthMm"] = 18
        with self.assertRaises(ValueError):
            stack_contract(cfg)

    def test_catalogue_assemblies_and_minimum_lots_not_mixed(self):
        report = cost(self.cfg, 40)
        self.assertAlmostEqual(report["historicalFourSkuMassG"], 59)
        self.assertAlmostEqual(report["purchasedCatalogueMassG"], 85.28)
        self.assertAlmostEqual(report["wholeCartridgeNominalMassG"], 125.28)
        self.assertAlmostEqual(report["purchasedMinimumLotUsd"], 40.70)
        spacer = next(p for p in report["purchasedRows"] if p["id"] == "H_SPACER")
        self.assertEqual(spacer["quantity"], 2)
        self.assertEqual(spacer["purchaseQuantity"], 4)
        self.assertEqual(spacer["unusedPieces"], 2)
        self.assertIsNone(report["measuredMassG"])
        self.assertIsNone(report["shippingJpy"])

    def test_four_original_parts_are_preserved(self):
        original = self.cfg["parts"][:4]
        self.assertAlmostEqual(sum(p["quantity"]*p["massG"] for p in original), 59)
        self.assertEqual([p["sku"] for p in original],
                         ["2101-0006-0120", "1611-0514-0006", "2910-0919-0006", "1309-0016-1006"])
        self.assertTrue(self.cfg["compatibility"]["hubShaftManufacturerSpecified"])
        self.assertIsNone(self.cfg["compatibility"]["numericFitTolerancePublished"])

    def test_coupon_adds_cost_without_becoming_an_assembly_mass(self):
        without = cost(self.cfg, 40)
        with_coupon = cost(self.cfg, 40, 13)
        self.assertEqual(without["wholeCartridgeNominalMassG"], with_coupon["wholeCartridgeNominalMassG"])
        self.assertGreater(with_coupon["jpyScenarios"][0]["materialSubtotalExShippingTaxFeesJpy"],
                           without["jpyScenarios"][0]["materialSubtotalExShippingTaxFeesJpy"])

    def test_beam_uses_actual_support_positions_and_keeps_drag_unknown(self):
        result = mechanics(self.cfg)
        self.assertEqual(result["supports"], [(16.5, "translation"), (96.5, "translation")])
        self.assertLess(result["force_balance_error_n"], 1e-6)
        self.assertLess(result["moment_balance_error_nmm"], 1e-5)
        self.assertEqual(result["two_input_bearing_drag_nmm_sensitivity"], [.2, .6, 2.0])
        self.assertIsNone(result["real_starting_resistance_nmm"])
        self.assertLess(result["torsion"]["lower_rad"], result["torsion"]["upper_rad"])

    def test_section_crop_preserves_the_long_shaft_outline(self):
        clipped = clip_segment(np.array([0., 33.]), np.array([120., 33.]), (86, 14), (106, 42))
        self.assertIsNotNone(clipped)
        np.testing.assert_allclose(clipped, [[86, 33], [106, 33]])
        self.assertIsNone(clip_segment(np.array([0., 50.]), np.array([120., 50.]), (86, 14), (106, 42)))


if __name__ == "__main__":
    unittest.main()
