from copy import deepcopy
import json
from pathlib import Path
import unittest

import numpy as np

from analyze_integrated_walkers import cad_positions, joint_losses as legacy_losses
from m3_a34_analysis import joint_losses
from walker_contact import ContactGait, dimensions


class PerNodeJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.assembly = json.loads((root / "docs/ver3/integrated_r7/A/assembly.json").read_text())
        common = cls.assembly["parameters"]["common"]
        gait = ContactGait(common, dimensions("reference", common), 30)
        cls.theta = gait.angles
        positions, masses, _, _ = cad_positions(cls.assembly, cls.theta)
        cog = np.sum(positions*masses[None, :, None], axis=1)/masses.sum()
        cls.contact = gait.evaluate(float(masses.sum()), cog_xy=cog[:, :2], guide_mode=0)
        cls.positions, cls.masses, _, _ = cad_positions(
            cls.assembly, cls.theta, np.asarray(cls.contact["data"]["spring_compression_mm"]))

    def evaluate(self, assembly, function=joint_losses):
        return function(assembly, self.theta, self.contact, self.positions, self.masses, 1)

    def test_frozen_default_results_are_unchanged(self):
        before = self.evaluate(self.assembly, legacy_losses)
        after = self.evaluate(self.assembly)
        np.testing.assert_allclose(after[0], before[0], rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(after[1], before[1], rtol=1e-12, atol=1e-12)
        self.assertEqual(after[2]["rootPins"], before[2]["rootPins"])

    def test_each_node_uses_its_own_radius_including_c_and_e(self):
        baseline = self.evaluate(self.assembly)[0]
        for node in ("A", "P", "B", "C", "D", "E"):
            with self.subTest(node=node):
                altered = deepcopy(self.assembly)
                journals = altered["parameters"]["common"]["legJournals"]
                journals["perNodeDiameterMm"] = {node: 6}
                six = self.evaluate(altered)[0]
                journals["perNodeDiameterMm"] = {node: 5}
                five = self.evaluate(altered)[0]
                self.assertGreater(float(np.max(six-baseline)), 1e-6)
                np.testing.assert_allclose(five, (baseline+six)/2, rtol=1e-11, atol=1e-11)

    def test_actual_sleeve_bore_changes_root_bending_not_friction(self):
        baseline = self.evaluate(self.assembly)
        altered = deepcopy(self.assembly)
        altered["parameters"]["common"]["legJournals"]["perNodeSleeveBoreMm"] = {"A": 3.2}
        result = self.evaluate(altered)
        np.testing.assert_allclose(result[0], baseline[0], rtol=1e-12, atol=1e-12)
        self.assertGreater(result[2]["rootPins"]["A"]["maximumSleeveBendingMpa"],
                           baseline[2]["rootPins"]["A"]["maximumSleeveBendingMpa"])
        self.assertEqual(result[2]["rootPins"]["P"], baseline[2]["rootPins"]["P"])


if __name__ == "__main__":
    unittest.main()
