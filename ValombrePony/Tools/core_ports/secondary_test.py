import sys, math, numpy as np; sys.path.insert(0, "/home/user/taigment/ValombrePony/Tools/core_ports")
from proc_port import *
TAIL=[IDX[f"tail_{i:02d}"] for i in range(1,11)]; MANE=[IDX[f"mane_{i:02d}"] for i in range(1,7)]
P={"tail":(60,7,0.25,1.0),"mane":(120,10,0.15,0.6),"stirrup":(30,3,0.9,1.2),"belly":(200,18,0,0.15)}
bones=[]
for i,j in enumerate(TAIL):
    child=TAIL[i+1] if i+1<len(TAIL) else -1
    L=np.linalg.norm(REST[child].t) if child>=0 else LEN[NAMES[j]]
    bones.append(dict(j=j,child=child,L=L,p=P["tail"],swish=(i+1)/10))
for j in MANE: bones.append(dict(j=j,child=-1,L=LEN[NAMES[j]],p=P["mane"],swish=0))
for n in ("stirrup_l","stirrup_r"): bones.append(dict(j=IDX[n],child=-1,L=LEN[n],p=P["stirrup"],swish=0))
bones.append(dict(j=IDX["belly"],child=-1,L=LEN["belly"],p=P["belly"],swish=0))
N=len(bones); pos=[None]*N; vel=[np.zeros(3) for _ in range(N)]; prev=[None]*N
wp=np.zeros(3); wy=0.0; init=False
def step(dt, pose, vroot, yaw, s=1.0):
    global wp, wy, init
    yq=qaxis(np.array([0,1.0,0]),wy); wp=wp+qact(yq,vroot)*dt; wy+=yaw*dt
    fr=qaxis(np.array([0,1.0,0]),wy); inv=qinv(fr)
    m=fk(pose); steps=max(1,min(8,int(math.ceil(dt*120)))); h=dt/steps
    maxdev=0.0
    for i,b in enumerate(bones):
        j=b["j"]; refresh(j,pose,m)
        head=m[j].t; tip=(m[j]*pose[b["child"]]).t if b["child"]>=0 else m[j].point(np.array([0,b["L"],0]))
        hw=wp+qact(fr,head*s); tw=wp+qact(fr,tip*s); ad=(tw-hw)/np.linalg.norm(tw-hw); L=max(np.linalg.norm(tw-hw),1e-4)
        k,c,gb,ma=b["p"]; td=ad*(1-gb)+np.array([0,-1.0,0])*gb; td/=np.linalg.norm(td); tgt=hw+td*L
        if not init: pos[i]=tgt.copy(); vel[i]=np.zeros(3); prev[i]=tgt.copy()
        tv=(tgt-prev[i])/dt; p=pos[i].copy(); v=vel[i].copy()
        for _ in range(steps):
            a=(tgt-p)*k-(v-tv)*c; v=v+a*h; p=p+v*h; d=p-hw; p=hw+d/np.linalg.norm(d)*L
        sd=(p-hw)/np.linalg.norm(p-hw); q=qclamp(qfromto(td,sd),ma); sd=qact(q,td); p=hw+sd*L
        v=v-sd*np.dot(v,sd); pos[i]=p; vel[i]=v; prev[i]=tgt
        dev=math.acos(np.clip(np.dot(sd,td),-1,1)); maxdev=max(maxdev,dev/ma)
        delta=qfromto(qact(inv,ad),qact(inv,sd)); rot_model(j,delta,pose,m)
    init=True
    return maxdev
dt=1/60; t=0; worst=0; finite=True
def body_pose(t, bob):
    pose=[p.copy() for p in REST]; b=IDX["body"]
    pose[b].t=pose[b].t+np.array([0,0,bob*math.sin(2*math.pi*2.2*t)])   # body local Z = up (root frame)
    pose[b].r=qnorm(qmul(qaxis(np.array([1.0,0,0]),0.04*math.sin(2*math.pi*2.2*t)),pose[b].r))
    return pose
log=[]
for phase,(dur,v,yaw,bob) in enumerate([(2,0,0,0),(4,4.8,1.0,0.03),(0.5,0,0,0),(3,0,0,0),(1,8,0,0.04),(3,0,0,0)]):
    for _ in range(int(dur*60)):
        pose=body_pose(t,bob); dev=step(dt,pose,np.array([0,0,-v]),yaw); t+=dt
        worst=max(worst,dev)
        if not all(np.all(np.isfinite(p.r)) for p in pose): finite=False
    # angle of tail tip vs rest at end of phase
    m=fk(pose); mr=fk(REST)
    tipdir=qact(m[TAIL[-1]].r,np.array([0,1.0,0])); restdir=qact(mr[TAIL[-1]].r,np.array([0,1.0,0]))
    log.append(f"phase {phase} (v={v}, yaw={yaw}): tail tip deviation {math.degrees(math.acos(np.clip(np.dot(tipdir,restdir),-1,1))):.1f} deg, stirrup speed {np.linalg.norm(vel[-3]):.3f}")
print("\n".join(log)); print("finite:", finite, " max deviation / maxAngle:", round(worst,3))
# big dt robustness
init=False
for dt2 in (0.1, 0.1, 0.1, 0.25):
    pose=body_pose(t,0.03); step(dt2,pose,np.array([0,0,-8.0]),1.5)
print("big-dt finite:", all(np.all(np.isfinite(p)) for p in pos))
