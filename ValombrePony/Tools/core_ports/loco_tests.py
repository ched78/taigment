import sys; sys.path.insert(0, "/home/user/taigment/ValombrePony/Tools/core_ports")
from loco_port import *
def make(seed=3): return Loco(PonyRandom(seed))
def step(c, seconds, mx=0.0, my=0.0, sprint=False, check=None):
    rng=PonyRandom(9)
    for _ in range(int(round(seconds*60))):
        c.update(1/60, mx, my, sprint, True, 1.0, rng)
        if check: check(c)
fails=[]
def check(cond, msg):
    print(("OK  " if cond else "FAIL"), msg)
    if not cond: fails.append(msg)
# test 1
c=make(); check(c.gait=="idle","idle start")
step(c,0.2,my=0.2); check(c.gait=="walk","walk after 0.2s")
step(c,4,my=0.2); check(abs(c.speed-0.96)<0.01, f"speed {c.speed:.4f}≈0.96")
check(c.w[IDLE]>0.05, f"idle weight {c.w[IDLE]:.3f}>0.05"); check(abs(c.rate[WALK]-0.82)<1e-5, f"walk rate {c.rate[WALK]}")
check(abs(-c.poseVelocity[2]-c.speed)<0.02, f"pose vel {-c.poseVelocity[2]:.4f} vs speed {c.speed:.4f}")
# test playback rate
c=make(); bad=[0]
def chk(c):
    for k in range(10):
        if cyclic(k) and c.w[k]>0 and not (0.82-1e-5<=c.rate[k]<=1.18+1e-5): bad[0]+=1
step(c,10,my=1,check=chk); check(bad[0]==0,"rates within tol"); check(c.gait=="canter", f"canter at y=1 ({c.gait})")
# hysteresis
c=make(); step(c,6,my=0.5); check(c.gait=="trot",f"trot ({c.gait})"); check(abs(c.speed-c.band('trot')[0])<0.01, f"speed {c.speed} at trot min")
st={"changes":0,"last":c.gait}
def counter(c):
    if c.gait!=st["last"]: st["changes"]+=1; st["last"]=c.gait
step(c,4,my=1.7/4.8,check=counter); check(c.gait=="trot" and st["changes"]==0, f"stays trot at 1.7 ({c.gait},{st['changes']})")
step(c,4,my=1.3/4.8); check(c.gait=="walk", f"walk at 1.3 ({c.gait})")
st["last"]=c.gait; st["changes"]=0
step(c,4,my=1.7/4.8,check=counter); check(c.gait=="walk" and st["changes"]==0, f"stays walk at 1.7 ({c.gait},{st['changes']})")
# phase
c=make(); s={"prev":c.cycles,"max":0.0,"min":1.0,"wt":False,"tc":False}
def ph(c):
    d=c.cycles-s["prev"]; s["max"]=max(s["max"],d); s["min"]=min(s["min"],d); s["prev"]=c.cycles
    if c.w[WALK]>0.1 and c.w[TROT]>0.1: s["wt"]=True
    if c.w[TROT]>0.1 and c.w[CL]>0.1: s["tc"]=True
step(c,9,my=0.9,check=ph)
check(s["wt"] and s["tc"], f"blends seen wt={s['wt']} tc={s['tc']}"); check(s["min"]>=0 and s["max"]<0.05, f"phase steps min={s['min']:.4f} max={s['max']:.4f}")
check(c.gait=="canter" and c.lead==CL, f"canter left ({c.gait},{c.lead})")
# lead
c=make(); step(c,9,mx=0.6,my=1); check(c.gait=="canter" and c.lead==CR, f"canter right ({c.gait},{SLOTS[c.lead]})")
step(c,2,mx=-0.6,my=1); check(c.lead==CL and abs(c.w[CL]-1)<1e-5 and abs(c.w[CR])<1e-5, f"flying change ({SLOTS[c.lead]}, {c.w[CL]:.3f},{c.w[CR]:.3f}) gait {c.gait}")
# turn
c=make(); step(c,4,mx=1,my=1.4/4.8); check(c.gait=="walk", f"walk ({c.gait})")
wl=min(1.5,max(c.speed,0.5)/1.2); check(abs(c.yawRate+wl)<0.02, f"walk yaw {c.yawRate:.4f} vs {-wl:.4f} speed {c.speed:.3f}")
step(c,14,mx=1,my=1,sprint=True); check(c.gait=="gallop", f"gallop ({c.gait})")
gl=c.speed/9.0; check(abs(c.yawRate)<=gl+1e-3 and abs(c.yawRate)>0.5, f"gallop yaw {c.yawRate:.4f} lim {gl:.4f} speed {c.speed:.3f}")
# back & turn in place
c=make(); step(c,2,my=-1); check(c.gait=="back" and c.poseVelocity[2]>0.3, f"back ({c.gait}, vz {c.poseVelocity[2]:.3f})")
step(c,2); check(c.gait=="idle", f"idle after back ({c.gait})")
step(c,2,mx=1); check(c.gait=="turnInPlace" and abs(c.yawRate+1.2*1.18)<0.01 and abs(c.poseVelocity[2])<1e-5, f"turn right yaw {c.yawRate:.4f}")
step(c,2,mx=-1); check(c.yawRate>1.0, f"turn left yaw {c.yawRate:.4f}")
# rest
c=make(); r={"rested":False}
def rr(c):
    if c.w[REST]>0.9: r["rested"]=True
step(c,45,check=rr); check(r["rested"], f"rest variant (limit initial)")
step(c,1,my=0.5); check(not c.resting, "rest interrupted")
# resume
c=make(); c.resume("canter",1.0,0.5); check(c.gait=="canter" and c.lead==CR and abs(c.speed-c.band('canter')[0])<1e-5 and c.w[CR]==1, "resume canter")
# timeline print
c=make(); t=0
for i in range(60*9):
    c.update(1/60,0,1,False,True,1,PonyRandom(1))
    if i%30==0: print(f"t={i/60:4.1f} gait={c.gait:7s} speed={c.speed:5.2f} v={-c.poseVelocity[2]:5.2f}")
print("FAILS:", fails)
