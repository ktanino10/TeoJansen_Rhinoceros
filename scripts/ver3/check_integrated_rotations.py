"""Conservative rotating-section clearance against actual stationary B-reps."""

import argparse
import hashlib
import json
import math
import sys
import time

import numpy as np
from shapely.geometry import GeometryCollection,Point,Polygon

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
parser.add_argument("--design",choices=("A","B","C"),required=True)
options=parser.parse_args()
sys.path.insert(0,options.freecad_lib)
import FreeCAD as App
import Part

from walker_geometry import OUT,CAD,involute_outline


def box_overlap(a,b):
    return all(min(getattr(a,k+"Max"),getattr(b,k+"Max"))-
               max(getattr(a,k+"Min"),getattr(b,k+"Min"))>1e-6 for k in "XYZ")


def volume(shape):
    return sum(abs(s.Volume) for s in shape.Solids)


def section_radius(shape,x,axis):
    radius=0.;inner=float("inf");unsupported=[]
    for wire in shape.slice(App.Vector(1,0,0),x):
        for edge in wire.Edges:
            curve=edge.Curve
            if isinstance(curve,Part.Circle) and abs(curve.Axis.x)>.999999:
                center=np.array([curve.Center.y,curve.Center.z])
                distance=float(np.linalg.norm(center-axis))
                radius=max(radius,distance+curve.Radius)
                inner=min(inner,abs(distance-curve.Radius))
            elif isinstance(curve,Part.Line):
                ends=[np.array([v.Point.y,v.Point.z]) for v in edge.Vertexes]
                for point in ends:
                    radius=max(radius,float(np.linalg.norm(point-axis)))
                if len(ends)==2:
                    delta=ends[1]-ends[0];length=np.dot(delta,delta)
                    fraction=np.clip(np.dot(axis-ends[0],delta)/length,0,1) if length>0 else 0
                    inner=min(inner,float(np.linalg.norm(ends[0]+fraction*delta-axis)))
            else:
                unsupported.append(type(curve).__name__)
                inner=0.
                for point in edge.discretize(Deflection=.001):
                    radius=max(radius,float(np.linalg.norm(np.array([point.y,point.z])-axis))+.002)
    if not math.isfinite(inner) or shape.isInside(App.Vector(x,*axis),1e-8,False):inner=0.
    return radius,inner,unsupported


def sections(item,shape,data):
    axis=np.array(item["motion"]["axisYz"])+[0,data["bodyOriginZMm"]]
    if item["part_id"]=="P_ROTOR":
        return [(shape.BoundBox.XMin,shape.BoundBox.XMax,data["candidate"]["rotorDiameterMm"]/2,0)],[],axis
    if item["part_id"]=="H_INPUT_SHAFT":
        return [(shape.BoundBox.XMin,shape.BoundBox.XMax,3,0)],[],axis
    if item["part_id"].startswith("P_COMPOUND_"):
        index=int(item["part_id"].rsplit("_",1)[1])
        incoming,outgoing=data["reduction"]["stages"][index-1:index+1]
        width=data["parameters"]["common"]["gears"]["faceWidthMm"]
        end=data["parameters"]["common"]["intermediateJournalEndXmm"]
        pieces=[
            (incoming["xMm"],incoming["xMm"]+width,incoming.get("moduleMm",1)*(incoming["wheel"]/2+incoming["wheelAddendumCoefficient"]+incoming["wheelProfileShift"])),
            (outgoing["xMm"],outgoing["xMm"]+width,outgoing.get("moduleMm",1)*(outgoing["pinion"]/2+outgoing["pinionAddendumCoefficient"]+outgoing["pinionProfileShift"])),
            (incoming["xMm"],outgoing["xMm"]+width,min(9.5,outgoing.get("moduleMm",1)*(outgoing["pinion"]/2-1.5+outgoing["pinionProfileShift"]))),
            (-45,incoming["xMm"],4),(-39.8,incoming["xMm"],4.6),
            (outgoing["xMm"]+width,end,4),(outgoing["xMm"]+width,-6.8,4.6)]
        ends=sorted({v for lo,hi,_ in pieces for v in (lo,hi)})
        result=[]
        for lo,hi in zip(ends,ends[1:]):
            mid=(lo+hi)/2
            radius=max((r for first,last,r in pieces if first<=mid<=last),default=0)
            if radius:
                result.append((lo,hi,radius,data["parameters"]["common"]["hexPrintedBoreAcrossFlatsMm"]/2))
        if not np.allclose([result[0][0],result[-1][1]],[shape.BoundBox.XMin,shape.BoundBox.XMax],atol=1e-6):
            raise ValueError("Compound axial segments disagree with actual native bounds")
        return result,[],axis
    ends=sorted({round(v.Point.x,7) for v in shape.Vertexes}|
                {shape.BoundBox.XMin,shape.BoundBox.XMax})
    result=[];unsupported=[]
    for low,high in zip(ends,ends[1:]):
        if high-low<1e-5:continue
        radii=[];inners=[]
        for fraction in (.01,.5,.99):
            print("STAGE_BEGIN axial-section",item["name"],low+(high-low)*fraction,flush=True)
            radius,inner,curves=section_radius(shape,low+(high-low)*fraction,axis)
            if radius==0:
                unsupported.append("empty_sampled_section")
                continue
            radii.append(radius);inners.append(inner);unsupported.extend(curves)
        if radii:result.append((low,high,max(radii),min(inners)))
    return result,sorted(set(unsupported)),axis


def gear_face_check(data,objects):
    results=[];common=data["parameters"]["common"]
    stages=data["reduction"]["stages"]
    for index,stage in enumerate(stages):
        for role,part_id in (
            ("pinion","P_INPUT_PINION" if index==0 else f"P_COMPOUND_{index}"),
            ("wheel","P_OUTPUT_WHEEL" if index==len(stages)-1 else f"P_COMPOUND_{index+1}"),
        ):
            print("STAGE_BEGIN gear-face",data["designId"],index,role,part_id,flush=True)
            item=next(i for i in data["instances"] if i["part_id"]==part_id)
            shape=objects[item["name"]]
            axis=stage[role+"Axis"];yz=np.array(data["reduction"]["axesYzMm"][axis])+[0,data["bodyOriginZMm"]]
            points=involute_outline(stage.get("moduleMm",1),stage[role],stage.get("pressureAngleDeg",25),.3,
                                    profile_shift=stage[role+"ProfileShift"],
                                    addendum_coefficient=stage[role+"AddendumCoefficient"])
            angle=stage[role+"ToothDatumRad"];c,s=math.cos(angle),math.sin(angle)
            points=points@np.array([[c,s],[-s,c]])+yz
            expected=Polygon(points)
            if not expected.is_valid:raise ValueError("Invalid canonical tooth polygon")
            root=stage.get("moduleMm",1)*(stage[role]/2-1.25+stage[role+"ProfileShift"])
            band=expected.difference(Point(*yz).buffer(root-.1,quad_segs=512))
            samples=[]
            for local in (.1,common["gears"]["faceWidthMm"]/2,common["gears"]["faceWidthMm"]-.1):
                x=stage["xMm"]+local
                print("STAGE_BEGIN actual-gear-section",part_id,x,flush=True)
                actual=GeometryCollection()
                wires=shape.slice(App.Vector(1,0,0),x)
                if not wires:raise ValueError("Missing actual gear face section")
                for wire in wires:
                    coordinates=np.array([(p.y,p.z) for p in wire.discretize(Deflection=.0001)])
                    # Close numerically identical trimmed-curve endpoints on
                    # a1e-8mm grid; no buffering or topological repair.
                    section=Polygon(np.round(coordinates,8))
                    if not section.is_valid:raise ValueError("Invalid native section polygon; no polygon repair applied")
                    actual=actual.symmetric_difference(section)
                samples.append({"xMm":x,"excessAreaMm2":actual.difference(expected).area,
                                "missingToothAreaMm2":band.difference(actual).area})
            excess=max(s["excessAreaMm2"] for s in samples);missing=max(s["missingToothAreaMm2"] for s in samples)
            results.append({"stage":index,"role":role,"partId":part_id,
                            "actualBrepSections":samples,"curveChordDeflectionMm":.0001,
                            "coordinateRoundoffGridMm":1e-8,
                            "maximumExcessAreaMm2":excess,"maximumMissingToothAreaMm2":missing,
                            "status":"PASS" if max(excess,missing)<1e-5 else "FAIL"})
    return results


def main():
    folder=OUT/options.design;data=json.loads((folder/"assembly.json").read_text())
    native=CAD/options.design/f"Walker_{options.design}.FCStd"
    print("STAGE_BEGIN rotation-native-open",options.design,flush=True)
    doc=App.openDocument(str(native))
    print("STAGE_END rotation-native-open",options.design,flush=True)
    try:
        objects={i["name"]:doc.getObject(i["name"]).Shape.copy() for i in data["instances"]}
        fixed=[i for i in data["instances"] if i["motion"]["kind"]=="body"]
        moving=[i for i in data["instances"] if i["motion"]["kind"]=="shaft"
                and i["group"] in ("input","reducer","synchronization")]
        hits=[];unproven=[];count=0;start=time.monotonic();section_cache={}
        profiles=gear_face_check(data,objects)
        for index,item in enumerate(moving):
            print("STAGE_BEGIN rotational-envelope",item["name"],index,len(moving),flush=True)
            axis=np.array(item["motion"]["axisYz"])+[0,data["bodyOriginZMm"]]
            relative=np.array(item["transform"]);relative[1:3,3]-=axis
            cache_key=(item["part_id"],tuple(np.round(relative.ravel(),8)))
            if cache_key not in section_cache:
                spans,curves,_=sections(item,objects[item["name"]],data)
                section_cache[cache_key]=(spans,curves)
            spans,curves=section_cache[cache_key]
            if curves:unproven.append({"name":item["name"],"curveTypes":curves})
            for low,high,radius,inner in spans:
                envelope=Part.makeCylinder(radius,high-low,App.Vector(low,*axis),App.Vector(1,0,0))
                if inner>1e-7:
                    envelope=envelope.cut(Part.makeCylinder(inner,high-low,App.Vector(low,*axis),App.Vector(1,0,0)))
                for stationary in fixed:
                    shape=objects[stationary["name"]]
                    if not box_overlap(envelope.BoundBox,shape.BoundBox):continue
                    print("BOOLEAN_BEGIN rotation",item["name"],stationary["name"],low,high,flush=True)
                    intersection=sum(volume(envelope.common(s)) for s in shape.Solids);count+=1
                    if intersection>1e-4:
                        hits.append({"moving":item["name"],"fixed":stationary["name"],"xIntervalMm":[low,high],
                                     "envelopeRadiusMm":radius,"envelopeIntersectionMm3":intersection})
        failed_profiles=any(p["status"]=="FAIL" for p in profiles)
        result={"revisionId":data["revisionId"],"designId":options.design,
                "nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "status":"FAIL" if failed_profiles else "UNKNOWN" if hits or unproven else "PASS",
                "continuousClearanceProof":False,
                "actualGearFaceProfiles":profiles,"envelopeIntersections":hits,
                "unsupportedAnalyticCurveBounds":unproven,"exactEnvelopePairs":count,
                "elapsedSeconds":time.monotonic()-start,
                "scope":"Finite axial-section radial envelopes of input,reducer and synchronous gears against stationary real solids. Crank/leg/foot motion has separate216-pose checks. Actual tooth-face material is checked; axial section sampling and unsupported curves are not a continuous-clearance proof. Envelope hits are candidates,not proof of real collision."}
        (folder/"rotating_clearance.json").write_text(json.dumps(result,indent=2)+"\n")
        print("STAGE_END rotational-envelope",result["status"],count,len(hits),flush=True)
        if result["status"]!="PASS":raise ValueError("Rotating-geometry verification did not pass")
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":main()
