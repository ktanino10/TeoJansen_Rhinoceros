"""Finite rigid insertion/removal paths using saved native solids and stages."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
parser.add_argument("--design",choices=("A","B","C"),required=True)
parser.add_argument("--stage")
parser.add_argument("--output-dir",type=Path)
args=parser.parse_args()
sys.path.insert(0,args.freecad_lib)
import FreeCAD as App
import Part

from walker_geometry import OUT,CAD
from build_integrated_contract import assembly_stages,assembly_path_scenarios


def broad(first,second):
    a,b=first.BoundBox,second.BoundBox
    return all(min(getattr(a,k+"Max"),getattr(b,k+"Max"))-
               max(getattr(a,k+"Min"),getattr(b,k+"Min"))>1e-6 for k in "XYZ")


def overlap(first,second):
    return sum(abs(s.Volume) for a in first.Solids for b in second.Solids
               for s in a.common(b).Solids)


def translated(shape,vector):
    result=shape.copy();result.translate(App.Vector(*vector));return result


def stages(data):
    items={item["name"]:item for item in data["instances"]}
    workflow=assembly_stages(data)
    notes={stage["id"]:stage["noteJa"] for stage in workflow}
    return [{**path,"moving":[items[name] for name in path["movingNames"]],
             "fixed":[items[name] for name in path["fixedNames"]],
             "note":notes[path["workflowStageId"]]} for path in assembly_path_scenarios(data,workflow)]


def main():
    folder=OUT/args.design;native=CAD/args.design/f"Walker_{args.design}.FCStd"
    data=json.loads((folder/"assembly.json").read_text())
    doc=App.openDocument(str(native))
    try:
        shapes={i["name"]:doc.getObject(i["name"]).Shape.copy() for i in data["instances"]}
        results=[];began=time.monotonic()
        for stage in stages(data):
            if args.stage and stage["id"]!=args.stage:continue
            intersections=[];reference=[];tested=0
            for distance in stage["distancesMm"]:
                vector=np.array(stage["direction"])*distance+stage["constantOffsetMm"]+np.array(stage["sceneOffsetMm"])
                print("STAGE_BEGIN access",stage["id"],distance,flush=True)
                for first in stage["moving"]:
                    moving=translated(shapes[first["name"]],vector)
                    for second in stage["fixed"]:
                        fixed_vector=np.array(stage["sceneOffsetMm"])+stage["fixedPoseOverridesByName"].get(second["name"],[0,0,0])
                        fixed=(translated(shapes[second["name"]],fixed_vector)
                               if np.any(fixed_vector) else shapes[second["name"]])
                        if not broad(moving,fixed):continue
                        print("BOOLEAN_BEGIN access",first["name"],second["name"],flush=True)
                        volume=overlap(moving,fixed);tested+=1
                        if volume<=1e-5:continue
                        row={"distanceMm":distance,"moving":first["name"],"fixed":second["name"],"overlapMm3":volume}
                        pair={first["part_id"],second["part_id"]}
                        if pair=={"H_INPUT_SHAFT","H_INPUT_HUB"} and volume<=1:
                            reference.append({**row,"status":"UNKNOWN clamp opening state; manufacturer6D compatibility,not a physical fit pass"})
                        else:
                            intersections.append(row)
                            print("COLLISION access",stage["id"],row,flush=True)
            binding={key:value for key,value in stage.items() if key not in ("moving","fixed")}
            results.append({**binding,"exactPairs":tested,
                            "unintendedIntersections":intersections,"clampReferenceContacts":reference,
                            "status":"FAIL" if intersections else "PASS"})
            print("STAGE_END access",stage["id"],tested,"pairs",len(intersections),"intersections",flush=True)
        if not results:raise ValueError("No matching insertion stage")
        result={"schemaVersion":2,"revisionId":data["revisionId"],"designId":args.design,"nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "stages":results,"status":"FAIL" if any(x["status"]=="FAIL" for x in results) else "PASS",
                "elapsedSeconds":time.monotonic()-began,
                "pathInventorySource":"Complete orderedOperations inventory at each bound operation boundary",
                "scope":"Finite rigid paths with all installed nonmoving parts present. Separate bench scenes contain only their declared uninstalled preassembly. No continuous sweep,tolerance,hand-force or material-fit proof."}
        output=args.output_dir or folder
        output.mkdir(parents=True,exist_ok=True)
        path=output/("assembly_access.json" if not args.stage else f"access_{args.stage}.json")
        path.write_text(json.dumps(result,indent=2)+"\n")
        if result["status"]!="PASS":
            raise ValueError("Unintended assembly path intersections; complete result preserved at "+str(path))
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":main()
