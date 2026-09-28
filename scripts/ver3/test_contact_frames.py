"""Export-only controls; these do not replace or independently re-solve contact."""

from copy import deepcopy
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from analyze_integrated_walkers import analyze, contact_frames
from walker_geometry import OUT


class ContactFrameTests(unittest.TestCase):
    def setUp(self):
        self.assembly=json.loads((OUT/"A/assembly.json").read_text())
        self.gait=SimpleNamespace(lanes=1,step_deg=90,
            legs=[(station,side,phase) for station,pair in zip((-84,0,84),((0,180),(180,0),(0,180)))
                  for side,phase in zip((-1,1),pair)],
            neutral=lambda:(None,np.full((4,6),.1)))
        velocity=np.array([[0,1,.001],[.1,2,.002],[.2,3,.003],[.3,4,.004]])
        total=velocity.sum(axis=0)*math.pi/2
        self.contact={
            "mass_kg":1,"minimum_loaded_feet":3,
            "lateral_per_cycle_mm":total[0],"advance_per_cycle_mm":total[1],"yaw_per_cycle_rad":total[2],
            "tangential_force_moment_residual_normalized_max":1e-9,
            "data":{"theta_rad":np.deg2rad([0,90,180,270]).tolist(),
                    "body_z_slopex_slopey":[[100+i,.01,.02] for i in range(4)],
                    "normal_n":[[5,5,5,0,0,0]]*4,"toes_body_mm":np.zeros((4,6,3)).tolist(),
                    "spring_compression_mm":[[0,1,2,3,4,5]]*4,
                    "body_velocity_mm_per_rad":velocity.tolist(),
                    "toe_slip_velocity_mm_per_rad":np.zeros((4,6,2)).tolist()}}
        self.result={"designId":"A","mechanicalInputSha256":"a"*64,"analysisSourcesSha256":{},
                     "actualCogContactIterations":2,"actualCogContactResidualMm":1e-7,
                     "kinematicTravel":{"advancePerCrankCycleMm":abs(total[1])}}

    def export(self,contact=None,result=None):
        with patch("build_integrated_contract.source_identity",return_value=([],[],"b"*64)):
            return contact_frames(self.assembly,self.gait,contact or self.contact,result or self.result,
                                  "c"*40,frame_step_deg=90)

    def test_dense_integration_and_periodic_closure_are_explicit(self):
        data=self.export()
        self.assertEqual(data["frameCount"],5)
        self.assertEqual(data["rawPhaseCount"],4)
        np.testing.assert_allclose(data["frames"][1]["integratedPlanarComponents"],
                                   np.array([0,1,.001])*math.pi/2)
        self.assertTrue(data["frames"][-1]["periodicClosure"])
        self.assertEqual(data["frames"][-1]["sourcePhaseIndex"],0)
        self.assertEqual(data["frames"][-1]["bodyHeightAndSlopes"],data["frames"][0]["bodyHeightAndSlopes"])
        self.assertEqual(data["frames"][-1]["integratedPlanarComponents"],
                         data["denseCycleSummary"]["integratedPlanarComponents"])
        self.assertTrue(all(f["independentRockerAngleRad"] is None for f in data["frames"]))
        self.assertEqual(data["frames"][0]["loadedFoot"],[True,True,True,False,False,False])

    def test_nonfinite_state_is_rejected_not_filled(self):
        wrong=deepcopy(self.contact)
        wrong["data"]["spring_compression_mm"][2][1]=float("nan")
        with self.assertRaisesRegex(ValueError,"nonfinite"):
            self.export(contact=wrong)

    def test_unconverged_or_nonfinite_residual_is_rejected(self):
        for value in (1e-3,float("nan")):
            wrong={**self.result,"actualCogContactResidualMm":value}
            with self.assertRaisesRegex(ValueError,"Unconverged"):
                self.export(result=wrong)

    def test_summary_disagreement_is_rejected(self):
        wrong={**self.contact,"advance_per_cycle_mm":1000}
        with self.assertRaisesRegex(ValueError,"disagrees"):
            self.export(contact=wrong)

    def test_export_cannot_overwrite_the_frozen_analysis_directory(self):
        with self.assertRaisesRegex(ValueError,"separate analysis output"):
            analyze("A",motion_output=OUT/"A/contact_frames.json",source_commit="c"*40)


if __name__=="__main__":
    unittest.main()
