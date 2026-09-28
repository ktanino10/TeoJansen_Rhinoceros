"""Finite rigid insertion/removal paths using saved native solids and stages."""

import argparse
import hashlib
import json
import sys
import time

import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--freecad-lib",required=True)
parser.add_argument("--design",choices=("A","B","C"),required=True)
parser.add_argument("--stage")
args=parser.parse_args()
sys.path.insert(0,args.freecad_lib)
import FreeCAD as App
import Part

from walker_geometry import OUT,CAD,nominal_thread_pair


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
    items=data["instances"];common=data["parameters"]["common"]
    def pid(item):return item["part_id"]
    def is_idler(item):
        if item["group"]!="synchronization":return False
        axis=item["motion"].get("axisYz")
        return (axis is not None and abs(abs(axis[0])-common["stationPitchMm"]/2)<1e-8
                or item["motion"]["kind"]=="body")
    body=[i for i in items if i["group"] in ("frame","frame_splice")]
    drive=[i for i in items if i["group"] in ("mainshafts","cranks","reducer","synchronization")
           and not pid(i).startswith("P_CRANK_JOURNAL_1")
           and not (i["group"]=="mainshafts" and i["transform"][0][3]>37)]
    pinion=[i for i in items if pid(i)=="P_INPUT_PINION"]
    module=[i for i in items if pid(i) in ("P_ROTOR","H_INPUT_HUB","P_ROTOR_CAGE_FRONT")
            or i["group"]=="input" and pid(i) in ("H_BOLT_M4_12","H_WASHER_4")]
    module+=pinion
    rotor=[i for i in module if pid(i)!="P_ROTOR_CAGE_FRONT"]
    front=[i for i in module if pid(i)=="P_ROTOR_CAGE_FRONT"]
    rear=[i for i in items if pid(i)=="P_ROTOR_CAGE_CAP"]
    frames=[i for i in body if pid(i).startswith("P_CHASSIS_")]
    frame_r=[i for i in frames if pid(i)=="P_CHASSIS_R"]
    frame_l=[i for i in frames if pid(i)=="P_CHASSIS_L"]
    if len(frame_r)!=1 or len(frame_l)!=1 or len(front)!=1 or len(rear)!=1:
        raise ValueError("Insertion proof requires the actual split frame and two cage pieces")
    stationary_input=[i for i in items if i["group"] in ("input","bearings","bearing_caps")
                      and pid(i) not in ("H_INPUT_SHAFT","P_ROTOR_CAGE_CAP") and not pid(i).startswith("H_BOLT")]
    collar_spacers=[i for i in items if pid(i) in ("H_INPUT_COLLAR","H_INPUT_SPACER")]
    left_carriers=[i for i in items if i["name"].startswith(("CAP_INTER_L","BEARING_INTER_L","CAP_INPUT_FIXED","BEARING_INPUT_FIXED"))]
    mounts=[m for m in data["bearingMounts"] if m["side"]<0 and m["axisYz"][1]!=0]
    for item in items:
        if item["group"]!="bearing_caps" or item["transform"][0][3]>=0 or not pid(item).startswith("H_"):continue
        point=np.array(item["transform"])[1:3,3]-[0,data["bodyOriginZMm"]]
        if any(np.linalg.norm(point-np.array(m["axisYz"])-offset)<1e-6
               for m in mounts for offset in m["boltOffsetsYzMm"]):left_carriers.append(item)
    upper_fixed=frames+[i for i in drive if not (is_idler(i) and
                 (pid(i)=="P_IDLER_CAP" or pid(i).startswith(("H_BOLT_M3","H_NUT_M3","H_WASHER_3"))))]+pinion
    source=[
        {"id":"frame_right_close","moving":frame_r+[i for i in items if is_idler(i)],
         "fixed":frame_l+[i for i in drive if not is_idler(i)]+pinion+left_carriers,
         "direction":[1,0,0],"distances":[120,80,40,20,10,5,2,1,0],
         "note":"Close the right frame around the compound shafts. Right cranks,rotor,cage and frame-splice screws are installed later."},
        {"id":"upper_pet_from_below","moving":[i for i in items if pid(i).startswith("S_GUARD_UPPER_RIGHT")],
         "fixed":upper_fixed,"direction":[0,0,-1],"constantOffsetMm":[0,-4,0],
         "distances":[300,220,160,120,80,40,20,10,5,2,0],
         "retractMainShaftsMm":53,
         "note":"Main shafts retracted53mm,input shaft and idler outer cap screws absent. Raise the sheet4mm left of its final Y position,clear of both transverse frame roots; the next stage completes its4mm lateral shift."},
        {"id":"upper_pet_lateral_seat","moving":[i for i in items if pid(i).startswith("S_GUARD_UPPER_RIGHT")],
         "fixed":upper_fixed,"direction":[0,-1,0],"distances":[4,3,2,1,0],"retractMainShaftsMm":53,
         "note":"At final height,slide4mm right so the open edge notch seats around the transverse frame root; fit upper cap and idler cap screws afterward."},
        {"id":"lower_pet_from_right","moving":[i for i in items if pid(i)=="S_GUARD_LOWER_RIGHT"],
         "fixed":frames+drive+pinion,"direction":[1,0,0],
         "distances":[120,80,40,20,10,5,2,0],
         "note":"Fit before right cranks and legs,with the main-right retaining screws removed. Steel washer stacks later capture the sheet without bearing-preload dependence on PET."},
        {"id":"left_pet_from_left","moving":[i for i in items if pid(i)=="S_GUARD_LEFT"],
         "fixed":frames+drive+pinion+collar_spacers+left_carriers,"direction":[-1,0,0],
         "distances":[120,80,40,20,10,5,2,0],
         "note":"Fit before left legs and their pins. Main-left cap screws are removed; explicit passages clear fixed P bosses,intermediate carriers and input fasteners."},
        {"id":"rotor_into_front_basket","moving":rotor,"fixed":front,"direction":[1,0,0],
         "distances":[140,100,60,30,10,5,2,0],
         "note":"The front cage basket has an open rear. Slide the bolted rotor/hub assembly inside before placing either in the frame."},
        {"id":"front_basket_and_rotor_lower","moving":module,
         "fixed":frames+drive,"direction":[0,0,1],
         "distances":[240,180,120,80,40,20,10,5,2,0],
         "note":"Lower the aligned rotor/hub/pinion and front basket together,with input shaft and rear cage absent. This is hand-supported partial assembly,not a self-retained module."},
        {"id":"input_shaft_insert","moving":[i for i in items if pid(i)=="H_INPUT_SHAFT"],
         "fixed":frames+drive+pinion+module+stationary_input+collar_spacers,
         "direction":[-1,0,0],"distances":[180,140,100,80,40,20,10,5,2,0],
         "note":"Thread the ready-length shaft through loose collars,spacers,pinion and hub. Manufacturer-compatible clamp reference contact is recorded separately,not cleared by resizing."},
        {"id":"rear_cage_cap_insert","moving":rear,
         "fixed":frames+drive+pinion+module+[i for i in items if pid(i)=="H_INPUT_SHAFT"],
         "direction":[1,0,0],"distances":[100,60,40,24,16,12,8,4,2,1,0],
         "note":"Open-ended rear slots pass the two stationary input braces. Join front/rear cage and install the floating-cap screws only after seating."},
    ]
    for row in source:
        moving={i["name"] for i in row["moving"]}
        row["fixed"]=list({i["name"]:i for i in row["fixed"] if i["name"] not in moving}.values())
        if not row["moving"]:raise ValueError("Empty insertion stage "+row["id"])
    return source


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
            for distance in stage["distances"]:
                vector=np.array(stage["direction"])*distance+np.array(stage.get("constantOffsetMm",[0,0,0]))
                print("STAGE_BEGIN access",stage["id"],distance,flush=True)
                for first in stage["moving"]:
                    moving=translated(shapes[first["name"]],vector)
                    for second in stage["fixed"]:
                        fixed=shapes[second["name"]]
                        if second["part_id"]=="H_MAIN_HEX100" and "retractMainShaftsMm" in stage:
                            fixed=translated(fixed,[-stage["retractMainShaftsMm"],0,0])
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
            results.append({"id":stage["id"],"note":stage["note"],"direction":stage["direction"],
                            "constantOffsetMm":stage.get("constantOffsetMm",[0,0,0]),
                            "distancesMm":stage["distances"],"movingNames":[i["name"] for i in stage["moving"]],
                            "fixedNames":[i["name"] for i in stage["fixed"]],"exactPairs":tested,
                            "unintendedIntersections":intersections,"clampReferenceContacts":reference,
                            "status":"FAIL" if intersections else "PASS"})
            print("STAGE_END access",stage["id"],tested,"pairs",len(intersections),"intersections",flush=True)
        if not results:raise ValueError("No matching insertion stage")
        result={"revisionId":data["revisionId"],"designId":args.design,"nativeSha256":hashlib.sha256(native.read_bytes()).hexdigest(),
                "stages":results,"status":"FAIL" if any(x["status"]=="FAIL" for x in results) else "PASS",
                "elapsedSeconds":time.monotonic()-began,
                "scope":"Finite rigid paths for the stated staged assembly. No continuous sweep,tolerance,hand-force or material-fit proof; future-stage parts are explicitly absent,not ignored in a finished assembly."}
        path=folder/("assembly_access.json" if not args.stage else f"access_{args.stage}.json")
        path.write_text(json.dumps(result,indent=2)+"\n")
    finally:
        App.closeDocument(doc.Name)


if __name__=="__main__":main()
