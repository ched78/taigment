"""Portage Python de Quat/Transform/FK, LookAtLayer.applyNeck, twoBoneIK, SecondaryMotion (vérification)."""
import math, re, numpy as np
SRC = "/home/user/taigment/ValombrePony/PonyKit/Sources/PonyCore/Rig/PonyRigDefaults.swift"
rows = re.findall(r'\("(\w+)", (-?\d+), \[([^\]]+)\], \[([^\]]+)\], ([\d.]+)\)', open(SRC).read())
NAMES=[r[0] for r in rows]; PAR=[int(r[1]) for r in rows]
T=[np.array([float(x) for x in r[2].split(",")]) for r in rows]
R=[np.array([float(x) for x in r[3].split(",")]) for r in rows]
LEN={r[0]: float(r[4]) for r in rows}
IDX={n:i for i,n in enumerate(NAMES)}
def qmul(a,b):
    ax,ay,az,aw=a; bx,by,bz,bw=b
    return np.array([aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz])
def qnorm(q): n=np.linalg.norm(q); return q/n if n>1e-12 else np.array([0,0,0,1.0])
def qinv(q): return np.array([-q[0],-q[1],-q[2],q[3]])/np.dot(q,q)
def qact(q,v):
    u=q[:3]; t=2*np.cross(u,v); return v+q[3]*t+np.cross(u,t)
def qaxis(axis,ang):
    l=np.linalg.norm(axis)
    if l<1e-9: return np.array([0,0,0,1.0])
    s=math.sin(ang/2)/l; return np.array([axis[0]*s,axis[1]*s,axis[2]*s,math.cos(ang/2)])
def qfromto(a,b):
    a=a/np.linalg.norm(a); b=b/np.linalg.norm(b); d=np.dot(a,b)
    if d< -1+1e-6:
        ax=np.cross([1,0,0],a)
        if np.dot(ax,ax)<1e-8: ax=np.cross([0,1,0],a)
        ax/=np.linalg.norm(ax); return np.array([ax[0],ax[1],ax[2],0.0])
    if d>=1-1e-7: return np.array([0,0,0,1.0])
    c=np.cross(a,b); s=math.sqrt((1+d)*2); return qnorm(np.array([c[0]/s,c[1]/s,c[2]/s,s/2]))
def qangle(q): q=qnorm(q); return 2*math.acos(min(1,abs(q[3])))
def qclamp(q,m):
    a=qangle(q)
    if a<=m or a<1e-7: return q
    q=qnorm(q); q = q if q[3]>=0 else -q; ax=q[:3]/np.linalg.norm(q[:3]); return qaxis(ax,m)
class Tr:
    def __init__(s,t=None,r=None,sc=None): s.t=np.zeros(3) if t is None else np.array(t,float); s.r=np.array([0,0,0,1.0]) if r is None else np.array(r,float); s.s=np.ones(3) if sc is None else np.array(sc,float)
    def __mul__(p,c): return Tr(p.t+qact(p.r,p.s*c.t), qmul(p.r,c.r), p.s*c.s)
    def inv(s):
        isc=1/s.s; ir=qinv(s.r); return Tr(isc*qact(ir,-s.t), ir, isc)
    def point(s,p): return s.t+qact(s.r,s.s*p)
    def copy(s): return Tr(s.t.copy(), s.r.copy(), s.s.copy())
REST=[Tr(T[i],qnorm(R[i])) for i in range(len(NAMES))]
def fk(pose):
    m=[None]*len(pose)
    for i,p in enumerate(PAR): m[i]= m[p]*pose[i] if p>=0 else pose[i].copy()
    return m
def rot_model(j,delta,pose,model):
    p=PAR[j]; pr=model[p].r if p>=0 else np.array([0,0,0,1.0])
    pose[j].r=qnorm(qmul(qmul(qmul(qinv(pr),delta),pr),pose[j].r)); model[j].r=qnorm(qmul(delta,model[j].r))
def refresh(j,pose,model):
    p=PAR[j]; model[j]= model[p]*pose[j] if p>=0 else pose[j].copy()
def azim(v): return math.atan2(-v[0],-v[2])
def elev(v): return math.atan2(v[1], math.hypot(v[0],v[2]))
