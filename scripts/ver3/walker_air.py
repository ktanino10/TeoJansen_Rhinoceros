"""Same adopted cold jet, actual rotor chord lines and explicit guard shadow.

This is a static ray/panel surrogate, not CFD. Guard wakes, pressure recovery,
rotating-blade flow and an appliance-specific measured lower bound are absent.
"""

import math

import numpy as np


def guard_transmission(z_mm,radius_mm,guard,sigma_mm=20):
    if not guard.get("rotorCage",False):
        return np.ones_like(z_mm),1.
    inner=radius_mm+guard["radialClearanceMm"]
    outer=inner+guard["radialWallMm"]
    width=guard["ribWidthMm"];pitch=guard["gridPitchMm"]
    count=math.ceil(2*math.pi*(inner+guard["radialWallMm"]/2)/pitch)
    blocked=np.zeros(len(z_mm),dtype=bool)
    for angle in np.arange(count)*2*math.pi/count:
        if "longitudinalBarDepthAlongWindMm" in guard:
            center=(inner+outer)/2*np.array([math.cos(angle),math.sin(angle)])
            depth,height=guard["longitudinalBarDepthAlongWindMm"],guard["longitudinalBarHeightAcrossWindMm"]
            yz=center+np.array([[y,z] for y in (-depth/2,depth/2) for z in (-height/2,height/2)])
        else:
            corners=np.array([[r,t] for r in (inner,outer) for t in (-width/2,width/2)])
            rotation=np.array([[math.cos(angle),math.sin(angle)],[-math.sin(angle),math.cos(angle)]])
            yz=corners@rotation
        if yz[:,0].min()<0:
            blocked |= (z_mm>=yz[:,1].min()) & (z_mm<=yz[:,1].max())
    total=sigma_mm*math.sqrt(math.pi)*math.erf(16/sigma_mm)
    starts=guard.get("hoopStartXmm")
    if starts is None:
        starts=np.linspace(guard["startXmm"],guard["endXmm"]-width,
                           math.ceil((guard["endXmm"]-guard["startXmm"])/pitch)+1)
    obscured=0.
    for x in starts:
        lo,hi=max(12,x),min(44,x+width)
        if hi>lo:
            obscured+=sigma_mm*math.sqrt(math.pi)/2*(math.erf((hi-28)/sigma_mm)-math.erf((lo-28)/sigma_mm))
    fraction=1-obscured/total
    if not 0<fraction<=1:raise ValueError("Guard rings close the adopted active jet")
    return (~blocked).astype(float)*fraction,fraction


def static_supply(assembly,rays=2048,step_deg=.5,guarded=True,peak_ms=6.4,sigma_mm=20,aim_shift_mm=0):
    if rays<32 or not 0<step_deg<=360:raise ValueError("Invalid finite air sampling")
    candidate=assembly["candidate"];guard=assembly["parameters"]["common"].get("guards",{})
    radius_mm=candidate["rotorDiameterMm"]/2
    sign=1 if assembly["reduction"]["speedRatios"][0]>0 else -1
    outer=(radius_mm-.8)/1000;span=candidate["activeSpanMm"]/1000
    rho,sigma,speed,coefficient=1.225,sigma_mm/1000,peak_ms,1.2
    if min(sigma,speed)<=0:raise ValueError("Positive explicit jet speed and width are required")
    z=np.linspace(-outer,outer,rays,endpoint=False)+outer/rays
    aim=-sign*(radius_mm/2+aim_shift_mm)/1000
    q=(.5*rho*speed**2*sigma*math.sqrt(math.pi)*math.erf(span/(2*sigma))*
       2*outer/rays*np.exp(-((z-aim)/sigma)**2))
    transmission,axial=guard_transmission(z*1000,radius_mm,guard if guarded else {},sigma_mm)
    r=np.linspace(.0225,outer,25)
    curve=sign*np.linspace(0,math.radians(20),25)
    rows=[]
    for progress in np.arange(0,360,step_deg):
        angles=sign*np.radians(progress)+np.arange(16)[:,None]*math.pi/8+curve[None,:]
        points=np.stack([r*np.cos(angles),r*np.sin(angles)],axis=-1)
        start=points[:,:-1].reshape(-1,2);delta=np.diff(points,axis=1).reshape(-1,2)
        usable=abs(delta[:,1])>1e-12
        fraction=np.zeros((len(start),rays))
        np.divide(z[None,:]-start[:,1,None],delta[:,1,None],out=fraction,where=usable[:,None])
        distances=np.where(usable[:,None]&(fraction>=0)&(fraction<1),
                           start[:,0,None]+fraction*delta[:,0,None],np.inf)
        first=np.argmin(distances,axis=0);hit_y=distances[first,np.arange(rays)]
        hit=np.isfinite(hit_y);hit_y=np.where(hit,hit_y,0)
        segment=delta[first]
        normal=np.column_stack([-segment[:,1],segment[:,0]])
        normal/=np.linalg.norm(normal,axis=1)[:,None]
        fy=coefficient*q*transmission*normal[:,0]**2*hit
        fz=coefficient*q*transmission*normal[:,0]*normal[:,1]*hit
        torque=sign*(hit_y*fz-z*fy)
        rows.append([float(progress),float(torque.sum()),float(fy.sum()),float(fz.sum()),
                     float(torque[torque<0].sum()),float((q*transmission*hit).sum()/q.sum())])
    values=np.array(rows)
    return {"method":"static first-hit panel-normal force on the actual25-point chord lines; explicit fixed cage ray shadow,not CFD",
            "angle_step_deg":step_deg,"rays":rays,"blade_count":16,"sweep_deg":20*sign,
            "physicalInputRotationSign":sign,"jetAimOffsetZMm":aim*1000,
            "peak_velocity_m_s":speed,"velocity_sigma_mm":sigma*1000,
            "activeSpanMm":span*1000,"outerRotorSpanMm":38,
            "guardAxialPressureAreaTransmission":axial,
            "guardPressureAreaTransmission":float((q*transmission).sum()/q.sum()),
            "rawGuardedMinimumNm":float(values[:,1].min()),
            "whole_jet_kinetic_power_w":rho*speed**3*math.pi*sigma**2/3,
            "wholeJetMomentumN":rho*speed**2*math.pi*sigma**2,
            "measured_supply_lower_bound_nm":None,"actual_self_start_status":"UNKNOWN",
            "limits":["Nominal6.4m/s Gaussian peak and sigma20mm,or explicitly labelled sensitivity inputs;not appliance calibration.",
                      "B uses the mirrored rotor and an equal-magnitude aim ABOVE its axis so the physical torque drives its negative input rotation. A/C aim below; no reversed useful torque is silently credited.",
                      "Incoming cage rays are blocked,not losslessly guided. Cage wakes/outflow/backpressure and sheet-shield flow interaction are uncalibrated.",
                      "Pressure recovery,recirculation and three-dimensional flow are absent; model rankings cannot prove another rotor shape impossible.",
                      "Static torque is not a running power curve. Nonzero speed additionally requires torque*omega below captured kinetic power."],
            "rows":rows,"columns":["positive_input_progress_deg","useful_torque_nm","global_force_y_n",
                                   "global_force_z_n","negative_useful_panel_torque_nm","hit_pressure_area_fraction"]}
