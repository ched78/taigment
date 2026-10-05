import math, numpy as np
from proc_port import *
def twobone(a,b,c,t,aM,bM,aL,bL):
    eps=1e-4; lab=np.linalg.norm(b-a); lcb=np.linalg.norm(b-c); lat=min(max(np.linalg.norm(t-a),eps),lab+lcb-eps)
    n=lambda v: v/np.linalg.norm(v)
    ac,ab,ba,bc,at=n(c-a),n(b-a),n(a-b),n(c-b),n(t-a)
    acab0=math.acos(np.clip(ac@ab,-1,1)); babc0=math.acos(np.clip(ba@bc,-1,1)); acat0=math.acos(np.clip(ac@at,-1,1))
    acab1=math.acos(np.clip((lcb*lcb-lab*lab-lat*lat)/(-2*lab*lat),-1,1)); babc1=math.acos(np.clip((lat*lat-lab*lab-lcb*lcb)/(-2*lab*lcb),-1,1))
    ax0=n(np.cross(c-a,b-a)); ax1r=np.cross(c-a,t-a)
    r0=qaxis(qact(qinv(aM),ax0),acab1-acab0); r1=qaxis(qact(qinv(bM),ax0),babc1-babc0)
    r2=qaxis(qact(qinv(aM),n(ax1r)),acat0) if np.dot(ax1r,ax1r)>1e-12 else np.array([0,0,0,1.0])
    return qnorm(qmul(aL,qmul(r0,r2))), qnorm(qmul(bL,r1))
