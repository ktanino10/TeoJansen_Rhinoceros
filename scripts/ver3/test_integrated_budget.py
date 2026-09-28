"""Budget approval cannot silently alter the reviewed physical design."""

from copy import deepcopy
import unittest

from refresh_integrated_budget import PRICE_KEYS,assert_only_changed,rebind_assembly


class BudgetMetadataTests(unittest.TestCase):
    def setUp(self):
        self.before={"parameters":{"requirements":{"materialBudgetJpy":23000,"budgetApproval":"previous",
                                                  "floor":"level floor","noMachineOperationOrPurchasing":True},
                                   "common":{"springRateNmm":.882}},
                     "instances":[{"name":"guard","transform":[0,0,0]}],
                     "nominalTotalMassG":1065.387580211831}
        self.requirements={**self.before["parameters"]["requirements"],
                           "materialBudgetJpy":24000,"budgetApproval":"approved2026-09-28"}

    def test_only_requirement_budget_changes(self):
        original=deepcopy(self.before)
        after=rebind_assembly(self.before,self.requirements)
        self.assertEqual(self.before,original)
        self.assertEqual(after["instances"],original["instances"])
        self.assertEqual(after["parameters"]["common"],original["parameters"]["common"])
        self.assertEqual(after["nominalTotalMassG"],original["nominalTotalMassG"])
        self.assertEqual(after["parameters"]["requirements"]["materialBudgetJpy"],24000)

    def test_floor_or_operation_scope_cannot_change(self):
        for key,value in (("floor","lowered floor"),("noMachineOperationOrPurchasing",False)):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"non-budget"):
                rebind_assembly(self.before,{**self.requirements,key:value})

    def test_unapproved_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"approved23000-to24000"):
            rebind_assembly(self.before,{**self.requirements,"materialBudgetJpy":25000})

    def test_cost_lot_or_quantity_change_is_not_a_budget_refresh(self):
        old={"targetMaterialCostApproxJpy":23000,"rows":[{"quantity":6}],
             "sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy":23305.13}
        new={**old,"targetMaterialCostApproxJpy":24000}
        assert_only_changed(old,new,PRICE_KEYS)
        for key,value in (("rows",[{"quantity":5}]),
                          ("sourceDisplayedPlusMaterialWithoutUncertainTaxReservesJpy",23000)):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"non-budget"):
                assert_only_changed(old,{**new,key:value},PRICE_KEYS)


if __name__=="__main__":
    unittest.main()
