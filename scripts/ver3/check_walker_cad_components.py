"""Small real-solid regressions, run with FreeCAD's isolated bundled Python."""

import itertools
import math
import sys
import unittest

import numpy as np

import build_integrated_walkers as b
from walker_geometry import nominal_thread_pair


class Capture:
    def __init__(self):
        self.defs={}
        self.cap_mounts=[]

    def define(self,pid,shape,*args,**kwargs):
        self.defs[pid]=shape

    def add(self,*args,**kwargs):
        pass

    def hardware(self,*args,**kwargs):
        pass


def overlap(first,second):
    return sum(abs(s.Volume) for a in first.Solids for c in second.Solids
               for s in a.common(c).Solids)


def broad_pair(first,second):
    a,c=first.BoundBox,second.BoundBox
    return all(min(getattr(a,k+"Max"),getattr(c,k+"Max"))-
               max(getattr(a,k+"Min"),getattr(c,k+"Min"))>1e-6 for k in "XYZ")


class WalkerCadTests(unittest.TestCase):
    def test_round_collar_clocking_changes_no_axial_datum_or_mass(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            old=b.own_r4_parts();axis=a.input["axisYz"]
            motion={"kind":"shaft","axisYz":axis,"speed":a.red["speedRatios"][0]}
            a.define("H_INPUT_COLLAR",old["H_COLLAR"],"purchased","test unchanged round collar",mass=7)
            a.define("H_INPUT_SHAFT",b.d_x(6,2.5,0,140),"purchased","test140mm shaft",mass=30)
            matrix=np.eye(4);matrix[:3,3]=[-68,axis[0],axis[1]+b.Z0]
            a.add("H_INPUT_SHAFT",matrix.tolist(),"input",motion)
            for x,direction in ((-58.1,(1,0,0)),(-44.9,(-1,0,0))):
                a.add("H_INPUT_COLLAR",b.axis_pose(x,axis[0],axis[1]+b.Z0,direction),"input",motion)
            before=[i["transform"][0][3] for i in a.instances]
            b.clock_input_collars(a)
            self.assertEqual(before,[i["transform"][0][3] for i in a.instances])
            self.assertLess(np.linalg.norm(a.collar_balance["afterFirstMomentGmm"]),1e-6)
            self.assertEqual(a.collar_balance["addedParts"],0)
            for item in a.instances:
                shape=a.doc.getObject(item["name"]).Shape
                expected=a.world[item["name"]]
                for name in ("XMin","XMax","YMin","YMax","ZMin","ZMax"):
                    self.assertAlmostEqual(getattr(shape.BoundBox,name),getattr(expected.BoundBox,name),places=8)
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_cap_arms_do_not_reclose_the_axial_bore(self):
        cases=[
            ("MAIN_L",dict(bearing_x=-38,cap_x=-41.2,side=-1)),
            ("MAIN_R_0",dict(bearing_x=32,cap_x=37.5,side=1)),
            ("INTER_R",dict(bearing_x=-6,cap_x=-.8,side=1)),
            ("INPUT_FIXED",dict(bearing_x=-54,cap_x=-54.3,side=-1,
                                input_kind=True,thrust=10.2,bolt_half=18)),
        ]
        for name,options in cases:
            with self.subTest(name=name):
                a=Capture();b.add_bearing_cap(a,name,[0,0],**options)
                shape=next(iter(a.defs.values()))
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids),1)
                for z in (-2,-.1,.1,1,2.5):
                    self.assertFalse(shape.isInside(b.V(0,0,z),1e-7,False))
                if name=="MAIN_L":
                    self.assertTrue(shape.isInside(b.V(7.65,0,-2),1e-7,False))
                    self.assertFalse(shape.isInside(b.V(6,0,-2),1e-7,False))
                else:
                    radius=6.2 if name=="INPUT_FIXED" else 7.65
                    self.assertTrue(shape.isInside(b.V(0,radius,1),1e-7,False))

    def test_fixed_pivot_has_a_full_floor_and_long_metal_socket(self):
        point=b.P["P"]
        for side in (-1,1):
            root=b.x_cylinder(b.C["fixedPivotPostDiameterMm"]/2,32,22,point)
            if side<0:root=b.mirror_x(root)
            root=b.fixed_pivot_socket(root,point,side)
            self.assertTrue(root.isValid())
            self.assertEqual(len(root.Solids),1)
            for x in (43,48,53.5):
                self.assertFalse(root.isInside(b.V(side*x,point[0]+2,point[1]),1e-7,False))
                self.assertTrue(root.isInside(b.V(side*x,point[0]+2.2,point[1]),1e-7,False))
            for angle in np.linspace(0,2*math.pi,16,endpoint=False):
                self.assertTrue(root.isInside(b.V(side*42,point[0]+1.6*math.cos(angle),
                                                  point[1]+1.6*math.sin(angle)),1e-7,False))

    def test_fixed_pivot_accepts_two_actual_size_open_end_tool_envelopes(self):
        root=b.fixed_pivot_socket(b.x_cylinder(b.C["fixedPivotPostDiameterMm"]/2,32,22),[0,0],1)
        bit=b.transformed(b.hexagon(1.45,20),b.axis_pose(20,0,0))
        self.assertLess(overlap(root,bit),1e-5)
        for center in (63.3,64.9):
            head=b.x_cylinder(3.5,center-.6,1.2)
            inner=b.transformed(b.hexagon(4.1,1.4),b.axis_pose(center-.7,0,0))
            head=head.cut(inner)
            head=head.cut(b.Part.makeBox(1.4,6,4.1,b.V(center-.7,0,-2.05)))
            handle=b.Part.makeBox(1.2,20,3,b.V(center-.6,-22,-1.5))
            tool=head.fuse(handle)
            self.assertLess(overlap(root,tool),1e-5)

    def test_clamp_hardware_seats_on_the_actual_flats(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            for clock in (0,math.pi/2,math.pi):
                shape=b.clamp_hub(0,8,clock=clock)
                before=len(a.instances)
                a.clamp(4,[0,0],"clamp_test",clock=clock)
                for item in a.instances[before:]:
                    self.assertLess(overlap(shape,a.world[item["name"]]),1e-5,item["part_id"])
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_left_crank_pockets_clear_hardware_and_cap(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            capture=Capture()
            b.add_bearing_cap(capture,"MAIN_L",[0,0],-38,-41.2,-1)
            cap=b.transformed(next(iter(capture.defs.values())),b.axis_pose(-41.2,0,0,(-1,0,0)))
            for phase in (0,math.pi):
                crank=b.left_crank(phase)
                before=len(a.instances)
                a.clamp(-48,[0,0],"clamp_test",clock=math.pi-phase)
                self.assertLess(overlap(crank,cap),1e-5)
                for item in a.instances[before:]:
                    self.assertLess(overlap(crank,a.world[item["name"]]),1e-5)
                    self.assertLess(overlap(cap,a.world[item["name"]]),1e-5)
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_guide_is_clear_through_six_mm_and_has_a_real_stop(self):
        fixed=b.leg_shape("CEF",1)
        matrix=b.foot_axes(b.P["F"])
        slider=b.transformed(b.foot_slider(),matrix)
        axis=matrix[:3,2]
        for stroke in (0,3,5.5,6):
            moving=b.translate(slider,axis*stroke)
            self.assertLess(overlap(fixed,moving),1e-5)
        self.assertGreater(overlap(fixed,b.translate(slider,axis*6.2)),.1)

    def test_input_ties_clear_the_affected_real_link_sweep(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            members=b.input_frame_members(a)
            links={name:b.leg_shape(name,1) for name in ("AB","PBD")}
            for degrees in (0,45,90,91,135,180,225,270,315):
                points=b.body_points(math.radians(degrees),common=b.C)
                for name,part in links.items():
                    moving=b.transformed(part,b.link_pose(points,b.P,b.rigids()[name],-b.C["stationPitchMm"],0))
                    for member in members:
                        if broad_pair(member,moving):
                            self.assertLess(overlap(member,moving),1e-5,(degrees,name))
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_rigid_link_and_low_foot_clearance_through_a_cycle(self):
        links={name:b.leg_shape(name,1) for name in b.rigids()}
        local=b.foot_axes(b.P["F"])
        feet=[b.transformed(s,local) for s in (b.foot_slider(),b.foot_rocker())]
        hits=[]
        for degrees in range(0,360,10):
            points=b.body_points(math.radians(degrees),common=b.C)
            poses={name:np.array(b.link_pose(points,b.P,b.rigids()[name],0,0)) for name in links}
            moving={name:b.transformed(shape,poses[name]) for name,shape in links.items()}
            for first,second in itertools.combinations(moving,2):
                x,y=moving[first],moving[second]
                if broad_pair(x,y) and overlap(x,y)>1e-5:hits.append((degrees,first,second))
            axis=poses["CEF"][:3,:3]@local[:3,2]
            for stroke in (0,6):
                for index,foot in enumerate(feet):
                    actual=b.translate(b.transformed(foot,poses["CEF"]),axis*stroke)
                    for name,shape in moving.items():
                        if broad_pair(shape,actual) and overlap(shape,actual)>1e-5:
                            hits.append((degrees,stroke,name,index))
        self.assertEqual(hits,[])

    def test_clamp_fasteners_clear_fixed_cap_fasteners_for_all_angles(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            a.define("H_NMB1680",b.standard_bearing(),"purchased","test bearing")
            a.define("H_NYLOCK4",b.own_r4_parts()["H_LOCKNUT"],"purchased","test original nut")
            for side,clock,x in ((-1,math.pi,-48),(1,0,45.15)):
                begin=len(a.instances)
                b.add_bearing_cap(a,"MAIN_L" if side<0 else "MAIN_R",[0,0],
                                  -38 if side<0 else 32,-41.2 if side<0 else 37.5,side)
                fixed=a.instances[begin:]
                begin=len(a.instances);a.clamp(x,[0,b.Z0],"clamp_test",clock=clock)
                moving=a.instances[begin:]
                for item in moving:
                    shape=a.world[item["name"]]
                    box=shape.BoundBox
                    radius=math.hypot(max(abs(box.YMin),abs(box.YMax)),
                                      max(abs(box.ZMin-b.Z0),abs(box.ZMax-b.Z0)))
                    sweep=b.x_cylinder(radius,box.XMin,box.XLength,[0,b.Z0])
                    for other in fixed:
                        if not other["part_id"].startswith("H_BOLT"):continue
                        target=a.world[other["name"]]
                        if broad_pair(sweep,target):
                            self.assertLess(overlap(sweep,target),1e-5,(side,item["part_id"],other["part_id"]))
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_small_pinion_face_is_not_buried_by_the_compound_bridge(self):
        train=b.reducer(b.CFG["candidates"][0],b.C)
        incoming,outgoing=train["stages"]
        compound=b.compound_geometry(incoming,outgoing)
        pinion=b.gear_disk(outgoing["pinion"],outgoing["xMm"],outgoing["pinionToothDatumRad"],
                          addendum_coefficient=outgoing["pinionAddendumCoefficient"])
        section=compound.common(b.Part.makeBox(.2,40,40,b.V(outgoing["xMm"]+1,-20,-20)))
        extra=section.cut(pinion)
        self.assertLess(sum(abs(s.Volume) for s in extra.Solids),1e-5)
        self.assertTrue(compound.isValid())
        self.assertEqual(len(compound.Solids),1)

    def test_compound_wheel_clears_output_carrier_between_mesh_planes(self):
        train=b.reducer(b.CFG["candidates"][0],b.C)
        compound=b.compound_geometry(*train["stages"])
        output=b.output_wheel_geometry(train["stages"][-1])
        for angle in (0,math.pi/train["stages"][-1]["wheel"]):
            first=compound.copy()
            first.rotate(b.V(),b.V(1,0,0),math.degrees(angle*train["speedRatios"][1]))
            first.translate(b.V(0,*train["axesYzMm"][1]))
            second=output.copy();second.rotate(b.V(),b.V(1,0,0),math.degrees(angle))
            self.assertLess(overlap(first,second),1e-5)

    def test_cage_join_fasteners_have_real_counterbores(self):
        a=b.Whole(b.CFG["candidates"][0])
        try:
            front,rear,joins=b.rotor_cage(a)
            bodies=[b.transformed(shape,b.axis_pose(0,0,0)) for shape in (front,rear)]
            split=b.C["guards"]["cageSplitXmm"]
            for y,z in joins:
                a.hardware("bolt",3,(split-3,y,z),(1,0,0),16,"test")
                for x in (split-3,split+3):a.hardware("washer",3,(x,y,z),group="test")
                for x in (split+3.5,split+5.9):a.hardware("nut",3,(x,y,z),group="test")
            for item in a.instances:
                for shape in bodies:
                    self.assertLess(overlap(shape,a.world[item["name"]]),1e-5,item["part_id"])
        finally:
            b.App.closeDocument(a.doc.Name)

    def test_actual_opposed_leg_stack_has_no_unintended_static_intersections(self):
        a=b.Whole(b.CFG["candidates"][0])
        stations,phases=b.STATIONS,b.C["legPhasesDeg"]
        try:
            b.STATIONS=[0.]
            b.C["legPhasesDeg"]=[[0,180]]
            b.add_legs(a)
            hits=[]
            for first,second in itertools.combinations(a.instances,2):
                if nominal_thread_pair(first,second):continue
                x,y=a.world[first["name"]],a.world[second["name"]]
                if not broad_pair(x,y):continue
                volume=overlap(x,y)
                if volume>1e-5:hits.append((first["part_id"],second["part_id"],volume))
            self.assertEqual(hits,[])
        finally:
            b.STATIONS=stations
            b.C["legPhasesDeg"]=phases
            b.App.closeDocument(a.doc.Name)


if __name__=="__main__":
    unittest.main(argv=[sys.argv[0]],verbosity=2)
