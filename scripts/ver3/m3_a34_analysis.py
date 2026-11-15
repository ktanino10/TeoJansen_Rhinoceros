"""Versioned 3.4 analysis: preserve frozen 3.1 code and account for per-node journals.

The two entry functions derive from the 3.1 reference-work model. Shared
kinematics, contact, airflow and shaft-power helpers remain imported unchanged.
"""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from core import LINKS
from study_r2 import INCIDENCE, VARIABLES
from walker_kinematics import points_many
from walker_contact import ContactGait, dimensions
from walker_geometry import ROOT, OUT
from analyze_integrated_walkers import (
    derivative, cad_positions, air_proxy, input_inertia,
    station_circulation, reflect_shaft_work, shaft_gravity_work, contact_frames,
)

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
                for node,variables,links in (
                    ("A",("A_AB","A_AC"),("AB","AC")),
                    ("P",("P_TRI","P_PC"),("PBD","PC")),
                ):
                    diameter=journals.get("perNodeDiameterMm",{}).get(node,journals["diameterMm"])
                    bore=journals.get("perNodeSleeveBoreMm",{}).get(node,2.2)
                    inertia=math.pi*(diameter**4-bore**4)/64
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
            journals=common.get("legJournals",{})
            radii={node:diameter/2 for node,diameter in journals.get("perNodeDiameterMm",{}).items()}
            radius=journals.get("diameterMm",6)/2
            a_radius=radii.get("A",radius);p_radius=radii.get("P",radius)
            friction=a_radius*(norm["A_AB"]*abs(rates["L_AB"][t]-1)+norm["A_AC"]*abs(rates["L_AC"][t]-1))
            friction+=p_radius*(norm["P_TRI"]*abs(rates["L_PBD"][t])+norm["P_PC"]*abs(rates["L_PC"][t]))
            for pin,first,second,pin_radius in (("B","L_AB","L_PBD",radius),("D","L_DE","L_PBD",radius),("E","L_DE","L_CEF",2)):
                pin_radius=radii.get(pin,pin_radius)
                friction+=pin_radius*norm[pin]*abs(rates[first][t]-rates[second][t])
            cweights=[norm["C_AC"],norm["C_PC"],np.linalg.norm(q["C_AC"]+q["C_PC"])]
            cr=[rates[n][t] for n in ("L_AC","L_PC","L_CEF")]
            # Retain the conservative free-journal rotation bound, rather than
            # silently assuming the lowest-drag pin rotation.
            friction+=radii.get("C",2)*max(sum(f*abs(v-pinv) for f,v in zip(cweights,cr)) for pinv in cr)
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


def analyze(design,step_deg=.5,assembly_override=None,output_dir=None,air_case=None,
            motion_output=None,source_commit=None,contact_sink=None):
    if motion_output is not None and output_dir is None:
        raise ValueError("Contact export requires a separate analysis output directory to preserve frozen budgets")
    if motion_output is not None and (assembly_override is not None or air_case is not None):
        raise ValueError("Publication contact frames must use the unchanged canonical assembly and reference air case")
    if motion_output is not None and not re.fullmatch(r"[0-9a-f]{40}",source_commit or ""):
        raise ValueError("Contact export requires an explicit source commit")
    source_folder=ROOT/"docs/ver3/m3_a34"
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
        mesh_work=[]
        required_nmm,reducer_loss=reflect_shaft_work(
            output_work,gravity_work,assembly["reduction"]["speedRatios"],eta,bearing_drag,mesh_work)
        mesh_forces=[]
        for load in sorted(mesh_work,key=lambda row:row["stage"]):
            stage=assembly["reduction"]["stages"][load["stage"]];module=stage.get("moduleMm",1)
            pinion_radius=module*stage["pinion"]/2;wheel_radius=module*stage["wheel"]/2
            tangential=max(load["pinionWorkMaximumNmmPerCrankRad"]/abs(stage["pinionSpeedPerCrank"])/pinion_radius,
                           load["wheelWorkMaximumNmmPerCrankRad"]/abs(stage["wheelSpeedPerCrank"])/wheel_radius)
            pressure=stage.get("pressureAngleDeg",25)
            mesh_forces.append({"stage":load["stage"],"moduleMm":module,"pressureAngleDeg":pressure,
                                "pinionPitchRadiusMm":pinion_radius,"wheelPitchRadiusMm":wheel_radius,
                                "tangentialForceUpperN":tangential,
                                "separatingForceUpperN":tangential*math.tan(math.radians(pressure)),
                                "resultantForceUpperN":tangential/math.cos(math.radians(pressure)),
                                "basis":"Maximum reflected per-shaft work divided by actual speed and pitch radius; conservative eta-dependent bound,not a resolved tooth-friction distribution."})
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
                "reducerMeshForceBounds":mesh_forces,
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
    result={"revisionId":assembly["revisionId"],"modelRevision":"shaft-power-flow-r4-per-node-m3","designId":design,"cadMassKg":mass,
            "airCase":air_case or {"id":"reference","peakMS":6.4,"sigmaMm":20,"aimShiftMm":0},
            "analysisSourcesSha256":{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ("m3_a34_analysis.py","analyze_integrated_walkers.py","walker_contact.py","walker_kinematics.py",
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
    if contact_sink is not None:
        contact_sink(assembly,gait,contact,result)
    if motion_output is not None:
        frames=contact_frames(assembly,gait,contact,result,source_commit)
        Path(motion_output).write_text(json.dumps(frames,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (folder/"work_budget.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    np.savetxt(folder/"work_profile.csv",np.column_stack([np.degrees(theta),potential_rate,slip_work_rate,wind_work_rate]),
               delimiter=",",header="crank_deg,potential_rate_Nmm,ground_slip_rate_Nmm,wind_force_rate_Nmm",comments="")
    print(design,"kg",mass,"support",contact["support_and_compliance_pass"],"stroke",contact["maximum_guide_compression_mm"])
    for r in cases:print(r["case"],"input_mNm",1000*r["requiredInputMaximumNm"],"phaseMargin_mNm",1000*r["rawPhaseMinimumMarginNm"],"slip_Nmm",r["workPerCycleNmm"]["groundSlip"])
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--step-deg", type=float, default=0.5)
    args = parser.parse_args()
    assembly = json.loads(args.assembly.read_text())
    analyze("A", args.step_deg, assembly_override=assembly, output_dir=args.output)
