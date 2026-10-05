import sys, math, numpy as np; sys.path.insert(0, "/home/user/taigment/ValombrePony/Tools/core_ports")
from proc_port import *
fails=[]
def check(c,m):
    print(("OK  " if c else "FAIL"),m)
    if not c: fails.append(m)
model=fk(REST)
check(np.allclose(model[IDX["front_hoof_l"]].t,[-0.115,0.046,-0.496],atol=2e-4), f"FK hoof {model[IDX['front_hoof_l']].t}")
check(np.allclose(model[IDX["head"]].t,[0,1.43,-0.90],atol=2e-4), f"FK head {model[IDX['head']].t}")
# --- Look at: target to the left of the head
head=IDX["head"]; el,er=IDX["eye_l"],IDX["eye_r"]
restElev=elev(qact(model[head].r,np.array([0,1.0,0])))
print("rest head elevation (deg)", math.degrees(restElev))
chain=[("neck_03",.10),("neck_04",.15),("neck_05",.20),("neck_06",.20),("head",.35)]
def apply_look(target, yawApplied=None):
    pose=[p.copy() for p in REST]; m=fk(pose)
    origin=(m[el].t+m[er].t)/2; v=target-origin
    hd=qact(m[head].r,np.array([0,1.0,0]))
    yawE=max(-1.2,min(1.2, (azim(v)-azim(hd)+math.pi)%(2*math.pi)-math.pi))
    pitchE=max(-0.8,min(0.6, elev(v)-(elev(hd)-restElev)))
    ay=yawE if yawApplied is None else yawApplied; ap=pitchE
    for n,w in chain:
        j=IDX[n]; refresh(j,pose,m); lat=qact(m[j].r,np.array([1.0,0,0]))
        d=qmul(qaxis(np.array([0,1.0,0]),ay*w), qaxis(lat,ap*w)); rot_model(j,d,pose,m)
    m2=fk(pose); hd2=qact(m2[head].r,np.array([0,1.0,0]))
    return yawE,pitchE,azim(hd2)-azim(hd),elev(hd2)-elev(hd), m2
tgt=model[head].t+np.array([-2.0,0,-0.5])
ye,pe,dy,dp,_=apply_look(tgt)
check(abs(ye-1.2)<1e-6 and dy>1.1 and dy<1.25, f"look left: yawErr {ye:.3f}, head azimuth change {dy:.3f}, pitch change {dp:.3f}")
tgt=model[head].t+np.array([0,1.0,-1.5])   # en haut devant
ye,pe,dy,dp,_=apply_look(tgt)
check(pe>0.3 and dp>0.3, f"look up: pitchErr {pe:.3f} head elev change {dp:.3f}, yaw change {dy:.3f}")
tgt=model[head].t+np.array([0,-1.0,-1.0])
ye,pe,dy,dp,_=apply_look(tgt)
check(pe<-0.3 and dp<-0.3, f"look down: pitchErr {pe:.3f} head elev change {dp:.3f}")
# --- Eyes: target straight ahead of left eye's gaze? local delta clamps
m=fk(REST); j=el; tgt=m[j].t+np.array([0,0,-3.0])   # devant
local=qact(qinv(m[j].r), tgt-m[j].t); d=qclamp(qfromto(np.array([0,1.0,0]),local),0.44)
newdir=qact(qmul(m[j].r,d),np.array([0,1.0,0]))
check(np.dot(newdir/np.linalg.norm(newdir),[0,0,-1])>np.dot(qact(m[j].r,[0,1.0,0]),[0,0,-1]), f"eye turns toward front: {newdir}")
# --- Two-bone IK: raise front carpus by 5 cm
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
for leg in [("upperarm_l","forearm_l","front_cannon_l","front_hoof_l"),("thigh_r","gaskin_r","hind_cannon_r","hind_hoof_r")]:
    pose=[p.copy() for p in REST]; m=fk(pose); u,mi,lo,ho=[IDX[x] for x in leg]
    for d in (0.05,-0.05):
        pose=[p.copy() for p in REST]; m=fk(pose)
        t=m[lo].t+np.array([0,d,0])
        pose[u].r,pose[mi].r=twobone(m[u].t,m[mi].t,m[lo].t,t,m[u].r,m[mi].r,pose[u].r,pose[mi].r)
        m2=fk(pose)
        reach=np.linalg.norm(m[mi].t-m[u].t)+np.linalg.norm(m[lo].t-m[mi].t)
        if np.linalg.norm(t-m[u].t)>reach-1e-6:   # cible hors d'atteinte : la chaîne doit être tendue vers la cible
            check(np.linalg.norm(m2[lo].t-m[u].t)>reach-2e-3, f"IK {leg[0]} d={d} (hors d'atteinte) chaîne tendue"); continue
        check(np.linalg.norm(m2[lo].t-t)<2e-3, f"IK {leg[0]} d={d}: end {m2[lo].t} target {t} err {np.linalg.norm(m2[lo].t-t):.2e}; hoof dy {m2[ho].t[1]-m[ho].t[1]:.4f}")
# --- Lean: rotate body about +Z by +0.1 around origin → withers move to -X (left)
pose=[p.copy() for p in REST]; m=fk(pose); b=IDX["body"]
dq=qaxis(np.array([0,0,1.0]),0.1); tm=Tr(qact(dq,m[b].t), qnorm(qmul(dq,m[b].r)))
pose[b]=m[PAR[b]].inv()*tm; m2=fk(pose)
check(m2[IDX["spine_03"]].t[0]< -0.05, f"lean left moves withers to -X: {m2[IDX['spine_03']].t}")
print("hoof y after lean:", [round(m2[IDX[h]].t[1],4) for h in ["front_hoof_l","front_hoof_r","hind_hoof_l","hind_hoof_r"]])
print("FAILS:",fails)
