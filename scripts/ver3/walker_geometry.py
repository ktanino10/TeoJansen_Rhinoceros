"""Canonical full-walker geometry, purchased profiles and explicit gear datums."""

import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from core import involute
from walker_contact import dimensions, load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/"docs/ver3/integrated_r7"
CAD = ROOT/"FreeCAD/Ver.3/integrated_r7"
PRINT = ROOT/"STL/Ver.3/integrated_r7"


def nominal_thread_pair(a,b):
    pa,pb=a["part_id"],b["part_id"]
    if pa.startswith("H_NUT_") or pa=="H_NYLOCK4":a,b=b,a;pa,pb=pb,pa
    if not pa.startswith("H_BOLT_M") or not (pb.startswith("H_NUT_M") or pb=="H_NYLOCK4"):
        return False
    size=pa.split("_")[2]
    if pb!="H_NYLOCK4" and size!=pb.split("_")[2]:return False
    if pb=="H_NYLOCK4" and size!="M4":return False
    first,second=np.array(a["transform"]),np.array(b["transform"])
    direction,other=first[:3,2],second[:3,2]
    offset=second[:3,3]-first[:3,3]
    alignment=direction@other
    if abs(abs(alignment)-1)>=1e-7 or np.linalg.norm(np.cross(offset,direction))>=1e-6:
        return False
    length=float(pa.split("_")[3])
    nut_height=5.2 if pb=="H_NYLOCK4" else {"M2":1.6,"M3":2.4,"M4":3.2}[size]
    begin=float(offset@direction);end=begin+alignment*nut_height
    return min(begin,end)>=-1e-7 and max(begin,end)<=length+1e-7


def reducer(candidate, common):
    ratios = candidate["stageRatios"]
    teeth = candidate["stagePinionTeeth"]
    module = common["gears"]["moduleMm"]
    centers = [None]*(len(ratios)+1)
    centers[-1] = np.array([0., 0.])
    speeds = [0]*(len(ratios)+1)
    speeds[-1] = 1.
    for i in range(len(ratios)-1, -1, -1):
        center = module*teeth[i]*(1+ratios[i])/2
        delta_y=candidate.get("stageAxisDeltaYmm",[-20]*len(ratios))[i]
        if abs(delta_y)>=center:raise ValueError("Invalid stage horizontal offset")
        centers[i] = centers[i+1]+[delta_y, math.sqrt(center**2-delta_y**2)]
        speeds[i] = -ratios[i]*speeds[i+1]
    stages = []
    for i, ratio in enumerate(ratios):
        delta = centers[i+1]-centers[i]
        alpha = math.atan2(delta[1], delta[0])
        shift=0.
        stages.append({"id": f"stage{i}", "pinion": teeth[i], "wheel": teeth[i]*ratio,
                       "pinionAxis": i, "wheelAxis": i+1, "centreMm": float(np.linalg.norm(delta)),
                       "xMm": candidate.get("firstGearPlaneXmm",common["gears"]["firstPlaneXmm"])+i*common["gears"]["axialLayerPitchMm"],
                       "pinionToothDatumRad": alpha,
                       "wheelToothDatumRad": alpha+math.pi+math.pi/(teeth[i]*ratio),
                       "pinionProfileShift":shift,"wheelProfileShift":-shift,
                       "pinionAddendumCoefficient":tip_addendum(module,teeth[i]),
                       "wheelAddendumCoefficient":tip_addendum(module,teeth[i]*ratio),
                       "pinionSpeedPerCrank": speeds[i], "wheelSpeedPerCrank": speeds[i+1]})
    return {"axesYzMm": [p.tolist() for p in centers], "speedRatios": speeds, "stages": stages}


def tip_addendum(module,teeth,pressure_deg=25,backlash=.3,minimum_tip_mm=.53):
    """One finite manufacturability solve, rounded before contact-ratio checks."""
    alpha=math.radians(pressure_deg)
    pitch=module*teeth/2;base=pitch*math.cos(alpha)
    half=(math.pi*module/2-backlash/2)/(2*pitch)
    def width(coefficient):
        tip=pitch+module*coefficient
        return 2*tip*(half+involute(alpha)-involute(math.acos(base/tip)))
    if width(.4)<minimum_tip_mm:
        raise ValueError("No admissible tip thickness in the bounded addendum range")
    value=1. if width(1)>=minimum_tip_mm else brentq(lambda a:width(a)-minimum_tip_mm,.4,1)
    return math.floor((value+1e-10)*100)/100


def involute_outline(module, teeth, pressure_deg=25, backlash=.3, samples=8,
                     profile_shift=0.,addendum_coefficient=None):
    alpha = math.radians(pressure_deg)
    pitch = module*teeth/2
    addendum=tip_addendum(module,teeth,pressure_deg,backlash) if addendum_coefficient is None else addendum_coefficient
    base,root,tip=pitch*math.cos(alpha),pitch-(1.25-profile_shift)*module,pitch+addendum*module
    half=(math.pi*module/2+2*profile_shift*module*math.tan(alpha)-backlash/2)/(2*pitch)
    start = max(root, base)
    def flank(radius):
        t = math.sqrt(max(0, (radius/base)**2-1))
        return half+involute(alpha)-(t-math.atan(t))
    points = []
    for i in range(teeth):
        angle = i*2*math.pi/teeth
        first = flank(start)
        points.append([root*math.cos(angle-first), root*math.sin(angle-first)])
        for radius in np.linspace(start, tip, samples):
            a = angle-flank(radius)
            points.append([radius*math.cos(a), radius*math.sin(a)])
        for a in np.linspace(angle-flank(tip), angle+flank(tip), 5)[1:]:
            points.append([tip*math.cos(a), tip*math.sin(a)])
        for radius in np.linspace(tip, start, samples)[1:]:
            a = angle+flank(radius)
            points.append([radius*math.cos(a), radius*math.sin(a)])
        points.append([root*math.cos(angle+first), root*math.sin(angle+first)])
        for a in np.linspace(angle+first, angle+2*math.pi/teeth-first, 5)[1:-1]:
            points.append([root*math.cos(a), root*math.sin(a)])
    return np.array(points)


def gear_pair_metrics(module, pinion, wheel, pressure_deg=25, backlash=.3,pinion_shift=0.):
    alpha = math.radians(pressure_deg)
    radii = np.array([pinion, wheel])*module/2
    if pinion_shift:
        raise ValueError("This revision uses zero profile shift and explicitly truncated tips")
    shifts=np.zeros(2)
    addenda=[tip_addendum(module,n,pressure_deg,backlash) for n in (pinion,wheel)]
    bases,tips=radii*math.cos(alpha),radii+module*np.array(addenda)
    contact = (sum(np.sqrt(tips**2-bases**2))-sum(radii)*math.sin(alpha))/(math.pi*module*math.cos(alpha))
    half=(math.pi*module/2+2*shifts*module*math.tan(alpha)-backlash/2)/(2*radii)
    tip_thick = 2*tips*(half+involute(alpha)-np.array([involute(math.acos(b/r)) for b,r in zip(bases,tips)]))
    return {"moduleMm": module, "pinionTeeth": pinion, "wheelTeeth": wheel,
            "centerDistanceMm": float(sum(radii)), "pressureAngleDeg": pressure_deg,
            "contactRatio": float(contact), "minimumTipThicknessMm": float(min(tip_thick)),
            "rackUndercutMinimumTeeth": 2/math.sin(alpha)**2,
            "noStandardRackUndercut": pinion >= 2/math.sin(alpha)**2,
            "backlashMm": backlash,
            "profileShifts":shifts.tolist(),
            "addendumCoefficients":addenda,
            "profileDefinition":"zero-shift true involutes with shortened addenda sized to>=0.53mm nominal tip then rounded down; center,ratio and25deg pressure preserved",
            "radialForcePerTangential": math.tan(alpha),
            "rootProfile": "radial continuation below base circle; no claimed generated hob trochoid",
            "printedProfileNeedsCoupon": True}


def input_layout(reduction):
    return {"axisYz": reduction["axesYzMm"][0], "shaftStartX": -68, "shaftLength": 140,
            "fixedBearingStartX": -54, "floatBearingStartX": 58,
            "fixedCarrierStartX": -54.3, "fixedCarrierEndX": -46,
            "fixedCapStartX": -57.3, "floatCarrierStartX": 55, "floatCarrierEndX": 64,
            "floatCapStartX": 64, "outerCollarBossFaceX": -58.1, "innerCollarBossFaceX": -44.9,
            "outerSpacerStartX": -58, "innerSpacerStartX": -49,
            "hubStartX": 0, "rotorRootX": 8,
            "inputPinionStartX": reduction["stages"][0]["xMm"], "inputPinionEndStemX": 0,
            "inputPinionOuterSpacerFaceX": -35,
            "differenceFromR6": "longer stock140mm input shaft and floating support shifted outward; avoids putting large rotor around intermediate shafts. Same bearing/hub/collar family, not three copies of the stand."}


def body_points(theta=0, which="reference", common=None):
    from walker_kinematics import points_many
    common = load()["common"] if common is None else common
    return points_many(np.array(theta), dimensions(which,common), common["linkScale"])[0]


def rigids():
    return {"AB": ("A","B"), "AC": ("A","C"), "PC": ("P","C"),
            "PBD": ("P","B","D"), "DE": ("D","E"), "CEF": ("C","E","F")}


def link_pose(points, reference, nodes, station, body_z=65):
    a,b = nodes[:2]
    base_angle = math.atan2(*(reference[b]-reference[a])[::-1])
    angle = math.atan2(*(points[b]-points[a])[::-1])-base_angle
    c,s=math.cos(angle),math.sin(angle)
    rotation=np.array([[1,0,0],[0,c,-s],[0,s,c]])
    target=np.array([0,points[a][0]+station,points[a][1]+body_z])
    origin=np.r_[0,reference[a]]
    translation=target-rotation@origin
    matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=translation
    return matrix.tolist()
