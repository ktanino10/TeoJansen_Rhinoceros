"""Conservative native-shape floor screening in the canonical contact frame."""

import hashlib
import json
import math

import numpy as np

from walker_contact import ContactGait, dimensions
from walker_geometry import body_points, rigids
from walker_kinematics import points_many


def identity(assembly):
    values={key:assembly[key] for key in ("parts","instances","bodyOriginZMm","parameters","reduction")}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def minimum_cloud(points,circles,normals):
    result=np.min(normals@np.asarray(points).T,axis=1)
    for circle in circles:
        center=np.asarray(circle["center"]);axis=np.asarray(circle["axis"])
        radial=np.sqrt(np.maximum(0,np.sum(normals*normals,axis=1)-(normals@axis)**2))
        result=np.minimum(result,normals@center-circle["radius"]*radial)
    return result


def rocker_minimum(points,normals,axis,limit):
    points=np.asarray(points)
    parallel=(points@axis)[:,None]*axis
    perpendicular=points-parallel
    a=normals@perpendicular.T
    b=normals@np.cross(np.broadcast_to(axis,points.shape),perpendicular).T
    fixed=normals@parallel.T
    low=np.minimum(a*math.cos(limit)-b*math.sin(limit),a*math.cos(limit)+b*math.sin(limit))
    extremum=(np.arctan2(b,a)+math.pi+math.pi)%(2*math.pi)-math.pi
    low=np.where(abs(extremum)<=limit,-np.hypot(a,b),low)
    return np.min(fixed+low,axis=1)


def radial_lower_bound(body,axis_yz,x_range,radius):
    xlo,xhi=x_range
    low=body[:,0]+axis_yz[1]+body[:,2]*axis_yz[0]
    low+=np.minimum(body[:,1]*xlo,body[:,1]*xhi)
    return low-radius*np.sqrt(1+body[:,2]**2)


def check(assembly,envelopes,contact,errors=None,case_id="reference"):
    errors=errors or {}
    if envelopes["mechanicalIdentity"]!=identity(assembly):
        raise ValueError("Native floor envelopes do not match the current assembly")
    if set(envelopes["parts"])!=set(assembly["parts"]):
        raise ValueError("Floor envelope inventory is incomplete")
    rotating={i["name"] for i in assembly["instances"] if i["motion"]["kind"] in ("shaft","crank")}
    if set(envelopes["rotatingInstances"])!=rotating:
        raise ValueError("Rotating floor envelope inventory is incomplete")
    c=assembly["parameters"]["common"];raw=contact["data"]
    theta=np.asarray(raw["theta_rad"]);body=np.asarray(raw["body_z_slopex_slopey"])
    compression=np.asarray(raw["spring_compression_mm"])
    if body.shape!=(len(theta),3) or compression.shape!=(len(theta),6):
        raise ValueError("Missing canonical body/foot state")
    if not all(np.isfinite(v).all() for v in (theta,body,compression)):
        raise ValueError("Nonfinite contact state cannot pass a floor check")
    if np.any(compression<0) or np.any(compression>c["foot"]["workingCompressionLimitMm"]+1e-8):
        raise ValueError("Floor screen requires the declared physical spring travel")
    floor=c["errors"]["floorHeightErrorMm"]
    profile_allowance=c["errors"]["linkPitchErrorMm"]+2*c["errors"]["pinRadialPlayMm"]
    normals=np.column_stack((body[:,1],body[:,2],np.ones(len(theta))))
    gait=ContactGait(c,dimensions("reference"),math.degrees(theta[1]-theta[0]))
    if gait.lanes!=1:raise ValueError("Floor screen requires the canonical six center-foot states")
    frames={}
    for j,(station,side,phase_deg) in enumerate(gait.legs):
        dims=dict(gait.dims)
        for key,delta in errors.get("lengths",[{} for _ in gait.legs])[j].items():
            dims[key]+=delta/c["linkScale"]
        angle=theta+math.radians(phase_deg+errors.get("phase_deg",[0]*6)[j])
        points,_=points_many(angle,dims,c["linkScale"])
        initial=body_points(math.radians(phase_deg),common=c)
        frames[(station,side,math.radians(phase_deg))]=(j,points,initial)
    rows=[]
    for item in assembly["instances"]:
        part=envelopes["parts"][item["part_id"]]
        matrix=np.asarray(item["transform"]);rotation=matrix[:3,:3];translation=matrix[:3,3]
        motion=item["motion"];kind=motion["kind"]
        if kind in ("shaft","crank"):
            radial=envelopes["rotatingInstances"][item["name"]]
            low=radial_lower_bound(body,motion["axisYz"],radial["nativeXRangeMm"],radial["radiusMm"])
        else:
            points=np.asarray(part["points"])@rotation.T+translation
            circles=[{"center":(rotation@np.asarray(circle["center"])+translation).tolist(),
                      "axis":(rotation@np.asarray(circle["axis"])).tolist(),"radius":circle["radius"]}
                     for circle in part.get("circles",[])]
            if kind=="body":
                low=minimum_cloud(points,circles,normals)-assembly["bodyOriginZMm"]+body[:,0]
            elif kind=="joint":
                _,p,initial=frames[(motion["station"],motion["side"],motion["phase"])]
                node=motion["node"]
                origin=np.r_[0,initial[node]+[motion["station"],assembly["bodyOriginZMm"]]]
                relative=points-origin
                radius=float(np.linalg.norm(relative[:,1:],axis=1).max())
                low=body[:,0]+p[node][:,1]+body[:,2]*(p[node][:,0]+motion["station"])
                low+=np.minimum(body[:,1]*points[:,0].min(),body[:,1]*points[:,0].max())
                low-=radius*np.sqrt(1+body[:,2]**2)
            elif kind in ("link","foot"):
                j,p,initial=frames[(motion["station"],motion["side"],motion["phase"])]
                first,second=rigids()[motion["link"] if kind=="link" else "CEF"][:2]
                current=np.arctan2((p[second]-p[first])[:,1],(p[second]-p[first])[:,0])
                before=math.atan2(*(initial[second]-initial[first])[::-1])
                angle=current-before;co,si=np.cos(angle),np.sin(angle)
                local_normals=np.column_stack((body[:,1],body[:,2]*co+si,-body[:,2]*si+co))
                anchor="F" if kind=="foot" else first
                origin=np.r_[0,initial[anchor]+[motion["station"],assembly["bodyOriginZMm"]]]
                relative=points-origin
                rel_circles=[{**circle,"center":(np.asarray(circle["center"])-origin).tolist()} for circle in circles]
                location=body[:,0]+p[anchor][:,1]+body[:,2]*(p[anchor][:,0]+motion["station"])
                gamma=current-math.radians(c["foot"]["pitchReferenceBodyAngleDeg"])
                if kind=="foot" and motion["piece"] in ("SLIDER","ROCKER","ROCKER_PIN"):
                    location+=compression[:,j]*(np.cos(gamma)-body[:,2]*np.sin(gamma))
                if kind=="foot" and motion["piece"]=="ROCKER":
                    if circles:raise ValueError("Rocker core must use a containing box,not omitted curved material")
                    pivot=rotation@np.asarray(part["rockerPivot"])+translation-origin
                    axis=rotation@np.asarray(part["rockerAxis"])
                    low=rocker_minimum(relative-pivot,local_normals,axis,
                                       math.radians(c["foot"]["rockerTravelDeg"]))
                    low+=local_normals@pivot+location
                else:
                    low=minimum_cloud(relative,rel_circles,local_normals)+location
            else:
                raise ValueError("Unclassified non-contact geometry: "+kind)
        # Effective length errors already move each modeled joint and foot.
        # Only retained nominal link profiles need the residual length envelope;
        # use the same reserve on cut PET, not a second length error on bolts.
        allowance=profile_allowance if kind=="link" or assembly["parts"][item["part_id"]]["category"]=="sheet_cut" else 0.
        index=int(np.argmin(low));clearance=float(low[index]-floor-allowance)
        rows.append({"instance":item["name"],"partId":item["part_id"],
                     "minimumBoundZMm":float(low[index]),"minimumReservedClearanceMm":clearance,
                     "additionalProfileAllowanceMm":allowance,
                     "crankDeg":float(np.degrees(theta[index])),"status":"PASS" if clearance>=0 else "FAIL"})
    if len(rows)!=len(assembly["instances"]) or {r["instance"] for r in rows}!={i["name"] for i in assembly["instances"]}:
        raise ValueError("The floor detector dropped an assembly instance")
    worst=min(rows,key=lambda row:row["minimumReservedClearanceMm"])
    return {"caseId":case_id,"status":"PASS" if all(r["status"]=="PASS" for r in rows) else "FAIL",
            "phaseCount":len(theta),"checkedInstances":len(rows),
            "maximumModeledFootNormalN":float(np.max(np.asarray(raw["normal_n"]))),
            "modeledFloorUpperBoundMm":floor,
            "profileAllowance":{"linkAndCutPetMm":profile_allowance,"otherNominalHardwareMm":0,
                                "basis":"Declared effective link-pitch error is also included in the solved joint positions; only nominal retained link profiles and cut PET receive this extra conservative material-bound reserve. Purchased-part dimensional tolerance remains unqualified."},
            "worst":worst,"failures":[r for r in rows if r["status"]!="PASS"],
            "perInstance":rows}
