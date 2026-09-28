"""Continuous r7 assembly branches; no coordinate-sorted branch switching."""

import numpy as np

from commercial_r3 import LENGTH_KEYS


def circle_oriented(p,radius,q,other,orientation):
    delta=q-p;distance=np.linalg.norm(delta,axis=-1)
    margin=np.minimum(distance-abs(radius-other),radius+other-distance)
    if np.any(margin<=0):raise ValueError("Non-closing or tangent linkage candidate")
    along=(radius**2-other**2+distance**2)/(2*distance)
    height=np.sqrt(np.maximum(0,radius**2-along**2))
    normal=np.stack([-delta[...,1],delta[...,0]],axis=-1)/distance[...,None]
    point=p+along[...,None]*delta/distance[...,None]+orientation*height[...,None]*normal
    return point,float(margin.min())


def points_many(theta,dimensions,scale):
    c={key:dimensions[key]*scale for key in LENGTH_KEYS}
    theta=np.asarray(theta)
    p=np.broadcast_to([-c["QP"],-c["OQ"]],theta.shape+(2,))
    a=c["OA"]*np.stack([np.cos(theta),np.sin(theta)],axis=-1)
    b,mb=circle_oriented(a,c["AB"],p,c["BP"],-1)
    cc,mc=circle_oriented(a,c["AC"],p,c["PC"],1)
    d,md=circle_oriented(b,c["BD"],p,c["PD"],-1)
    e,me=circle_oriented(cc,c["CE"],d,c["DE"],1)
    f,mf=circle_oriented(cc,c["CF"],e,c["EF"],1)
    return dict(O=np.zeros_like(a),P=p,A=a,B=b,C=cc,D=d,E=e,F=f),min(mb,mc,md,me,mf)
