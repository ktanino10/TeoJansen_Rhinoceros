"""Small checks of the integrated mechanism contract; not a walking test."""

import math
import unittest
from copy import deepcopy

import numpy as np

from walker_contact import ContactGait, dimensions, foot_total_rate, load,functional_swing_budget
from walker_geometry import gear_pair_metrics, involute_outline, reducer
from analyze_integrated_walkers import shaft_gravity_work,reflect_shaft_work,station_circulation
from walker_kinematics import points_many as continuous_points
from walker_contact import error_cases


class WholeWalkerMathTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load()

    def test_each_real_external_mesh_keeps_its_phase_relation(self):
        expected={"A":144,"B":-512,"C":156}
        for candidate in self.cfg["candidates"]:
            train=reducer(candidate,self.cfg["common"])
            self.assertEqual(train["speedRatios"][0],expected[candidate["id"]])
            for stage in train["stages"]:
                for crank in (0,.3,1.7,2*math.pi):
                    change=(stage["pinion"]*stage["pinionSpeedPerCrank"]
                            +stage["wheel"]*stage["wheelSpeedPerCrank"])*crank
                    self.assertAlmostEqual(change,0,places=11)
                distance=np.linalg.norm(np.array(train["axesYzMm"][stage["wheelAxis"]])
                                        -train["axesYzMm"][stage["pinionAxis"]])
                self.assertAlmostEqual(distance,stage["centreMm"],places=11)

    def test_pressure_angle_reaches_all_pinion_wheel_pairs(self):
        for candidate in self.cfg["candidates"]:
            for stage in reducer(candidate,self.cfg["common"])["stages"]:
                pressure=stage["pressureAngleDeg"]
                pair=gear_pair_metrics(stage["moduleMm"],stage["pinion"],stage["wheel"],pressure,.3,stage["pinionProfileShift"])
                self.assertTrue(pair["noStandardRackUndercut"])
                self.assertGreater(pair["contactRatio"],1.3)
                self.assertGreater(pair["minimumTipThicknessMm"],.5)
                self.assertAlmostEqual(pair["radialForcePerTangential"],math.tan(math.radians(pressure)))

    def test_hex_stock_has_a_real_round_journal_not_a_false_diameter_match(self):
        c=self.cfg["common"];s=self.cfg["sources"]["bearing"]
        maximum_corner_diameter=c["hexPrintedBoreAcrossFlatsMm"]/math.cos(math.pi/6)
        self.assertGreater((c["bearingJournalDiameterMm"]-maximum_corner_diameter)/2,1)
        self.assertLess(c["bearingJournalShoulderDiameterMm"],s["innerShoulderDiameterMm"])
        self.assertGreater(14.6,s["outerShoulderDiameterMm"])

    def test_sampled_involute_mates_do_not_interpenetrate(self):
        from shapely.geometry import Polygon
        pairs=[(1,p,w,25,0) for p,w in ((12,120),(12,144),(12,156),(14,112),(18,144),(42,42))]
        pairs.append((.9,12,156,20,.35))
        for module,pinion,wheel,pressure,shift in pairs:
            p=involute_outline(module,pinion,pressure,profile_shift=shift)
            w=involute_outline(module,wheel,pressure,profile_shift=-shift)
            self.assertTrue(Polygon(p).is_valid);self.assertTrue(Polygon(w).is_valid)
            for angle in np.linspace(0,2*math.pi/pinion,33):
                other=math.pi+math.pi/wheel-angle*pinion/wheel
                def rotate(points,a):
                    return points@np.array([[math.cos(a),math.sin(a)],[-math.sin(a),math.cos(a)]])
                a=Polygon(rotate(p,angle))
                b=Polygon(rotate(w,other)+[module*(pinion+wheel)/2,0])
                self.assertLess(a.intersection(b).area,1e-8)

    def test_c_pair_preserves_contact_target_and_clears_the_nonmating_carrier(self):
        candidate=next(c for c in self.cfg["candidates"] if c["id"]=="C")
        train=reducer(candidate,self.cfg["common"]);first,last=train["stages"]
        radius=first["moduleMm"]*(first["wheel"]/2+first["wheelProfileShift"]+first["wheelAddendumCoefficient"])
        self.assertGreater(last["centreMm"]-radius-4,3)
        self.assertGreater(first["moduleMm"]*(first["pinion"]/2-1.25+first["pinionProfileShift"]),4)
        self.assertLess(gear_pair_metrics(.9,12,156,25)["contactRatio"],1.3)

    def test_catalogued_coil_rate_is_not_a_print_modulus(self):
        foot=self.cfg["common"]["foot"]
        self.assertAlmostEqual(foot_total_rate(foot),.882*foot["springCountPerFoot"])
        self.assertAlmostEqual(foot_total_rate(foot,.1),.9702*foot["springCountPerFoot"])
        self.assertLess(foot["workingCompressionLimitMm"],foot["springRatedTravelMm"])
        self.assertLess(foot["workingCompressionLimitMm"]*foot["springRateNmm"],foot["springRatedMaxLoadN"])

    def test_normal_spring_equilibrium_has_the_analytical_flat_case(self):
        gait=ContactGait(self.cfg["common"],dimensions("reference"),10)
        feet=np.array([[x,y,-50] for y in (-70,0,70) for x in (-61,61)],float)
        body,forces,toes,compression,_=gait.normal_equilibrium(
            feet,np.zeros(6),6,[0,0],np.full(6,.882),np.zeros(6))
        np.testing.assert_allclose(forces,np.ones(6),atol=1e-8)
        self.assertAlmostEqual(body[0],56-1/.882,places=8)
        np.testing.assert_allclose(body[1:],0,atol=1e-10)
        np.testing.assert_allclose(compression,1/.882,atol=1e-8)
        np.testing.assert_allclose(toes[:,2]+body[0],6,atol=1e-8)
        actual_air_gap=-40+body[0]-6
        self.assertAlmostEqual(actual_air_gap,10-1/.882,places=8)
        self.assertAlmostEqual(functional_swing_budget(self.cfg["common"]),.9)

    def test_loaded_self_locking_envelope_is_an_explicit_failure(self):
        gait=ContactGait(self.cfg["common"],dimensions("reference"),10)
        feet=np.array([[x,y,-50] for y in (-70,0,70) for x in (-61,61)],float)
        with self.assertRaisesRegex(ValueError,"self-locking"):
            gait.normal_equilibrium(feet,np.full(6,math.radians(70)),6,[0,0],
                                    np.full(6,.882),np.zeros(6),guide_mode=-1)

    def test_balanced_hardware_has_no_fictitious_mesh_loss(self):
        theta=np.linspace(0,2*math.pi,721);zero=np.zeros_like(theta)
        axes=[[0,20],[0,0]]
        fast=[{"massKg":.002,"speed":-8,"axisYzMm":axes[0],"offsetYzMm":offset}
              for offset in ((8,8),(-8,8),(8,-8),(-8,-8))]
        gravity=shaft_gravity_work(fast,axes,theta,zero,zero)
        for eta in (.8,.9,1):
            required,loss=reflect_shaft_work(zero,gravity,[-8,1],eta,0)
            np.testing.assert_allclose(required,0,atol=1e-12)
            np.testing.assert_allclose(loss,0,atol=1e-12)

    def test_input_gravity_is_upstream_of_every_mesh(self):
        theta=np.linspace(0,2*math.pi,721);zero=np.zeros_like(theta)
        axes=[[0,30],[0,15],[0,0]]
        fast=[{"massKg":.003,"speed":64,"axisYzMm":axes[0],"offsetYzMm":[4,0]}]
        gravity=shaft_gravity_work(fast,axes,theta,zero,zero)
        expected=.003*9.80665*4*np.cos(64*theta)
        for eta in (.8,.9,1):
            required,_=reflect_shaft_work(zero,gravity,[64,-8,1],eta,0)
            np.testing.assert_allclose(required,expected,atol=1e-12)

    def test_each_real_mesh_transforms_net_power_once(self):
        zero=np.zeros((3,2))
        required,loss=reflect_shaft_work(np.array([100.,-100.]),zero,[64,-8,1],.9,0)
        np.testing.assert_allclose(required,[100/(64*.9**2),-100*.9**2/64])
        self.assertTrue(np.all(loss>=0))
        required,_=reflect_shaft_work(np.zeros(2),zero,[64,-8,1],.9,.3)
        np.testing.assert_allclose(required,2*.3+2*.3/(8*.9))

    def test_opposed_legs_cancel_only_on_their_real_shaft(self):
        values=np.array([[5.,-5.]])
        np.testing.assert_array_equal(station_circulation(values,[(0,-1,0),(0,1,math.pi)]),[0])
        np.testing.assert_array_equal(station_circulation(values,[(-70,-1,0),(70,1,math.pi)]),[10])

    def test_planar_wind_is_balanced_by_the_actual_coulomb_forces(self):
        c=self.cfg["common"];gait=ContactGait(c,dimensions("reference"),10)
        force=np.array([0,.126,3.528])
        result=gait.evaluate(.9,external_planar_load=force)
        self.assertLess(result["tangential_force_moment_residual_normalized_max"],1e-7)
        normals=np.array(result["data"]["normal_n"])
        slips=np.array(result["data"]["toe_slip_velocity_mm_per_rad"])
        friction=-c["foot"]["groundFrictionCoefficientAssumed"]*normals[:,:,None]*slips/np.sqrt(np.sum(slips**2,axis=2)+.01**2)[:,:,None]
        np.testing.assert_allclose(friction.sum(axis=1),np.broadcast_to(-force[:2],(len(normals),2)),atol=1e-7)
        with self.assertRaisesRegex(ValueError,"friction envelope"):
            gait.evaluate(.1,external_planar_load=(1,0,0))

    def test_continuous_assembly_branches_preserve_legacy_nominal_geometry(self):
        from commercial_r3 import points_many as old_points
        theta=np.arange(720)*math.pi/360
        first,_=old_points(theta,dimensions("reference"),.65)
        second,_=continuous_points(theta,dimensions("reference"),.65)
        for key in first:np.testing.assert_allclose(first[key],second[key],atol=1e-10)

    def test_repaired_pc_pitch_survives_the_declared_effective_length_cases(self):
        c=self.cfg["common"];theta=np.arange(720)*math.pi/360
        for case in error_cases(c):
            for perturbation in case["errors"].get("lengths",[{}]):
                lengths=dimensions("reference",c)
                for key,delta in perturbation.items():lengths[key]+=delta/c["linkScale"]
                points,margin=continuous_points(theta,lengths,c["linkScale"])
                self.assertGreater(margin,0)
                for key in ("B","C","D","E","F"):
                    increments=np.linalg.norm(np.roll(points[key],-1,axis=0)-points[key],axis=1)
                    self.assertLess(increments.max(),2)
        nominal,_=continuous_points(np.array(0.),dimensions("reference",c),c["linkScale"])
        self.assertAlmostEqual(np.linalg.norm(nominal["C"]-nominal["P"]),26.5,places=9)

    def test_polygon_section_and_rotated_loadpoint_work(self):
        from analyze_integrated_structure import regular_section,tower_side
        section=regular_section(8)
        self.assertAlmostEqual(section["areaMm2"]/(math.pi*16),.9744953584,places=9)
        head=[0,0,20]
        members=[{"aMm":[0,y,0],"bMm":head,"circumDiameterMm":8,"sectionSides":16} for y in (-10,10)]
        for force in np.eye(3):
            result=tower_side(members,head,force,[-1.5,0,0],800)
            self.assertLess(abs(result["virtualWorkErrorNmm"]),1e-12)

    def test_guard_edge_retains_the_full_right_steel_washer(self):
        c=self.cfg["common"]
        self.assertGreaterEqual(c["guards"]["sideSheetBoundsYmm"][1]-(c["stationPitchMm"]+19+5.75),.5)

    def test_static_air_force_scales_with_dynamic_pressure(self):
        from walker_air import static_supply
        candidate=self.cfg["candidates"][0]
        a={"candidate":candidate,"parameters":self.cfg,"reduction":reducer(candidate,self.cfg["common"])}
        low=static_supply(a,rays=64,step_deg=45,peak_ms=3.2)
        high=static_supply(a,rays=64,step_deg=45,peak_ms=6.4)
        np.testing.assert_allclose(np.array(high["rows"])[:,1:5],4*np.array(low["rows"])[:,1:5],atol=1e-12)
        self.assertAlmostEqual(high["whole_jet_kinetic_power_w"],8*low["whole_jet_kinetic_power_w"])
        mirrored=deepcopy(a);mirrored["reduction"]["speedRatios"][0]*=-1
        opposite=static_supply(mirrored,rays=64,step_deg=45,peak_ms=6.4)
        np.testing.assert_allclose(np.array(high["rows"])[:,1:3],np.array(opposite["rows"])[:,1:3],atol=1e-10)
        self.assertEqual(high["jetAimOffsetZMm"],-opposite["jetAimOffsetZMm"])


if __name__=="__main__":
    unittest.main()
