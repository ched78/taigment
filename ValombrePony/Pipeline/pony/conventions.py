"""Conventions partagées par tout le pipeline (cf. Docs/SPEC.md §1).

Blender : +Z haut, nez du poney vers +Y, droite du poney = +X, sol z = 0, mètres.
RealityKit / USD : +Y haut, nez vers -Z, droite = +X, sol y = 0, mètres.
Conversion des points : (x, y, z)_B -> (x, z, -y)_RK  (rotation propre, det = +1).
Repères des joints : M_RK = C · M_B (les axes locaux des os sont conservés, cf. world_frame_b2rk).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

# --- Chemins ---------------------------------------------------------------
PIPELINE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = PIPELINE_DIR.parent                      # ValombrePony/
BUILD_DIR = Path(os.environ.get("PONY_BUILD_DIR", PIPELINE_DIR / "build"))
TEXTURE_BUILD_DIR = BUILD_DIR / "textures"
PREVIEW_DIR = PROJECT_DIR / "Previews"
RESOURCES_DIR = PROJECT_DIR / "PonyKit" / "Sources" / "PonyKit" / "Resources"
PARTS_RESOURCES_DIR = RESOURCES_DIR / "Parts"

FPS = 30

# --- Conversion d'axes -------------------------------------------------------
# C : matrice 3x3 qui envoie un vecteur Blender vers RealityKit.
C3 = np.array([[1.0, 0.0, 0.0],
               [0.0, 0.0, 1.0],
               [0.0, -1.0, 0.0]])
C4 = np.eye(4)
C4[:3, :3] = C3


def vec_b2rk(v):
    """Point(s)/vecteur(s) Blender (…, 3) -> RealityKit."""
    v = np.asarray(v, dtype=np.float64)
    return v @ C3.T


def world_frame_b2rk(m):
    """Repère monde 4x4 d'un joint (convention colonne p' = M p) Blender -> RealityKit : C · M.

    Choix du projet : les repères locaux des joints GARDENT les axes des os Blender
    (Y le long de l'os, X = latéral droit en pose de repos). Seul le repère monde est tourné.
    Conséquence : les transformations locales parent->enfant sont identiques en Blender et en
    RealityKit, sauf pour le joint racine `root` dont la locale vaut C · L_root.
    """
    m = np.asarray(m, dtype=np.float64)
    return C4 @ m


def root_local_b2rk(m):
    """Transformation locale du joint racine Blender -> RealityKit (C · L)."""
    return world_frame_b2rk(m)


def quat_wxyz_to_xyzw(q):
    w, x, y, z = q
    return np.array([x, y, z, w], dtype=np.float64)


def ensure_dirs():
    for d in (BUILD_DIR, TEXTURE_BUILD_DIR, PREVIEW_DIR, RESOURCES_DIR, PARTS_RESOURCES_DIR):
        d.mkdir(parents=True, exist_ok=True)
