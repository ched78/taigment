import sys, numpy as np
sys.path.insert(0, "/home/user/taigment/ValombrePony/Pipeline")
from pony import template, conventions as cv
exec(open("/home/user/taigment/ValombrePony/Tools/gen_default_rig.py").read().split("table = template")[0])
table = template.joint_table(); names=[e["name"] for e in table]; idx={n:i for i,n in enumerate(names)}
W = [cv.C4 @ bone_frame(e["head"], e["tail"]) for e in table]
def rotx(a):
    c,s=np.cos(a),np.sin(a); return np.array([[1,0,0],[0,c,-s],[0,s,c]])
def roty(a):
    c,s=np.cos(a),np.sin(a); return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def tip_after(jn, R_local, length=None):
    w = W[idx[jn]]; L = length or np.linalg.norm(np.array(table[idx[jn]]["tail"])-np.array(table[idx[jn]]["head"]))
    tip0 = w[:3,3] + w[:3,:3] @ np.array([0,L,0])
    tip1 = w[:3,3] + w[:3,:3] @ R_local @ np.array([0,L,0])
    return tip0, tip1
for jn, R, label in [("neck_03", rotx(0.2), "+X neck"), ("head", rotx(0.2), "+X head"), ("ear_l", rotx(0.3), "+X ear_l"),
                     ("eyelid_upper_l", rotx(-0.5), "-X upper lid"), ("eyelid_lower_l", rotx(0.5), "+X lower lid"),
                     ("forearm_l", rotx(0.3), "+X forearm"), ("front_cannon_l", rotx(0.3), "+X cannon"), ("gaskin_l", rotx(0.3), "+X gaskin"),("tail_01", rotx(0.3), "+X tail_01")]:
    a,b = tip_after(jn, R); print(f"{label:16s} tip RK {np.round(a,3)} -> {np.round(b,3)}  delta {np.round(b-a,3)}")
# ear opening: local -Z in model space
for e in ["ear_l","ear_r"]:
    w=W[idx[e]]; print(e, "local -Z (opening?) in RK:", np.round(-w[:3,2],3), " local X:", np.round(w[:3,0],3))
    R = roty(0.5); print("  +Y swivel: -Z ->", np.round(w[:3,:3]@R@np.array([0,0,-1]),3))
for e in ["eye_l","eye_r","head","neck_03","spine_02"]:
    w=W[idx[e]]; print(e, "X", np.round(w[:3,0],3), "Y", np.round(w[:3,1],3), "Z", np.round(w[:3,2],3))
