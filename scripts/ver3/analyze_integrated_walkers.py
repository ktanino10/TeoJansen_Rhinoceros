"""Actual-CAD mass and non-cancelling work budgets for the complete candidates.

This is a quasi-static reference-work bound, not a calibrated airflow or impact
simulation. Guide losses are added to a frictionless-normal reference once.
"""

import argparse
from collections import defaultdict
from copy import deepcopy
import json
import hashlib
import math
from pathlib import Path
import re

import numpy as np

from walker_kinematics import points_many
from core import LINKS
from study_r2 import INCIDENCE, VARIABLES, static_jet_proxy
from walker_contact import ContactGait, dimensions
from walker_geometry import ROOT, OUT, rigids, link_pose


def derivative(values,step):
    return (np.roll(values,-1,axis=0)-np.roll(values,1,axis=0))/(2*step)


def shaft_gravity_work(fast,axes,theta,pitch,pitch_rate):
    """Sum rigidly co-rotating masses before any transmission loss."""
    moments=np.zeros((len(axes),2))
    for item in fast:
        matches=[i for i,axis in enumerate(axes)
                 if np.allclose(axis,item["axisYzMm"],atol=1e-10,rtol=0)]
        if len(matches)!=1:raise ValueError("Fast body has no unique real shaft")
        moments[matches[0]]+=item["massKg"]*np.array(item["offsetYzMm"])
    result=np.zeros((len(axes),len(theta)))
    for index,axis in enumerate(axes):
        members=[item for item in fast if np.allclose(axis,item["axisYzMm"],atol=1e-10,rtol=0)]
        if not members:continue
        speed=members[0]["speed"]
        if any(item["speed"]!=speed for item in members):
            raise ValueError("Rigid shaft bodies have inconsistent speeds")
        y,z=moments[index]
        off=y*np.cos(speed*theta)-z*np.sin(speed*theta)
        rate=speed*(-y*np.sin(speed*theta)-z*np.cos(speed*theta))
        result[index]=9.80665*(speed*off+pitch_rate*off+pitch*rate)
    return result


def reflect_shaft_work(output_work,gravity_work,speeds,eta,bearing_each):
    """Walk the real train from output to input in Nmm per crank radian."""
    if not 0<eta<=1 or bearing_each<0 or len(speeds)!=len(gravity_work):
        raise ValueError("Invalid shaft power-flow inputs")
    work=np.array(output_work,dtype=float,copy=True)
    losses=[]
    for shaft in range(len(speeds)-2,-1,-1):
        after=np.where(work>=0,work/eta,work*eta)
        losses.append(after-work)
        work=after+gravity_work[shaft]+2*bearing_each*abs(speeds[shaft])
    return work/abs(speeds[0]),np.array(losses)


def station_circulation(leg_torques,leg_order):
    stations={}
    for column,key in enumerate(leg_order):
        stations.setdefault(key[0],np.zeros(len(leg_torques)))
        stations[key[0]]+=leg_torques[:,column]
    return 2*sum(np.maximum(-values,0) for values in stations.values())


def cad_positions(assembly,theta,compression=None,average_fast=True):
    common=assembly["parameters"]["common"]
    scale=common["linkScale"]
    ref,_=points_many(np.array(0.),dimensions("reference",common),scale)
    body_z=assembly["bodyOriginZMm"]
    stations=(np.arange(len(common["legPhasesDeg"]))-(len(common["legPhasesDeg"])-1)/2)*common["stationPitchMm"]
    legs=[(s,side,math.radians(p)) for s,pair in zip(stations,common["legPhasesDeg"]) for side,p in zip((-1,1),pair)]
    frames={}
    for station,side,phase in legs:
        p,_=points_many(theta+phase,dimensions("reference",common),scale)
        initial,_=points_many(np.array(phase),dimensions("reference",common),scale)
        frames[(station,side,phase)]=(p,initial)
    result=np.zeros((len(theta),len(assembly["instances"]),3))
    masses=[];fast=[];leg_index={v:i for i,v in enumerate(legs)}
    for index,item in enumerate(assembly["instances"]):
        part=assembly["parts"][item["part_id"]]
        mass=part["mass_g"]/1000;masses.append(mass)
        com=np.array(part["local_com_mm"])
        original=(np.array(item["transform"])@np.r_[com,1])[:3]
        motion=item["motion"];kind=motion["kind"]
        if kind=="body":
            result[:,index]=original
        elif kind in ("shaft","crank"):
            axis=np.array([0,motion["axisYz"][0],body_z+motion["axisYz"][1]])
            offset=original-axis;speed=motion["speed"]
            if average_fast and abs(speed)>1:
                result[:,index]=axis+[offset[0],0,0]
                fast.append({"massKg":mass,"speed":speed,"axisYzMm":motion["axisYz"],
                             "offsetYzMm":offset[1:].tolist()})
            else:
                c,s=np.cos(speed*theta),np.sin(speed*theta)
                result[:,index,0]=original[0]
                result[:,index,1]=axis[1]+c*offset[1]-s*offset[2]
                result[:,index,2]=axis[2]+s*offset[1]+c*offset[2]
        elif kind=="joint":
            key=(motion["station"],motion["side"],motion["phase"])
            p,initial=frames[key];node=motion["node"]
            result[:,index]=original
            result[:,index,1:]+=p[node]-initial[node]
        elif kind in ("link","foot"):
            key=(motion["station"],motion["side"],motion["phase"])
            p,initial=frames[key]
            labels=rigids()[motion["link"]] if kind=="link" else rigids()["CEF"]
            a,b=labels[:2]
            new_angle=np.unwrap(np.arctan2((p[b]-p[a])[:,1],(p[b]-p[a])[:,0]))
            if kind=="link":
                old_angle=math.atan2(*(ref[b]-ref[a])[::-1])
                offset=com[1:]-ref[a]
                x=com[0]
            else:
                old_angle=math.atan2(*(initial[b]-initial[a])[::-1])
                offset=original[1:]-initial[a]-[motion["station"],body_z]
                x=original[0]
            angle=new_angle-old_angle;c,s=np.cos(angle),np.sin(angle)
            result[:,index,0]=x
            result[:,index,1]=p[a][:,0]+motion["station"]+c*offset[0]-s*offset[1]
            result[:,index,2]=p[a][:,1]+body_z+s*offset[0]+c*offset[1]
            if kind=="foot" and compression is not None:
                factor=.5 if motion["piece"]=="SPRING" else 1. if motion["piece"] in ("SLIDER","ROCKER","ROCKER_PIN") else 0.
                gamma=new_angle-math.radians(common["foot"]["pitchReferenceBodyAngleDeg"])
                displacement=factor*compression[:,leg_index[key]]
                result[:,index,1]-=displacement*np.sin(gamma)
                result[:,index,2]+=displacement*np.cos(gamma)
        else:
            raise ValueError("Unknown actual-CAD motion "+kind)
    return result,np.array(masses),fast,legs


def air_proxy(assembly,air_case=None):
    air_case=air_case or {}
    if assembly["parameters"]["common"].get("guards",{}).get("rotorCage",False):
        from walker_air import static_supply
        return static_supply(assembly,rays=2048,peak_ms=air_case.get("peakMS",6.4),
                             sigma_mm=air_case.get("sigmaMm",20),aim_shift_mm=air_case.get("aimShiftMm",0))
    if air_case:raise ValueError("Legacy unguarded baseline has no alternative-air override")
    candidate=assembly["candidate"];common=assembly["parameters"]["common"]
    radius=candidate["rotorDiameterMm"]/2
    proxy_common={"rotor":{"innerRadiusFraction":22.5/(radius-.8),"proxyPanelDragCoefficient":1.2}}
    fluid={"airDensityKgM3":1.225,"airKinematicViscosityM2S":1.5e-5}
    jet=static_jet_proxy(radius-.8,32,proxy_common,fluid,16,20,-.5*radius/(radius-.8),
                         6.4,20,step_deg=.5,rays=512)
    return jet


def input_inertia(assembly):
    axis=assembly["inputLayout"]["axisYz"];total=0.;rows=[]
    for item in assembly["instances"]:
        motion=item["motion"]
        if motion["kind"]!="shaft" or motion["axisYz"]!=axis:continue
        part=assembly["parts"][item["part_id"]]
        if "centralVolumeInertiaMm5" not in part:return None
        matrix=np.array(item["transform"]);rotation=matrix[:3,:3]
        center=(matrix@np.r_[part["local_com_mm"],1])[:3]
        inertia=rotation@np.array(part["centralVolumeInertiaMm5"])@rotation.T
        mass=part["mass_g"]/1000
        offset=center[1:]-axis-[0,assembly["bodyOriginZMm"]]
        value=(inertia[0,0]*mass/part["solid_volume_mm3"]+mass*np.dot(offset,offset))*1e-6
        total+=value;rows.append({"name":item["name"],"kgM2":float(value)})
    return {"inputShaftAssemblyKgM2":float(total),"components":rows,
            "basis":"actual B-rep volume inertia,scaled to each nominal part mass; purchased internal mass distribution is an envelope estimate",
            "includesReflectedDownstreamAndBodyInertia":False}

def joint_losses(assembly,theta,contact,positions,masses,mu):
    """Actual links/attached hardware gravity and existing18-equation linkage."""
    common=assembly["parameters"]["common"];scale=common["linkScale"];g=9.80665
    data=contact["data"];bodies=np.array(data["body_z_slopex_slopey"])
    normals=np.array(data["normal_n"]);slip=np.array(data["toe_slip_velocity_mm_per_rad"])
    feet=np.array(data["toes_body_mm"]);dt=theta[1]-theta[0]
    mu_ground=common["foot"]["groundFrictionCoefficientAssumed"]
    fxy=-mu_ground*normals[:,:,None]*slip/np.sqrt(np.sum(slip**2,axis=2)+.01**2)[:,:,None]
    leg_groups=defaultdict(list)
    for j,item in enumerate(assembly["instances"]):
        m=item["motion"]
        if m["kind"] in ("link","foot","joint"):
            leg_groups[(m["station"],m["side"],m["phase"])].append(j)
    loss=np.zeros(len(theta));reaction=np.zeros((len(theta),len(leg_groups)))
    side_forces=np.zeros((len(theta),2,2));side_moments=np.zeros((len(theta),2))
    max_force=0.;maximum_residual=0.
    root_stats={}
    if "fixedRootPocketEmbedMm" in common.get("legJournals",{}):
        root_stats={node:{"maximumResultantN":0.,"maximumMouthMomentNmm":0.,
                         "maximumProjectedSocketPressureMpa":0.,"maximumSleeveBendingMpa":0.}
                    for node in ("A","P")}
    for leg,(key,indices) in enumerate(leg_groups.items()):
        station,side,phase=key
        p,_=points_many(theta+phase,dimensions("reference",common),scale)
        angles={name:np.unwrap(np.arctan2((p[labels[1]]-p[labels[0]])[:,1],
                                         (p[labels[1]]-p[labels[0]])[:,0]))
                for name,labels in LINKS.items()}
        rates={name:derivative(value,dt) for name,value in angles.items()}
        for t in range(len(theta)):
            matrix=np.zeros((18,18));rhs=np.zeros(18)
            external={name:[] for name in LINKS}
            for index in indices:
                item=assembly["instances"][index];motion=item["motion"]
                if motion["kind"]=="link":targets=["L_"+motion["link"]]
                elif motion["kind"]=="foot":targets=["L_CEF"]
                elif motion["node"] in ("A","P"):continue
                else:targets=[n for n,labels in LINKS.items() if motion["node"] in labels]
                force=np.array([-bodies[t,2]*masses[index]*g,-masses[index]*g])/len(targets)
                yz=positions[t,index,1:]-[station,assembly["bodyOriginZMm"]]
                for name in targets:external[name].append((yz,force))
            ground=np.r_[fxy[t,leg],normals[t,leg]]
            ground_yz=np.array([ground[1]+bodies[t,2]*ground[2],
                                ground[2]-bodies[t,1]*ground[0]-bodies[t,2]*ground[1]])
            toe=feet[t,leg,1:]-[station,0]+[-bodies[t,2]*common["foot"]["toeRadiusMm"],-common["foot"]["toeRadiusMm"]]
            external["L_CEF"].append((toe,ground_yz))
            for row,name in enumerate(LINKS):
                reference=p[LINKS[name][0]][t]
                for variable,node,sign in INCIDENCE[name]:
                    column=2*VARIABLES.index(variable);arm=p[node][t]-reference
                    matrix[3*row,column]+=sign
                    matrix[3*row+1,column+1]+=sign
                    matrix[3*row+2,column]-=sign*arm[1]
                    matrix[3*row+2,column+1]+=sign*arm[0]
                for point,force in external[name]:
                    arm=point-reference
                    rhs[3*row:3*row+2]-=force
                    rhs[3*row+2]-=arm[0]*force[1]-arm[1]*force[0]
            forces=np.linalg.solve(matrix,rhs)
            maximum_residual=max(maximum_residual,float(abs(matrix@forces-rhs).max()))
            q={name:forces[2*j:2*j+2] for j,name in enumerate(VARIABLES)}
            norm={name:np.linalg.norm(value) for name,value in q.items()}
            max_force=max(max_force,max(norm.values()))
            if root_stats:
                journals=common["legJournals"];layers=common["legLayers"]
                diameter=journals["diameterMm"]
                inertia=math.pi*(diameter**4-2.2**4)/64
                for node,variables,links in (
                    ("A",("A_AB","A_AC"),("AB","AC")),
                    ("P",("P_TRI","P_PC"),("PBD","PC")),
                ):
                    embed=journals["rootPocketEmbedMm"] if node=="A" else journals["fixedRootPocketEmbedMm"]
                    mouth=50.5+journals["rootPocketEmbedMm"] if node=="A" else 54
                    arms=[54.65+layers[n]*common["legLayerPitchMm"]+common["linkThicknessMm"]/2-mouth for n in links]
                    resultant=np.linalg.norm(sum(q[n] for n in variables))
                    mouth=np.linalg.norm(sum(arm*q[n] for arm,n in zip(arms,variables)))
                    middle=np.linalg.norm(sum((arm+embed/2)*q[n] for arm,n in zip(arms,variables)))
                    pressure=resultant/(diameter*embed)+6*middle/(diameter*embed**2)
                    values={"maximumResultantN":resultant,"maximumMouthMomentNmm":mouth,
                            "maximumProjectedSocketPressureMpa":pressure,
                            "maximumSleeveBendingMpa":mouth*diameter/2/inertia}
                    for name,value in values.items():
                        root_stats[node][name]=max(root_stats[node][name],float(value))
            radius=common.get("legJournals",{}).get("diameterMm",6)/2
            friction=radius*(norm["A_AB"]*abs(rates["L_AB"][t]-1)+norm["A_AC"]*abs(rates["L_AC"][t]-1))
            friction+=radius*(norm["P_TRI"]*abs(rates["L_PBD"][t])+norm["P_PC"]*abs(rates["L_PC"][t]))
            for pin,first,second,pin_radius in (("B","L_AB","L_PBD",radius),("D","L_DE","L_PBD",radius),("E","L_DE","L_CEF",2)):
                friction+=pin_radius*norm[pin]*abs(rates[first][t]-rates[second][t])
            cweights=[norm["C_AC"],norm["C_PC"],np.linalg.norm(q["C_AC"]+q["C_PC"])]
            cr=[rates[n][t] for n in ("L_AC","L_PC","L_CEF")]
            # Retain the conservative free-journal rotation bound, rather than
            # silently assuming the lowest-drag pin rotation.
            friction+=2*max(sum(f*abs(v-pinv) for f,v in zip(cweights,cr)) for pinv in cr)
            loss[t]+=mu*friction
            crank=q["A_AB"]+q["A_AC"]
            reaction[t,leg]=p["A"][t,0]*crank[1]-p["A"][t,1]*crank[0]
            pivot=q["P_TRI"]+q["P_PC"]
            side_column=0 if side<0 else 1
            side_forces[t,side_column]-=crank+pivot
            arm_a=p["A"][t]+[station,0];arm_p=p["P"][t]+[station,0]
            side_moments[t,side_column]-=(arm_a[0]*crank[1]-arm_a[1]*crank[0]+arm_p[0]*pivot[1]-arm_p[1]*pivot[0])
    return loss,reaction,{"maxJournalForceN":max_force,"equilibriumResidual":maximum_residual,
                         "legOrder":[list(k) for k in leg_groups],
                         "rootPins":root_stats,
                         "coherentSideFrameForceMaximumN":np.linalg.norm(side_forces,axis=2).max(axis=0).tolist(),
                         "coherentSideFrameMomentMaximumNmm":abs(side_moments).max(axis=0).tolist(),
                         "rootPinMethod":"Same-phase signed link forces at actual axial link midplanes; projected linear socket pressure and annular sleeve bending,not Hertz stress or a material certificate.",
                         "method":"existing18-equation rigid-link statics with actual part mass; friction force feedback is not solved, retained as a modeling uncertainty"}


def retime_for_hex_cranks(assembly,new_phases):
    """Rigid repositioning only;60-degree indices leave the real hex profile invariant."""
    result=deepcopy(assembly)
    common=result["parameters"]["common"]
    original_phases=deepcopy(common["legPhasesDeg"])
    stations=(np.arange(len(new_phases))-(len(new_phases)-1)/2)*common["stationPitchMm"]
    phase_map={(float(s),side):math.radians(p) for s,pair in zip(stations,new_phases)
               for side,p in zip((-1,1),pair)}
    old_map={(float(s),side):math.radians(p) for s,pair in zip(stations,original_phases)
             for side,p in zip((-1,1),pair)}
    reference,_=points_many(np.array(0.),dimensions("reference",common),common["linkScale"])
    for item in result["instances"]:
        motion=item["motion"];kind=motion["kind"];matrix=np.array(item["transform"])
        if kind in ("link","joint","foot"):
            key=(motion["station"],motion["side"]);before=motion["phase"];after=phase_map[key]
            if abs((after-before)/(math.pi/3)-round((after-before)/(math.pi/3)))>1e-8:
                raise ValueError("Crank phase is not a real60-degree hex index")
            old_points,_=points_many(np.array(before),dimensions("reference",common),common["linkScale"])
            new_points,_=points_many(np.array(after),dimensions("reference",common),common["linkScale"])
            if kind=="link":
                matrix=np.array(link_pose(new_points,reference,rigids()[motion["link"]],key[0],assembly["bodyOriginZMm"]))
            elif kind=="joint":
                matrix[1:3,3]+=new_points[motion["node"]]-old_points[motion["node"]]
            else:
                old=np.array(link_pose(old_points,reference,rigids()["CEF"],key[0],assembly["bodyOriginZMm"]))
                new=np.array(link_pose(new_points,reference,rigids()["CEF"],key[0],assembly["bodyOriginZMm"]))
                matrix=new@np.linalg.inv(old)@matrix
            motion["phase"]=after
        elif kind=="crank" or (kind=="shaft" and item["group"]=="mainshafts"):
            point=(matrix@np.r_[result["parts"][item["part_id"]]["local_com_mm"],1])[:3]
            if kind=="crank" or abs(point[0])>40 and item["part_id"].startswith(("H_BOLT","H_NUT")):
                side=-1 if point[0]<0 else 1;key=(float(motion["axisYz"][0]),side)
                delta=phase_map[key]-old_map[key]
                center=np.array([0,key[0],assembly["bodyOriginZMm"]])
                c,s=math.cos(delta),math.sin(delta)
                rotation=np.eye(4);rotation[:3,:3]=[[1,0,0],[0,c,-s],[0,s,c]]
                rotation[:3,3]=center-rotation[:3,:3]@center
                matrix=rotation@matrix
        item["transform"]=matrix.tolist()
    common["legPhasesDeg"]=new_phases
    result["screeningOnly"]="rigid60-degree indexing of existing geometry; not a replacement final native export"
    return result


def contact_frames(assembly,gait,contact,result,source_commit,frame_step_deg=5):
    from build_integrated_contract import source_identity

    if not re.fullmatch(r"[0-9a-f]{40}",source_commit or ""):
        raise ValueError("Contact export requires an explicit source commit")
    if gait.lanes!=1:
        raise ValueError("Contact export currently requires the canonical single modeled center per foot")
    raw=contact["data"];theta=np.asarray(raw["theta_rad"])
    count=len(theta);stride=round(frame_step_deg/gait.step_deg)
    if (count<2 or stride<1 or count%stride or not math.isclose(count*gait.step_deg,360)
            or not math.isclose(stride*gait.step_deg,frame_step_deg)
            or not np.allclose(np.diff(theta),math.radians(gait.step_deg),atol=1e-12)):
        raise ValueError("Export frames must evenly sample the existing periodic solver grid")
    arrays={key:np.asarray(raw[key]) for key in (
        "body_z_slopex_slopey","normal_n","toes_body_mm","spring_compression_mm",
        "body_velocity_mm_per_rad","toe_slip_velocity_mm_per_rad")}
    foot_count=len(gait.legs)
    shapes={"body_z_slopex_slopey":(count,3),"normal_n":(count,foot_count),
            "toes_body_mm":(count,foot_count,3),"spring_compression_mm":(count,foot_count),
            "body_velocity_mm_per_rad":(count,3),"toe_slip_velocity_mm_per_rad":(count,foot_count,2)}
    for key,values in arrays.items():
        if values.shape!=shapes[key] or not np.all(np.isfinite(values)):
            raise ValueError("Missing,nonfinite or incorrectly shaped contact state: "+key)
    if (not np.all(np.isfinite(theta))
            or not math.isfinite(result["actualCogContactResidualMm"])
            or not math.isfinite(contact["tangential_force_moment_residual_normalized_max"])
            or result["actualCogContactResidualMm"]>=1e-5
            or contact["tangential_force_moment_residual_normalized_max"]>1e-6):
        raise ValueError("Unconverged contact state cannot become render frames")
    dt=math.radians(gait.step_deg)
    integrated=np.vstack([np.zeros(3),np.cumsum(arrays["body_velocity_mm_per_rad"]*dt,axis=0)])
    expected=np.array([contact["lateral_per_cycle_mm"],contact["advance_per_cycle_mm"],
                       contact["yaw_per_cycle_rad"]])
    if not np.allclose(integrated[-1],expected,rtol=1e-10,atol=1e-9):
        raise ValueError("Export integration disagrees with the existing contact summary")
    _,gamma=gait.neutral()
    if gamma.shape!=(count,foot_count) or not np.all(np.isfinite(gamma)):
        raise ValueError("Missing canonical guide pitch")
    speed=assembly["reduction"]["speedRatios"][0]
    input_rpm=120
    threshold=assembly["parameters"]["common"]["criteria"]["loadFootFraction"]*contact["mass_kg"]*9.80665
    frames=[]
    for index in range(0,count+1,stride):
        phase=index%count
        degrees=index*gait.step_deg
        frames.append({
            "crankDeg":degrees,"sourcePhaseIndex":phase,"periodicClosure":index==count,
            "inputDegUnwrapped":degrees*speed,
            "secondsAtPrescribed120InputRpm":degrees/360*abs(speed)*60/input_rpm,
            "bodyHeightAndSlopes":arrays["body_z_slopex_slopey"][phase].tolist(),
            "integratedPlanarComponents":integrated[index].tolist(),
            "bodyPlanarVelocityPerCrankRad":arrays["body_velocity_mm_per_rad"][phase].tolist(),
            "normalN":arrays["normal_n"][phase].tolist(),
            "loadedFoot":(arrays["normal_n"][phase]>threshold).tolist(),
            "springCompressionMm":arrays["spring_compression_mm"][phase].tolist(),
            "toesBodyMm":arrays["toes_body_mm"][phase].tolist(),
            "guidePitchRad":gamma[phase].tolist(),
            "toeSlipVelocityMmPerCrankRad":arrays["toe_slip_velocity_mm_per_rad"][phase].tolist(),
            "independentRockerAngleRad":None,
        })
    return {
        "schemaVersion":1,"revisionId":assembly["revisionId"],"designId":result["designId"],
        "sourceCommit":source_commit,"sourceHash":source_identity()[2],
        "reviewedGeometryArtifactCommit":"f50978e55384d1b03417ed7115395e6e2c010e85",
        "assemblySha256":hashlib.sha256((OUT/result["designId"]/"assembly.json").read_bytes()).hexdigest(),
        "mechanicalInputSha256":result["mechanicalInputSha256"],
        "analysisSourcesSha256":result["analysisSourcesSha256"],
        "method":"Decimated states from the existing converged analyze()/ContactGait.evaluate() result; no replacement contact,airflow,friction or walking solver.",
        "rawPhaseCount":count,"rawStepDeg":gait.step_deg,"frameStepDeg":frame_step_deg,
        "frameCount":len(frames),"cadReferenceBodyOriginZMm":assembly["bodyOriginZMm"],
        "footOrder":[{"stationYmm":float(station),"side":side,"phaseDeg":phase}
                     for station,side,phase in gait.legs],
        "units":{"bodyHeightAndSlopes":["mm","dz/dx","dz/dy"],
                 "integratedPlanarComponents":["mm","mm","rad"],
                 "bodyPlanarVelocityPerCrankRad":["mm/rad","mm/rad","rad/rad"],
                 "length":"mm","force":"N","anglesUnlessDeg":"rad"},
        "coordinates":{
            "native":"Right-handed native X=shaft/lateral,Y=station/longitudinal,Z=up.",
            "toesBodyMm":"Converged,compression-corrected foot-center coordinates relative to the body reference origin,not native absolute Z.",
            "bodyHeightAndSlopes":"Exactly the existing solver's body_z_slopex_slopey. Its point map is x'=x-slopeX*z,y'=y-slopeY*z,z'=z+height+slopeX*x+slopeY*y.",
            "integratedPlanarComponents":"Componentwise rectangular quadrature of the original dense body velocity in its reference axes. Origin at crank0 is chosen as [0,0,0]; not missing-state padding. This exactly preserves the saved lateral/advance/yaw aggregates; no new SE(2) trajectory solve.",
            "closure":"The explicit 360-degree endpoint uses the converged periodic phase0 state and the full dense-cycle integrated displacement.",
        },
        "prescribedTiming":{"absoluteInputRpm":input_rpm,"signedInputTurnsPerCrank":speed,
                            "cycleSeconds":abs(speed)*60/input_rpm,"achievedOrPredicted":False},
        "convergence":{"actualCogContactIterations":result["actualCogContactIterations"],
                       "actualCogContactResidualMm":result["actualCogContactResidualMm"],
                       "maximumTangentialResidualNormalized":contact["tangential_force_moment_residual_normalized_max"]},
        "denseCycleSummary":{"integratedPlanarComponents":integrated[-1].tolist(),
                             "maximumCompressionMm":float(arrays["spring_compression_mm"].max()),
                             "minimumLoadedFeet":contact["minimum_loaded_feet"],
                             "savedAdvancePerCrankCycleMm":result["kinematicTravel"]["advancePerCrankCycleMm"]},
        "unavailableComponents":{"independentRockerAngleRad":"Not a solved independent state in the canonical single-center/equalizing-rocker model. Null is intentional; never substitute zero.",
                                 "rigidBodyWorld4x4":"The canonical body pose is a small-angle approximation,not a measured/exact rigid-body trajectory.",
                                 "actualInputSpeed":"Prescribed120RPM is a display clock,not an achieved or predicted speed."},
        "manufacturingRelease":False,"physicalTestsPerformed":False,"frames":frames,
    }


def analyze(design,step_deg=.5,assembly_override=None,output_dir=None,air_case=None,
            motion_output=None,source_commit=None):
    if motion_output is not None and output_dir is None:
        raise ValueError("Contact export requires a separate analysis output directory to preserve frozen budgets")
    if motion_output is not None and (assembly_override is not None or air_case is not None):
        raise ValueError("Publication contact frames must use the unchanged canonical assembly and reference air case")
    if motion_output is not None and not re.fullmatch(r"[0-9a-f]{40}",source_commit or ""):
        raise ValueError("Contact export requires an explicit source commit")
    source_folder=OUT/design
    folder=Path(output_dir) if output_dir else source_folder
    folder.mkdir(parents=True,exist_ok=True)
    assembly=assembly_override or json.loads((source_folder/"assembly.json").read_text())
    common=assembly["parameters"]["common"];g=9.80665
    gait=ContactGait(common,dimensions("reference"),step_deg)
    theta=gait.angles;dt=theta[1]-theta[0]
    positions,masses,fast,legs=cad_positions(assembly,theta)
    mass=float(masses.sum())
    cog=np.sum(positions*masses[None,:,None],axis=1)/mass
    jet=air_proxy(assembly,air_case);air=np.array(jet["rows"])
    # A whole-jet momentum force envelope is a SUPPORT load, never credited as
    # obtainable driving torque.
    momentum=1.225*jet["peak_velocity_m_s"]**2*math.pi*(jet["velocity_sigma_mm"]/1000)**2
    side_force=2*momentum;down_force=momentum
    iy,iz=assembly["inputLayout"]["axisYz"];height=assembly["bodyOriginZMm"]+iz
    normal_total=mass*g+down_force
    effective_cog=cog[:,:2].copy()*mass*g/normal_total
    effective_cog[:,1]+=(down_force*iy+side_force*height)/normal_total
    effective_cog[:,0]+=down_force*28/normal_total
    input_cop_x=28
    for contact_iteration in range(12):
        contact=gait.evaluate(mass+down_force/g,cog_xy=effective_cog,guide_mode=0,
                             external_planar_load=(0,side_force,input_cop_x*side_force))
        compression=np.array(contact["data"]["spring_compression_mm"])
        positions,masses,fast,legs=cad_positions(assembly,theta,compression)
        bodies=np.array(contact["data"]["body_z_slopex_slopey"])
        cog=np.sum(positions*masses[None,:,None],axis=1)/mass
        world_cog=cog[:,:2]-bodies[:,1:]*((cog[:,2]-assembly["bodyOriginZMm"])[:,None])
        updated=world_cog*mass*g/normal_total
        head_xy=np.array([input_cop_x,iy])-bodies[:,1:]*iz
        updated+=down_force*head_xy/normal_total
        head_height=bodies[:,0]+iz+bodies[:,1]*input_cop_x+bodies[:,2]*iy
        updated[:,1]+=side_force*head_height/normal_total
        cop_error=float(abs(updated-effective_cog).max())
        if cop_error<1e-5:break
        effective_cog=updated
    else:
        raise ValueError("Actual-CAD COM/contact fixed point did not converge")
    body_xy=positions[:,:,0:2];z=positions[:,:,2]-assembly["bodyOriginZMm"]
    height_points=z+bodies[:,None,0]+bodies[:,None,1]*body_xy[:,:,0]+bodies[:,None,2]*body_xy[:,:,1]
    gravity_potential=np.sum(masses[None,:]*g*height_points,axis=1)
    stiffness=np.array(contact["foot_k_nmm"])
    spring_potential=.5*np.sum(compression**2*stiffness,axis=1)
    potential_rate=derivative(gravity_potential+spring_potential,dt)
    normals=np.array(contact["data"]["normal_n"]);slip=np.array(contact["data"]["toe_slip_velocity_mm_per_rad"])
    ground_mu=common["foot"]["groundFrictionCoefficientAssumed"]
    slip_work_rate=ground_mu*np.sum(normals*np.linalg.norm(slip,axis=2),axis=1)
    body_v=np.array(contact["data"]["body_velocity_mm_per_rad"])
    pitch_rate=derivative(bodies[:,2],dt)
    input_y_rate=body_v[:,1]+body_v[:,2]*(input_cop_x-bodies[:,1]*iz)-pitch_rate*iz
    input_z_rate=derivative(bodies[:,0]+bodies[:,1]*input_cop_x+bodies[:,2]*iy,dt)
    wind_work_rate=-side_force*input_y_rate+down_force*input_z_rate
    compression_rate=derivative(compression,dt)
    guide_base=np.zeros_like(normals);rocker_base=np.zeros(len(theta))
    guide_root_moment=0.;guide_axial_residual=0.
    ground_xy=-ground_mu*normals[:,:,None]*slip/np.sqrt(np.sum(slip**2,axis=2)+.01**2)[:,:,None]
    for i,(station,side,phase) in enumerate(legs):
        points,_=points_many(theta+phase,dimensions("reference",common),common["linkScale"])
        angle=np.unwrap(np.arctan2((points["E"]-points["C"])[:,1],(points["E"]-points["C"])[:,0]))
        gamma=angle-math.radians(common["foot"]["pitchReferenceBodyAngleDeg"])
        n=np.column_stack([-bodies[:,1]*np.cos(gamma),-np.sin(gamma)-bodies[:,2]*np.cos(gamma),
                          np.cos(gamma)-bodies[:,2]*np.sin(gamma)])
        n/=np.linalg.norm(n,axis=1)[:,None]
        force=np.column_stack([ground_xy[:,i],normals[:,i]])
        lever=common["foot"]["movingBushingStartAboveFmm"]+common["foot"]["guideBearingLengthMm"]/2-common["foot"]["toeOffsetFromFNeutralMm"][1]
        arm=-lever*n;arm[:,2]-=common["foot"]["toeRadiusMm"]
        offset=common["foot"].get("guideCenterFootYmm",0.)
        local_y=np.column_stack([-bodies[:,1]*np.sin(gamma),
                                 np.cos(gamma)-bodies[:,2]*np.sin(gamma),
                                 np.sin(gamma)+bodies[:,2]*np.cos(gamma)])
        local_y-=np.sum(local_y*n,axis=1)[:,None]*n
        local_y/=np.linalg.norm(local_y,axis=1)[:,None]
        spring_force=stiffness[i]*compression[:,i]
        spring_arm=-offset*local_y
        moment=np.cross(arm+spring_arm,force)+np.cross(spring_arm,-spring_force[:,None]*n)
        parallel=np.sum(moment*n,axis=1)
        moment_perp=moment-parallel[:,None]*n
        perpendicular=force-n*np.sum(force*n,axis=1)[:,None]
        differential=np.cross(n,moment_perp)/common["foot"]["guideBearingLengthMm"]
        first=-.5*perpendicular-differential;second=-.5*perpendicular+differential
        guide_base[:,i]=np.linalg.norm(first,axis=1)+np.linalg.norm(second,axis=1)+abs(parallel)/common["foot"].get("antiRotationLeverMm",10)
        root_lever=common["foot"]["guideRootAboveFmm"]-(common["foot"]["movingBushingStartAboveFmm"]+common["foot"]["guideBearingLengthMm"]/2)
        at_root=moment+np.cross(-root_lever*n,force)
        guide_root_moment=max(guide_root_moment,float(np.linalg.norm(at_root,axis=1).max()))
        guide_axial_residual=max(guide_axial_residual,float(abs(np.sum(force*n,axis=1)-spring_force).max()))
        rocker_angle=bodies[:,1]/np.maximum(n[:,2],.2)
        rocker_base+=common["foot"].get("rockerPinJournalRadiusMm",3)*np.linalg.norm(force,axis=1)*abs(derivative(rocker_angle,dt))
    cases=[]
    ratios=assembly["candidate"]["stageRatios"];ratio=math.prod(ratios)
    fine=np.arange(0,2*math.pi,math.radians(.5)/ratio)
    raw_supply=np.interp(np.degrees(ratio*fine)%360,np.r_[air[:,0],360],np.r_[air[:,1],air[0,1]])
    pitch=np.interp(fine,np.r_[theta,2*math.pi],np.r_[bodies[:,2],bodies[0,2]])
    pitch_derivative=np.interp(fine,np.r_[theta,2*math.pi],np.r_[pitch_rate,pitch_rate[0]])
    gravity_work=shaft_gravity_work(fast,assembly["reduction"]["axesYzMm"],fine,pitch,pitch_derivative)
    inertia=input_inertia(assembly)
    unit_pin_loss,reaction,statistics=joint_losses(assembly,theta,contact,positions,masses,1)
    linkage_work_reference=potential_rate+wind_work_rate+slip_work_rate
    statistics["wholeReferenceWorkResidualMaximumNmm"]=float(abs(reaction.sum(axis=1)-linkage_work_reference).max())
    statistics["wholeReferenceWorkResidualRmsNmm"]=float(np.sqrt(np.mean((reaction.sum(axis=1)-linkage_work_reference)**2)))
    statistics["wholeReferenceWorkPeakNmm"]=float(abs(linkage_work_reference).max())
    resistance=assembly["parameters"]["resistance"]
    if any(len(values)!=3 for values in (resistance["bearingEachNmmCases"],resistance["journalMuCases"],
                                         common["foot"]["guideFrictionMuSensitivity"],resistance["meshEfficiencyCases"])):
        raise ValueError("Exactly three aligned resistance cases are required")
    for case,(bearing_drag,mu,guide_mu,eta) in enumerate(zip(
        assembly["parameters"]["resistance"]["bearingEachNmmCases"],
        assembly["parameters"]["resistance"]["journalMuCases"],
        common["foot"]["guideFrictionMuSensitivity"],
        assembly["parameters"]["resistance"]["meshEfficiencyCases"])):
        pin_loss=unit_pin_loss*mu
        guide_loss=guide_mu*np.sum(guide_base*abs(compression_rate),axis=1)
        rocker_loss=mu*rocker_base
        dissipative=slip_work_rate+guide_loss+rocker_loss+pin_loss
        net=potential_rate+wind_work_rate+dissipative
        circulation=station_circulation(reaction,statistics["legOrder"])
        bus_bound=(1/eta**2-1)*(abs(potential_rate+wind_work_rate)+dissipative+circulation)
        bus_bearings=bearing_drag*(2+4/eta**2+2/eta)
        downstream=np.maximum(net+bus_bound,0)+bus_bearings
        input_pair=2*bearing_drag
        output_work=np.interp(fine,np.r_[theta,2*math.pi],np.r_[downstream,downstream[0]])
        required_nmm,reducer_loss=reflect_shaft_work(
            output_work,gravity_work,assembly["reduction"]["speedRatios"],eta,bearing_drag)
        required=required_nmm/1000
        margin=raw_supply-required;worst=int(np.argmin(margin))
        # Absolute increments prevent forward/backward slip from cancelling.
        work_slip=float(np.sum(slip_work_rate)*dt)
        record={"case":("low","nominal","high")[case],
                "requiredInputMaximumNm":float(required.max()),
                "rawSupplyMinimumNm":float(raw_supply.min()),
                "rawPhaseMinimumMarginNm":float(margin[worst]),
                "rawEnvelopeMarginNm":float(raw_supply.min()-required.max()),
                "halfProxyPhaseMinimumMarginNm":float((.5*raw_supply-required).min()),
                "downstream2xPhaseMinimumMarginNm":float((raw_supply-(2*(required-input_pair/1000)+input_pair/1000)).min()),
                "inputBearingPairNmAssumed":input_pair/1000,
                "maximumInputBearingPairForRawBalanceNm":float((raw_supply-required+input_pair/1000).min()),
                "inputOnlyAccelerationHeadroomRadS2":float(margin.min()/inertia["inputShaftAssemblyKgM2"]) if inertia else None,
                "guideMuAssumed":guide_mu,"meshEfficiencyAssumed":eta,
                "guideRootMomentMaximumNmm":guide_root_moment,
                "guideAxialForceResidualMaximumN":guide_axial_residual,
                "workPerCycleNmm":{"groundSlip":work_slip,"guide":float(guide_loss.sum()*dt),
                                  "rocker":float(rocker_loss.sum()*dt),"legJournals":float(pin_loss.sum()*dt),
                                  "potentialNet":float(potential_rate.sum()*dt),
                                  "windForce":float(wind_work_rate.sum()*dt)},
                "worstPhase":{"crankDeg":float(np.degrees(fine[worst])),
                              "signedInputDeg":float(np.degrees(fine[worst])*assembly["reduction"]["speedRatios"][0]),
                              "supplyNm":float(raw_supply[worst]),"requiredNm":float(required[worst])},
                "forceStatistics":statistics,
                "reducerMeshLossPerCycleNmm":[float(x.sum()*(fine[1]-fine[0])) for x in reducer_loss],
                "sameShaftCancellationBeforeLoss":True,
                "reactionEnergyConsistencyInputScaleNm":statistics["wholeReferenceWorkResidualMaximumNmm"]/(ratio*eta**len(ratios)*1000),
                "rawReferenceBudgetStatus":"PASS" if margin.min()>=0 else "FAIL",
                "physicalSelfStart":"UNKNOWN"}
        assert work_slip>=0 and min(record["workPerCycleNmm"][k] for k in ("guide","rocker","legJournals"))>=0
        cases.append(record)
    contact_summary={k:v for k,v in contact.items() if k!="data"}
    advance=abs(contact["advance_per_cycle_mm"])
    result={"revisionId":assembly["revisionId"],"modelRevision":"shaft-power-flow-r4-full-wind-point-velocity","designId":design,"cadMassKg":mass,
            "airCase":air_case or {"id":"reference","peakMS":6.4,"sigmaMm":20,"aimShiftMm":0},
            "analysisSourcesSha256":{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ("analyze_integrated_walkers.py","walker_contact.py","walker_kinematics.py",
                             "walker_geometry.py","walker_air.py","core.py","design.json")},
            "mechanicalInputSha256":hashlib.sha256(json.dumps(
                {"common":common,"candidate":assembly["candidate"],"parts":assembly["parts"],
                 "instances":assembly["instances"]},sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            "meanBodyCogMm":cog.mean(axis=0).tolist(),
            "actualCogContactIterations":contact_iteration+1,"actualCogContactResidualMm":cop_error,
            "effectiveSupportCopTrajectoryMm":effective_cog.tolist(),
            "inputInertia":inertia,
            "supportWindEnvelope":{"sideN":side_force,"downN":down_force,
                 "basis":"whole adopted Gaussian-jet momentum SUPPORT bound; no torque/power extraction credit"},
            "contact":contact_summary,"cases":cases,
            "kinematicTravel":{"advancePerCrankCycleMm":advance,"inputRevolutionsFor300mm":300/advance*ratio,
                 "minutesAt120InputRpmNotPredicted":300/advance*ratio/120,
                 "inputRpmFor300mmInTwoMinutes":300/advance*ratio/2,
                 "runningAirTorqueModel":None},
            "proxy":{k:v for k,v in jet.items() if k!="rows"},
            "limits":["Reference-work model,not calibrated startup or impact dynamics.",
                      "Normal path uses the frictionless guide reference; guide dissipation is added once,not hidden in a changed spring rate.",
                      "No measured friction or aero coefficient. No requiredRPM is claimed to be achieved.",
                      "Bus losses bound internal circulation rather than cancelling regenerative leg work.",
                      "Opposed legs on one shaft and balanced rotating hardware cancel before mesh losses; each real mesh transforms net shaft power once. Input-shaft gravity does not traverse reducer meshes.",
                      "Negative aggregate output demand is still clipped as a conservative reference bound,not a claim that spring energy is dissipated twice.",
                      "Journal reactions are first-order statics; friction-force feedback remains unquantified.",
                      "Only the saved CAD BOM is counted; unmodeled guards/access fixes cannot be silently declared covered."]}
    if motion_output is not None:
        frames=contact_frames(assembly,gait,contact,result,source_commit)
        Path(motion_output).write_text(json.dumps(frames,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (folder/"work_budget.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    np.savetxt(folder/"work_profile.csv",np.column_stack([np.degrees(theta),potential_rate,slip_work_rate,wind_work_rate]),
               delimiter=",",header="crank_deg,potential_rate_Nmm,ground_slip_rate_Nmm,wind_force_rate_Nmm",comments="")
    print(design,"kg",mass,"support",contact["support_and_compliance_pass"],"stroke",contact["maximum_guide_compression_mm"])
    for r in cases:print(r["case"],"input_mNm",1000*r["requiredInputMaximumNm"],"phaseMargin_mNm",1000*r["rawPhaseMinimumMarginNm"],"slip_Nmm",r["workPerCycleNmm"]["groundSlip"])
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design",choices=("A","B","C"),required=True)
    parser.add_argument("--step-deg",type=float,default=.5)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--motion-output",type=Path)
    parser.add_argument("--source-commit")
    args=parser.parse_args()
    analyze(args.design,args.step_deg,output_dir=args.output_dir,
            motion_output=args.motion_output,source_commit=args.source_commit)
