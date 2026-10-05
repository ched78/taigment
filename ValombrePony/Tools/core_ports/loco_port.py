"""Portage Python fidèle de LocomotionController.swift (vérification numérique des scénarios de test)."""
import math
import numpy as np

F = np.float32
MASK64 = (1 << 64) - 1

class PonyRandom:
    def __init__(self, seed): self.state = seed & MASK64
    def next(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)
    def nextFloat(self): return F((self.next() >> 40) / 16777216.0)
    def range(self, lo, hi): return F(lo + (hi - lo) * self.nextFloat())
    def chance(self, p): return self.nextFloat() < p

class Settings:
    stickDeadZone=0.12; playbackTolerance=0.18; cruiseSpeed=4.8; sprintSpeed=8.0
    walkUp=0.15; walkDown=0.06; trotUp=1.85; trotDown=1.55; canterUp=4.0; canterDown=3.5; gallopUp=6.4; gallopDown=5.6
    walkAcceleration=1.2; trotAcceleration=2.0; canterAcceleration=2.5; gallopAcceleration=3.0; backAcceleration=1.0
    decelerationFactor=1.5
    walkMinTurnRadius=1.2; trotMinTurnRadius=3.0; canterMinTurnRadius=5.0; gallopMinTurnRadius=9.0; backMinTurnRadius=1.0
    minTurnSpeed=0.5; maxYawRate=1.5; yawAcceleration=4.0; gaitFadeDuration=0.3; minGaitDuration=0.35
    leadChangeFadeDuration=0.25; leadChangeDelay=0.6
    idleRestDelayMin=12; idleRestDelayMax=30; idleRestDurationMin=8; idleRestDurationMax=20; restFadeDuration=1.0

SLOTS = ["idle","idle_rest_hind","walk","trot","canter_left","canter_right","gallop","back","turn_left","turn_right"]
IDLE, REST, WALK, TROT, CL, CR, GALLOP, BACK, TL, TR = range(10)
DEFAULTS = {"idle":(6.0,0,0),"idle_rest_hind":(6.0,0,0),"walk":(1.05,1.4,0),"trot":(0.66,3.0,0),"canter_left":(0.57,4.8,0),
            "canter_right":(0.57,4.8,0),"gallop":(0.46,8.0,0),"back":(1.2,-0.6,0),"turn_left":(1.4,0,1.2),"turn_right":(1.4,0,-1.2)}
def cyclic(k): return k not in (IDLE, REST)
LEVEL = {"idle":0,"back":0,"turnInPlace":0,"walk":1,"trot":2,"canter":3,"gallop":4}
ATLEVEL = {1:"walk",2:"trot",3:"canter",4:"gallop"}
def clamp(v,a,b): return min(max(v,a),b)
def clamp01(v): return clamp(v,0.0,1.0)
def move_towards(c,t,d):
    d=max(0.0,d)
    if abs(t-c)<=d: return t
    return c+(d if t>c else -d)
def fract(x): f = x - math.floor(x); return 0.0 if f >= 1 else f

class Loco:
    def __init__(self, rng, settings=Settings, missing=()):
        self.s=settings
        self.info=[]
        for k,name in enumerate(SLOTS):
            dur, fwd, yaw = DEFAULTS[name]
            clipIndex = -1 if name in missing else k
            vel = (0,0,-fwd)
            if k in (TL,TR): yaw = abs(yaw) if k==TL else -abs(yaw); fwd=0; vel=(0,0,0)
            self.info.append(dict(clipIndex=clipIndex, fwd=fwd, vel=np.array(vel,float), yaw=yaw, dur=dur, off=0.0, sf=1.0/dur))
        n=len(SLOTS)
        self.w=[0.0]*n; self.t=[0.0]*n; self.rate=[1.0]*n; self.clipTime=[0.0]*n; self.prevClipTime=[0.0]*n
        self.cycles=0.0; self.prevCycles=0.0; self.speed=0.0; self.steerYaw=0.0; self.gait="idle"; self.gaitTimer=0.0
        self.lead=CL; self.leadMismatch=0.0; self.leadFade=False; self.resting=False; self.restTimer=0.0; self.restLimit=20.0; self.lastSteer=0.0
        self.w[IDLE]=1; self.t[IDLE]=1
        self.restLimit = rng.range(self.s.idleRestDelayMin, self.s.idleRestDelayMax)
    def spd(self,k): return max(0.1, abs(self.info[k]["fwd"]))
    @property
    def walkSpeed(self): return self.spd(WALK)
    @property
    def trotSpeed(self): return self.spd(TROT)
    @property
    def canterSpeed(self): return max(0.1, 0.5*(abs(self.info[CL]["fwd"])+abs(self.info[CR]["fwd"])))
    @property
    def gallopSpeed(self): return self.spd(GALLOP)
    @property
    def backSpeed(self): return self.spd(BACK)
    def band(self,g):
        tol=self.s.playbackTolerance
        return {"idle":(0,0),"turnInPlace":(0,0),"walk":(0,self.walkSpeed*(1+tol)),"trot":(self.trotSpeed*(1-tol),self.trotSpeed*(1+tol)),
                "canter":(self.canterSpeed*(1-tol),self.canterSpeed*(1+tol)),"gallop":(self.gallopSpeed*(1-tol),self.gallopSpeed*(1+tol)),
                "back":(-self.backSpeed*(1+tol),0)}[g]
    def up(self,l): return [self.s.walkUp,self.s.trotUp,self.s.canterUp,self.s.gallopUp][min(l,3)]
    def down(self,l): return [self.s.walkDown,self.s.trotDown,self.s.canterDown,self.s.gallopDown][min(l,3)]
    def desiredForward(self,cmd):
        l=LEVEL[self.gait]
        while l<4 and cmd>self.up(l): l+=1
        while l>0 and cmd<self.down(l-1): l-=1
        return ATLEVEL.get(l,"idle")
    def accel(self,g):
        return {"walk":self.s.walkAcceleration,"idle":self.s.walkAcceleration,"turnInPlace":self.s.walkAcceleration,"trot":self.s.trotAcceleration,
                "canter":self.s.canterAcceleration,"gallop":self.s.gallopAcceleration,"back":self.s.backAcceleration}[g]
    def radius(self,g):
        return {"walk":self.s.walkMinTurnRadius,"idle":self.s.walkMinTurnRadius,"turnInPlace":self.s.walkMinTurnRadius,"trot":self.s.trotMinTurnRadius,
                "canter":self.s.canterMinTurnRadius,"gallop":self.s.gallopMinTurnRadius,"back":self.s.backMinTurnRadius}[g]
    @property
    def isStanding(self): return self.gait=="idle" and abs(self.speed)<0.05
    def setGait(self,g):
        if g==self.gait: return
        if g=="canter":
            if self.lastSteer < -0.05: self.lead=CL
            elif self.lastSteer > 0.05: self.lead=CR
            self.leadMismatch=0
        self.gait=g; self.gaitTimer=0
    def update(self, dt, mx, my, sprint, enabled, timeScale, rng):
        tol=self.s.playbackTolerance
        cmd=0.0; steer=0.0
        if enabled:
            if my>0: cmd = my*(self.s.sprintSpeed if sprint else self.s.cruiseSpeed)
            elif my<0: cmd = my*self.backSpeed*(1+tol)
            steer=mx
        self.lastSteer=steer; self.gaitTimer+=dt
        if cmd < -0.01: desired="back"
        elif cmd<=0.01 and steer!=0 and abs(self.speed)<0.15: desired="turnInPlace"
        else: desired=self.desiredForward(cmd)
        goal=0.0
        g=self.gait
        if g=="idle":
            if desired=="back": self.setGait("back")
            elif desired=="turnInPlace": self.setGait("turnInPlace")
            elif LEVEL[desired]>0: self.setGait("walk")
        elif g=="turnInPlace":
            if desired!="turnInPlace": self.setGait("idle")
        elif g=="back":
            if desired=="back": goal=max(cmd, self.band("back")[0])
            else:
                goal=0
                if self.speed > -0.03: self.setGait("idle")
        else:
            lc=LEVEL[g]; ld=LEVEL[desired]; b=self.band(g)
            if ld>lc:
                goal=b[1]
                if self.speed>=b[1]-0.05 and self.gaitTimer>=self.s.minGaitDuration: self.setGait(ATLEVEL.get(lc+1,"idle"))
            elif ld<lc:
                goal=b[0]
                if self.speed<=b[0]+0.05 and self.gaitTimer>=self.s.minGaitDuration: self.setGait(ATLEVEL.get(lc-1,"idle"))
            else: goal=clamp(cmd,b[0],b[1])
        a=self.accel(self.gait)
        if abs(goal)<abs(self.speed): a*=self.s.decelerationFactor
        self.speed=move_towards(self.speed,goal,a*dt)
        if self.gait in ("idle","turnInPlace"): self.speed=move_towards(self.speed,0,a*self.s.decelerationFactor*dt)
        if self.gait=="canter":
            wanted=None
            if steer<-0.3: wanted=CL
            if steer>0.3: wanted=CR
            if wanted is not None and wanted!=self.lead:
                self.leadMismatch+=dt
                if self.leadMismatch>=self.s.leadChangeDelay: self.lead=wanted; self.leadMismatch=0; self.leadFade=True
            else: self.leadMismatch=0
        # rest
        if self.gait=="idle" and abs(self.speed)<0.01 and self.lastSteer==0:
            self.restTimer+=dt
            if not self.resting and self.restTimer>=self.restLimit:
                self.resting=True; self.restTimer=0; self.restLimit=rng.range(self.s.idleRestDurationMin,self.s.idleRestDurationMax); self.clipTime[REST]=0
            elif self.resting and self.restTimer>=self.restLimit:
                self.resting=False; self.restTimer=0; self.restLimit=rng.range(self.s.idleRestDelayMin,self.s.idleRestDelayMax)
        else:
            if self.resting: self.resting=False; self.restLimit=rng.range(self.s.idleRestDelayMin,self.s.idleRestDelayMax)
            self.restTimer=0
        self.computeTargets(steer)
        gf=dt/max(self.s.gaitFadeDuration,0.01); rf=dt/max(self.s.restFadeDuration,0.01); lf=dt/max(self.s.leadChangeFadeDuration,0.01)
        for k in range(10):
            st=gf
            if self.gait=="idle" and k in (IDLE,REST): st=rf
            if self.leadFade and k in (CL,CR): st=lf
            self.w[k]=move_towards(self.w[k],self.t[k],st)
        if self.leadFade and self.w[self.lead]>=1: self.leadFade=False
        for k in range(10):
            if k in (IDLE,REST): self.rate[k]=1
            elif k in (TL,TR): self.rate[k]=(1-tol)+2*tol*clamp01(abs(steer))
            else:
                ref=abs(self.info[k]["fwd"])
                self.rate[k]=clamp(abs(self.speed)/ref,1-tol,1+tol) if ref>0.01 else 1
        self.prevCycles=self.cycles
        cw=0.0; fr=0.0
        for k in range(10):
            if not cyclic(k): continue
            w=self.w[k]
            if w<=0: continue
            cw+=w; fr+=w*self.rate[k]*self.info[k]["sf"]
        if cw>1e-4:
            self.cycles+= fr/cw*dt*timeScale
            if self.cycles>=840: self.cycles-=840; self.prevCycles-=840
        else: self.cycles=0; self.prevCycles=0
        for k in range(2): self.prevClipTime[k]=self.clipTime[k]; self.clipTime[k]+=dt*timeScale
        cy=0.0
        if self.gait in ("walk","trot","canter","gallop"):
            v=max(abs(self.speed),self.s.minTurnSpeed); cy=-steer*min(self.s.maxYawRate, v/max(self.radius(self.gait),0.1))
        elif self.gait=="back":
            v=max(abs(self.speed),0.3); cy=-steer*min(self.s.maxYawRate, v/max(self.s.backMinTurnRadius,0.1))
        self.steerYaw=move_towards(self.steerYaw,cy,self.s.yawAcceleration*dt)
    def computeTargets(self,steer):
        tol=self.s.playbackTolerance
        self.t=[0.0]*10
        g=self.gait
        if g=="idle": self.t[REST if (self.resting and self.info[REST]["clipIndex"]>=0) else IDLE]=1
        elif g=="walk": a=clamp01(self.speed/(self.walkSpeed*(1-tol))); self.t[WALK]=a; self.t[IDLE]=1-a
        elif g=="trot": self.t[TROT]=1
        elif g=="canter": self.t[self.lead]=1
        elif g=="gallop": self.t[GALLOP]=1
        elif g=="back": a=clamp01(-self.speed/(self.backSpeed*(1-tol))); self.t[BACK]=a; self.t[IDLE]=1-a
        elif g=="turnInPlace":
            b=clamp01(abs(steer)/0.5); k=TL if steer<0 else TR; self.t[k]=b; self.t[IDLE]=1-b
    def resetToIdle(self):
        self.w=[0.0]*10; self.t=[0.0]*10; self.w[IDLE]=1; self.t[IDLE]=1
        self.speed=0; self.steerYaw=0; self.gait="idle"; self.gaitTimer=0; self.cycles=0; self.prevCycles=0; self.resting=False; self.restTimer=0
    def resume(self,g,speed,steer):
        self.resetToIdle(); self.lastSteer=steer; self.gait="idle"; self.setGait(g)
        b=self.band(g); self.speed=clamp(speed,b[0],b[1]); self.w=[0.0]*10; self.computeTargets(steer); self.w=list(self.t)
    @property
    def poseVelocity(self):
        tot=sum(self.w)
        if tot<=1e-6: return np.zeros(3)
        v=np.zeros(3)
        for k in range(10):
            if self.w[k]>0: v+=self.info[k]["vel"]*(self.w[k]*self.rate[k])
        return v/tot
    @property
    def yawRate(self):
        tot=sum(self.w); cy=0.0
        if tot>1e-6:
            cy=(self.info[TL]["yaw"]*self.w[TL]*self.rate[TL]+self.info[TR]["yaw"]*self.w[TR]*self.rate[TR])/tot
        return self.steerYaw+cy
