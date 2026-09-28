"""Finite exact-B-rep assembly audit; never treats display envelopes as CAD."""

import argparse
import faulthandler
import json
from pathlib import Path
import sys
import time

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
parser.add_argument("--design",choices=("A","B","C"),required=True)
parser.add_argument("--limit",type=int,default=100000)
args=parser.parse_args()
sys.path.insert(0,args.freecad_lib)
import FreeCAD as App
import Part
from walker_geometry import ROOT,OUT,CAD,nominal_thread_pair


def main():
    folder=OUT/args.design;data=json.loads((folder/"assembly.json").read_text())
    doc=App.openDocument(str(CAD/args.design/f"Walker_{args.design}.FCStd"))
    try:
        items=data["instances"];shapes={i["name"]:doc.getObject(i["name"]).Shape for i in items}
        boxes=[]
        for item in items:
            b=shapes[item["name"]].BoundBox
            boxes.append([b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax])
        boxes=np.array(boxes)
        hits=[];allowed=[];tested=0;start=time.monotonic()
        for i,a in enumerate(items):
            if i%50==0:print("STAGE_BEGIN collision",args.design,i,"/",len(items),tested,flush=True)
            low=np.maximum(boxes[i,:3],boxes[i+1:,:3]);high=np.minimum(boxes[i,3:],boxes[i+1:,3:])
            candidates=np.flatnonzero(np.all(high-low>1e-6,axis=1))+i+1
            for j in candidates:
                b=items[j]
                if nominal_thread_pair(a,b):
                    allowed.append({"a":a["name"],"b":b["name"],"reason":"coaxial corresponding screw/nut nominal threads"})
                    continue
                pa,pb=a["part_id"],b["part_id"]
                # Input hub clamp-state and its threaded M4 fixing holes are
                # declared physical interfaces, not clearance tolerances.
                if {pa,pb}=={"H_INPUT_HUB","H_INPUT_SHAFT"}:
                    allowed.append({"a":a["name"],"b":b["name"],"reason":"manufacturer6D clamp-state reference,physical fit not verified"})
                    continue
                if "H_INPUT_HUB" in (pa,pb) and "H_BOLT_M4_12" in (pa,pb):
                    allowed.append({"a":a["name"],"b":b["name"],"reason":"declared rotor fixing M4 threaded hub holes"})
                    continue
                if tested>=args.limit:break
                first,second=shapes[a["name"]],shapes[b["name"]]
                print("BOOLEAN_BEGIN",a["name"],b["name"],flush=True)
                volume=0.
                for s in first.Solids:
                    for t in second.Solids:
                        # Individual solids avoid FreeCAD's recursive compound
                        # cut bug without fusing independent assembly bodies.
                        common=s.common(t)
                        volume+=sum(abs(x.Volume) for x in common.Solids)
                tested+=1
                if volume>1e-5:
                    row={"a":a["name"],"aPart":pa,"aGroup":a["group"],
                         "b":b["name"],"bPart":pb,"bGroup":b["group"],"overlapMm3":volume,
                         "intersectionBoundsMinMm":low[j-i-1].tolist(),"intersectionBoundsMaxMm":high[j-i-1].tolist()}
                    hits.append(row)
                    if volume>10:print("COLLISION",a["name"],b["name"],f"{volume:.3f}mm3",flush=True)
            if tested>=args.limit:break
        result={"designId":args.design,"revisionId":data["revisionId"],"poses":["saved reference assembly"],
                "exactPairsTested":tested,"limited":tested>=args.limit,"unintendedIntersections":hits,
                "declaredThreadAndClampInterfaces":allowed,
                "status":"FAIL" if hits else "UNKNOWN" if tested>=args.limit else "PASS",
                "elapsedSeconds":time.monotonic()-start,
                "scope":"static saved B-reps only; no full-cycle or tolerance sweep approval"}
        (folder/"static_collisions.json").write_text(json.dumps(result,indent=2)+"\n")
        print("STAGE_END collision",args.design,"tested",tested,"hits",len(hits),"elapsed",time.monotonic()-start,flush=True)
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":
    faulthandler.dump_traceback_later(45,repeat=True)
    main()
    faulthandler.cancel_dump_traceback_later()
