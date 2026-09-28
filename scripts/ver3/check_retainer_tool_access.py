"""Required working-end tool envelopes at the corrected B retainer, not a tool purchase."""

import argparse
import hashlib
import json
import math
import sys

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
args=parser.parse_args()
sys.path.insert(0,args.freecad_lib)
import FreeCAD as App
import Part

from walker_geometry import OUT,CAD


def prism(points,x,width):
    points=[App.Vector(x,*point) for point in points]
    return Part.Face(Part.makePolygon(points+[points[0]])).extrude(App.Vector(width,0,0))


def wrench(x,y,z,away,outer=7.6,thickness=1.8):
    head=Part.makeCylinder(outer/2,thickness,App.Vector(x-thickness/2,y,z),App.Vector(1,0,0))
    handle_y=y-30 if away<0 else y+3
    handle=Part.makeBox(thickness,27,3,App.Vector(x-thickness/2,handle_y,z-1.5))
    head=head.fuse(handle)
    points=[(y+5.65/math.sqrt(3)*math.cos(i*math.pi/3),
             z+5.65/math.sqrt(3)*math.sin(i*math.pi/3)) for i in range(6)]
    head=head.cut(prism(points,x-thickness/2-.1,thickness+.2))
    opening_y=y if away<0 else y-8
    head=head.cut(Part.makeBox(thickness+.2,8,5.65,App.Vector(x-thickness/2-.1,opening_y,z-2.825)))
    return head


def main():
    folder=OUT/"B";data=json.loads((folder/"assembly.json").read_text())
    stage=data["reduction"]["stages"][-1];axis=np.array(data["reduction"]["axesYzMm"][stage["pinionAxis"]])
    mount=next(m for m in data["bearingMounts"] if m["side"]>0 and np.allclose(m["axisYz"],axis))
    native=CAD/"B"/"Walker_B.FCStd";doc=App.openDocument(str(native))
    try:
        records=[];all_shapes={i["name"]:doc.getObject(i["name"]).Shape for i in data["instances"]}
        for item in data["instances"]:
            if item["part_id"]!="H_NUT_M3" or item["group"]!="bearing_caps":continue
            origin=np.array(item["transform"])[:3,3]
            yz=origin[1:]-[0,data["bodyOriginZMm"]]
            if origin[0]>=0 or not any(np.linalg.norm(yz-axis-offset)<1e-6 for offset in mount["boltOffsetsYzMm"]):continue
            nut=all_shapes[item["name"]];center=nut.CenterOfMass
            tool=wrench(center.x,center.y,center.z,1 if center.y>axis[0] else -1)
            intersections=[]
            for other in data["instances"]:
                shape=all_shapes[other["name"]]
                a,b=tool.BoundBox,shape.BoundBox
                if not all(min(getattr(a,k+"Max"),getattr(b,k+"Max"))-
                           max(getattr(a,k+"Min"),getattr(b,k+"Min"))>1e-6 for k in "XYZ"):continue
                print("BOOLEAN_BEGIN retainer-tool",item["name"],other["name"],flush=True)
                volume=sum(abs(s.Volume) for first in tool.Solids for second in shape.Solids
                           for s in first.common(second).Solids)
                if volume>1e-5:intersections.append({"part":other["name"],"overlapMm3":volume})
            records.append({"targetNut":item["name"],"toolHeadOuterWidthMm":7.6,"toolThicknessMm":1.8,
                            "toolAcrossFlatsMm":5.65,"workingHandleLengthMm":27,
                            "status":"PASS" if not intersections else "FAIL","intersections":intersections})
        if len(records)!=4:raise ValueError("Expected four jam nuts on the final-stage right retainer")
        result={"revisionId":data["revisionId"],"designId":"B",
                "nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "status":"PASS_REQUIRED_TOOL_ENVELOPE" if all(r["status"]=="PASS" for r in records) else "FAIL",
                "stopCrankDeg":0,"retainerOffsetsYzMm":mount["boltOffsetsYzMm"],
                "nominalCapHoleEdgeWallMm":4.5-(mount["boltDiameter"]/2+.25),
                "nominalCarrierBossHoleEdgeWallMm":5-(mount["boltDiameter"]/2+.25),
                "records":records,
                "actualToolModelOrOwnershipConfirmed":False,
                "limits":["This verifies required miniature-spanner working-end dimensions,not an identified manufacturer's complete handle or an actual user's tool.",
                          "A larger spanner is not assumed to fit. Actual tools and tightening forces remain a pre-build acceptance condition.",
                          "Nominal CAD clearance is not a tolerance or deformation guarantee; no physical wrench operation was performed."]}
        (folder/"retainer_tool_access.json").write_text(json.dumps(result,indent=2)+"\n")
        print(result["status"],flush=True)
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":main()
