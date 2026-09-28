"""Floor geometry, continuous rocker envelopes and fail-closed inventory controls."""

from copy import deepcopy
import json
import math
import unittest

import numpy as np

from walker_floor import check,identity,minimum_cloud,rocker_minimum,radial_lower_bound
from walker_geometry import OUT


class FloorTests(unittest.TestCase):
    def test_published_c_and_b_floor_conflicts_remain_failure_controls(self):
        baseline=json.loads((OUT/"review/floor_conflict_baseline.json").read_text())
        failures=[]
        for row in baseline["bodyFixedControls"]:
            h,sx,sy=row["bodyHeightAndSlopes"]
            z=minimum_cloud([row["nativeVertexMm"]],[],np.array([[sx,sy,1]]))[0]
            z+=h-row["cadReferenceBodyOriginZMm"]
            self.assertAlmostEqual(z,row["minimumSourceWorldZMm"],places=9)
            if z<0:failures.append((row["design"],row["crankDeg"]))
        self.assertEqual(failures,[("B",120),("C",0),("C",120),("C",240)])
        gear=baseline["rotatingOutputControl"]
        bound=radial_lower_bound(np.array([gear["bodyHeightAndSlopes"]]),gear["axisYzMm"],
                                 gear["toothFaceXRangeMm"],gear["tipRadiusMm"])[0]
        self.assertLess(bound,-1.24)
        self.assertLessEqual(bound,gear["sourceMeshSampleMinimumZMm"]+1e-6)

    def test_full_circle_bound_uses_tilted_plane_not_three_vertices(self):
        n=np.array([[0,.02,1],[.01,-.03,1]])
        circles=[{"center":[0,0,10],"axis":[1,0,0],"radius":3}]
        actual=minimum_cloud([[0,0,10]],circles,n)
        np.testing.assert_allclose(actual,10-3*np.sqrt(1+n[:,1]**2))

    def test_continuous_rocker_bound_contains_dense_angles(self):
        points=np.array([[12,0,-2],[-12,0,-2],[0,1.9,-5]])
        n=np.array([[.01,.03,1],[-.04,.02,1]])
        angle=math.radians(5)
        bound=rocker_minimum(points,n,np.array([0,1,0]),angle)
        sampled=[]
        for a in np.linspace(-angle,angle,1001):
            c,s=math.cos(a),math.sin(a)
            r=np.array([[c,0,s],[0,1,0],[-s,0,c]])
            sampled.append(np.min(n@(points@r.T).T,axis=1))
        self.assertTrue(np.all(bound<=np.min(sampled,axis=0)+1e-12))
        np.testing.assert_allclose(bound,np.min(sampled,axis=0),atol=1e-6)

    def test_missing_part_or_rotating_instance_is_rejected_before_screening(self):
        a=json.loads((OUT/"A/assembly.json").read_text())
        envelope={"mechanicalIdentity":identity(a),"parts":{},"rotatingInstances":{}}
        with self.assertRaisesRegex(ValueError,"inventory"):
            check(a,envelope,{})
        envelope["parts"]={pid:{} for pid in a["parts"]}
        with self.assertRaisesRegex(ValueError,"Rotating.*inventory"):
            check(a,envelope,{})

    def test_any_assembly_change_invalidates_native_envelopes(self):
        a=json.loads((OUT/"A/assembly.json").read_text());wrong=deepcopy(a)
        wrong["instances"][0]["transform"][2][3]+=.1
        with self.assertRaisesRegex(ValueError,"do not match"):
            check(wrong,{"mechanicalIdentity":identity(a)},{})


if __name__=="__main__":
    unittest.main()
