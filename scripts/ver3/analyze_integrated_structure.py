"""Load-path screens from saved r7 CAD; no solid FEM or material certificate."""

import argparse
import json
import math

import numpy as np

from beam import d_section, solve_beam, twist_bound
from frame3d import member_matrix
from walker_geometry import OUT,gear_pair_metrics


def regular_section(diameter,sides=16):
    radius=diameter/2
    angle=2*math.pi/sides
    area=sides*radius**2*math.sin(angle)/2
    inertia=sides*radius**4*math.sin(angle)*(2+math.cos(angle))/24
    return {"areaMm2":area,"inertiaMm4":inertia,"extremeMm":radius,
            "torsionLowerMm4":math.pi*(radius*math.cos(math.pi/sides))**4/2,
            "torsionUpperMm4":math.pi*radius**4/2}


def strut_matrix(first,second,diameter,modulus,sides=16):
    first,second=np.array(first,float),np.array(second,float)
    delta=second-first;axis=delta/np.linalg.norm(delta)
    reference=np.array([1.,0,0]) if abs(axis[0])<.95 else np.array([0.,1,0])
    _,local,transform,length,_=member_matrix(first,second,1,1,reference,modulus,.35)
    section=regular_section(diameter,sides)
    for indices,scale in (
        ([0,6],section["areaMm2"]),
        ([1,5,7,11],12*section["inertiaMm4"]),
        ([2,4,8,10],12*section["inertiaMm4"]),
    ):
        local[np.ix_(indices,indices)]*=scale
    shear=modulus/(2*1.35)
    local[np.ix_([3,9],[3,9])]=shear*section["torsionLowerMm4"]/length*np.array([[1,-1],[-1,1]])
    return transform.T@local@transform,local,transform,section,length


def tower_side(members,head,force,offset,modulus,additional_load=None):
    """Two actual input braces, both base sections rigidly restrained."""
    stiffness=np.zeros((6,6));records=[]
    for member in members:
        matrix,local,transform,section,length=strut_matrix(
            member["aMm"],member["bMm"],member["circumDiameterMm"],modulus,member["sectionSides"])
        stiffness+=matrix[6:,6:]
        records.append((member,local,transform,section,length))
    offset=np.array(offset,float);force=np.array(force,float)
    extra=np.zeros(6) if additional_load is None else np.asarray(additional_load,float)
    load=np.r_[force,np.cross(offset,force)]+extra
    move=np.linalg.solve(stiffness,load)
    screens=[]
    for member,local,transform,section,length in records:
        values=local@transform@np.r_[np.zeros(6),move]
        axial=max(abs(values[0]),abs(values[6]))
        bending=max(np.linalg.norm(values[4:6]),np.linalg.norm(values[10:12]))
        stress=axial/section["areaMm2"]+bending*section["extremeMm"]/section["inertiaMm4"]
        compression=max(values[0],0)
        buckling=math.pi**2*modulus*section["inertiaMm4"]/(2*length)**2
        screens.append({"spanMm":length,"diameterMm":member["circumDiameterMm"],
                        "section":section,"normalStressMpa":float(stress),"compressionN":float(compression),
                        "eulerCantileverK2N":buckling})
    bearing=move[:3]+np.cross(move[3:],offset)
    work=float(np.dot(load,move)-np.dot(force,bearing)-np.dot(extra,move))
    if abs(work)>1e-9:raise ValueError("Load-point transformation violates virtual work")
    return {"referencePointMm":head,"offsetToBearingMm":offset.tolist(),
            "referenceMotionMmRad":move.tolist(),"bearingCenterShiftMm":bearing.tolist(),
            "additionalRootWrenchNAndNmm":extra.tolist(),
            "virtualWorkErrorNmm":work,"members":screens}


def analyze(design):
    folder=OUT/design
    a=json.loads((folder/"assembly.json").read_text())
    w=json.loads((folder/"work_budget.json").read_text())
    if a["revisionId"]!=w["revisionId"]:raise ValueError("Structure inputs mix CAD and work revisions")
    c=a["parameters"]["common"];gravity=9.80665
    masses=[];rotating=0.;head=a["inputLayout"]["axisYz"]
    for item in a["instances"]:
        motion=item["motion"]
        if motion["kind"]=="shaft" and motion["axisYz"]==head:
            p=a["parts"][item["part_id"]]
            point=(np.array(item["transform"])@np.r_[p["local_com_mm"],1])[:3]
            masses.append((float(point[0]+68),-p["mass_g"]/1000*gravity))
            rotating+=p["mass_g"]/1000
    section=d_section(6,.5)
    supports=[(16.5,"translation"),(128.5,"translation")]
    momentum=1.225*6.4**2*math.pi*.02**2
    z=solve_beam(140,193000,section,masses+[(96,-momentum)],supports)
    y=solve_beam(140,193000,section,[(96,2*momentum)],supports)
    guard_wrench=np.zeros(6)
    for item in a["instances"]:
        part=a["parts"][item["part_id"]]
        if not (item["part_id"].startswith("P_ROTOR_CAGE") or
                item["group"]=="guards" and part["category"]=="purchased"):continue
        point=(np.array(item["transform"])@np.r_[part["local_com_mm"],1])[:3]
        arm=point-[59,head[0],head[1]+a["bodyOriginZMm"]]
        load=np.array([0,0,-part["mass_g"]/1000*gravity])
        guard_wrench+=np.r_[load,np.cross(arm,load)]
    cases=[]
    for modulus in c["materials"]["printedEcasesMpa"]:
        for axial in (-1,0,1):
            sides=[]
            for i,(x,bearing_x) in enumerate(((-50,-51.5),(59,60.5))):
                members=[m for m in a["frameMembersBeforeUnion"]
                         if np.allclose(m["bMm"],[x,*head],atol=1e-8)]
                if len(members)!=2:raise ValueError("Actual input tower must have exactly two registered braces")
                force=[axial if i==0 else 0,-y["reactions"][i]["value_n_or_nmm"],
                       -z["reactions"][i]["value_n_or_nmm"]]
                sides.append(tower_side(members,[x,*head],force,[bearing_x-x,0,0],modulus,
                                        guard_wrench if i==1 else None))
            shifts=np.array([side["bearingCenterShiftMm"] for side in sides])
            differential=shifts[1]-shifts[0]
            axes=[]
            line=differential[1:]/(112+differential[0])
            for i,support in enumerate((16.5,128.5)):
                rotations=np.array(sides[i]["referenceMotionMmRad"])[3:]
                field_y,field_z=np.array(y["field"]),np.array(z["field"])
                slopes=np.array([field_y[np.argmin(abs(field_y[:,0]-support)),2],
                                 field_z[np.argmin(abs(field_z[:,0]-support)),2]])
                mismatch=line+slopes-np.array([rotations[2],-rotations[1]])
                axes.append({"support":i,"relativeTiltRad":float(np.linalg.norm(mismatch)),
                             "manufacturerAllowableTiltRad":None})
            cases.append({"modulusMpa":modulus,"extraAxialForceN":axial,"sides":sides,
                          "commonTranslationMm":shifts.mean(axis=0).tolist(),
                          "differentialTranslationMm":differential.tolist(),
                          "bearingAxisAlignment":axes,
                          "localFramePlusShaftDeflectionUpperMm":float(np.linalg.norm(differential[1:])+
                              math.hypot(y["max_deflection_mm"],z["max_deflection_mm"]))})
    same_load=[]
    for case in w["cases"]:
        pin=case["forceStatistics"]["rootPins"]
        guide_moment=case["guideRootMomentMaximumNmm"]
        sleeve_contact_kernel=(2**2+1.6**2)/(4*2)
        head_contact_kernel=(1.9**2+1.6**2)/(4*1.9)
        kernel=min(sleeve_contact_kernel,head_contact_kernel)
        minimum_preload=guide_moment/kernel
        spread_radius,spread_inner=4.5,2.15
        area=math.pi*(spread_radius**2-spread_inner**2)
        inertia=math.pi*(spread_radius**4-spread_inner**4)/4
        maximum_preload=max(0,(c["materials"]["printedStressScreenMpa"]-guide_moment*spread_radius/inertia)*area)
        thread_area=2.07
        same_load.append({"case":case["case"],"rootPins":pin,
                          "guideRootMomentNmm":guide_moment,
                          "minimumClampPreloadForNoSeparationN":minimum_preload,
                          "contactKernRadiusMm":kernel,
                          "provisionalPrintedPressurePreloadUpperN":maximum_preload,
                          "nonemptyPreloadScreenWindow":maximum_preload>minimum_preload,
                          "M2StressAtTwiceMinimumPreloadMpa":2*minimum_preload/thread_area,
                          "guideLoadSpread":"M3 plus M4 steel washers at each end. Kern follows the actual head/sleeve contact annulus,not the washer-hole radius; plate bending,flatness and physical preload remain unverified.",
                          "guideSleeveElasticBendingMpa":guide_moment*2/(math.pi*(4**4-2.2**4)/64),
                          "loadModelLimitation":"first-order joint statics; no Coulomb-force feedback, impacts or verified clamp preload"})
    foot=c["foot"];travel=foot["workingCompressionLimitMm"]
    spring={"freeLengthMm":foot["springFreeLengthMm"],"catalogueRatedTravelMm":foot["springRatedTravelMm"],
            "modelledMechanicalStopMm":travel,
            "estimatedSolidHeightMm":foot["springTotalTurns"]*foot["springWireMm"],
            "remainingSolidHeightClearanceAtStopMm":foot["springFreeLengthMm"]-travel-foot["springTotalTurns"]*foot["springWireMm"],
            "forceEachAtStopN":travel*foot["springRateNmm"],
            "catalogueRatedForceN":foot["springRatedMaxLoadN"],
            "loadedCompressionFromCadMassMm":w["contact"]["maximum_guide_compression_mm"],
            "notAMeasuredSpringCurve":True}
    meshes=[]
    for stage in a["reduction"]["stages"]:
        meshes.append(gear_pair_metrics(1,stage["pinion"],stage["wheel"],25,.3))
    meshes.append(gear_pair_metrics(1,c["synchronization"]["teeth"],c["synchronization"]["teeth"],25,.3))
    splice=[]
    if "frameSpliceStationsYmm" in c:
        span=np.ptp(c["frameSpliceStationsYmm"])
        for case in w["cases"]:
            statistics=case["forceStatistics"]
            force=max(statistics["coherentSideFrameForceMaximumN"])
            couple=max(statistics["coherentSideFrameMomentMaximumNmm"])
            shear=force+couple/span
            splice.append({"case":case["case"],"coherentSideForceN":force,"coherentSideMomentNmm":couple,
                           "oneKeyConservativeTransverseLoadN":shear,
                           "printed4AfKeyShearScreenMpa":shear/(math.sqrt(3)/2*4**2),
                           "fourM3BoltsAndFrontHexRearRelievedKey":True,
                           "keyClearanceAndJointFlexibilityNotIncludedInLocalTowerModel":True})
    result={"revisionId":a["revisionId"],"designId":design,"actualInputRotatingMassKg":rotating,
            "inputShaftGravityBeam":z,"inputShaftTransverseBeam":y,
            "fixedCageGravityWrenchAtFloatingTowerNAndNmm":guard_wrench.tolist(),
            "inputTowerLocalCases":cases,"loadPathScreens":same_load,"springStop":spring,
            "frameSplice":splice,
            "gearGeometry":meshes,
            "wholeStructureQualification":"UNKNOWN",
            "limits":["Actual16-sided prism area and second moment,not a circle with unchanged mass.",
                      "Input braces' base sections are fixed; chassis/cap/root deformation is omitted. This is not complete support compliance.",
                      "Bearing translation includes reference rotation cross load-point offset; common and differential motion remain separate.",
                      "8MPa is a provisional printed-material screen,not a tested FDM strength or fatigue value.",
                      "Thin tooth tips require an actual slice and fit coupon; contact ratio alone does not certify printing or strength.",
                      "Bolt class, washer flatness, tightening/preload and real sleeve OD/fit remain procurement/physical acceptance conditions."]}
    (folder/"structure.json").write_text(json.dumps(result,indent=2)+"\n")
    print(design,"structure local frame",max(x["localFramePlusShaftDeflectionUpperMm"] for x in cases),
          "mm","shaft stress",z["max_bending_stress_mpa"],"MPa")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--designs",nargs="+",default=["A","B","C"])
    options=parser.parse_args()
    for design in options.designs:analyze(design)
