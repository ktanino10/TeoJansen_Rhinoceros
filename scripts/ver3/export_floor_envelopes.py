"""Containing native B-rep envelopes; only the two intended rolling pads are exempt."""

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import ConvexHull

from walker_geometry import ROOT,OUT,CAD,body_points
from walker_floor import identity


def export(design,library,output,snapshot=None):
    sys.path.insert(0,library)
    import FreeCAD as App
    import Part
    print("STAGE_BEGIN floor-native-open",design,flush=True)
    folder=OUT/design if snapshot is None else snapshot/design/"docs"
    a=json.loads((folder/"assembly.json").read_text());c=a["parameters"]["common"]
    cad=CAD/design if snapshot is None else snapshot/design/"CAD"
    native=cad/f"Walker_{design}.FCStd";doc=App.openDocument(str(native))
    print("STAGE_END floor-native-open",design,flush=True)
    def moved(shape,matrix):
        value=shape.copy()
        value.Placement=App.Placement(App.Matrix(*matrix.ravel().tolist())).multiply(value.Placement)
        return value
    def corners(shape):
        b=shape.BoundBox
        return list(itertools.product((b.XMin,b.XMax),(b.YMin,b.YMax),(b.ZMin,b.ZMax)))
    def radial_bound(shape,yz):
        bound=0.
        for face in shape.Faces:
            if isinstance(face.Surface,Part.Plane):
                for edge in face.Edges:
                    if isinstance(edge.Curve,Part.Circle):
                        circle=edge.Curve
                        value=np.linalg.norm(np.array([circle.Center.y,circle.Center.z])-yz)+circle.Radius
                    elif isinstance(edge.Curve,Part.Line):
                        value=max(np.linalg.norm(np.array([v.Point.y,v.Point.z])-yz) for v in edge.Vertexes)
                    else:
                        value=max(math.hypot(y-yz[0],z-yz[1]) for _,y,z in corners(edge))
                    bound=max(bound,float(value))
            elif isinstance(face.Surface,Part.Cylinder) and abs(face.Surface.Axis.x)>1-1e-10:
                cylinder=face.Surface
                bound=max(bound,float(np.linalg.norm(np.array([cylinder.Center.y,cylinder.Center.z])-yz)+cylinder.Radius))
            else:
                bound=max(bound,max(math.hypot(y-yz[0],z-yz[1]) for _,y,z in corners(face)))
        return bound
    def circle_points(center,axis,radius):
        axis=np.asarray(axis);axis=axis/np.linalg.norm(axis)
        basis=np.array([1,0,0]) if abs(axis[0])<.9 else np.array([0,1,0])
        u=np.cross(axis,basis);u/=np.linalg.norm(u);v=np.cross(axis,u)
        angles=np.arange(32)*2*math.pi/32
        outside=(radius+1e-8)/math.cos(math.pi/32)
        return np.asarray(center)+outside*(np.cos(angles)[:,None]*u+np.sin(angles)[:,None]*v)
    def enclosing_points(shape,orientation):
        inverse=np.eye(4);inverse[:3,:3]=orientation.T
        aligned=moved(shape,inverse);points=[]
        for face in aligned.Faces:
            if isinstance(face.Surface,Part.Plane):
                for edge in face.Edges:
                    if isinstance(edge.Curve,Part.Circle):
                        curve=edge.Curve
                        points.extend(circle_points(list(curve.Center),list(curve.Axis),curve.Radius))
                    elif isinstance(edge.Curve,Part.Line):
                        points.extend(list(v.Point) for v in edge.Vertexes)
                    else:points.extend(corners(edge))
            elif isinstance(face.Surface,Part.Cylinder):
                cylinder=face.Surface;center=np.asarray(list(cylinder.Center));axis=np.asarray(list(cylinder.Axis))
                positions=(np.asarray(corners(face))-center)@axis
                for position in (positions.min(),positions.max()):
                    points.extend(circle_points(center+position*axis,axis,cylinder.Radius))
            else:points.extend(corners(face))
        cloud=np.unique(np.asarray(points),axis=0)
        if len(cloud)<4:raise ValueError("Incomplete native boundary envelope")
        if np.linalg.matrix_rank(cloud-cloud[0])==3:
            cloud=cloud[ConvexHull(cloud).vertices]
        return (cloud@orientation.T).tolist()
    try:
        representatives={}
        for item in a["instances"]:representatives.setdefault(item["part_id"],item)
        result={};rotating={}
        for item in a["instances"]:
            motion=item["motion"];pid=item["part_id"]
            if motion["kind"] not in ("shaft","crank"):continue
            shape=doc.getObject(item["name"]).Shape.copy()
            yz=np.asarray(motion["axisYz"])+[0,a["bodyOriginZMm"]];box=shape.BoundBox
            radius=max(math.hypot(y-yz[0],z-yz[1]) for _,y,z in corners(shape))
            exact=None
            if pid=="P_OUTPUT_WHEEL":
                stage=a["reduction"]["stages"][-1]
                radius=stage["wheel"]/2+stage["wheelAddendumCoefficient"];exact=True
            elif pid.startswith("P_COMPOUND_"):
                index=int(pid.rsplit("_",1)[1])-1;stage=a["reduction"]["stages"][index]
                radius=stage["wheel"]/2+stage["wheelAddendumCoefficient"];exact=True
            if exact:
                native_radius=radial_bound(shape,yz)
                if native_radius>radius+1e-7:raise ValueError(f"Native rotating solid escapes its floor cylinder: {pid}: {native_radius}>{radius}")
            else:
                native_radius=radius
            rotating[item["name"]]={"radiusMm":radius+1e-7,"nativeXRangeMm":[box.XMin,box.XMax],
                                   "nativeRadiusUpperBoundMm":native_radius,
                                   "containment":"native plane-edge/cylinder analytic bounds; unsupported faces use containing face boxes" if exact else "circumscribed native bounding box"}
        for pid,item in representatives.items():
            shape=doc.getObject(item["name"]).Shape.copy();motion=item["motion"]
            transform=np.asarray(item["transform"]);shape=moved(shape,np.linalg.inv(transform))
            extra={};orientation=np.eye(3)
            if pid.startswith("P_FOOT_"):
                p=body_points(common=c);f=c["foot"]
                gamma=math.atan2(*(p["E"]-p["C"])[::-1])-math.radians(f["pitchReferenceBodyAngleDeg"])
                co,si=math.cos(gamma),math.sin(gamma)
                orientation=np.array([[1,0,0],[0,co,-si],[0,si,co]])
            if motion.get("piece")=="ROCKER":
                p=body_points(common=c);f=c["foot"]
                gamma=math.atan2(*(p["E"]-p["C"])[::-1])-math.radians(f["pitchReferenceBodyAngleDeg"])
                co,si=math.cos(gamma),math.sin(gamma)
                foot=np.eye(4);foot[:3,:3]=[[1,0,0],[0,co,-si],[0,si,co]]
                foot[:3,3]=[f["centerAbsXmm"],p["F"][0]+co*f["toeOffsetFromFNeutralMm"][0],
                           p["F"][1]+si*f["toeOffsetFromFNeutralMm"][0]]
                pivot=f["toeOffsetFromFNeutralMm"][1]
                pads=[moved(Part.makeCylinder(f["toeRadiusMm"],8,App.Vector(x-4,0,pivot),App.Vector(1,0,0)),foot)
                      for x in (-f["rockerHalfSpanMm"],f["rockerHalfSpanMm"])]
                if pid.endswith("_L"):
                    pads=[pad.mirror(App.Vector(),App.Vector(1,0,0)) for pad in pads]
                    foot[0,:]*=-1
                core=shape
                removed=[]
                for pad in pads:
                    overlap=sum(abs(s.Volume) for s in core.common(pad).Solids)
                    if overlap<100:raise ValueError("The declared rolling pad is absent from its native rocker")
                    removed.append(overlap);core=core.cut(pad)
                if not core.isValid() or not core.Solids:raise ValueError("Missing actual non-pad rocker core")
                shape=core
                extra={"excludedContactGeometry":"Only the two radius6mm,width8mm intended rolling-pad cylinders; the remaining rocker core is checked over the full +/-5 degree stop envelope.",
                       "rockerPivot":(foot@np.array([0,0,pivot,1]))[:3].tolist(),
                       "rockerAxis":foot[:3,1].tolist(),"removedNativePadVolumeMm3":removed}
            if all(isinstance(face.Surface,Part.Plane) for face in shape.Faces) and not extra:
                points=[list(v.Point) for v in shape.Vertexes];circles=[]
                for edge in shape.Edges:
                    curve=edge.Curve
                    if isinstance(curve,Part.Circle):
                        circles.append({"center":list(curve.Center),"axis":list(curve.Axis),"radius":curve.Radius})
                    elif not isinstance(curve,Part.Line):
                        points.extend(corners(edge))
                if not points:raise ValueError("No points in a planar native envelope")
                entry={"kind":"planar_boundary","points":points,"circles":circles}
            else:
                entry={"kind":"containing_boundary_hull","points":enclosing_points(shape,orientation),"circles":[]}
            result[pid]={**entry,**extra}
            print("STAGE_END floor-envelope",design,pid,flush=True)
        payload={"designId":design,"revisionId":a["revisionId"],"mechanicalIdentity":identity(a),
                 "nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                 "parts":result,"rotatingInstances":rotating,"allAssemblyPartsRepresented":set(result)==set(a["parts"]),
                 "scope":"Native B-rep bounding boxes or planar edge extrema/full-circle enclosures. Gear cylinders checked against native analytic face/edge upper bounds. Every instance remains checked; only intended rolling-pad volumes are removed from the rocker core.",
                 "physicalFloorTestPerformed":False}
        output.write_text(json.dumps(payload,indent=2)+"\n")
    finally:App.closeDocument(doc.Name)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--snapshot",type=Path)
    args=parser.parse_args()
    export(args.design,args.freecad_lib,args.output,args.snapshot)
