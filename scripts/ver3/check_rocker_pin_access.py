"""Finite miniature-tool access to recessed rocker-pin seats, before mounting the legs."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from walker_geometry import OUT,CAD


def check(design,library):
    sys.path.insert(0,library)
    import FreeCAD as App
    import Part
    a=json.loads((OUT/design/"assembly.json").read_text())
    native=CAD/design/f"Walker_{design}.FCStd";doc=App.openDocument(str(native))
    def prism(points,start,length):
        wire=[App.Vector(x,y,start) for x,y in points]
        return Part.Face(Part.makePolygon(wire+[wire[0]])).extrude(App.Vector(0,0,length))
    def wrench(angle):
        depth=.8;start=.75;radius=3.8
        head=Part.makeCylinder(radius,depth,App.Vector(0,0,start))
        u=np.array([math.cos(angle),math.sin(angle)]);v=np.array([-u[1],u[0]])
        rectangle=[u*length+v*width for length,width in ((3,-1.5),(30,-1.5),(30,1.5),(3,1.5))]
        head=head.fuse(prism(rectangle,start,depth))
        hexagon=[[4.15/math.sqrt(3)*math.cos(i*math.pi/3),4.15/math.sqrt(3)*math.sin(i*math.pi/3)] for i in range(6)]
        head=head.cut(prism(hexagon,start-.01,depth+.02))
        mouth=[-u*length+v*width for length,width in ((0,-2.075),(8,-2.075),(8,2.075),(0,2.075))]
        return head.cut(prism(mouth,start-.01,depth+.02))
    def intersections(tool,items):
        hits=[]
        for item in items:
            shape=doc.getObject(item["name"]).Shape
            first,second=tool.BoundBox,shape.BoundBox
            if not all(min(getattr(first,k+"Max"),getattr(second,k+"Max"))-
                       max(getattr(first,k+"Min"),getattr(second,k+"Min"))>1e-6 for k in "XYZ"):continue
            volume=sum(abs(s.Volume) for x in tool.Solids for y in shape.Solids for s in x.common(y).Solids)
            if volume>1e-5:hits.append({"instance":item["name"],"overlapMm3":volume})
        return hits
    try:
        records=[]
        for item in a["instances"]:
            m=item["motion"]
            if m.get("piece")!="ROCKER_PIN" or item["part_id"]!="H_NUT_M2":continue
            scene=[i for i in a["instances"] if i["motion"].get("station")==m["station"]
                   and i["motion"].get("side")==m["side"]]
            matrix=np.asarray(item["transform"])
            choices=[]
            for angle in np.deg2rad((45,135,225,315)):
                tool=wrench(float(angle))
                tool.Placement=App.Placement(App.Matrix(*matrix.ravel().tolist())).multiply(tool.Placement)
                hits=intersections(tool,scene)
                choices.append({"handleAngleDeg":float(np.degrees(angle)),"intersections":hits})
            usable=next((r for r in choices if not r["intersections"]),None)
            records.append({"targetNut":item["name"],"sceneInstances":[i["name"] for i in scene],
                            "status":"PASS" if usable else "FAIL","selected":usable,"tested":choices})
            print("STAGE_END rocker-nut-tool",design,item["name"],records[-1]["status"],flush=True)
        if len(records)!=12:raise ValueError("Both jam nuts on all six feet must be checked")
        result={"revisionId":a["revisionId"],"designId":design,"nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "status":"PASS_REQUIRED_TOOL_ENVELOPE" if all(r["status"]=="PASS" for r in records) else "FAIL",
                "tool":{"acrossFlatsMm":4.15,"headOuterMm":7.6,"thicknessMm":.8,"workingHandleMm":27},
                "scene":"Each complete leg/foot preassembly before body installation; no foot component omitted.",
                "records":records,"actualToolModelOrOwnershipConfirmed":False,
                "limits":["Finite working-end access,not torque/preload or a confirmed real user's tool.",
                          "The recessed inner nut requires a spanner working-end thickness<=0.8mm; do not substitute a thicker tool.",
                          "Physical cutting/deburring,thread engagement and final fitting remain unperformed."]}
        (OUT/design/"rocker_pin_access.json").write_text(json.dumps(result,indent=2)+"\n")
        if result["status"]=="FAIL":raise ValueError("Rocker-pin tool access failed")
    finally:App.closeDocument(doc.Name)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    args=parser.parse_args();check(args.design,args.freecad_lib)
