"""Machine-readable handoff for the existing site worker; does not publish."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from walker_geometry import ROOT,OUT,CAD


def resource(path):
    return {"path":str(path.relative_to(ROOT)),"bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}


def assembly_stages(data):
    items={i["name"]:i for i in data["instances"]}
    groups=defaultdict(set);center=data["inputLayout"]["axisYz"]
    for name,item in items.items():
        pid,group=item["part_id"],item["group"]
        if group in ("bearings","bearing_caps"):
            label=None
            for prefix,key in (("MAIN_L","mainL"),("MAIN_R","mainR"),("INTER_L","interL"),
                               ("INTER_R","interR"),("INPUT_FIXED","inputL"),("INPUT_FLOAT","inputR")):
                if name.startswith(("CAP_"+prefix,"BEARING_"+prefix)):label=key;break
            if label is None:
                origin=np.array(item["transform"])[:3,3]
                yz=origin[1:]-[0,data["bodyOriginZMm"]]
                candidates=[]
                for mount in data["bearingMounts"]:
                    if not any(np.linalg.norm(yz-np.array(mount["axisYz"])-offset)<1e-6
                               for offset in mount["boltOffsetsYzMm"]):continue
                    kind="input" if np.allclose(mount["axisYz"],center) else "main" if mount["axisYz"][1]==0 else "inter"
                    candidates.append((abs(origin[0]-(mount["frameStart"]+mount["frameEnd"])/2),
                                       kind+("L" if mount["side"]<0 else "R")))
                if not candidates:raise ValueError("Unassigned retainer hardware: "+name)
                label=min(candidates)[1]
            groups[label].add(name)
            groups[label+("Hardware" if group=="bearing_caps" and pid.startswith("H_") else "Body")].add(name)
        elif group=="frame":
            groups["leftFrame" if pid.endswith("_L") else "rightFrame"].add(name)
        elif group=="frame_splice":groups["splice"].add(name)
        elif group=="mainshafts":
            groups["rightCrankClamps" if item["transform"][0][3]>37 else "mainBase"].add(name)
            if pid=="H_MAIN_HEX100":groups["mainMetalShafts"].add(name)
        elif group=="cranks":
            groups["leftCranks" if pid.startswith("P_CRANK_JOURNAL_-1") else "rightCranks"].add(name)
        elif group=="reducer":groups["reducer"].add(name)
        elif group=="synchronization":
            axis=item["motion"].get("axisYz")
            idler=item["motion"]["kind"]=="body" or axis is not None and abs(abs(axis[0])-data["parameters"]["common"]["stationPitchMm"]/2)<1e-8
            groups["idlers" if idler else "syncDrivers"].add(name)
            if idler and (pid=="P_IDLER_CAP" or pid.startswith(("H_BOLT_M3","H_NUT_M3","H_WASHER_3"))):
                groups["idlerCapRemovable"].add(name)
        elif group=="input":
            if pid=="H_INPUT_SHAFT":groups["inputShaft"].add(name)
            elif pid=="P_INPUT_PINION":groups["inputPinion"].add(name)
            elif pid in ("H_INPUT_COLLAR","H_INPUT_SPACER"):groups["inputLooseStops"].add(name)
            else:groups["rotorSubassembly"].add(name)
        elif group=="guards":
            if pid.startswith("S_GUARD_UPPER_RIGHT"):groups["upperSheets"].add(name)
            elif pid.startswith("S_GUARD_"):groups["sideSheets"].add(name)
            elif pid=="P_ROTOR_CAGE_FRONT":groups["frontBasket"].add(name)
            else:groups["cageJoinHardware"].add(name)
        elif group in ("legs","feet"):groups["legsAndFeet"].add(name)
        else:raise ValueError("Unassigned assembly group: "+group)
    visible=set();ever=set();steps=[]
    def step(identity,title,operations,tools=(),routes=(),prepare=(),note=""):
        rows=[];combined=defaultdict(list)
        for verb,names in operations:
            names=set(names)
            if not names<=items.keys():raise ValueError("Unknown stage part")
            if verb=="add":
                if names&ever:raise ValueError("Repeated part must use reinsert: "+str(names&ever))
                visible.update(names);ever.update(names)
            elif verb=="remove":
                if not names<=visible:raise ValueError("Removal of an absent part")
                visible.difference_update(names)
            elif verb=="reinsert":
                if not names<=ever or names&visible:raise ValueError("Invalid reinsertion")
                visible.update(names)
            else:raise ValueError("Unknown stage operation")
            rows.append({"operation":verb,"instances":sorted(names)});combined[verb]+=sorted(names)
        steps.append({"id":identity,"titleJa":title,"orderedOperations":rows,
                      "add":combined["add"],"remove":combined["remove"],"reinsert":combined["reinsert"],
                      "prepareOnly":sorted(prepare),"visibleAfter":sorted(visible),
                      "stopCrankDeg":0,"requiredTools":list(tools),"validatedPathIds":list(routes),
                      "fasteningTorqueNm":None,"noteJa":note,
                      "physicalAssemblyPerformed":False})
    g=groups
    step("01_left_support","左フレーム・左側軸受保持",
         [("add",g["leftFrame"]|g["mainL"]|g["interL"]|g["inputL"])],("HEX_2P5","HEX_3","WRENCH_5P5","WRENCH_7"),
         note="無負荷の支持・保持。固定/浮動側を混同しない。")
    step("02_open_drive","開いた状態で下流・左クランクを配置",
         [("add",g["mainBase"]|g["leftCranks"]|g["reducer"]|g["syncDrivers"]|g["inputPinion"])],
         ("HEX_2P5","WRENCH_5P5"),note="主軸クランプは後で引き込み可能な段階。入力ピニオンは軸なしの仮置き。")
    right_bearing={name for name in g["inputR"] if name.startswith("BEARING_")}
    step("03_close_frame","右フレームを閉じ、キー・継手を固定",
         [("add",g["rightFrame"]|g["splice"]|g["idlers"]|g["mainRBody"]|right_bearing)],
         ("HEX_2P5","WRENCH_5P5"),("frame_right_close",))
    step("04_upper_sheets","一時取り外し・上側PETの挿入",
         [("remove",g["idlerCapRemovable"]),("add",g["upperSheets"]),("add",g["interR"]),
          ("reinsert",g["idlerCapRemovable"])],
         ("HEX_2P5","WRENCH_5P5"),("upper_pet_from_below","upper_pet_lateral_seat"),
         note="主軸を一時53mm引き込み、上側PETをY=-4mmで上げてからY=0へ。アイドラーキャップ部品を同じIDで戻す。")
    steps[-1]["temporaryPoseOperations"]=[
        {"instances":sorted(g["mainMetalShafts"]),"translationFromCadMm":[-53,0,0],"when":"before upper-sheet insertion"},
        {"instances":sorted(g["mainMetalShafts"]),"translationFromCadMm":[0,0,0],"when":"after upper-sheet seating"}]
    step("05_side_sheets","側面PETと鋼ワッシャー保持",
         [("remove",g["mainLHardware"]),("add",g["sideSheets"]),("reinsert",g["mainLHardware"]),
          ("add",g["mainRHardware"])],
         ("HEX_2P5","HEX_3","WRENCH_5P5","WRENCH_7"),("left_pet_from_left","lower_pet_from_right"),
         note="PETを軸受予圧の圧縮スペーサーにしない。左脚・右クランクの取り付け前。")
    module=g["rotorSubassembly"]|g["frontBasket"]|g["inputPinion"]
    step("06_prepare_rotor","風車・ハブ・入力ピニオン・前バスケットを部分組立",
         [("remove",g["inputPinion"])],("HEX_3",),("rotor_into_front_basket",),module,
         note="準備中の部品は本体へ追加済みと数えない。軸が通るまで手で支持する。")
    step("07_lower_rotor","前バスケットと風車部分組立を下ろす",
         [("add",g["rotorSubassembly"]|g["frontBasket"]|g["inputLooseStops"]),("reinsert",g["inputPinion"])],
         (),("front_basket_and_rotor_lower",),note="ピニオンを同じIDで戻す。カラー・スペーサーもまだ仮置き。")
    steps[-1]["temporarilyHandSupported"]=sorted(module|g["inputLooseStops"])
    step("08_input_shaft","140mm入力軸を通し、カラー位置・向きを設定",
         [("add",g["inputShaft"])],("HEX_2P5",),("input_shaft_insert",),
         note="実際のはめあいと締付けは未確認。名目Dハブ接触は独立した未確認界面。")
    steps[-1]["collarClocking"]=data.get("inputCollarClocking")
    steps[-1]["clockingAlreadyIncludedInCadTransforms"]=True
    step("09_rear_cage","後部ガードと前後の接合を固定",
         [("add",(g["inputR"]-right_bearing)|g["cageJoinHardware"])],
         ("HEX_2P5","HEX_3","WRENCH_5P5","WRENCH_7"),("rear_cage_cap_insert",))
    step("10_right_cranks","右クランク・丸ジャーナル・正係合",
         [("add",g["rightCranks"]|g["rightCrankClamps"])],("HEX_2P5","WRENCH_5P5"),
         note="印刷された0/180度の部品とクランプ方向を識別する。")
    step("11_prepare_legs","6脚・案内・ばね・ロッカーを準備",[],("HEX_1P5","HEX_2P5","WRENCH_4"),
         prepare=g["legsAndFeet"],note="ねじ山ではなく平滑金属スリーブを摺動面にする。")
    step("12_legs","リンク層と金属ピンを取り付ける",
         [("add",g["legsAndFeet"])],("HEX_1P5","HEX_2P5","WRENCH_4"),
         note="Pのねじ頭は内側、ジャムナットは外側。ばね行程/停止は組立図と有限検査を参照。運転許可ではない。")
    if visible!=items.keys():raise ValueError("Incomplete assembly contract: "+str(items.keys()-visible))
    if any(len(row["visibleAfter"])!=len(set(row["visibleAfter"])) for row in steps):
        raise ValueError("A stage duplicates a physical instance")
    return steps


def build(source_commit):
    source_files=[
        "walker_r7.json","design.json","input_cartridge.json","requirements.txt","requirements_integrated_r7.txt",
        "walker_geometry.py","walker_kinematics.py","walker_contact.py","walker_air.py",
        "build_integrated_walkers.py","build_integrated_accessories.py","refresh_integrated_roots.py",
        "analyze_integrated_walkers.py","analyze_integrated_structure.py","analyze_integrated_sensitivities.py",
        "price_integrated_walkers.py","run_cad_bounded.py","verify_integrated_exports.py",
        "check_integrated_collisions.py","check_integrated_motion.py","check_integrated_access.py",
        "check_integrated_contact.py","check_integrated_rotations.py","check_retainer_tool_access.py",
        "check_walker_cad_components.py","test_walker_math.py","export_integrated_prints.py",
        "report_integrated_walkers.py","build_integrated_contract.py","verify_integrated_package.py","beam.py","frame3d.py",
        "cad_parts.py","core.py","commercial_r3.py","study_r2.py","input_cartridge.py"]
    sources=[resource(ROOT/"scripts/ver3"/name) for name in source_files]
    dependencies=[resource(ROOT/"docs/ver3/common_input_r4/assembly.json"),
                  resource(ROOT/"FreeCAD/Ver.3/common_input_r4/CommonInputR4.FCStd"),
                  resource(ROOT/"scripts/ver3/commercial_r3.json")]
    source_digest=hashlib.sha256(json.dumps(sources+dependencies,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    cfg=json.loads((ROOT/"scripts/ver3/walker_r7.json").read_text())
    designs=[]
    for name in "ABC":
        folder=OUT/name;a=json.loads((folder/"assembly.json").read_text())
        stages=assembly_stages(a)
        if name=="B":
            tool_requirement=resource(folder/"retainer_tool_access.json")
            stages[3]["additionalToolRequirement"]=tool_requirement
            stages[3]["noteJa"]+=" Bの最終段右保持ナットには先端外幅7.6mm以下・厚さ1.8mm以下の小型工具という未確認の工具条件がある。大きい工具が入るとは扱わない。"
        native=resource(CAD/name/f"Walker_{name}.FCStd")
        paths=json.loads((folder/"assembly_access.json").read_text())
        if paths["nativeSha256"]!=native["sha256"]:raise ValueError("Stale assembly path verification "+name)
        available={row["id"] for row in paths["stages"]}
        if any(not set(row["validatedPathIds"])<=available for row in stages):
            raise ValueError("Contract references an unverified path")
        stage_file=folder/"assembly_stages.json"
        stage_file.write_text(json.dumps({"revisionId":a["revisionId"],"designId":name,
            "nativeSha256":native["sha256"],"schemaVersion":1,"operationsAreOrdered":True,"stages":stages,
            "finalVisibleInstanceCount":len(a["instances"]),"sameIdReinsertionsRequired":True,
            "scope":"Staged geometry reference with explicit temporary removals and hand support,not an executed assembly or dynamics animation."},
            ensure_ascii=False,indent=2)+"\n")
        designs.append({"id":name,"revisionId":a["revisionId"],"direction":a["candidate"]["direction"],
            "native":native,"step":resource(CAD/name/f"Walker_{name}.step"),
            "mesh":resource(CAD/name/"render_geometry.json.gz"),"assembly":resource(folder/"assembly.json"),
            "bom":resource(folder/"BOM.csv"),"purchaseLots":resource(folder/"purchase_lots.json"),
            "stages":resource(stage_file),"printAndSheetTemplates":resource(folder/"print_geometry.json"),
            "validationFiles":[resource(folder/file) for file in
                ("static_collisions.json","gait_motion.json","assembly_access.json","contact_sensitivity.json",
                 "rotating_clearance.json","structure.json","work_budget.json","environment_sensitivity.json")],
            "generationBuildInputSha256":a["buildInputSha256"],
            "instanceCount":len(a["instances"]),"partClasses":["printed","purchased","cut_to_length","sheet_cut"],
            "cadReferenceBodyOriginZMm":a["bodyOriginZMm"],"crankReferenceDeg":0,
            "mainShaftPhasesDeg":a["parameters"]["common"]["legPhasesDeg"],
            "signedInputRevolutionsPerCrank":a["reduction"]["speedRatios"][0],
            "nominalMassG":a["nominalTotalMassG"],"nominalCogMm":a["nominalCenterOfMassMm"]})
    contract={"schemaVersion":1,"revisionId":cfg["revisionId"],"sourceCommit":source_commit,
        "sourceHash":source_digest,"sourceFiles":sources,"requirements":cfg["requirements"],
        "readOnlyExistingDependencies":dependencies,
        "requirementsApproval":resource(OUT/"requirements_approval.json"),
        "designs":designs,"sharedAccessories":resource(OUT/"common/accessories.json"),
        "slicingStatus":resource(OUT/"slicing_status.json"),"sharedOrder":resource(OUT/"purchase_lots.json"),
        "meshEncoding":"gzip JSON,local vertices in millimetres and triangle indices",
        "transformConvention":"row-major4x4 matrices multiplied by homogeneous column vectors; millimetres",
        "handedness":"Left-hand geometry is already mirrored in its mesh; do not mirror it again.",
        "stageTools":[{"id":identifier,"torqueNm":None} for identifier in
                      ("HEX_1P5","HEX_2P5","HEX_3","WRENCH_4","WRENCH_5P5","WRENCH_7")],
        "renderingLimits":["Assembly reference is uncompressed and not a solved floor-contact pose; do not impose a floor atZ=0 as a performance claim.",
                           "Camera orbit and stated assembly paths are allowed representations; no self-start or dynamic walking animation is validated.",
                           "Generation hashes describe the actual build history,including incremental root-only updates. The current source hash also includes the approved budget-only metadata update.",
                           "Old first-cut GLB,r3 calculations andr4/r6 data remain separately versioned; do not merge their numbers or geometry."],
        "manufacturingRelease":False,"qualifiedWalkingPrototypeCount":0,
        "physicalSelfStart":"UNKNOWN","real30cmTravel":"UNKNOWN","publicationAuthorized":False}
    contract["bRetainerCorrection"]=resource(OUT/"B/retainer_corner_correction.json")
    contract["bRequiredToolEnvelope"]=resource(OUT/"B/retainer_tool_access.json")
    (OUT/"integration_contract.json").write_text(json.dumps(contract,ensure_ascii=False,indent=2)+"\n")
    print("Integration contract",contract["revisionId"],source_digest)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--source-commit")
    options=parser.parse_args();build(options.source_commit)
