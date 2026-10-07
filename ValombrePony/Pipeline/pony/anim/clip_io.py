"""Conteneur de clip et format d'échange `.npz` pour l'agent d'export.

Fichier `Pipeline/build/clips/<nom>.npz` :
- `local`         float64 (F, 70, 4, 4) : transformations LOCALES Blender de chaque joint (ordre
                  `rig.joint_names()`), au sens de `rig.locals_from_world(..., to_rk=False)` ;
                  le joint `root` reste à l'identité ;
- `weights_names` (W,) chaînes ; `weights` float64 (F, W) : pistes de blend shapes (noms du SPEC §5) ;
- `meta`          chaîne JSON : {name, loop, fps, frameCount, duration, rootVelocity [x,y,z] (espace
                  RealityKit, avant = −Z), rootYawRate (rad/s, + = vers la gauche, autour de +Y RK),
                  mask (liste de joints ou null), events [{time, name}], notes, …}.

Convention temporelle [I] :
- clip en boucle : F images aux temps k/fps, k = 0..F−1, couvrant [0, durée[ ; durée = F/fps ;
  l'image F (non stockée) est identique à l'image 0 ;
- clip non bouclé : F images aux temps k/fps, k = 0..F−1, couvrant [0, durée] ; durée = (F−1)/fps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import conventions as cv
from .skeleton import Skeleton

FPS = cv.FPS
CLIP_DIR = cv.BUILD_DIR / "clips"


def b2rk_vec(v):
    """Vecteur Blender -> RealityKit : (x, y, z) -> (x, z, −y)."""
    v = np.asarray(v, dtype=np.float64)
    return [float(v[0]) + 0.0, float(v[2]) + 0.0, float(-v[1]) + 0.0]      # + 0.0 : pas de « −0.0 » dans le JSON


@dataclass
class Clip:
    name: str
    loop: bool
    ang: np.ndarray                      # (F, N, 3) angles [flex X, twist Y, lat Z] (rad), base Blender
    trans: np.ndarray                    # (F, N, 3) translations de base (repère de repos de l'os)
    fps: int = FPS
    weights: dict = field(default_factory=dict)        # nom -> (F,)
    root_velocity_b: tuple = (0.0, 0.0, 0.0)          # m/s, repère Blender du poney (avant = +Y)
    root_yaw_rate: float = 0.0                         # rad/s, + = gauche
    root_pivot_b: tuple | None = None                  # pivot de rotation (info)
    mask: list | None = None
    events: list = field(default_factory=list)          # [(time, name)]
    notes: str = ""
    extra_meta: dict = field(default_factory=dict)
    # diagnostics (non exportés) : contacts prévus par membre (F,) bool, cibles de sabots, etc.
    contacts: dict = field(default_factory=dict)
    diag: dict = field(default_factory=dict)

    @property
    def F(self):
        return self.ang.shape[0]

    @property
    def duration(self):
        return self.F / self.fps if self.loop else (self.F - 1) / self.fps

    def times(self):
        return np.arange(self.F) / self.fps

    def basis(self, sk: Skeleton):
        return sk.basis_from_angles(self.ang, self.trans)

    def world(self, sk: Skeleton):
        return sk.fk(self.basis(sk))

    def local(self, sk: Skeleton):
        L = sk.locals_from_basis(self.basis(sk))
        L[:, sk.idx("root")] = np.eye(4)
        return L

    def meta(self):
        ev = sorted(({"time": round(float(t), 4), "name": n} for t, n in self.events), key=lambda e: e["time"])
        m = {
            "name": self.name,
            "loop": bool(self.loop),
            "fps": int(self.fps),
            "frameCount": int(self.F),
            "duration": round(float(self.duration), 6),
            "rootVelocity": [round(c, 6) for c in b2rk_vec(self.root_velocity_b)],
            "rootYawRate": round(float(self.root_yaw_rate), 6),
            "mask": self.mask,
            "events": ev,
            "notes": self.notes,
        }
        if self.root_pivot_b is not None:
            m["rootPivot"] = [round(c, 4) for c in b2rk_vec((self.root_pivot_b[0], self.root_pivot_b[1], 0.0))]
        if self.contacts:
            # appuis prévus par image (1 = sabot planté) — utile au runtime (verrouillage de pied) et aux checks
            m["contacts"] = {l: "".join("1" if c else "0" for c in np.asarray(v, dtype=bool))
                             for l, v in self.contacts.items()}
        m.update(self.extra_meta)
        return m

    def save(self, sk: Skeleton, out_dir: Path = CLIP_DIR):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        names = sorted(self.weights)
        W = np.stack([np.asarray(self.weights[n], dtype=np.float64) for n in names], axis=1) if names \
            else np.zeros((self.F, 0))
        path = out_dir / f"{self.name}.npz"
        np.savez_compressed(path, local=self.local(sk), weights_names=np.array(names, dtype=str),
                            weights=W, meta=np.array(json.dumps(self.meta(), ensure_ascii=False)))
        return path


def load_npz(path):
    d = np.load(path, allow_pickle=False)
    meta = json.loads(str(d["meta"]))
    return d["local"], [str(n) for n in d["weights_names"]], d["weights"], meta
