"""R7-I1 regressions: real ordered inventory is the path obstacle source."""

from collections import Counter
from copy import deepcopy
import json
import unittest

import numpy as np

from build_integrated_contract import assembly_stages,assembly_path_scenarios,validate_path_inventory
from walker_geometry import OUT


def inventories(workflow):
    counts=Counter();result={}
    for stage in workflow:
        result[stage["id"],-1]={name for name,count in counts.items() if count}
        for index,operation in enumerate(stage["orderedOperations"]):
            delta=-1 if operation["operation"]=="remove" else 1
            counts.update({name:delta for name in operation["instances"]})
            if any(value not in (0,1) for value in counts.values()):
                raise AssertionError("Invalid independent stage inventory")
            result[stage["id"],index]={name for name,count in counts.items() if count}
    return result


class AssemblyInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs={name:json.loads((OUT/name/"assembly.json").read_text()) for name in "ABC"}

    def test_every_installed_path_contains_every_nonmoving_installed_part(self):
        for name,data in self.designs.items():
            workflow=assembly_stages(data);states=inventories(workflow)
            paths=assembly_path_scenarios(data,workflow)
            self.assertEqual(len(paths),10)
            for path in paths:
                if path["sceneKind"]!="installed":continue
                state=states[path["workflowStageId"],path["afterOperationIndex"]]
                with self.subTest(design=name,path=path["id"]):
                    self.assertEqual(set(path["fixedNames"]),state-set(path["movingNames"]))
                    self.assertEqual(set(path["sceneInventoryNames"]),state)
            self.assertEqual(len(workflow),12)
            self.assertEqual(set(workflow[-1]["visibleAfter"]),{i["name"] for i in data["instances"]})

    def test_original_b_obstacles_are_present_in_both_corrected_segments(self):
        data=self.designs["B"]
        paths={p["id"]:p for p in assembly_path_scenarios(data)}
        obstacles={"S_GUARD_UPPER_RIGHT_2_001","H_BOLT_M3_20_011","H_BOLT_M3_20_012"}
        for identity in ("front_basket_and_rotor_lower","front_basket_axial_seat"):
            path=paths[identity]
            self.assertTrue(obstacles<=set(path["fixedNames"]))
            self.assertEqual(path["workflowStageId"],"07_lower_rotor")
            self.assertEqual(path["afterOperationIndex"],1)
            self.assertEqual(path["sceneKind"],"installed")

    def test_partially_completed_operations_do_not_prematurely_install_hardware(self):
        for data in self.designs.values():
            items={i["name"]:i for i in data["instances"]}
            paths={p["id"]:p for p in assembly_path_scenarios(data)}
            module=paths["front_basket_and_rotor_lower"]
            self.assertFalse(any(items[n]["part_id"] in ("H_INPUT_COLLAR","H_INPUT_SPACER")
                                 for n in module["sceneInventoryNames"]))
            frame=paths["frame_right_close"]
            self.assertFalse(any(items[n]["group"]=="frame_splice" for n in frame["sceneInventoryNames"]))
            rear=paths["rear_cage_cap_insert"]
            self.assertFalse(any(items[n]["group"]=="guards" and items[n]["part_id"].startswith("H_")
                                 for n in rear["sceneInventoryNames"]))

    def test_bench_scope_is_a_declared_disjoint_preassembly(self):
        for data in self.designs.values():
            workflow=assembly_stages(data);states=inventories(workflow)
            scene=next(p for p in assembly_path_scenarios(data,workflow) if p["id"]=="rotor_into_front_basket")
            prepared=next(s["prepareOnly"] for s in workflow if s["id"]=="06_prepare_rotor")
            self.assertEqual(set(scene["sceneInventoryNames"]),set(prepared))
            self.assertFalse(set(prepared)&states["06_prepare_rotor",0])
            self.assertEqual(scene["sceneOffsetMm"],[300,0,0])

    def test_module_descent_and_seating_are_continuous_without_cad_changes(self):
        for data in self.designs.values():
            paths={p["id"]:p for p in assembly_path_scenarios(data)}
            first=paths["front_basket_and_rotor_lower"];second=paths["front_basket_axial_seat"]
            end=np.array(first["direction"])*first["distancesMm"][-1]+first["constantOffsetMm"]
            start=np.array(second["direction"])*second["distancesMm"][0]+second["constantOffsetMm"]
            np.testing.assert_array_equal(end,[4,0,0])
            np.testing.assert_array_equal(start,end)
            np.testing.assert_array_equal(np.array(second["direction"])*second["distancesMm"][-1]+second["constantOffsetMm"],[0,0,0])
            self.assertEqual(first["movingNames"],second["movingNames"])
            self.assertEqual(first["fixedNames"],second["fixedNames"])

    def test_omitted_installed_obstacle_invalidates_a_claimed_pass(self):
        data=self.designs["B"]
        results={"stages":[{**p,"status":"PASS"} for p in assembly_path_scenarios(data)]}
        validate_path_inventory(data,results)
        wrong=deepcopy(results)
        path=next(p for p in wrong["stages"] if p["id"]=="front_basket_and_rotor_lower")
        path["fixedNames"].remove("S_GUARD_UPPER_RIGHT_2_001")
        with self.assertRaisesRegex(ValueError,"fixedNames"):
            validate_path_inventory(data,wrong)

    def test_manual_exclusion_and_discontinuous_segments_are_rejected(self):
        data=self.designs["B"];workflow=assembly_stages(data)
        stage=next(s for s in workflow if s["id"]=="07_lower_rotor")
        stage["pathChecks"][0]["fixedNames"]=[]
        with self.assertRaisesRegex(ValueError,"cannot filter"):
            assembly_path_scenarios(data,workflow)
        workflow=assembly_stages(data)
        stage=next(s for s in workflow if s["id"]=="07_lower_rotor")
        stage["pathChecks"][1]["constantOffsetMm"]=[0,0,1]
        with self.assertRaisesRegex(ValueError,"Discontinuous"):
            assembly_path_scenarios(data,workflow)


if __name__=="__main__":
    unittest.main()
