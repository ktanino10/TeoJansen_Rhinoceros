"""Check new design-basis assumptions and the bounded kinematic/torque changes."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from commercial_r3 import (INPUT, LENGTH_KEYS, RedesignedGait, fast_gait_metrics,
                           linkage_drawing, points_many, rod_startup, tolerance_screen, torque_decomposition)
from core import CONFIG, gait


class CommercialBasisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(INPUT.read_text())
        old_cfg = json.loads(INPUT.with_name("study_r2.json").read_text())
        cls.common = old_cfg["common"]
        cls.original = {k: CONFIG["linkage"][k] for k in LENGTH_KEYS}
        cls.rounded = {**cls.original, "QP": 26.9/0.7, "OQ": 7.4/0.7,
                       "DE": 30.2/0.7, "CF": 37.1/0.7, "EF": 43.3/0.7}
        cls.design = {**old_cfg["candidates"][0], **cls.cfg["candidates"][0]}

    def test_local_published_velocity_is_not_a_measured_gaussian_peak(self):
        reference = self.cfg["referenceData"]["publishedColdExperiment"]
        self.assertIsNone(reference["dryerModel"])
        self.assertIn("does not establish", reference["velocityInterpretation"])
        self.assertFalse(self.cfg["modelAssumptions"]["measuredGuarantee"])
        self.assertIsNone(self.cfg["modelAssumptions"]["availableTorqueLowerBoundNm"])
        self.assertFalse(self.cfg["requirements"]["requiresUserMeasurementBeforeDesign"])

    def test_vector_linkage_matches_old_geometry(self):
        theta = np.array([0, 0.2, 1.9, 3.2, 5.7])
        many, margin = points_many(theta, self.original, 0.7)
        self.assertGreater(margin, 0)
        for index, angle in enumerate(theta):
            old = gait(angle)
            for name in many:
                np.testing.assert_allclose(many[name][index], old[name]*0.5, atol=1e-12)

    def test_rounded_geometry_improves_without_erasing_clearance_cost(self):
        old = fast_gait_metrics(self.original, self.common, 1440)
        new = fast_gait_metrics(self.rounded, self.common, 1440)
        self.assertLess(new["body_bounce_mm"], old["body_bounce_mm"]/2)
        self.assertLess(new["peak_stance_vertical_rate_mm_per_rad"], old["peak_stance_vertical_rate_mm_per_rad"]/2)
        self.assertGreater(new["swing_gap_max_mm"], 8)
        self.assertLess(new["swing_gap_max_mm"], old["swing_gap_max_mm"])
        self.assertEqual(new["stance_switch_count"], 2)
        self.assertGreater(new["minimum_forward_rate_mm_per_rad"], 0)

    def test_exact_closed_linkage_and_same_real_phase_map(self):
        study = RedesignedGait(self.common, self.rounded, step_deg=10)
        summary = study.summary()
        self.assertLess(summary["closure_residual_mm"], 1e-6)
        self.assertEqual([l["phase_deg"] for l in study.legs], [0, 180, 180, 0, 0, 180])
        self.assertEqual(summary["physical_continuous_walk_status"], "UNKNOWN")

    def test_torque_loss_decomposition_uses_one_case_and_one_peak(self):
        study = RedesignedGait(self.common, self.rounded, step_deg=10)
        profile, forces, required, meta = rod_startup(study, self.design, self.common, 1, 0.04, 0.015)
        result = torque_decomposition(profile, required, self.design, self.common, 1, meta)
        self.assertLess(forces["virtual_work_residual_nmm"], 1e-4)
        self.assertAlmostEqual(result["input_two_bearing_loss_nm"], 0.0006)
        total = result["total_required_input_nm"]
        self.assertAlmostEqual(total, float(required.max()))
        self.assertAlmostEqual(result["gross_aerodynamic_target_nm"], 2*total-0.0006)
        self.assertAlmostEqual(result["net_output_target_nm"], 2*(total-0.0006))

    def test_zero_bearing_drag_is_not_a_stored_production_assumption(self):
        self.assertEqual(self.common["bearingDragNmmCases"], [0.1, 0.3, 1.0])
        self.assertEqual(self.common["journalFrictionCases"], [0.05, 0.10, 0.18])
        self.assertEqual(self.common["meshEfficiencyCases"], [0.95, 0.9, 0.8])

    def test_spacer_exceeds_exact_shielded_shoulder_limit(self):
        interface = self.cfg["bearingInterfaceUpdate"]
        self.assertGreater(interface["candidateSpacerRetail"]["dimensionsMm"][1],
                           interface["shieldedShaftShoulderMaximumMm"])
        self.assertIn("not proven identical", interface["retailerDesignation"])
        self.assertEqual(interface["qualification"], "UNKNOWN")

    def test_nonclosing_geometry_is_rejected(self):
        impossible = {**self.original, "AB": 1}
        with self.assertRaises(ValueError):
            points_many(np.array([0, 1]), impossible, 0.7)

    def test_adverse_print_tolerance_is_retained_not_filtered(self):
        result = tolerance_screen(self.rounded, self.common, self.cfg)
        self.assertEqual(len(result["cases"]), 10)
        self.assertLess(result["minimum_swing_gap_mm"], 8)
        self.assertGreater(result["maximum_handoff_rate_jump_mm_per_rad"], 6)
        self.assertEqual(result["all_combined_errors_status"], "UNKNOWN")

    def test_reference_626_fallback_is_not_silently_used(self):
        fallback = self.cfg["documentedSupportFallback"]
        self.assertTrue(fallback["notAppliedToBaseline"])
        self.assertEqual(fallback["bearing"]["retailerExactSku"], "626ZZ")
        self.assertEqual(fallback["collar"]["bossDiameterMm"], 9.2)
        self.assertEqual(fallback["physicalOrProcurementQualification"], "UNKNOWN")

    def test_linkage_drawing_keeps_geometry_out_of_heading(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/"linkage.svg"
            linkage_drawing(output, self.rounded, self.common, self.cfg)
            self.assertIn('height="920"', output.read_text())


if __name__ == "__main__":
    unittest.main()
