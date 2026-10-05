import sys, math, numpy as np; sys.path.insert(0, "/home/user/taigment/ValombrePony/Tools/core_ports")
from proc_port import *
from twobone import twobone
LEGS=[("upperarm_l","forearm_l","front_cannon_l","front_hoof_l"),("upperarm_r","forearm_r","front_cannon_r","front_hoof_r"),
      ("thigh_l","gaskin_l","hind_cannon_l","hind_hoof_l"),("thigh_r","gaskin_r","hind_cannon_r","hind_hoof_r")]
w=np.mean([abs(fk(REST)[IDX[l[3]]].t[0]) for l in LEGS]); print("hoof half width", w)
for lean in (0.1, 0.2, -0.2):
    pose=[p.copy() for p in REST]; m=fk(pose)
    ref={l[3]:m[IDX[l[3]]].t.copy() for l in LEGS}
    b=IDX["body"]; dq=qaxis(np.array([0,0,1.0]),lean); piv=np.array([w if lean>0 else -w,0,0])
    tm=Tr(piv+qact(dq,m[b].t-piv), qnorm(qmul(dq,m[b].r))); pose[b]=m[PAR[b]].inv()*tm; m=fk(pose)
    before={l[3]:m[IDX[l[3]]].t.copy() for l in LEGS}
    for l in LEGS:
        u,mi,lo,ho=[IDX[x] for x in l]
        d=-(m[ho].t[1]-ref[l[3]][1])
        if abs(d)<1e-4: continue
        lowerRot=m[lo].r.copy(); t=m[lo].t+np.array([0,d,0])
        pose[u].r,pose[mi].r=twobone(m[u].t,m[mi].t,m[lo].t,t,m[u].r,m[mi].r,pose[u].r,pose[mi].r)
        refresh(u,pose,m); refresh(mi,pose,m)
        pose[lo].r=qnorm(qmul(qinv(m[mi].r),lowerRot)); m=fk(pose)
    after={l[3]:m[IDX[l[3]]].t for l in LEGS}
    print(f"lean {lean:+.2f}: body {np.round(m[b].t,3)}")
    for l in LEGS:
        h=l[3]; print(f"   {h:13s} ref y {ref[h][1]:.4f}  leaned {before[h][1]:.4f}  planted {after[h][1]:.4f}  dx {after[h][0]-ref[h][0]:+.4f} dz {after[h][2]-ref[h][2]:+.4f}")
