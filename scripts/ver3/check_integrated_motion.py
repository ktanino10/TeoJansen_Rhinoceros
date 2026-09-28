"""Finite actual-CAD gait and guided-foot clearance checks, not dynamics."""

import argparse
from collections import Counter
import itertools
import json
import math
import sys
import time

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
parser.add_argument("--design",choices=("A","B","C"),required=True)
parser.add_argument("--step-deg",type=float,default=10)
parser.add_argument("--foot-only",action="store_true")
args=parser.parse_args()
sys.path.insert(0,args.freecad_lib)
import FreeCAD as App
import Part

from walker_geometry import OUT,CAD,body_points,rigids,link_pose,nominal_thread_pair


def rotation(axis,angle,point):
    x,y,z=np.array(axis)/np.linalg.norm(axis)
    c,s=math.cos(angle),math.sin(angle);q=1-c
    r=np.array([[c+x*x*q,x*y*q-z*s,x*z*q+y*s],
                [y*x*q+z*s,c+y*y*q,y*z*q-x*s],
                [z*x*q-y*s,z*y*q+x*s,c+z*z*q]])
    matrix=np.eye(4);matrix[:3,:3]=r;matrix[:3,3]=point-r@point
    return matrix


def displacement(vector):
    matrix=np.eye(4);matrix[:3,3]=vector
    return matrix


def moved(shape,matrix):
    result=shape.copy()
    result.Placement=App.Placement(App.Matrix(*matrix.ravel().tolist())).multiply(result.Placement)
    return result


def transform(item,theta,common,body_z,compression,rocker,frames):
    m=item["motion"];kind=m["kind"]
    if kind=="body":return np.eye(4)
    if kind in ("shaft","crank"):
        return rotation([1,0,0],theta*m["speed"],np.array([0,m["axisYz"][0],body_z+m["axisYz"][1]]))
    key=(m["station"],m["side"],m["phase"])
    p,initial,reference=frames[key]
    if kind=="joint":
        shift=np.r_[0,p[m["node"]]-initial[m["node"]]]
        delta=displacement(shift)
        if m["node"]=="A":
            center=np.array([0,p["A"][0]+m["station"],p["A"][1]+body_z])
            delta=rotation([1,0,0],theta,center)@delta
        return delta
    name=m["link"] if kind=="link" else "CEF"
    now=np.array(link_pose(p,reference,rigids()[name],m["station"],body_z))
    before=np.array(link_pose(initial,reference,rigids()[name],m["station"],body_z))
    delta=now@np.linalg.inv(before)
    if kind=="foot":
        gamma=math.atan2(*(p["E"]-p["C"])[::-1])-math.radians(common["foot"]["pitchReferenceBodyAngleDeg"])
        shift=np.array([0,-math.sin(gamma)*compression,math.cos(gamma)*compression])
        if m["piece"] in ("SLIDER","ROCKER","ROCKER_PIN","SPRING"):delta=displacement(shift)@delta
        if m["piece"]=="ROCKER":
            dy,dz=common["foot"]["toeOffsetFromFNeutralMm"]
            pivot=np.array([m["side"]*common["foot"].get("centerAbsXmm",61),
                            m["station"]+p["F"][0]+dy*math.cos(gamma)-dz*math.sin(gamma),
                            body_z+p["F"][1]+dy*math.sin(gamma)+dz*math.cos(gamma)])+shift
            delta=rotation([0,math.cos(gamma),math.sin(gamma)],rocker,pivot)@delta
    return delta


def main():
    folder=OUT/args.design;data=json.loads((folder/"assembly.json").read_text())
    common=data["parameters"]["common"];body_z=data["bodyOriginZMm"]
    doc=App.openDocument(str(CAD/args.design/f"Walker_{args.design}.FCStd"))
    try:
        items=[i for i in data["instances"] if i["group"] in
               ("frame","frame_splice","guards","legs","feet","mainshafts","cranks","bearings","bearing_caps")]
        if args.foot_only:
            items=[i for i in items if i["motion"].get("station")==0 and i["motion"].get("side")==1
                   and (i["motion"]["kind"]=="foot" or i["motion"].get("link")=="CEF")]
        original={i["name"]:doc.getObject(i["name"]).Shape.copy() for i in items}
        reference=body_points(0,common=common)
        keys={(i["motion"]["station"],i["motion"]["side"],i["motion"]["phase"])
              for i in items if "phase" in i["motion"]}
        cache={};hits=[];start=time.monotonic();tested=0;poses=0
        phases=[0] if args.foot_only else np.arange(0,360,args.step_deg)
        strokes=np.linspace(0,6,13) if args.foot_only else (0,6)
        rocker_angles=(-5,0,5)
        for degrees,stroke,rocker_deg in itertools.product(phases,strokes,rocker_angles):
            poses+=1;theta=math.radians(degrees)
            frames={k:(body_points(theta+k[2],common=common),
                       body_points(k[2],common=common),reference) for k in keys}
            matrices={i["name"]:transform(i,theta,common,body_z,stroke,math.radians(rocker_deg),frames)
                      for i in items}
            shapes={i["name"]:moved(original[i["name"]],matrices[i["name"]]) for i in items}
            # The continuous annulus contains every coil wire at this length.
            # It is only a conservative audit envelope, never an exported part.
            for item in items:
                if item["motion"].get("piece")!="SPRING":continue
                foot=common["foot"];height=foot["springFreeLengthMm"]-stroke
                r=foot["springOuterDiameterMm"]/2
                envelope=Part.makeCylinder(r,height).cut(
                    Part.makeCylinder(r-foot["springWireMm"],height+2,App.Vector(0,0,-1)))
                matrix=matrices[item["name"]]@np.array(item["transform"])
                shapes[item["name"]]=moved(envelope,matrix)
            boxes=[]
            effective=[]
            for item in items:
                b=shapes[item["name"]].BoundBox
                boxes.append([b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax])
                effective.append(matrices[item["name"]]@np.array(item["transform"]))
            boxes=np.array(boxes)
            print("STAGE_BEGIN motion",args.design,poses,degrees,stroke,rocker_deg,"pairs",tested,flush=True)
            for i,first in enumerate(items):
                low=np.maximum(boxes[i,:3],boxes[i+1:,:3]);high=np.minimum(boxes[i,3:],boxes[i+1:,3:])
                js=np.flatnonzero(np.all(high-low>1e-6,axis=1))+i+1
                for j in js:
                    second=items[j]
                    if first["motion"]["kind"]==second["motion"]["kind"]=="body":continue
                    a={**first,"transform":effective[i].tolist()}
                    b={**second,"transform":effective[j].tolist()}
                    if nominal_thread_pair(a,b):continue
                    relative=np.linalg.inv(effective[i])@effective[j]
                    is_spring=first["motion"].get("piece")=="SPRING" or second["motion"].get("piece")=="SPRING"
                    key=(first["part_id"],second["part_id"],tuple(np.round(relative.ravel(),12)),
                         float(stroke) if is_spring else None)
                    if key not in cache:
                        print("BOOLEAN_BEGIN motion",first["name"],second["name"],flush=True)
                        intersection=[]
                        for x in shapes[first["name"]].Solids:
                            for y in shapes[second["name"]].Solids:
                                intersection.extend(x.common(y).Solids)
                        cache[key]=sum(abs(s.Volume) for s in intersection);tested+=1
                    volume=cache[key]
                    if volume>1e-5:
                        row={"crankDeg":float(degrees),"compressionMm":float(stroke),"rockerDeg":rocker_deg,
                             "a":first["name"],"b":second["name"],"aPart":first["part_id"],"bPart":second["part_id"],
                             "overlapMm3":volume,"springConservativeEnvelope":is_spring}
                        hits.append(row)
                        print("COLLISION",first["name"],second["name"],volume,flush=True)
            if poses%12==0:
                print("STAGE_END motion",poses,"uniquePairs",tested,"hits",len(hits),flush=True)
        result={"revisionId":data["revisionId"],"designId":args.design,
                "status":"FAIL" if hits else "PASS","poses":poses,"exactOrConservativePairs":tested,
                "crankStepDeg":None if args.foot_only else args.step_deg,
                "compressionSamplesMm":[float(x) for x in strokes],"rockerSamplesDeg":list(rocker_angles),
                "unintendedIntersections":hits,"elapsedSeconds":time.monotonic()-start,
                "scope":"actual saved B-reps for gait/feet/frame/mainshafts. Springs use conservative annuli; fast rotor/reducer and manufacturing error are separate checks. Finite samples,not continuous proof.",
                "parametersFromSavedAssembly":True}
        target=folder/("foot_motion.json" if args.foot_only else "gait_motion.json")
        target.write_text(json.dumps(result,indent=2)+"\n")
        print("STAGE_END motion-audit",args.design,"poses",poses,"hits",len(hits),"seconds",time.monotonic()-start,flush=True)
        if result["status"]!="PASS":raise ValueError("Finite motion verification did not pass")
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":
    main()
