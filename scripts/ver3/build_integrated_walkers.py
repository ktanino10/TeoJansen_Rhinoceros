"""One canonical complete mechanism expanded to A/B/C; no live CAD or video.

Purchased parts are independently constructed dimensional envelopes, not copied
vendor models. Full CAD exports and stable instances feed all subsequent checks.
"""

import argparse
from collections import Counter
from copy import deepcopy
import csv
import faulthandler
import gzip
import hashlib
import json
import inspect
import math
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib", required=True)
parser.add_argument("--design", choices=("A","B","C","BC","all"), default="all")
parser.add_argument("--diagnostics", type=Path)
parser.add_argument("--stop-after", choices=("drive","frame","complete"), default="complete")
args = parser.parse_args()
sys.path.insert(0, args.freecad_lib)
import FreeCAD as App
import Part
import MeshPart
import numpy as np

from cad_parts import cylinder, disk, capsule, polygon, hexagon, bolt
from input_cartridge import write_json
from walker_contact import load
from walker_geometry import ROOT, OUT, CAD, PRINT, body_points, rigids, link_pose, reducer, input_layout, involute_outline, gear_pair_metrics

V = App.Vector
CFG = load()
C = CFG["common"]
Z0 = 70.
P = body_points(common=C)
LAYERS = C["legLayers"]
PIN_SIZE = {node:2 for node in ("A","P","B","C","D","E")}
STATIONS = [-float(C["stationPitchMm"]),0.,float(C["stationPitchMm"])]
BOOLEAN_INDEX = 0
FRAME_SEGMENTS = []
BUILD_INPUTS=[Path(__file__).resolve(),*[Path(__file__).resolve().with_name(name) for name in
              ("walker_r7.json","walker_geometry.py","walker_kinematics.py","walker_contact.py")]]
BUILD_HASHES={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in BUILD_INPUTS}


def solid(shape):
    """Remove singleton compound wrappers before FreeCAD's recursive cut path."""
    if shape.ShapeType in ("Compound","CompSolid"):
        if len(shape.Solids)!=1:
            raise RuntimeError(f"Boolean requires one connected solid, got {len(shape.Solids)}")
        result=shape.Solids[0].copy()
        if any(abs(getattr(result.BoundBox,k)-getattr(shape.BoundBox,k))>1e-7
               for k in ("XMin","XMax","YMin","YMax","ZMin","ZMax")):
            raise RuntimeError("Unwrapping compound changed its placement")
        return result
    return shape


def cut(shape,tool):
    global BOOLEAN_INDEX
    BOOLEAN_INDEX+=1
    caller=inspect.currentframe().f_back
    label=f"{caller.f_code.co_name}:{caller.f_lineno}"
    started=time.monotonic()
    if args.diagnostics:
        args.diagnostics.mkdir(parents=True,exist_ok=True)
        shape.exportBrep(str(args.diagnostics/"last-cut-target.brep"))
        tool.exportBrep(str(args.diagnostics/"last-cut-tool.brep"))
    meta={"index":BOOLEAN_INDEX,"partContext":label,"targetType":shape.ShapeType,
          "targetSolids":len(shape.Solids),"toolType":tool.ShapeType,"toolSolids":len(tool.Solids),
          "targetValid":shape.isValid(),"toolValid":tool.isValid()}
    print("BOOLEAN_BEGIN "+json.dumps(meta),flush=True)
    if not meta["targetValid"] or not meta["toolValid"]:
        raise RuntimeError("Invalid Boolean input; snapshots at "+str(args.diagnostics))
    if not shape.Solids or not tool.Solids:
        raise RuntimeError("Boolean input is not a solid; snapshots at "+str(args.diagnostics))
    result=solid(solid(shape).cut(solid(tool)))
    if not result.isValid() or len(result.Solids)!=1:
        raise RuntimeError("Boolean output invalid or disconnected; "+label)
    print(f"BOOLEAN_END {BOOLEAN_INDEX} {time.monotonic()-started:.3f}s {result.Volume:.9f}mm3",flush=True)
    return result


def x_cylinder(radius, start, length, yz=(0,0)):
    return Part.makeCylinder(radius, length, V(start,*yz), V(1,0,0))


def translate(shape, vector):
    result=shape.copy();result.translate(V(*vector));return result


def mirror_x(shape):
    result=shape.mirror(V(),V(1,0,0))
    if not result.isValid() or abs(result.Volume-shape.Volume)>1e-6:
        raise RuntimeError("Handed B-rep reflection failed")
    return result


def prism_x(points, start, thickness):
    vertices=[V(start,float(p[0]),float(p[1])) for p in points]
    return Part.Face(Part.makePolygon(vertices+[vertices[0]])).extrude(V(thickness,0,0))


def capsule_x(a,b,width,start,thickness):
    # Reuse the original XY capsule, then map its Z extrusion to the shaft axis.
    shape=capsule(a,b,width,thickness)
    matrix=App.Matrix(0,0,1,start, 1,0,0,0, 0,1,0,0, 0,0,0,1)
    shape.Placement=App.Placement(matrix).multiply(shape.Placement)
    return shape


def hex_x(af,start,length,yz=(0,0)):
    radius=af/math.sqrt(3)
    points=np.array([[radius*math.cos(math.pi/6+i*math.pi/3),radius*math.sin(math.pi/6+i*math.pi/3)] for i in range(6)])+yz
    return prism_x(points,start,length)


def d_x(diameter,flat_from_center,start,length,yz=(0,0)):
    solid=x_cylinder(diameter/2,start,length,yz)
    result=solid.common(Part.makeBox(length,diameter,diameter/2+flat_from_center,
                                    V(start,yz[0]-diameter/2,yz[1]-diameter/2)))
    result.rotate(V(0,*yz),V(1,0,0),-45)
    return result


def rod(a,b,width):
    a,b=np.array(a,float),np.array(b,float)
    delta=b-a
    if np.linalg.norm(delta)<1e-8:raise ValueError("Zero frame member")
    axis=delta/np.linalg.norm(delta)
    reference=np.array([1.,0,0]) if abs(axis[0])<.95 else np.array([0.,1,0])
    first=np.cross(axis,reference);first/=np.linalg.norm(first)
    second=np.cross(axis,first)
    count=C["frameStrutSectionSides"]
    points=[V(*(a+width/2*(math.cos(2*math.pi*i/count)*first
                           +math.sin(2*math.pi*i/count)*second))) for i in range(count)]
    result=Part.Face(Part.makePolygon(points+[points[0]])).extrude(V(*delta))
    FRAME_SEGMENTS.append({"aMm":a.tolist(),"bMm":b.tolist(),"circumDiameterMm":width,"sectionSides":count})
    return result


def union(shapes):
    shapes=[solid(s) for s in shapes]
    if any(not s.isValid() for s in shapes):
        raise RuntimeError("Invalid shape entered a part union")
    large=len(shapes)>10
    if large:
        caller=inspect.currentframe().f_back
        print(f"UNION_BEGIN {caller.f_code.co_name}:{caller.f_lineno} {len(shapes)}solids",flush=True)
        if args.diagnostics:
            args.diagnostics.mkdir(parents=True,exist_ok=True)
            Part.makeCompound(shapes).exportBrep(str(args.diagnostics/"last-union-operands.brep"))
    # The captured106-solid chassis union is invalid at OCC's default
    # coincidence tolerance. 1e-6mm is a numerical B-rep tolerance, not a
    # manufacturing gap or a license to join separate assembly components.
    tolerance=1e-6 if large else 0.
    result=shapes[0].multiFuse(shapes[1:],tolerance).removeSplitter() if len(shapes)>1 else shapes[0]
    if large:print(f"UNION_END {result.ShapeType} {len(result.Solids)}solids valid={result.isValid()}",flush=True)
    if not result.isValid():
        if args.diagnostics:result.exportBrep(str(args.diagnostics/"invalid-union-result.brep"))
        raise RuntimeError("Invalid part union; no following cut attempted; "+str(args.diagnostics))
    return solid(result)


def clamp_hub(start,length=8,af=5.12,cross_x=None,clock=0):
    shape=x_cylinder(9.5,start,length)
    # Real parallel lands stay within the cap's circular running clearance.
    shape=cut(shape,Part.makeBox(length+2,24,9,V(start-1,-12,5)))
    shape=cut(shape,Part.makeBox(length+2,24,9,V(start-1,-12,-14)))
    shape=cut(shape,hex_x(af,start-1,length+2))
    shape=cut(shape,Part.makeBox(length+2,12,.8,V(start-1,0,-.4)))
    shape=cut(shape,Part.makeCylinder(1.65,24,V(start+length/2 if cross_x is None else cross_x,6,-12),V(0,0,1)))
    if clock:shape.rotate(V(),V(1,0,0),math.degrees(clock))
    return shape.removeSplitter()


def gear_disk(teeth,start,phase=0,face=None,profile_shift=0.,addendum_coefficient=None):
    face=C["gears"]["faceWidthMm"] if face is None else face
    outline=involute_outline(1,teeth,C["gears"]["pressureAngleDeg"],.3,
                             profile_shift=profile_shift,addendum_coefficient=addendum_coefficient)
    co,si=math.cos(phase),math.sin(phase)
    outline=outline@np.array([[co,si],[-si,co]])
    body=prism_x(outline,start,face)
    root=teeth/2-1.25+profile_shift
    if root>16:
        rim=cut(body,x_cylinder(root-3,start-1,face+2))
        spokes=[capsule_x([0,0],[(root-2)*math.cos(phase+i*math.pi/3),
                                (root-2)*math.sin(phase+i*math.pi/3)],3.5,start,face) for i in range(6)]
        body=union([rim,x_cylinder(9.5,start,face),*spokes])
    return body.removeSplitter()


def main_crank(side, phase):
    # Positive5mm-AF torque path; the rod ends before all moving link planes.
    r=15*C["linkScale"]
    tip=np.array([r*math.cos(phase),r*math.sin(phase)])
    if side<0:
        shape=mirror_x(main_crank(1,phase))
        return shape
    mouth=50.5+C["legJournals"]["rootPocketEmbedMm"]
    arm=union([x_cylinder(9.5,50,4),capsule_x([0,0],tip,8,49.5,4.5),
               x_cylinder(4,53.5,mouth-53.5,tip)])
    neck=clamp_hub(40.3,9.7,clock=math.pi-phase)
    shoulder=x_cylinder(4.6,37.8,2.5)
    journal=x_cylinder(4,29.5,8.3)
    shape=union([arm,neck,shoulder,journal])
    shape=cut(shape,hex_x(5.12,28,28))
    shape=cut(shape,x_cylinder(1.15,49,6,tip))
    shape=cut(shape,x_cylinder(2.05,50.5,C["legJournals"]["rootPocketEmbedMm"]+.1,tip))
    shape=cut(shape,x_cylinder(2.6,46,3.5,tip))
    return shape.removeSplitter()


def left_crank(phase):
    r=15*C["linkScale"]
    tip=[r*math.cos(phase),r*math.sin(phase)]
    mouth=50.5+C["legJournals"]["rootPocketEmbedMm"]
    positive=union([x_cylinder(9.5,50,4),capsule_x([0,0],tip,8,49.5,4.5),
                    x_cylinder(4,53.5,mouth-53.5,tip),
                    clamp_hub(41,9,cross_x=48,clock=math.pi-phase),
                    x_cylinder(4.6,38,3),x_cylinder(4,33.2,4.8)])
    positive=cut(cut(positive,hex_x(5.12,31,24)),x_cylinder(1.15,49,6,tip))
    positive=cut(positive,x_cylinder(2.05,50.5,C["legJournals"]["rootPocketEmbedMm"]+.1,tip))
    positive=cut(positive,x_cylinder(2.6,46,3.5,tip))
    for radius,z in ((3.1,-15),(3.45,5)):
        tool=cylinder(radius,10,48,6,z)
        tool.rotate(V(),V(1,0,0),math.degrees(math.pi-phase))
        positive=cut(positive,tool)
    return mirror_x(positive.removeSplitter())


def retaining_collar(start):
    body=clamp_hub(start+1.2,5.6)
    return cut(union([body,x_cylinder(4.6,start,1.2)]),hex_x(5.12,start-1,12)).removeSplitter()


def foot_axes(point):
    beta=math.atan2(*(P["E"]-P["C"])[::-1])
    gamma=beta-math.radians(C["foot"]["pitchReferenceBodyAngleDeg"])
    co,si=math.cos(gamma),math.sin(gamma)
    m=np.eye(4);m[:3,:3]=[[1,0,0],[0,co,-si],[0,si,co]]
    advance=C["foot"]["toeOffsetFromFNeutralMm"][0]
    m[:3,3]=[C["foot"]["centerAbsXmm"],point[0]+co*advance,point[1]+si*advance]
    return m


def transformed(shape,matrix):
    result=shape.copy()
    result.Placement=App.Placement(App.Matrix(*np.array(matrix).ravel().tolist())).multiply(result.Placement)
    return result


def foot_fixed():
    f=C["foot"]
    roof_z=f["roofBottomAboveFmm"];gy=f["guideCenterFootYmm"]
    bottom=f["springBottomSeatAboveFmm"];top=f["springTopSeatAboveFmm"]
    roof=Part.makeBox(28,24,f["roofThicknessMm"],V(-14,-15,roof_z))
    # Downward annular seat sets the catalogued15mm free spring length.
    seats=[]
    for x in f["springLateralCentersMm"]:
        seats += [cylinder(4.6,roof_z-top,x,0,top),cylinder(2,2,x,0,top-2)]
    stop=cylinder(5.5,roof_z-f["compressionStopAboveFmm"],0,gy,f["compressionStopAboveFmm"])
    result=union([roof,stop,*seats])
    result=cut(result,cylinder(1.15,roof_z+f["roofThicknessMm"]-top+2,0,gy,top-1))
    # Positive extension stops; the slider inserts sideways before the guide bolt.
    for sign in (-1,1):
        wall=Part.makeBox(26,1.5,roof_z-bottom+.5,V(-13,sign*8-.75,bottom))
        shelves=[Part.makeBox(6,2,1.2,V(x,6 if sign>0 else -8,bottom-1)) for x in (-13,7)]
        result=union([result,wall,*shelves])
    result=cut(result,Part.makeBox(11.2,4,roof_z-bottom+1,V(-5.6,-9,bottom-1)))
    return result.removeSplitter()


def foot_slider():
    f=C["foot"]
    start=f["movingBushingStartAboveFmm"];gy=f["guideCenterFootYmm"]
    plate_z=f["springBottomSeatAboveFmm"]-3
    sleeve=cylinder(f["plungerOuterDiameterMm"]/2,f["guideBearingLengthMm"],0,gy,start)
    plate=Part.makeBox(28,10,3,V(-14,-5,plate_z))
    spine=translate(capsule((0,gy),(0,0),10,3),(0,0,plate_z))
    locators=[cylinder(2,2,x,0,f["springBottomSeatAboveFmm"]) for x in f["springLateralCentersMm"]]
    result=cut(union([sleeve,plate,spine,*locators]),
               cylinder(f["guideBoreMm"]/2,f["guideBearingLengthMm"]+5,0,gy,plate_z-1))
    result=cut(result,cylinder(2.65,3.1,0,gy,plate_z-.1))
    for sign in (-1,1):
        for x in (-12,7):
            rib=Part.makeBox(5,1.2,2.9,V(x,4.6 if sign>0 else -5.8,start-.5))
            ear=Part.makeBox(5,1.4,2,V(x,5.4 if sign>0 else -6.8,start+.4))
            result=union([result,rib,ear])
    # The8mm sleeve embeds1mm into each2mm cheek, leaving a6mm rocker gap.
    pivot=f["toeOffsetFromFNeutralMm"][1]
    gap=f["rockerForkInnerHalfGapMm"]
    for sign in (-1,1):
        cheek=Part.makeBox(10,2,plate_z-pivot+3,V(-5,gap if sign>0 else -gap-2,pivot-2))
        result=union([result,cheek])
    result=cut(result,Part.makeCylinder(1.15,16,V(0,-8,pivot),V(0,1,0)))
    result=cut(result,Part.makeCylinder(2.05,8,V(0,-4,pivot),V(0,1,0)))
    # Nominal8-degree stops;5 degrees is the accepted minimum after print error.
    stop_z=pivot+6*math.sin(math.radians(8))+2*math.cos(math.radians(8))
    for x in (-6,6):
        result=union([result,Part.makeBox(1.2,5,plate_z-stop_z,V(x-.6,-2.5,stop_z))])
    return result.removeSplitter()


def foot_rocker():
    f=C["foot"];pivot=f["toeOffsetFromFNeutralMm"][1]
    cross=Part.makeBox(24,f["rockerWidthAtPivotMm"],4,V(-12,-f["rockerWidthAtPivotMm"]/2,pivot-2))
    boss=Part.makeCylinder(5,f["rockerWidthAtPivotMm"],V(0,-f["rockerWidthAtPivotMm"]/2,pivot),V(0,1,0))
    toes=[Part.makeCylinder(f["toeRadiusMm"],8,V(x-4,0,pivot),V(1,0,0)) for x in (-12,12)]
    shape=union([cross,boss,*toes])
    return cut(shape,Part.makeCylinder(2.1,10,V(0,-5,pivot),V(0,1,0))).removeSplitter()


def leg_shape(name,side):
    nodes=rigids()[name];x=54.65+LAYERS[name]*C["legLayerPitchMm"];th=C["linkThicknessMm"]
    paths=list(zip(nodes,nodes[1:]))+([(nodes[-1],nodes[0])] if len(nodes)==3 else [])
    if name=="CEF":
        f=C["foot"];m=foot_axes(P["F"])
        g=(m@np.array([0,0,f["roofBottomAboveFmm"],1]))[1:3]
        paths=[("C","E")]
        shapes=[capsule_x(P["C"],P["E"],7,x,th),
                capsule_x(P["C"],g,7,x,th),capsule_x(P["E"],g,7,x,th),
                transformed(foot_fixed(),m)]
        shape=union(shapes)
        gy=f["guideCenterFootYmm"];start=f["guideStartAboveFmm"]-1
        shape=cut(shape,transformed(cylinder(2.1,f["guideRootAboveFmm"]-start,0,gy,start),m))
        shape=cut(shape,transformed(cylinder(2.9,f["compressionStopAboveFmm"]-start,0,gy,start),m))
        shape=cut(shape,transformed(cylinder(3.6,.5,0,gy,f["guideRootAboveFmm"]),m))
        shape=cut(shape,transformed(cylinder(4.6,.8,0,gy,f["guideRootAboveFmm"]+.5),m))
        shape=cut(shape,transformed(cylinder(1.15,12,0,gy,f["roofBottomAboveFmm"]-.1),m))
        shape=cut(shape,transformed(cylinder(4.6,12,0,gy,f["roofBottomAboveFmm"]+f["roofThicknessMm"]),m))
    else:
        shape=union([capsule_x(P[a],P[b],C["linkWidthMm"],x,th) for a,b in paths])
    for n in nodes:
        if n=="F":continue
        diameter=C["legJournals"]["clearanceBoreMm"]
        boss=x_cylinder(diameter/2+2.5,x,th,P[n])
        shape=cut(union([shape,boss]),x_cylinder(diameter/2,x-1,th+2,P[n]))
    shape=shape.removeSplitter()
    return mirror_x(shape) if side<0 else shape


def standard_bearing():
    # NMB DDL-1680HH catalogue shoulders; rolling race detail is not recreated.
    inner=disk(9.68/2,5,8)
    outer=disk(8,5,14.23)
    shields=[translate(disk(7.08,.15,9.8),(0,0,z)) for z in (.3,4.55)]
    return Part.makeCompound([inner,outer,*shields])


def axis_pose(x,y,z,direction=(1,0,0)):
    if tuple(direction)==(1,0,0):
        return [[0,0,1,x],[1,0,0,y],[0,1,0,z],[0,0,0,1]]
    if tuple(direction)==(-1,0,0):
        return [[0,0,-1,x],[1,0,0,y],[0,-1,0,z],[0,0,0,1]]
    rotation=App.Rotation(V(0,0,1),V(*direction))
    placement=App.Placement(V(x,y,z),rotation)
    a=placement.toMatrix()
    return [[getattr(a,f"A{i}{j}") for j in range(1,5)] for i in range(1,5)]


def metric_bolt(size,length):
    if size!=2:return bolt(size,length)
    return cut(union([cylinder(1,length),cylinder(1.9,2,z=-2)]),hexagon(1.5,1.1,z=-2.1))


def nut_shape(size):
    width,height={2:(4,1.6),3:(5.5,2.4),4:(7,3.2)}[size]
    return cut(hexagon(width,height),cylinder(size*.42,height+2,z=-1))


def steel_sleeve(size,length):
    outer,inner=(6,3.2) if size==3 else (4,2.2)
    return disk(outer/2,length,inner)


def spring_shape():
    f=C["foot"]
    pitch=(f["springFreeLengthMm"]-f["springWireMm"])/f["springTotalTurns"]
    radius=(f["springOuterDiameterMm"]-f["springWireMm"])/2
    path=Part.Wire(Part.makeHelix(pitch,f["springFreeLengthMm"]-f["springWireMm"],radius).Edges)
    tangent=V(0,radius,pitch/(2*math.pi))
    circle=Part.Wire(Part.makeCircle(f["springWireMm"]/2,V(radius,0,0),tangent))
    return translate(path.makePipeShell([circle],True,False),(0,0,f["springWireMm"]/2))


def own_r4_parts():
    source=json.loads((ROOT/"docs/ver3/common_input_r4/assembly.json").read_text())
    doc=App.openDocument(str(ROOT/"FreeCAD/Ver.3/common_input_r4/CommonInputR4.FCStd"))
    result={}
    for item in source["instances"]:
        pid=item["part_id"]
        if pid not in ("H_HUB","H_COLLAR","H_BEARING","H_SPACER","H_BOLT20","H_LOCKNUT") or pid in result:continue
        shape=doc.getObject(item["name"]).Shape.copy()
        inverse=App.Placement(App.Matrix(*np.array(item["transform"]).ravel().tolist())).inverse()
        shape.Placement=inverse.multiply(shape.Placement);result[pid]=shape
    App.closeDocument(doc.Name)
    return result


class Whole:
    def __init__(self,candidate):
        self.candidate=candidate;self.id=candidate["id"]
        self.red=reducer(candidate,C);self.input=input_layout(self.red)
        self.doc=App.newDocument("Integrated_"+self.id)
        self.defs={};self.instances=[];self.world={};self.counts=Counter()
        self.cap_mounts=[]
        self.groups={k:self.doc.addObject("App::DocumentObjectGroup",k) for k in ("printed","purchased","cut_to_length","sheet_cut")}

    def define(self,pid,shape,category,spec,mass=None,density=1.27,sku=None):
        if pid in self.defs:return
        print("define",self.id,pid,shape.ShapeType,flush=True)
        if not shape.isValid() or not shape.Solids:raise RuntimeError("Invalid part "+pid)
        if category=="printed" and len(shape.Solids)!=1:raise RuntimeError("Disconnected printed part "+pid)
        volume=sum(s.Volume for s in shape.Solids)
        centroid=sum((s.CenterOfMass*s.Volume for s in shape.Solids),V())/volume
        inertia=np.zeros((3,3))
        for item in shape.Solids:
            matrix=item.MatrixOfInertia
            delta=np.array(list(item.CenterOfMass-centroid))
            inertia+=np.array([[getattr(matrix,f"A{i}{j}") for j in range(1,4)] for i in range(1,4)])
            inertia+=item.Volume*(np.dot(delta,delta)*np.eye(3)-np.outer(delta,delta))
        self.defs[pid]={"shape":shape,"category":category,"spec":spec,"sku":sku,
                        "solid_volume_mm3":volume,"local_com_mm":list(centroid),
                        "centralVolumeInertiaMm5":inertia.tolist(),
                        "mass_g":mass if mass is not None else volume*density/1000,
                        "mass_basis":"supplier unit value or explicitly tagged estimate" if mass is not None else "actual solid CAD volume x assumed material density"}

    def add(self,pid,matrix=None,group="frame",motion=None,name=None):
        matrix=np.eye(4).tolist() if matrix is None else matrix
        self.counts[pid]+=1;name=name or f"{pid}_{self.counts[pid]:03}"
        feature=self.doc.addObject("Part::Feature",name);feature.Shape=self.defs[pid]["shape"]
        name=feature.Name
        feature.Placement=App.Placement(App.Matrix(*np.array(matrix).ravel().tolist())).multiply(feature.Placement)
        for prop,value in (("PartId",pid),("RevisionId",CFG["revisionId"]),("Category",self.defs[pid]["category"]),("Specification",self.defs[pid]["spec"])):
            feature.addProperty("App::PropertyString",prop,"Walker");setattr(feature,prop,value)
        feature.addProperty("App::PropertyFloat","NominalMassGram","Walker");feature.NominalMassGram=self.defs[pid]["mass_g"]
        self.groups[self.defs[pid]["category"]].addObject(feature)
        item={"name":name,"part_id":pid,"transform":matrix,"group":group,"motion":motion or {"kind":"body"}}
        self.instances.append(item);self.world[name]=transformed(self.defs[pid]["shape"],matrix)
        return name

    def hardware(self,kind,size,origin,direction=(1,0,0),length=0,group="hardware",motion=None):
        if kind=="bolt":
            pid=f"H_BOLT_M{size}_{length}";shape=metric_bolt(size,length);sku=f"BOLT_M{size}_{length}";density=7.85
        elif kind=="nut":
            pid=f"H_NUT_M{size}";shape=nut_shape(size);sku=f"NUT_M{size}";density=7.85
        elif kind=="washer":
            inner,outer,th={2:(2.2,5,.3),3:(3.2,7,.5),4:(4.3,9,.8),6:(6.4,11.5,.8)}[size]
            pid=f"H_WASHER_{size}";shape=disk(outer/2,th,inner);sku=f"WASHER_M{size}" if size in (2,3) else f"THRUST{size}";density=7.85
        elif kind=="sleeve":
            pid=f"H_SLEEVE_{size}_{length}";shape=steel_sleeve(size,length)
            sku="CE-308N" if size==3 else {8:"CE-2008N",12:"CE-2012N",20:"CE-2020N"}[length]
            density=8.5
        else:raise ValueError(kind)
        self.define(pid,shape,"purchased",sku+"; metric dimensional model, no physical material certification",density=density,sku=sku)
        return self.add(pid,axis_pose(*origin,direction),group,motion)

    def clamp(self,x,yz,group,motion=None,clock=0):
        co,si=math.cos(clock),math.sin(clock)
        def point(z):return (x,yz[0]+6*co-z*si,yz[1]+6*si+z*co)
        direction=(0,-si,co)
        self.hardware("bolt",3,point(-5),direction,16,group,motion)
        for t in (5,7.4):
            self.hardware("nut",3,point(t),direction,group=group,motion=motion)

    def pin(self,node,station,side,phase):
        p=body_points(phase,common=C)[node]+[station,Z0]
        j=C["legJournals"]
        size=2
        root=node in ("A","P")
        length=j["rootSleeveLengthMm"] if root else j["threeBodySleeveLengthMm"] if node in ("C","E") else j["freeSleeveLengthMm"]
        direction=(side,0,0)
        first=42.5 if node=="P" else 50.5 if root else 54.5
        motion={"kind":"joint","node":node,"station":station,"phase":phase,"side":side}
        self.hardware("sleeve",size,(side*first,*p),direction,length,"legs",motion)
        if node=="P":
            self.hardware("washer",2,(side*41.2,*p),direction,group="legs",motion=motion)
            self.hardware("bolt",2,(side*41.2,*p),direction,C["fixedPivotBoltLengthMm"],"legs",motion)
            for x in (62.5,64.1):
                self.hardware("nut",2,(side*x,*p),direction,group="legs",motion=motion)
        else:
            start=49.2 if root else first-.3
            for x in (start,first+length):
                self.hardware("washer",size,(side*x,*p),direction,group="legs",motion=motion)
            bolt_length=j["rootBoltLengthMm"] if root else j["threeBodyBoltLengthMm"] if node in ("C","E") else j["freeBoltLengthMm"]
            self.hardware("bolt",2,(side*start,*p),direction,bolt_length,"legs",motion)
            for offset in (0,1.6):
                self.hardware("nut",2,(side*(first+length+.3+offset),*p),direction,group="legs",motion=motion)
        levels=sorted({LAYERS[n] for n,points in rigids().items() if node in points})
        for left,right in zip(levels,levels[1:]):
            begin=54.65+left*4.1+3.1;end=54.65+right*4.1
            self.hardware("washer",4,(side*begin,*p),direction,group="legs",motion=motion)
            if right-left>1:
                spacer=end-begin-1.6-.2
                pid=f"P_LAYER_SPACER_{spacer:.1f}"
                self.define(pid,disk(4,spacer,4.3),"printed","Free axial spacing between nonadjacent link planes; not in the screw clamp path")
                self.add(pid,axis_pose(side*(begin+.8),*p,direction),"legs",motion)
                self.hardware("washer",4,(side*(end-.8),*p),direction,group="legs",motion=motion)
        last=54.65+max(levels)*4.1+3.1
        tail=first+length-last-.2
        if tail>.8:
            pid=f"P_PIN_TAIL_{tail:.1f}"
            self.define(pid,disk(4,tail,4.3),"printed","Free axial keeper around4mm sleeve; bolt load closes on metal sleeve,not this spacer")
            self.add(pid,axis_pose(side*last,*p,direction),"legs",motion)


def fixed_pivot_socket(shape,point,side):
    shape=cut(shape,x_cylinder(1.15,-56 if side<0 else 31,25,point))
    shape=cut(shape,x_cylinder(2.05,-54.2 if side<0 else 42.5,11.7,point))
    shape=cut(shape,x_cylinder(C["fixedPivotNutDriverBoreMm"]/2,-41.5 if side<0 else 32,9.5,point))
    return shape


def cap_seat_clearance(shape,mount):
    plane=mount["frameStart"] if mount["side"]<0 else mount["frameEnd"]
    start=plane-20 if mount["side"]<0 else plane
    yz=mount["axisYz"]
    tool=union([x_cylinder(mount["capOuterRadiusMm"]+.25,start,20,yz),
                *[capsule_x(yz,np.array(yz)+offset,9.5,start,20) for offset in mount["boltOffsetsYzMm"]]])
    return cut(shape,tool)


def input_frame_members(a):
    pieces=[];iyz=a.input["axisYz"];height=C["frameInputTieBaseZMm"];front=C["stationPitchMm"]
    for x in (-50,59):
        pieces += [rod([x,-105,height],[x,*iyz],8 if a.id!="C" else 6),
                   rod([x,front,height],[x,*iyz],8 if a.id!="C" else 6),
                   rod([-38,-105,27],[x,-105,height],7),rod([32,front,27],[x,front,height],7)]
    return pieces


def rotor_cage(a):
    guard=C["guards"];radius=a.candidate["rotorDiameterMm"]/2+guard["radialClearanceMm"]
    outer=radius+guard["radialWallMm"];width=guard["ribWidthMm"];pitch=guard["gridPitchMm"]
    start,end=guard["startXmm"],guard["endXmm"]
    sections=[]
    for x in guard["hoopStartXmm"]:
        sections.append(translate(disk(outer,width,2*radius),(0,0,x)))
    count=math.ceil(2*math.pi*(radius+guard["radialWallMm"]/2)/pitch)
    depth,height=guard["longitudinalBarDepthAlongWindMm"],guard["longitudinalBarHeightAcrossWindMm"]
    center_radius=(radius+outer)/2
    for i in range(count):
        angle=2*math.pi*i/count
        bar=Part.makeBox(depth,height,end-start,
                        V(center_radius*math.cos(angle)-depth/2,
                          center_radius*math.sin(angle)-height/2,start))
        sections.append(bar)
    for x in (start,end-guard["endGridThicknessMm"]):
        plate=disk(outer,guard["endGridThicknessMm"])
        strips=[]
        for offset in np.arange(-outer+pitch,outer,pitch):
            for transpose in (False,True):
                box=Part.makeBox(2*outer,width,guard["endGridThicknessMm"],V(-outer,offset-width/2,0))
                if transpose:box.rotate(V(),V(0,0,1),90)
                intersection=plate.common(box)
                if not intersection.isNull():strips.append(solid(intersection))
        sections.append(translate(union([*strips,disk(20,guard["endGridThicknessMm"],10.2)]),(0,0,x)))
    cage=union(sections)
    cage=cut(cage,cylinder(16.4,3,z=start-1))
    cage=cut(cage,cylinder(5.1,end-start+2,z=start-1))
    pose=np.array(axis_pose(0,*a.input["axisYz"]))
    inverse=np.linalg.inv(pose)
    for member in input_frame_members(a):
        # The explicit regular clearance follows the static brace centerline.
        # It is a manufactured opening,not an ignored collision.
        vertices=np.array([list(v.Point) for v in member.Vertexes])
        center=vertices.mean(axis=0)
        covariance=(vertices-center).T@(vertices-center)
        _,directions=np.linalg.eigh(covariance);axis=directions[:,-1]
        projection=(vertices-center)@axis
        first=center+axis*projection.min();length=float(np.ptp(projection))
        radius_clear=float(np.linalg.norm(vertices-center-((vertices-center)@axis)[:,None]*axis,axis=1).max())+.4
        tool=Part.makeCylinder(radius_clear,length+.8,V(*(first-axis*.4)),V(*axis))
        tool=transformed(tool,inverse)
        if cage.BoundBox.intersect(tool.BoundBox):
            cage=cut(cage,tool)
        if abs(center[0]-59)<.1:
            local_first=(inverse@np.r_[first,1])[:3]
            local_end=(inverse@np.r_[first+axis*length,1])[:3]
            slit=translate(capsule(local_first[:2],local_end[:2],2*radius_clear,64-guard["cageSplitXmm"]),
                           (0,0,guard["cageSplitXmm"]))
            if cage.BoundBox.intersect(slit.BoundBox):cage=cut(cage,slit)
    for item in a.instances:
        if item["group"]!="bearing_caps" or not item["part_id"].startswith("H_BOLT_"):continue
        bounds=a.world[item["name"]].BoundBox
        if bounds.XMax<=start or bounds.XMin>=start+guard["endGridThicknessMm"]:continue
        origin=np.array(item["transform"])[:3,3]-[0,0,Z0]
        point=(inverse@np.r_[origin,1])[:3]
        cage=cut(cage,cylinder(3.25,guard["endGridThicknessMm"]+2,point[0],point[1],start-1))
    split=guard["cageSplitXmm"]
    front=solid(cage.common(Part.makeBox(2*outer+10,2*outer+10,split-start,V(-outer-5,-outer-5,start))))
    rear=solid(cage.common(Part.makeBox(2*outer+10,2*outer+10,end-split,V(-outer-5,-outer-5,split))))
    rear=union([rear,translate(disk(outer,1,2*radius),(0,0,split))])
    # Rear escape slots are open at the split plane, so the cap can slide
    # along X over the stationary braces without passing through the rotor.
    for member in input_frame_members(a):
        vertices=np.array([list(v.Point) for v in member.Vertexes])
        if abs(vertices[:,0].mean()-59)>.1:continue
        yz=vertices[:,1:]-a.input["axisYz"]
        covariance=(yz-yz.mean(axis=0)).T@(yz-yz.mean(axis=0))
        _,basis=np.linalg.eigh(covariance);direction=basis[:,-1]
        projected=yz@direction
        first=yz.mean(axis=0)+direction*(projected.min()-projected.mean())
        last=yz.mean(axis=0)+direction*(projected.max()-projected.mean())
        tool=translate(capsule(first,last,9 if a.id!="C" else 7,64-split),(0,0,split))
        rear=cut(rear,tool)
    joins=[]
    for degrees in guard["cageJoinAnglesDeg"]:
        angle=math.radians(degrees);point=center_radius*np.array([math.cos(angle),math.sin(angle)])
        front=union([front,cylinder(4,2.5,*point,split-2.5)])
        rear=union([rear,cylinder(4,3,*point,split)])
        front=cut(front,cylinder(1.65,30,*point,split-10))
        rear=cut(rear,cylinder(1.65,30,*point,split-10))
        front=cut(front,cylinder(3.8,8,*point,split-10.5))
        rear=cut(rear,cylinder(3.8,15,*point,split+3))
        joins.append(point.tolist())
    return front,rear,joins


def build_main_frame(a):
    # Main rails and all pivot standoffs are one real chassis. No temporary
    # laboratory base is counted as a walking support.
    pieces=[];member_start=len(FRAME_SEGMENTS)
    for x in (-39.5,32):
        pieces.append(Part.makeBox(6,np.ptp(C["frameRailYmm"]),6,V(x-3,C["frameRailYmm"][0],12)))
        for station in STATIONS:
            p=P["P"]+[station,0]
            pieces += [rod([x,station,15],[x,station,0],9),
                       rod([x,station,0],[x,*p],8),rod([x,*p],[x,station,15],7)]
            if x<0:
                pieces += [x_cylinder(14,-41.2,3,[station,0]),
                           x_cylinder(10,-38.2,6.2,[station,0])]
                pieces.append(x_cylinder(C["fixedPivotPostDiameterMm"]/2,-54,16,p))
            else:
                pieces.append(x_cylinder(11,30.5,7,[station,0]))
                pieces.append(x_cylinder(C["fixedPivotPostDiameterMm"]/2,32,22,p))
    front=C["stationPitchMm"]
    for y in (-105,front):
        pieces += [rod([-38,y,15],[-38,y,27],7),rod([32,y,15],[32,y,27],7),
                   rod([-38,y,27],[32,y,27],7)]
    # Short stationary idler axles stay out of the reducer planes.
    for y in (-C["stationPitchMm"]/2,C["stationPitchMm"]/2):
        pieces += [rod([32,y,15],[32,y,0],7),rod([32,y,0],[17,y,0],7)]
        pieces.append(x_cylinder(5.5,14.1,12.5,[y,0]))
    # Two outside roots carry intermediate-bearing frames and the input tower.
    for y in (-105,):
        pieces.append(rod([-38,y,25],[32,y,25],6))
    stages=a.red["stages"]
    for index,yz in enumerate(a.red["axesYzMm"][1:-1],start=1):
        for x in (-41.4,-4.5):
            pieces += [rod([x,-105,25],[x,*yz],7 if a.id!="C" else 6),
                       rod([x,front,27],[x,*yz],7 if a.id!="C" else 6),
                       rod([-38,-105,27],[x,-105,25],7),rod([32,front,27],[x,front,27],7)]
        pieces += [x_cylinder(14,-48.2,9.2,yz),x_cylinder(11,-8,7.2,yz)]
    iyz=a.input["axisYz"]
    pieces.extend(input_frame_members(a))
    for y in C["frameSpliceStationsYmm"]:
        pieces.append(capsule_x([y,C["frameSpliceBoltZmm"][0]],[y,C["frameSpliceBoltZmm"][1]],8,C["frameSplitXmm"]-6,12))
    pieces += [x_cylinder(12,-54.3,8.3,iyz),x_cylinder(12,55,9,iyz)]
    for mount in a.cap_mounts:
        yz=mount["axisYz"]
        for offset in mount["boltOffsetsYzMm"]:
            point=(np.array(yz)+offset).tolist()
            pieces.append(capsule_x(yz,point,9,mount["frameStart"],mount["frameEnd"]-mount["frameStart"]))
            pieces.append(x_cylinder(5,mount["frameStart"],mount["frameEnd"]-mount["frameStart"],point))
    result=union(pieces)
    for station in STATIONS:
        result=cut(result,x_cylinder(4.2,-65,135,[station,0]))
        result=cut(result,x_cylinder(12.1,-55,16.8,[station,0]))
        result=cut(result,x_cylinder(8.1,-38.2,5.2,[station,0]))
        result=cut(result,x_cylinder(7.3,-33,2,[station,0]))
        result=cut(result,x_cylinder(8.1,31.5,7,[station,0]))
        result=cut(result,x_cylinder(7.3,29,3,[station,0]))
        for side in (-1,1):
            point=P["P"]+[station,0]
            result=fixed_pivot_socket(result,point,side)
    for yz in a.red["axesYzMm"][1:-1]:
        result=cut(result,x_cylinder(4.2,-65,80,yz))
        result=cut(result,x_cylinder(12.1,-65,19.8,yz))
        result=cut(cut(result,x_cylinder(8.1,-45.2,5.2,yz)),x_cylinder(7.3,-40,4,yz))
        result=cut(cut(result,x_cylinder(8.1,-6.5,6.5,yz)),x_cylinder(7.3,-9,3,yz))
    # Input flanged bearing pockets preserve the specified14/15mm family.
    result=cut(result,x_cylinder(5.1,-80,160,iyz))
    result=cut(result,x_cylinder(7.6,-70,17,iyz))
    result=cut(result,x_cylinder(7.1,-53,4.2,iyz))
    result=cut(result,x_cylinder(5.1,-55,10,iyz))
    result=cut(result,x_cylinder(7.1,56.8,4.2,iyz))
    result=cut(cut(result,x_cylinder(7.6,61,3.1,iyz)),x_cylinder(5.1,54,11,iyz))
    for mount in a.cap_mounts:
        result=cap_seat_clearance(result,mount)
        for offset in mount["boltOffsetsYzMm"]:
            yz=(np.array(mount["axisYz"])+offset).tolist()
            result=cut(result,x_cylinder(mount["boltDiameter"]/2+.25,mount["frameStart"]-12,
                                        mount["frameEnd"]-mount["frameStart"]+24,yz))
            if mount["recessedNutSeat"] is not None:
                result=cut(result,x_cylinder(3.8,mount["recessedNutSeat"],
                                             10,yz))
            else:
                start=mount["frameEnd"] if mount["side"]<0 else mount["frameStart"]-10
                result=cut(result,x_cylinder(4.75 if mount["boltDiameter"]==4 else 3.8,start,10,yz))
    for y in (-C["stationPitchMm"]/2,C["stationPitchMm"]/2):
        result=cut(result,x_cylinder(1.15,13,22,[y,0]))
        result=cut(result,x_cylinder(2.6,17.1,6,[y,0]))
        result=cut(result,Part.makeBox(5.4,12,4.5,V(17.1,y-6,-2.25)))
    for y in C["frameSpliceStationsYmm"]:
        for z in C["frameSpliceBoltZmm"]:
            result=cut(result,x_cylinder(1.65,C["frameSplitXmm"]-17,34,[y,z]))
            result=cut(result,x_cylinder(3.8,C["frameSplitXmm"]-16,10,[y,z]))
            result=cut(result,x_cylinder(3.8,C["frameSplitXmm"]+6,12,[y,z]))
    split=C["frameSplitXmm"];bounds=result.BoundBox
    left=solid(result.common(Part.makeBox(split-bounds.XMin+1,bounds.YLength+2,bounds.ZLength+2,
                                         V(bounds.XMin-1,bounds.YMin-1,bounds.ZMin-1))))
    right=solid(result.common(Part.makeBox(bounds.XMax-split+1,bounds.YLength+2,bounds.ZLength+2,
                                          V(split,bounds.YMin-1,bounds.ZMin-1))))
    for index,y in enumerate(C["frameSpliceStationsYmm"]):
        key_z=sum(C["frameSpliceBoltZmm"])/2
        key=hex_x(4,split-.5,3.5,[y,key_z]);left=union([left,key])
        pocket=hex_x(4.2,split-.1,3.5,[y,key_z]) if index==0 else capsule_x([y-.5,key_z],[y+.5,key_z],4.85,split-.1,3.5)
        right=cut(right,pocket)
    a.frame_members=deepcopy(FRAME_SEGMENTS[member_start:])
    matrix=np.eye(4);matrix[2,3]=Z0
    for hand,shape in (("L",left),("R",right)):
        a.define("P_CHASSIS_"+hand,shape.removeSplitter(),"printed",
                 "Real longitudinal frame half;4M3 bolts,front locating hex key and rear relieved key. Close around the shafts rather than trapping integral gears in a one-piece housing.")
        a.add("P_CHASSIS_"+hand,matrix.tolist(),name="CHASSIS_"+hand)
    for y in C["frameSpliceStationsYmm"]:
        for z in C["frameSpliceBoltZmm"]:
            a.hardware("bolt",3,(split-6.5,y,z+Z0),(1,0,0),20,"frame_splice")
            for x in (split-6.5,split+6):
                a.hardware("washer",3,(x,y,z+Z0),group="frame_splice")
            for x in (split+6.5,split+8.9):
                a.hardware("nut",3,(x,y,z+Z0),group="frame_splice")


def add_bearing_cap(a,name,yz,bearing_x,cap_x,side=1,thrust=14.6,bolt_half=13,input_kind=False):
    left_nmb=side<0 and not input_kind
    main_right=name.startswith("MAIN_R")
    shield=C.get("guards",{}).get("petGearShields",False)
    shield_left=shield and name.startswith("MAIN_L")
    shield_reducer=shield and name.startswith("INTER_R")
    if shield_reducer:cap_x+=1
    thickness=3 if input_kind or left_nmb else 3.5
    size=4 if input_kind or main_right else 3
    bolt_half=max(bolt_half,17) if left_nmb or main_right else bolt_half
    offsets=((-14,-13),(19,0)) if name.startswith("MAIN_") else ((-bolt_half,0),(bolt_half,0))
    local_offsets=[(y,side*z) for y,z in offsets]
    if left_nmb:cap_x=bearing_x-3.2
    cap=union([disk(13 if left_nmb or main_right else 11,thickness,21 if left_nmb else thrust),
               *[capsule((0,0),point,9,thickness) for point in local_offsets]])
    cap=cut(cap,cylinder((21 if left_nmb else thrust)/2,thickness+2,z=-1))
    if left_nmb:
        nose=translate(disk(12,3,thrust),(0,0,-3))
        # Local -Z points inboard for the left cap.
        nose=cut(nose,cylinder(10.5,.7,z=-.7))
        cap=union([cap,nose])
    if main_right:cap=cut(cap,cylinder(10.5,thickness-2.3+.1,z=2.3))
    if shield_reducer:cap=union([cap,translate(disk(8.6,1,thrust),(0,0,-1))])
    cage_enabled=name=="INPUT_FLOAT" and C.get("guards",{}).get("rotorCage",False)
    if cage_enabled:
        front,cage,joins=rotor_cage(a)
        a.define("P_ROTOR_CAGE_FRONT",front,"printed",
                 "Front cage basket: fit rotor/hub inside,lower radially into open chamber before threading the input shaft. Rear cap is separate.")
        a.add("P_ROTOR_CAGE_FRONT",axis_pose(0,yz[0],yz[1]+Z0),"guards")
        split=C["guards"]["cageSplitXmm"]
        for y,z in joins:
            point=(yz[0]+y,yz[1]+z+Z0)
            a.hardware("bolt",3,(split-3,*point),(1,0,0),16,"guards")
            for x in (split-3,split+3):a.hardware("washer",3,(x,*point),group="guards")
            for x in (split+3.5,split+5.9):a.hardware("nut",3,(x,*point),group="guards")
        cage=translate(cage,(0,0,-cap_x))
        cap=union([cap,cage])
    if shield_left:
        cap=union([cap,*[cylinder(4,.8,y,z,thickness) for y,z in local_offsets]])
    for y,z in local_offsets:cap=cut(cap,cylinder(size/2+.25,thickness+3,y,z,-1))
    tag="_".join(f"{y:g}_{z:g}" for y,z in offsets)
    pid=f"P_CAP_{'STEP' if left_nmb else 'WIDE' if main_right else 'PLAIN'}_{tag}_{size}_{thrust:g}"
    if cage_enabled:pid="P_ROTOR_CAGE_CAP"
    a.define(pid,cap,"printed","Outer-ring-only retainer; lands and pocket length define axial allowance,not torque preload")
    a.add(pid,axis_pose(cap_x,yz[0],yz[1]+Z0,(side,0,0)),"bearing_caps",name="CAP_"+name)
    bearing_pid="H_INPUT_BEARING" if input_kind else "H_NMB1680"
    direction=(-1,0,0) if input_kind and side<0 else (1,0,0)
    a.add(bearing_pid,axis_pose(bearing_x+5 if direction[0]<0 else bearing_x,yz[0],yz[1]+Z0,direction),
          "bearings",name="BEARING_"+name)
    if input_kind:
        frame_start,frame_end=(-54.3,-46) if side<0 else (55,64)
    elif left_nmb:
        frame_start,frame_end=bearing_x-3.2,bearing_x+6
    else:frame_start,frame_end=(30.5,37.5) if main_right else (-8,-.8)
    nut_seat=bearing_x+2 if left_nmb else None
    a.cap_mounts.append({"axisYz":yz,"boltOffsetsYzMm":offsets,"frameStart":frame_start,"frameEnd":frame_end,
                         "boltDiameter":size,"recessedNutSeat":nut_seat,"side":side,
                         "capOuterRadiusMm":13 if left_nmb or main_right else 11})
    for y_offset,z_offset in offsets:
        wt=.8 if size==4 else .5
        stack=2.6 if shield_left else 2.4 if shield and main_right else wt
        p=(cap_x+side*(thickness+stack),yz[0]+y_offset,yz[1]+Z0+z_offset)
        direction=(-side,0,0)
        a.hardware("bolt",size,p,direction,16 if left_nmb and not shield_left else 20,"bearing_caps")
        if shield_left:
            face=cap_x+side*(thickness+.8)
            for distance in (.5,1):
                a.hardware("washer",3,(face+side*distance,*p[1:]),direction,group="bearing_caps")
            a.hardware("washer",4,p,direction,group="bearing_caps")
        elif shield and main_right:
            for distance in (.8,1.6):
                a.hardware("washer",4,(cap_x+thickness+distance,*p[1:]),direction,group="bearing_caps")
            a.hardware("washer",6,p,direction,group="bearing_caps")
        else:
            a.hardware("washer",4 if size==4 else 3,p,direction,group="bearing_caps")
        if shield_reducer:
            for x in (-.8,-.3):
                a.hardware("washer",3,(x,*p[1:]),(1,0,0),group="bearing_caps")
        seat=nut_seat if left_nmb else frame_end if side<0 else frame_start
        a.hardware("washer",4 if size==4 else 3,(seat,*p[1:]),(-side,0,0),group="bearing_caps")
        face=seat-side*wt
        if size==4:
            a.add("H_NYLOCK4",axis_pose(face,*p[1:],(-side,0,0)),"bearing_caps")
        else:
            for distance in (0,2.4):
                a.hardware("nut",3,(face-side*distance,*p[1:]),(-side,0,0),group="bearing_caps")
    return pid


def add_legs(a):
    reference=P
    for side in (-1,1):
        for name in rigids():
            pid=f"P_LEG_{name}_{'L' if side<0 else 'R'}"
            a.define(pid,leg_shape(name,side),"printed","Shared Jansen body with real smooth journals;"+name)
        for kind,shape in (("SLIDER",foot_slider()),("ROCKER",foot_rocker())):
            part=transformed(shape,foot_axes(P["F"]))
            if side<0:part=mirror_x(part)
            a.define(f"P_FOOT_{kind}_{'L' if side<0 else 'R'}",part,"printed","Guided stock-spring equalizer; "+kind)
    f=C["foot"]
    a.define("H_FOOT_SPRING",spring_shape(),"purchased",
             "SAMINI12-0721;OD7,wire0.6,free15,total6.8active4.8,rate0.882N/mm. Coil drawing is envelope;end pitch simplified.",
             mass=.31,sku="12-0721")
    for station,pair in zip(STATIONS,C["legPhasesDeg"]):
        for side,degrees in zip((-1,1),pair):
            phase=math.radians(degrees);points=body_points(phase,common=C);hand="L" if side<0 else "R"
            for name,nodes in rigids().items():
                motion={"kind":"link","link":name,"station":station,"side":side,"phase":phase}
                a.add(f"P_LEG_{name}_{hand}",link_pose(points,reference,nodes,station,Z0),"legs",motion)
            for node in ("A","P","B","C","D","E"):a.pin(node,station,side,phase)
            foot_matrix=np.array(link_pose(points,reference,rigids()["CEF"],station,Z0))
            for kind in ("SLIDER","ROCKER"):
                a.add(f"P_FOOT_{kind}_{hand}",foot_matrix.tolist(),"feet",
                      {"kind":"foot","piece":kind,"station":station,"side":side,"phase":phase})
            local=foot_axes(P["F"])
            if side<0:
                reflected=np.diag([-1,1,1,1]);local=reflected@local
            # Build physical hardware in world coordinates using vectors; no
            # reflected placement matrix is passed to FreeCAD.
            location=foot_matrix@local
            axis=location[:3,2]
            for lateral in f["springLateralCentersMm"]:
                spring_origin=(location@np.array([lateral,0,f["springBottomSeatAboveFmm"],1]))[:3]
                spring_pose=axis_pose(*spring_origin,axis)
                a.add("H_FOOT_SPRING",spring_pose,"feet",{"kind":"foot","piece":"SPRING","station":station,"side":side,"phase":phase})
            roof_top=f["roofBottomAboveFmm"]+f["roofThicknessMm"]
            guide_parts=[("sleeve",2,f["guideStartAboveFmm"],f["guideLengthMm"],1),
                         ("bolt",2,roof_top+f["guideWasherStackMm"],30,-1),
                         ("washer",2,f["guideStartAboveFmm"]-.3,0,1),
                         ("nut",2,f["guideStartAboveFmm"]-.3,0,-1),
                         ("nut",2,f["guideStartAboveFmm"]-1.9,0,-1)]
            guide_parts += [("washer",3,f["guideRootAboveFmm"],0,1),
                            ("washer",4,f["guideRootAboveFmm"]+.5,0,1),
                            ("washer",4,roof_top,0,1),("washer",3,roof_top+.8,0,1)]
            for kind,size,z,length,direction_sign in guide_parts:
                origin=(location@np.array([0,f["guideCenterFootYmm"],z,1]))[:3]
                a.hardware(kind,size,origin,axis*direction_sign,length,"feet",
                           {"kind":"foot","piece":"GUIDE","station":station,"side":side,"phase":phase})
            pivot=f["toeOffsetFromFNeutralMm"][1]
            direction=location[:3,1]
            for kind,size,b,length in (("sleeve",2,-4,8),("bolt",2,-5.3,16),("washer",2,-5.3,0),
                                      ("washer",2,5,0),("nut",2,5.3,0),("nut",2,6.9,0),
                                      ("washer",4,-2.7,0),("washer",4,1.9,0)):
                origin=(location@np.array([0,b,pivot,1]))[:3]
                a.hardware(kind,size,origin,direction,length,"feet",
                           {"kind":"foot","piece":"ROCKER_PIN","station":station,"side":side,"phase":phase})


def add_drive(a,old):
    a.define("H_NYLOCK4",old["H_LOCKNUT"],"purchased","goBILDA2812-0004-0007 M4 prevailing torque nut; shared25-piece purchase lot",mass=.78,sku="2812-0004-0007")
    a.define("H_INPUT_SHAFT",d_x(6,2.5,0,140),"purchased","goBILDA2101-0006-0140 stock140mm D shaft; no machining",mass=30,sku="2101-0006-0140")
    for pid,oldpid,mass,sku in (("H_INPUT_BEARING","H_BEARING",3,"1611-0514-0006"),
                              ("H_INPUT_HUB","H_HUB",14,"1309-0016-1006"),
                              ("H_INPUT_COLLAR","H_COLLAR",7,"2910-0919-0006"),
                              ("H_INPUT_SPACER","H_SPACER",.64,"1521-0008-0040")):
        a.define(pid,old[oldpid],"purchased",sku+"; original R4 dimensional envelope, not redistributed vendorCAD",mass=mass,sku=sku)
    a.define("H_NMB1680",standard_bearing(),"purchased","NMB DDL-1680HH8x16x5,Li9.68,Lo14.23;4g conservative UNVERIFIED unit-mass allowance",mass=4,sku="DDL-1680HH")
    a.define("H_MAIN_HEX100",hex_x(5,-50,100),"cut_to_length","C3604B5mm-AF stock cut100mm; tolerance acceptance+/-2,round8mm keyed journals are separate",density=8.5,sku="HEX5")
    a.define("H_INTER_HEX58",hex_x(5,-60,C["intermediateShaftCutLengthMm"]),"cut_to_length",
             "C3604B5mm-AF stock cut58mm,+/-0.5mm acceptance; short flush end permits the upper PET panel's radial insertion; no end tapping",
             density=8.5,sku="HEX5")
    for station,pair in zip(STATIONS,C["legPhasesDeg"]):
        matrix=np.eye(4);matrix[:3,3]=[0,station,Z0]
        a.add("H_MAIN_HEX100",matrix.tolist(),"mainshafts",{"kind":"shaft","axisYz":[station,0],"speed":1})
        for side,deg in zip((-1,1),pair):
            pid=f"P_CRANK_JOURNAL_{side}_{deg}"
            shape=left_crank(math.radians(deg)) if side<0 else main_crank(side,math.radians(deg))
            a.define(pid,shape,"printed","One keyed crank/round8mm journal with9.2mm shoulder and clamp; no hex stock directly inside round bearing")
            a.add(pid,matrix.tolist(),"cranks",{"kind":"crank","axisYz":[station,0],"speed":1})
        collar=retaining_collar(-32.8)
        a.define("P_MAIN_INNER_STOP",collar,"printed","Keyed inner stop,0.2mm locating-bearing allowance; clamp is axialretention,hexprofile carries torque")
        if station!=0:a.add("P_MAIN_INNER_STOP",matrix.tolist(),"mainshafts",{"kind":"shaft","axisYz":[station,0],"speed":1})
        motion={"kind":"shaft","axisYz":[station,0],"speed":1}
        a.clamp(-48,[station,Z0],"mainshafts",motion,math.pi-math.radians(pair[0]))
        a.clamp(45.15,[station,Z0],"mainshafts",motion,math.pi-math.radians(pair[1]))
        a.clamp(-28.8,[station,Z0],"mainshafts",motion)
        add_bearing_cap(a,f"MAIN_L_{station}",[station,0],-38,-38.2,-1)
        add_bearing_cap(a,f"MAIN_R_{station}",[station,0],32,37.5,1)
    sync=C["synchronization"];halfturn=math.pi+math.pi/sync["teeth"]
    for index,y in enumerate(sync["gearCentersYmm"]):
        g=gear_disk(sync["teeth"],sync["gearPlaneXmm"],0 if index%2==0 else halfturn,3.2)
        if index%2==0:
            g=cut(union([g,clamp_hub(3,7)]),hex_x(5.12,2,14))
            pid="P_SYNC_DRIVE"
            a.define(pid,g,"printed",f"{sync['teeth']}-tooth m1,25deg synchronous maingear; two-idler bus makes all mainshafts same direction")
            a.clamp(6.5,[y,Z0],"synchronization",{"kind":"shaft","axisYz":[y,0],"speed":1})
        else:
            # Annular bolt land stays inside the16.25mm tooth root, avoiding
            # coincident spoke/capsule edges and supporting both cap screws.
            g=union([g,x_cylinder(16,8,7)])
            for by in (-13,13):g=cut(g,x_cylinder(1.65,7,9,[by,0]))
            g=cut(cut(g,x_cylinder(8.1,7.9,5.6)),x_cylinder(7.3,13.5,3))
            pid="P_SYNC_IDLER"
            a.define(pid,g,"printed",f"{sync['teeth']}-tooth idler with real8mm bearing; short fixed journal must not enter reducer planes")
            a.add("H_NMB1680",axis_pose(8.1,y,Z0),"synchronization",{"kind":"shaft","axisYz":[y,0],"speed":-1})
            cap=union([disk(11,2,14.6),capsule([-13,0],[13,0],7,2)])
            cap=cut(cap,cylinder(7.3,4,z=-1))
            for by in (-13,13):cap=cut(cap,cylinder(1.65,4,by,0,-1))
            a.define("P_IDLER_CAP",cap,"printed","Outer ring cap with0.4mm front clearance;two M3 bolts")
            motion={"kind":"shaft","axisYz":[y,0],"speed":-1}
            a.add("P_IDLER_CAP",axis_pose(5.7,y,Z0),"synchronization",motion)
            for by in (-13,13):
                a.hardware("bolt",3,(15.5,y+by,Z0),(-1,0,0),20,"synchronization",motion)
                a.hardware("washer",3,(5.2,y+by,Z0),group="synchronization",motion=motion)
                a.hardware("washer",3,(15,y+by,Z0),group="synchronization",motion=motion)
                for nx in (5.2,2.8):a.hardware("nut",3,(nx,y+by,Z0),(-1,0,0),group="synchronization",motion=motion)
            journal=union([disk(4,5,4.2),translate(disk(4.6,1,4.2),(0,0,5))])
            a.define("P_IDLER_JOURNAL",journal,"printed","Round8mm journal around4mm stationary brasssleeve;9.2mm inner-ring shoulder")
            a.define("P_IDLER_INNER_WASHER",disk(4.6,1.8,4.2),"printed","Inner-ring-only axial keeper;0.2mm total inner stack freedom")
            a.add("P_IDLER_JOURNAL",axis_pose(8.1,y,Z0),"synchronization")
            a.add("P_IDLER_INNER_WASHER",axis_pose(6.3,y,Z0),"synchronization")
            a.hardware("sleeve",2,(6.1,y,Z0),(1,0,0),8,"synchronization")
            a.hardware("bolt",2,(5.8,y,Z0),(1,0,0),16,"synchronization")
            for nx in (5.8,17.1):a.hardware("washer",2,(nx,y,Z0),group="synchronization")
            for nx in (17.4,19):a.hardware("nut",2,(nx,y,Z0),group="synchronization")
        matrix=np.eye(4);matrix[:3,3]=[0,y,Z0]
        a.add(pid,matrix.tolist(),"synchronization",{"kind":"shaft","axisYz":[y,0],"speed":1 if index%2==0 else -1})
    # Compound intermediate gears reduce keyed interfaces and hold their
    # manufacturer-sized round journals outside the rotor's X8..46 span.
    for axis_index in range(1,len(a.red["axesYzMm"])-1):
        yz=a.red["axesYzMm"][axis_index]
        incoming=a.red["stages"][axis_index-1];outgoing=a.red["stages"][axis_index]
        body=compound_geometry(incoming,outgoing)
        pid=f"P_COMPOUND_{axis_index}"
        a.define(pid,body,"printed","Two rigid involute stages on one keyed carrier;8mm journals; exact two clocked tooth datums")
        matrix=np.eye(4);matrix[:3,3]=[0,yz[0],yz[1]+Z0]
        motion={"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][axis_index]}
        a.add(pid,matrix.tolist(),"reducer",motion)
        a.add("H_INTER_HEX58",matrix.tolist(),"reducer",motion)
        # Separate collar construction at the far left; not used as a generic
        # interference-free placeholder during access validation.
        stop=cut(union([clamp_hub(-59,8),x_cylinder(4.6,-51,5.8)]),hex_x(5.12,-60,16))
        a.define("P_INTER_STOP",stop,"printed","Removable5mm-AF intermediate clamp and9.2mm shoulder;0.4mm inner-stack freedom")
        a.add("P_INTER_STOP",matrix.tolist(),"reducer",motion)
        a.clamp(-55,[yz[0],yz[1]+Z0],"reducer",motion)
        add_bearing_cap(a,f"INTER_L_{axis_index}",yz,-45,-48.2,-1,bolt_half=13)
        pinion_tip=outgoing["pinion"]/2+outgoing["pinionAddendumCoefficient"]
        # Include the M3 nut's corner radius,not just its across-flats size.
        retainer_pitch=max(13,math.ceil(pinion_tip+5.5/math.sqrt(3)+.6))
        add_bearing_cap(a,f"INTER_R_{axis_index}",yz,-6,-.8,1,bolt_half=retainer_pitch)
    # Main output wheel.
    last=a.red["stages"][-1]
    wheel=output_wheel_geometry(last)
    a.define("P_OUTPUT_WHEEL",wheel,"printed","Reducer output on the third common shaft;positive5mm-AF profile")
    matrix=np.eye(4);matrix[:3,3]=[0,0,Z0]
    a.add("P_OUTPUT_WHEEL",matrix.tolist(),"reducer",{"kind":"shaft","axisYz":[0,0],"speed":1})
    inp=a.input;yz=inp["axisYz"]
    matrix=np.eye(4);matrix[:3,3]=[0,yz[0],yz[1]+Z0]
    a.add("H_INPUT_SHAFT",(np.array(matrix)@np.array([[1,0,0,-68],[0,1,0,0],[0,0,1,0],[0,0,0,1]])).tolist(),
          "input",{"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][0]})
    for pid,x,reverse in (("H_INPUT_SPACER",-58,False),("H_INPUT_SPACER",-49,False),
                          ("H_INPUT_COLLAR",-58.1,False),("H_INPUT_COLLAR",-44.9,True)):
        a.add(pid,axis_pose(x,yz[0],yz[1]+Z0,(-1,0,0) if reverse else (1,0,0)),"input",
              {"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][0]})
    a.add("H_INPUT_HUB",axis_pose(0,yz[0],yz[1]+Z0),"input",{"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][0]})
    first=a.red["stages"][0]
    if not -35<=first["xMm"]<=-C["gears"]["faceWidthMm"]:
        raise ValueError("Input gear plane does not fit the retained D-shaft carrier")
    pinion=union([gear_disk(first["pinion"],first["xMm"],first["pinionToothDatumRad"],
                           profile_shift=first["pinionProfileShift"],addendum_coefficient=first["pinionAddendumCoefficient"]),
                   x_cylinder(4,-35,35)])
    pinion=cut(pinion,d_x(6.2,2.6,-36,38))
    a.define("P_INPUT_PINION",pinion,"printed","Positive6mmD pinion with integral spacerstem;0.4mm axial clearance between inner collar and metal hub,not an unsupported round-bore friction fit")
    a.add("P_INPUT_PINION",matrix.tolist(),"input",{"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][0]})
    add_bearing_cap(a,"INPUT_FIXED",yz,-54,-54.3,-1,thrust=10.2,bolt_half=18,input_kind=True)
    add_bearing_cap(a,"INPUT_FLOAT",yz,58,64,1,thrust=10.2,bolt_half=18,input_kind=True)


def compound_geometry(incoming,outgoing):
    # The connection must remain inside the small pinion's root cylinder.
    # A large-wheel hub radius carried through this face buries its teeth.
    bridge_radius=min(9.5,C["gears"]["moduleMm"]*(outgoing["pinion"]/2-1.25+outgoing["pinionProfileShift"])-.25)
    body=union([gear_disk(incoming["wheel"],incoming["xMm"],incoming["wheelToothDatumRad"],
                         profile_shift=incoming["wheelProfileShift"],addendum_coefficient=incoming["wheelAddendumCoefficient"]),
                gear_disk(outgoing["pinion"],outgoing["xMm"],outgoing["pinionToothDatumRad"],
                          profile_shift=outgoing["pinionProfileShift"],addendum_coefficient=outgoing["pinionAddendumCoefficient"]),
                x_cylinder(bridge_radius,incoming["xMm"],outgoing["xMm"]-incoming["xMm"]+3.2),
                x_cylinder(4,-45,incoming["xMm"]+45),
                x_cylinder(4.6,-39.8,incoming["xMm"]+39.8),
                x_cylinder(4,outgoing["xMm"]+3.2,C["intermediateJournalEndXmm"]-outgoing["xMm"]-3.2),
                x_cylinder(4.6,outgoing["xMm"]+3.2,-6.8-outgoing["xMm"]-3.2)])
    return cut(body,hex_x(5.12,-62,70))


def output_wheel_geometry(last):
    wheel=gear_disk(last["wheel"],last["xMm"],last["wheelToothDatumRad"],
                    profile_shift=last["wheelProfileShift"],addendum_coefficient=last["wheelAddendumCoefficient"])
    items=[wheel,retaining_collar(-32.8)]
    if last["xMm"]>-26:items.append(x_cylinder(4,-26,last["xMm"]+26))
    return cut(union(items),hex_x(5.12,-34,32))


def rotor(a):
    radius=a.candidate["rotorDiameterMm"]/2
    inner=22.5;tip=radius-.8
    phase_sign=1 if a.red["speedRatios"][0]>0 else -1
    angles=np.linspace(0,math.radians(20),25)*phase_sign
    radii=np.linspace(inner,tip,25)
    center=np.column_stack([radii*np.cos(angles),radii*np.sin(angles)])
    derivative=np.diff(center,axis=0);derivative/=np.linalg.norm(derivative,axis=1)[:,None]
    normal=np.column_stack([-derivative[:,1],derivative[:,0]])
    normals=np.vstack([normal[0],(normal[:-1]+normal[1:])/(1+np.sum(normal[:-1]*normal[1:],axis=1))[:,None],normal[-1]])
    end=translate(disk(radius,2,2*(radius-4)),(0,0,36))
    # Root ring and hub are separate intermediate sections until the actual
    # spokes are present; only the final connected printable rotor is fused.
    bodies=[disk(radius,4,2*(radius-4)),disk(20,4,6.5),end]
    for i in range(16):
        angle=i*2*math.pi/16;rotation=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        line=center@rotation.T;n=normals@rotation.T
        spoke_end=line[-1]*(radius-2)/np.linalg.norm(line[-1])
        bodies.append(capsule([0,0],spoke_end,4,4))
        wires=[]
        for z,t in ((4,2.4),(6,1.6),(8,1.2),(32,1.2),(34,1.6),(36,2.4)):
            poly=np.vstack([line+n*t/2,(line-n*t/2)[::-1]])
            pts=[V(float(x),float(y),z) for x,y in poly]
            wires.append(Part.Wire(Part.makePolygon(pts+[pts[0]]).Edges))
        bodies.append(Part.makeLoft(wires,True,True))
    shape=union(bodies)
    shape=cut(shape,cylinder(3.25,40,z=-1))
    shape=cut(shape,cylinder(7.15,2.15))
    for y in (-8,8):
        for z in (-8,8):shape=cut(shape,cylinder(2.25,6,y,z,-1))
    a.define("P_ROTOR",shape.removeSplitter(),"printed","16 bare curved blades;4mm spoke root+32mm active span+2mm outer end ring,matched6D hub;not air-calibrated")
    yz=a.input["axisYz"];motion={"kind":"shaft","axisYz":yz,"speed":a.red["speedRatios"][0]}
    a.add("P_ROTOR",axis_pose(8,yz[0],yz[1]+Z0),"input",motion)
    for y in (-8,8):
        for z in (-8,8):
            a.hardware("washer",4,(12,yz[0]+y,yz[1]+Z0+z),(1,0,0),group="input",motion=motion)
            a.hardware("bolt",4,(12.8,yz[0]+y,yz[1]+Z0+z),(-1,0,0),12,"input",motion)


def clock_input_collars(a):
    if not C.get("inputCollarStaticBalanceByClocking",False):return
    axis=a.input["axisYz"];center=np.array([0,axis[0],axis[1]+Z0])
    rotating=[i for i in a.instances if i["motion"]["kind"]=="shaft" and i["motion"]["axisYz"]==axis]
    collars=[i for i in rotating if i["part_id"]=="H_INPUT_COLLAR"]
    if len(collars)!=2:raise RuntimeError("Static clocking requires the two unchanged purchased collars")
    def moment(item):
        part=a.defs[item["part_id"]]
        point=(np.array(item["transform"])@np.r_[part["local_com_mm"],1])[:3]
        return part["mass_g"]*(point[1:]-center[1:])
    original=sum((moment(i) for i in rotating),np.zeros(2))
    fixed=sum((moment(i) for i in rotating if i not in collars),np.zeros(2))
    radii=[np.linalg.norm(moment(i)) for i in collars]
    target=-fixed
    if not np.isclose(radii[0],radii[1],atol=1e-8) or np.linalg.norm(target)>sum(radii):
        raise RuntimeError("Purchased collar clocking cannot balance the actual nominal first moment")
    middle=math.atan2(target[1],target[0])
    spread=math.acos(np.linalg.norm(target)/sum(radii))
    rotations=[]
    for item,angle in zip(collars,(middle+spread,middle-spread)):
        before=moment(item);delta_angle=angle-math.atan2(before[1],before[0])
        co,si=math.cos(delta_angle),math.sin(delta_angle)
        change=np.eye(4);change[:3,:3]=[[1,0,0],[0,co,-si],[0,si,co]]
        change[:3,3]=center-change[:3,:3]@center
        item["transform"]=(change@np.array(item["transform"])).tolist()
        feature=a.doc.getObject(item["name"])
        feature.Placement=App.Placement(App.Matrix(*change.ravel().tolist())).multiply(feature.Placement)
        a.world[item["name"]]=transformed(a.defs[item["part_id"]]["shape"],item["transform"])
        rotations.append({"name":item["name"],"additionalClockingDeg":math.degrees(delta_angle),
                          "unchangedAxialDatumXmm":item["transform"][0][3]})
    remaining=sum((moment(i) for i in rotating),np.zeros(2))
    if np.linalg.norm(remaining)>1e-6:raise RuntimeError("Nominal collar clocking did not close the first moment")
    a.collar_balance={"beforeFirstMomentGmm":original.tolist(),"afterFirstMomentGmm":remaining.tolist(),
                      "collars":rotations,"addedParts":0,"removedMaterial":False,
                      "scope":"Actual assembly rotations of two round-bore collars; axial bearing datums unchanged. Nominal single-plane gravity balance only,not measured or dynamic balance."}


def add_gear_shields(a):
    guard=C.get("guards",{})
    if not guard.get("petGearShields",False):return
    thick=guard["petThicknessMm"];flange=guard["petReturnFlangeMm"]
    top=a.input["axisYz"][1]+14
    bottom=min(stage["xMm"]*0+a.red["axesYzMm"][stage["wheelAxis"]][1]
               -stage["wheel"]/2-stage["wheelAddendumCoefficient"]-3
               for stage in a.red["stages"])
    layouts=[("LEFT",-45.5,bottom,top,1),("LOWER_RIGHT",41.8,bottom,guard["lowerRightSheetTopZmm"],-1),
             ("UPPER_RIGHT",-.55,20,top,-1)]
    a.guard_sheet_blanks=[]
    a.guard_cut_scrap=[]
    for name,x,low,high,inward in layouts:
        ymin,ymax=guard["upperSheetBoundsYmm"] if name=="UPPER_RIGHT" else guard["sideSheetBoundsYmm"]
        mounts=[]
        for mount in a.cap_mounts:
            chosen=(name=="LEFT" and mount["side"]<0 and mount["axisYz"][1]==0
                    or name=="LOWER_RIGHT" and mount["side"]>0 and mount["axisYz"][1]==0
                    or name=="UPPER_RIGHT" and mount["side"]>0 and mount["axisYz"] in a.red["axesYzMm"][1:-1])
            if chosen:mounts.append(mount)
        anchors=[]
        for mount in mounts:
            for offset in mount["boltOffsetsYzMm"]:
                offset=np.array(offset,float)
                retained_radius=5.1 if name=="LOWER_RIGHT" else 4.2
                yz=np.array(mount["axisYz"])+offset+retained_radius*offset/np.linalg.norm(offset)
                anchors.append(V(x+thick/2,*yz))
        if not anchors:raise RuntimeError("PET guard has no defined physical attachment")
        def trim(sheet,tool):
            print("BOOLEAN_BEGIN PET",name,flush=True)
            if not sheet.isValid() or not tool.isValid():raise RuntimeError("Invalid PET cutting input")
            fragments=[]
            for material in sheet.Solids:
                fragments.extend(material.cut(solid(tool)).Solids)
            cut_result=Part.makeCompound(fragments)
            if not cut_result.isValid() or not cut_result.Solids:raise RuntimeError("PET cut invalid or removes all material")
            retained=[part for part in cut_result.Solids if any(part.isInside(p,1e-7,False) for p in anchors)]
            split_allowed=name=="UPPER_RIGHT" and len(a.red["stages"])==3
            missing=[list(p) for p in anchors if not any(part.isInside(p,1e-7,False) for part in retained)]
            insufficient=split_allowed and any(sum(part.isInside(p,1e-7,False) for p in anchors)<2 for part in retained)
            if not retained or missing or insufficient or len(retained)>1 and not split_allowed:
                missing=[list(p) for p in anchors if not any(part.isInside(p,1e-7,False) for part in cut_result.Solids)]
                if args.diagnostics:
                    args.diagnostics.mkdir(parents=True,exist_ok=True)
                    cut_result.exportBrep(str(args.diagnostics/f"rejected-{name}-guard.brep"))
                    tool.exportBrep(str(args.diagnostics/f"rejected-{name}-tool.brep"))
                raise RuntimeError(f"Frame clearance separates {name} guard attachment; missing={missing}; preserved={args.diagnostics}; do not discard a functional panel")
            for fragment in cut_result.Solids:
                if any(fragment.isSame(part) for part in retained):continue
                a.guard_cut_scrap.append({"panel":name,"volumeMm3":fragment.Volume,
                                         "centroidMm":list(fragment.CenterOfMass),
                                         "reason":"enclosed frame-slot cutout; no attachment point, removed as sheet scrap"})
            print("BOOLEAN_END PET",name,len(cut_result.Solids),"retained",len(retained),sum(p.Volume for p in retained),flush=True)
            return retained[0] if len(retained)==1 else Part.makeCompound(retained)
        shape=Part.makeBox(thick,ymax-ymin,high-low,V(x,ymin,low))
        if flange:
            raise ValueError("This revision uses flat PET cuts; folded returns need their own manufacturing profile")
        # Round passages clear the full real rotating envelopes, not just
        # the saved crank angle. Left links are wholly outside this panel.
        for station in STATIONS:
            shape=trim(shape,x_cylinder(14.7 if name!="UPPER_RIGHT" else 5,x-10,20,[station,0]))
            if name!="UPPER_RIGHT":shape=trim(shape,x_cylinder(C["fixedPivotPostDiameterMm"]/2+.4,x-10,20,P["P"]+[station,0]))
        for yz in a.red["axesYzMm"][1:-1]:
            radius=14.4 if name=="LEFT" else 11.3
            shape=trim(shape,x_cylinder(radius,x-10,20,yz))
        input_clearance=(a.candidate["rotorDiameterMm"]/2+guard["radialClearanceMm"]+guard["radialWallMm"]+.6
                         if name=="LOWER_RIGHT" else 16.5)
        shape=trim(shape,x_cylinder(input_clearance,x-10,20,a.input["axisYz"]))
        if name=="LEFT":
            for mount in a.cap_mounts:
                if mount["side"]>=0 or mount["axisYz"][1]==0:continue
                for offset in mount["boltOffsetsYzMm"]:
                    yz=np.array(mount["axisYz"])+offset
                    if mount["boltDiameter"]==4:
                        shape=trim(shape,x_cylinder(5.3,x-1,thick+2,yz))
                    else:
                        shape=trim(shape,capsule_x(mount["axisYz"],yz,10.8,x-1,thick+2))
        for member in a.frame_members:
            start=np.array(member["aMm"]);end=np.array(member["bMm"]);delta=end-start
            radius=member["circumDiameterMm"]/2+guard["petFrameClearanceMm"]
            sweep_min=min(start[0],end[0])-radius if name=="LEFT" else x
            sweep_max=max(start[0],end[0])+radius if name=="LOWER_RIGHT" else x+thick
            if abs(delta[0])<1e-8:
                gap=max(sweep_min-start[0],start[0]-sweep_max,0)
                if gap>=radius:continue
                projected_radius=math.sqrt(radius**2-gap**2)
                ends=[start[1:],end[1:]]
            else:
                t=sorted(((sweep_min-radius-start[0])/delta[0],(sweep_max+radius-start[0])/delta[0]))
                lo,hi=max(t[0],0),min(t[1],1)
                if hi<=lo:continue
                ends=[(start+delta*lo)[1:],(start+delta*hi)[1:]];projected_radius=radius
            if np.linalg.norm(ends[1]-ends[0])<1e-8:
                tool=x_cylinder(projected_radius,x-1,thick+2,ends[0])
            else:
                tool=capsule_x(*ends,2*projected_radius,x-1,thick+2)
            if shape.BoundBox.intersect(tool.BoundBox):shape=trim(shape,tool)
        for rail_x in (-39.5,32):
            shape=trim(shape,Part.makeBox(6.8,np.ptp(C["frameRailYmm"])+.8,6.8,
                                         V(rail_x-3.4,C["frameRailYmm"][0]-.4,11.6)))
        for mount in mounts:
            for offset in mount["boltOffsetsYzMm"]:
                yz=np.array(mount["axisYz"])+offset
                diameter=9.2 if name=="LOWER_RIGHT" else 7.2
                shape=trim(shape,x_cylinder(diameter/2,x-10,20,yz))
        matrix=np.eye(4);matrix[2,3]=Z0
        panels=sorted(shape.Solids,key=lambda part:part.CenterOfMass.z)
        piece_ids=[]
        for index,panel in enumerate(panels):
            suffix="" if len(panels)==1 else "_"+str(index+1)
            pid="S_GUARD_"+name+suffix;piece_ids.append(pid)
            a.define(pid,panel,"sheet_cut",
                     "PAC34-05 PET0.5mm flat sheet; full-thickness cuts only. Every retained piece has at least two declared supports; no adhesive or pocket milling.",
                     density=guard["petDensityGcm3Assumed"],sku="PAC34-05")
            a.add(pid,matrix.tolist(),"guards")
        a.guard_sheet_blanks.append({"partId":"S_GUARD_"+name,"piecePartIds":piece_ids,"widthMm":ymax-ymin+2*flange,
                                    "heightMm":high-low,"thicknessMm":thick,
                                    "assembledXmm":x,"lowZmm":low,"highZmm":high,
                                    "materialAttachmentSamplesMm":[list(p) for p in anchors],
                                    "fingersafeOrImpactCertified":False})


def finalize(a):
    changed=[str(p.relative_to(ROOT)) for p in BUILD_INPUTS
             if hashlib.sha256(p.read_bytes()).hexdigest()!=BUILD_HASHES[str(p.relative_to(ROOT))]]
    if changed:raise RuntimeError("CAD inputs changed during build; do not label mixed outputs: "+", ".join(changed))
    out=OUT/a.id;cad=CAD/a.id;stl=PRINT/a.id
    for path in (out,cad,stl):path.mkdir(parents=True,exist_ok=True)
    a.doc.recompute();native=cad/f"Walker_{a.id}.FCStd"
    temporary=cad/f"Walker_{a.id}.new.FCStd";a.doc.saveAs(str(temporary));temporary.replace(native)
    print("STAGE_END native-saved",a.id,native.stat().st_size,flush=True)
    objects=[o for o in a.doc.Objects if o.TypeId=="Part::Feature"]
    step=cad/f"Walker_{a.id}.step";Part.export(objects,str(step))
    step.write_text("\n".join(line.rstrip() for line in step.read_text().splitlines())+"\n")
    print("STAGE_END step-saved",a.id,step.stat().st_size,flush=True)
    meshes={};definitions={}
    for pid,p in a.defs.items():
        vertices,triangles=p["shape"].tessellate(.16)
        meshes[pid]={"vertices":[list(v) for v in vertices],"triangles":triangles,"category":p["category"]}
        definitions[pid]={k:v for k,v in p.items() if k!="shape"}
        if p["category"]=="printed":
            shape=p["shape"].copy()
            # Bed pose is separately recorded; no scaling of the printed parts.
            if pid.startswith("P_CHASSIS_"):
                shape.rotate(V(),V(0,1,0),90 if pid.endswith("_L") else -90)
            elif pid=="P_ROTOR_CAGE_CAP":
                shape.rotate(V(),V(1,0,0),180)
            shape.translate(V(0,0,-shape.BoundBox.ZMin))
            mesh=MeshPart.meshFromShape(Shape=shape,LinearDeflection=.12,AngularDeflection=.18,Relative=False)
            mesh.write(str(stl/(pid+".stl")))
        print("MESH_DONE",a.id,pid,flush=True)
    for file in sorted(stl.glob("*.stl")):
        if file.stem not in definitions or definitions[file.stem]["category"]!="printed":
            print("REMOVE_OBSOLETE_GENERATED_STL",file.name,flush=True)
            file.unlink()
    (cad/"render_geometry.json.gz").write_bytes(gzip.compress(json.dumps(meshes,separators=(",",":")).encode(),mtime=0))
    total=0.;cog=np.zeros(3);printed=0.
    for item in a.instances:
        p=definitions[item["part_id"]];mass=p["mass_g"]
        point=np.array(item["transform"])@np.r_[p["local_com_mm"],1]
        total+=mass;cog+=mass*point[:3]
        if p["category"]=="printed":printed+=mass
    manifest={"revisionId":CFG["revisionId"],"designId":a.id,"parameters":CFG,"candidate":a.candidate,
              "buildInputSha256":BUILD_HASHES,
              "reduction":a.red,"inputLayout":a.input,"bodyOriginZMm":Z0,"parts":definitions,
              "bearingMounts":a.cap_mounts,"frameMembersBeforeUnion":a.frame_members,
              "guardSheetBlanks":getattr(a,"guard_sheet_blanks",[]),
              "guardCutScrap":getattr(a,"guard_cut_scrap",[]),
              "inputCollarClocking":getattr(a,"collar_balance",None),
              "instances":a.instances,"cadMeshes":str((cad/"render_geometry.json.gz").relative_to(ROOT)),
              "nominalTotalMassG":total,"nominalPrintedMassG":printed,"nominalCenterOfMassMm":(cog/total).tolist(),
              "physicalQualification":"UNKNOWN","fullAssemblyVerification":"IN_PROGRESS",
              "manufacturerModelsRedistributed":False,"assemblyReference":"uncompressed supported pose,not dynamic walking CG"}
    write_json(out/"assembly.json",manifest)
    with (out/"BOM.csv").open("w",newline="") as stream:
        w=csv.writer(stream,lineterminator="\n")
        w.writerow(["part_id","category","quantity","sku","unit_nominal_mass_g","total_nominal_mass_g","basis","spec"])
        for pid,p in definitions.items():
            w.writerow([pid,p["category"],a.counts[pid],p["sku"],p["mass_g"],p["mass_g"]*a.counts[pid],p["mass_basis"],p["spec"]])
    App.closeDocument(a.doc.Name)
    from verify_integrated_exports import verify
    print("STAGE_BEGIN native-step-verification",a.id,flush=True)
    verify(a.id,ROOT)
    print(a.id,len(a.instances),"instances",total,"g",printed,"printedg",cog/total,flush=True)


if __name__=="__main__":
    faulthandler.dump_traceback_later(45,repeat=True)
    old=own_r4_parts()
    for candidate in CFG["candidates"]:
        if args.design=="BC" and candidate["id"] not in ("B","C"):continue
        if args.design not in ("all","BC") and args.design!=candidate["id"]:continue
        print("Building complete",candidate["id"],flush=True)
        a=Whole(candidate)
        add_drive(a,old)
        print("STAGE_END drivetrain",candidate["id"],len(a.instances),flush=True)
        if args.stop_after=="drive":
            App.closeDocument(a.doc.Name)
            continue
        print("STAGE_BEGIN frame",candidate["id"],flush=True)
        build_main_frame(a)
        print("STAGE_END frame",candidate["id"],len(a.instances),flush=True)
        if args.stop_after=="frame":
            App.closeDocument(a.doc.Name)
            continue
        print("STAGE_BEGIN legs",candidate["id"],flush=True)
        add_legs(a)
        print("STAGE_BEGIN rotor",candidate["id"],flush=True)
        rotor(a)
        clock_input_collars(a)
        print("STAGE_BEGIN gear-shields",candidate["id"],flush=True)
        add_gear_shields(a)
        print("STAGE_BEGIN export",candidate["id"],flush=True)
        finalize(a)
    faulthandler.cancel_dump_traceback_later()
