"""Stock DN-03 full-tool access in the explicitly isolated foot preassembly."""

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
    def prism(af,start,length):
        points=[App.Vector(af/math.sqrt(3)*math.cos(i*math.pi/3),
                           af/math.sqrt(3)*math.sin(i*math.pi/3),start) for i in range(6)]
        return Part.Face(Part.makePolygon(points+[points[0]])).extrude(App.Vector(0,0,length))
    def driver(swept=False):
        body=Part.makeCylinder(4,75,App.Vector(0,0,.05)).fuse(
             Part.makeCylinder(6.5,70,App.Vector(0,0,75.05)))
        hole=Part.makeCylinder(4.5/2,9.02,App.Vector(0,0,.04)) if swept else prism(4.5,.04,9.02)
        return body.cut(hole)
    def placed(shape,matrix,offset=0):
        value=shape.copy();translation=np.eye(4);translation[2,3]=offset
        value.Placement=App.Placement(App.Matrix(*(matrix@translation).ravel().tolist())).multiply(value.Placement)
        return value
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
            if m.get("piece")!="ROCKER_PIN" or item["part_id"]!="H_LOCK_NUT_M2":continue
            scene=[i for i in a["instances"] if i["motion"].get("station")==m["station"]
                   and i["motion"].get("side")==m["side"]
                   and (i["motion"]["kind"]=="foot" or i["motion"].get("link")=="CEF")]
            matrix=np.asarray(item["transform"]);samples=[]
            for offset in (40,20,10,5,2,0):
                hits=intersections(placed(driver(),matrix,offset),scene)
                samples.append({"withdrawalMm":offset,"intersections":hits})
            rotating=intersections(placed(driver(True),matrix),[i for i in scene if i["name"]!=item["name"]])
            grip=Part.makeCylinder(35,75,App.Vector(0,0,75.05))
            grip_hits=intersections(placed(grip,matrix),scene)
            if not any(i["part_id"].startswith("P_LEG_CEF") for i in scene):
                raise ValueError("The foot-support body was omitted from tool access")
            failures=any(s["intersections"] for s in samples) or bool(rotating) or bool(grip_hits)
            records.append({"targetNut":item["name"],"sceneInstances":[i["name"] for i in scene],
                            "status":"FAIL" if failures else "PASS","insertionSamples":samples,
                            "fullRotationEnvelopeIntersections":rotating,
                            "gripEnvelopeIntersections":grip_hits,
                            "rotationTargetContactTreatment":"Exact hex engagement checked with target present; the continuous outer-tool rotation envelope excludes only that actively driven nut. All other foot parts remain."})
            print("STAGE_END stock-nut-tool",design,item["name"],records[-1]["status"],flush=True)
        if len(records)!=6:raise ValueError("All six stock locking nuts must be checked")
        result={"revisionId":a["revisionId"],"designId":design,"nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "status":"PASS_STOCK_TOOL_ENVELOPE" if all(r["status"]=="PASS" for r in records) else "FAIL",
                "tool":{"manufacturer":"ENGINEER","model":"DN-03","acrossFlatsMm":4.5,
                        "workingEndOuterDiameterMm":8,"workingEndLengthMm":18,"socketDepthMm":9,
                        "shaftLengthMm":75,"overallLengthMm":145,"handleDiameterMm":13,
                        "modeling":"Conservative8mm cylinder for all75mm of metal shaft,plus13mm handle; not an exact cosmetic tool mesh.",
                        "publishedPriceExTaxJpy":360,"catalog":"https://online.fliphtml5.com/jhzqw/fqqa/",
                        "catalogYear":2026,"printedPage":69,"pdfPage":72},
                "scene":"Prepare and tighten the CEF-integrated foot module before adding the other leg links or mounting it on the body. Every foot component is present.",
                "gripEnvelope":{"diameterMm":70,"lengthMm":75,"basis":"Declared design clearance around the handle,not a measured hand or an ergonomics guarantee."},
                "records":records,"toolModelAndPublishedDimensionsConfirmed":True,
                "actualToolOwnershipOrOperationConfirmed":False,
                "limits":["Nylon locking function is not a tested holding-torque or reuse equivalent to two jam nuts.",
                          "The opposite M2 cap screw is held with a normal1.5mm hex tool; actual tightening and prevailing torque remain untested.",
                          "Parts,tool and hands have not been physically fitted. Stock acceptance and final fit checks remain mandatory."]}
        (OUT/design/"rocker_pin_access.json").write_text(json.dumps(result,indent=2)+"\n")
        if result["status"]=="FAIL":raise ValueError("Full stock-tool/hand access failed")
    finally:App.closeDocument(doc.Name)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freecad-lib",required=True)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    args=parser.parse_args();check(args.design,args.freecad_lib)
