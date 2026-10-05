"""Génère la table Swift du squelette synthétique (PonyRigDefaults.swift) à partir de Pipeline/pony/template.py.
Repères d'os = convention de rig.py (Y le long de l'os, Z = X_monde × Y, X = Y × Z), conversion C de conventions.py."""
import sys
import numpy as np
sys.path.insert(0, "/home/user/taigment/ValombrePony/Pipeline")
from pony import template, conventions as cv

def bone_frame(head, tail):
    d = np.array(tail) - np.array(head); d /= np.linalg.norm(d)
    xw = np.array([1.0, 0.0, 0.0])
    z = np.cross(xw, d)
    if np.linalg.norm(z) < 1e-4:
        z = np.array([0.0, 0.0, 1.0])
    z /= np.linalg.norm(z)
    x = np.cross(d, z); x /= np.linalg.norm(x)
    m = np.eye(4); m[:3, 0] = x; m[:3, 1] = d; m[:3, 2] = z; m[:3, 3] = head
    return m

def quat_from_m(m):
    R = m[:3, :3]
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2; w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([x, y, z, w])
    if q[3] < 0: q = -q
    return q / np.linalg.norm(q)

table = template.joint_table()
names = [e["name"] for e in table]
idx = {n: i for i, n in enumerate(names)}
world_b = [bone_frame(e["head"], e["tail"]) for e in table]
lines = []
for i, e in enumerate(table):
    p = -1 if e["parent"] is None else idx[e["parent"]]
    if p < 0:
        local = cv.C4 @ world_b[i]
    else:
        local = np.linalg.inv(world_b[p]) @ world_b[i]
    t = local[:3, 3]; q = quat_from_m(local)
    L = float(np.linalg.norm(np.array(e["tail"]) - np.array(e["head"])))
    f = lambda v: ", ".join(f"{float(x):.6f}" for x in v)
    lines.append(f'        ("{e["name"]}", {p}, [{f(t)}], [{f(q)}], {L:.6f}),')
print("\n".join(lines))
