"""Vérifications des clips (sur le `.npz` écrit, c.-à-d. exactement ce que reçoit l'export).

Pour chaque clip :
- patinage des sabots en appui : déplacement HORIZONTAL en monde (mouvement racine du meta réappliqué)
  des points de sole au sol (z < 3 mm aux deux images) entre images consécutives d'un même appui
  (mm/image) — la levée des talons à la bascule (mouvement vertical autour de la pince) n'est pas du
  patinage ;
- pénétration du sol : min z des points de sole (seuil −5 mm) ; min z des points du mannequin
  (ellipsoïdes, cf. skeleton.MANNEQUIN [A]) séparément pour le corps et pour les segments distaux ;
- amplitudes articulaires vs SPEC §3 « Limites » (deltas par rapport à la pose de liaison, angles
  anatomiques) ; couplage grasset↔jarret (|Δjarret − Δgrasset|) ;
- continuité de boucle : saut de pose et d'« accélération » à la jointure vs le reste du clip ;
- quaternions / rotations : orthonormalité, déterminant, norme ; pas d'échelle ;
- durée et nombre d'images ; interférence entre sabots (distance mini entre soles au sol).
"""
from __future__ import annotations

import math

import numpy as np

from . import mathutil as mu
from .skeleton import HOOF, LIMB_JOINTS, LIMBS, NECK, Skeleton, body_sample_points, transform_points

D = mu.DEG

# Limites SPEC §3 (delta / pose de liaison sauf mention) — (joint, axe, min°, max°, libellé)
# Conventions de signe : cf. limb_ik.py (rotation autour de X local).
LIMITS = []
for _s in ("l", "r"):
    LIMITS += [
        (f"upperarm_{_s}", 0, -40, 20, "épaule +40° flexion / −20° extension"),
        (f"forearm_{_s}", 0, -10, 65, "coude +65° / −10°"),
        (f"front_hoof_{_s}", 0, -50, 15, "paturon+sabot ≈ 50° flexion (15° ext.)"),
        (f"front_pastern_{_s}", 0, -105, 999, "boulet AV : flexion ≤ 105°"),
        (f"thigh_{_s}", 0, -25, 40, "hanche +40° / −25°"),
        (f"hind_hoof_{_s}", 0, -50, 15, "paturon+sabot ≈ 50° (POST., même règle) [I]"),
        (f"hind_pastern_{_s}", 0, -105, 999, "boulet POST. : flexion ≤ 105° [I]"),
        (f"scapula_{_s}", 0, -15, 15, "omoplate ±15° (anatomy.md §1.6 [I])"),
        (f"thigh_{_s}", 2, -10, 10, "hanche abduction ±10° (anatomy.md [I])"),
    ]
for _n in NECK:
    LIMITS.append((_n, 2, -30, 30, "encolure latéral ≤ 30°/segment"))
    LIMITS.append((_n, 0, -35, 35, "encolure flexion ≤ 35°/segment [I]"))
for _n in ("spine_01", "spine_02", "spine_03"):
    LIMITS.append((_n, 0, -7, 7, "dos 5–7°/os (flexion)"))
    LIMITS.append((_n, 2, -7, 7, "dos 5–7°/os (latéral)"))
    LIMITS.append((_n, 1, -7, 7, "dos 5–7°/os (rotation)"))
LIMITS.append(("hips", 0, -15, 15, "lombo-sacrée ±15° [I]"))


def _sagittal_angle(u, v, axis):
    """Angle signé de u vers v autour de `axis` (projection dans le plan normal)."""
    axis = axis / np.linalg.norm(axis)
    u = u - axis * (u @ axis)
    v = v - axis * (v @ axis)
    return math.atan2(np.cross(u, v) @ axis, u @ v)


def rest_anatomy(sk: Skeleton):
    """Angles de repos utiles (rad) : hyperextension des boulets et flexion des carpes depuis la rectitude."""
    out = {}
    for s in ("l", "r"):
        for pre, cannon in (("front", f"front_cannon_{s}"), ("hind", f"hind_cannon_{s}")):
            pj = sk.idx(f"{pre}_pastern_{s}")
            cj = sk.idx(cannon)
            ax = sk.rest_world[cj][:3, 0]
            # + = pastern tourné vers l'avant (CCW vu de droite autour de +X) = hyperextension
            out[f"{pre}_fetlock_hyper_{s}"] = _sagittal_angle(sk.rest_world[cj][:3, 1], sk.rest_world[pj][:3, 1], ax)
        fj, cj = sk.idx(f"forearm_{s}"), sk.idx(f"front_cannon_{s}")
        out[f"carpus_flex_{s}"] = -_sagittal_angle(sk.rest_world[fj][:3, 1], sk.rest_world[cj][:3, 1],
                                                   sk.rest_world[fj][:3, 0])
    return out


def world_from_local(sk: Skeleton, local):
    F = local.shape[0]
    W = np.empty_like(local)
    for i in range(sk.N):
        p = sk.parents[i]
        W[:, i] = local[:, i] if p < 0 else W[:, p] @ local[:, i]
    return W


def root_frames(meta, t):
    """Mouvement racine (Blender) : R (T,3,3), p (T,3)."""
    from .gait import root_motion
    v_rk = np.array(meta["rootVelocity"], dtype=np.float64)
    v_b = np.array([v_rk[0], -v_rk[2], v_rk[1]])
    return root_motion(t, v_b, meta["rootYawRate"])


def check_clip(sk: Skeleton, local, meta, contacts=None, target=None, verbose=False):
    """Renvoie un dict de résultats chiffrés (et une liste d'alertes)."""
    F = local.shape[0]
    fps = meta["fps"]
    if contacts is None and meta.get("contacts"):
        contacts = {l: np.array([c == "1" for c in v]) for l, v in meta["contacts"].items()}
    loop = meta["loop"]
    res = {"name": meta["name"], "frames": F, "duration": meta["duration"], "loop": loop}
    warn = []
    # --- rotations / quaternions
    R = local[..., :3, :3]
    orth = np.abs(np.einsum("fnji,fnjk->fnik", R, R) - np.eye(3)).max()
    det = np.linalg.det(R.reshape(-1, 3, 3))
    q = mu.mat_to_quat(R.reshape(-1, 3, 3))
    qn = np.abs(np.linalg.norm(q, axis=1) - 1).max()
    res["rot_orthonormal_err"] = float(orth)
    res["rot_det_min"] = float(det.min())
    res["quat_norm_err"] = float(qn)
    res["root_identity_err"] = float(np.abs(local[:, sk.idx("root")] - np.eye(4)).max())
    if orth > 1e-9 or det.min() < 0.999999 or res["root_identity_err"] > 1e-12:
        warn.append("rotations non orthonormées ou root non identité")
    # --- durée
    exp_dur = F / fps if loop else (F - 1) / fps
    res["duration_ok"] = abs(exp_dur - meta["duration"]) < 1e-6 and meta["frameCount"] == F
    if target is not None:
        res["duration_target"] = target
    # --- monde
    W = world_from_local(sk, local)
    t = np.arange(F) / fps
    Rr, pr = root_frames(meta, t)
    # sole en monde (clip) et monde réel
    sole_clip = {l: sk.sole_world(W, l) for l in LIMBS}
    sole_w = {l: np.einsum("tij,tpj->tpi", Rr, sole_clip[l]) + pr[:, None, :] for l in LIMBS}
    res["hoof_min_z_mm"] = float(min(sole_clip[l][..., 2].min() for l in LIMBS) * 1000)
    if res["hoof_min_z_mm"] < -5:
        warn.append(f"pénétration sabot {res['hoof_min_z_mm']:.1f} mm")
    # patinage
    slip = {}
    pairs = [(k, k + 1) for k in range(F - 1)]
    if loop:
        # image F = image 0 décalée d'un cycle de mouvement racine
        pairs.append((F - 1, F))
    T = F / fps
    RF, pF = root_frames(meta, np.array([T]))
    for l in LIMBS:
        mx = 0.0
        for a, b in pairs:
            pa = sole_w[l][a]
            if b == F:
                pb = (RF[0] @ sole_clip[l][0].T).T + pF[0]
                cb = contacts[l][0] if contacts is not None else None
                zb = sole_clip[l][0, :, 2]
            else:
                pb = sole_w[l][b]
                cb = contacts[l][b] if contacts is not None else None
                zb = sole_clip[l][b, :, 2]
            ca = contacts[l][a] if contacts is not None else None
            za = sole_clip[l][a, :, 2]
            if contacts is not None and not (ca and cb):
                continue
            on = (za < 0.003) & (zb < 0.003)
            if not on.any():
                continue
            d = np.linalg.norm((pb[on] - pa[on])[:, :2], axis=1).max()     # glissement horizontal
            mx = max(mx, d)
        slip[l] = mx * 1000
    res["slip_mm_per_frame"] = {l: round(float(v), 3) for l, v in slip.items()}
    # hauteur de la pince pendant les appuis prévus (un sabot « planté » qui ne touche pas le sol)
    if contacts is not None:
        hz = [float(sole_clip[l][np.asarray(contacts[l], bool), 0, 2].max()) for l in LIMBS if np.any(contacts[l])]
        res["stance_toe_z_max_mm"] = round(max(hz) * 1000, 2) if hz else 0.0
        if hz and max(hz) > 0.005:
            warn.append(f"sabot planté décollé de {max(hz) * 1000:.1f} mm")
    res["slip_max_mm"] = float(max(slip.values()))
    if res["slip_max_mm"] > 2.0:
        warn.append(f"patinage {res['slip_max_mm']:.2f} mm/image")
    # interférence entre sabots : distance horizontale mini entre centres de sole (z < 4 cm)
    cen = {l: sole_clip[l][:, [0, 5]].mean(axis=1) for l in LIMBS}
    dmin = 9.9
    for i, a in enumerate(LIMBS):
        for b in LIMBS[i + 1:]:
            low = (cen[a][:, 2] < 0.04) & (cen[b][:, 2] < 0.04)
            if low.any():
                dmin = min(dmin, float(np.linalg.norm((cen[a] - cen[b])[low, :2], axis=1).min()))
    res["hoof_gap_min_m"] = round(dmin, 4)
    if dmin < 0.09:
        warn.append(f"sabots trop proches ({dmin * 100:.1f} cm)")
    # corps
    js, ps, distal = body_sample_points(sk, n_per=48)
    P = transform_points(W, js, ps)
    zmin = P[..., 2].min(axis=0)
    res["body_min_z_mm"] = float(zmin[~distal].min() * 1000)
    res["distal_min_z_mm"] = float(zmin[distal].min() * 1000)
    kmin = int(np.argmin(zmin))
    res["lowest_point"] = {"bone": sk.names[js[kmin]], "frame": int(np.argmin(P[:, kmin, 2])),
                           "z_mm": round(float(zmin[kmin] * 1000), 1)}
    if min(res["body_min_z_mm"], res["distal_min_z_mm"]) < -5.0:
        warn.append(f"pénétration du corps ({res['lowest_point']})")
    # --- articulations
    ang = np.empty((F, sk.N, 3))
    for i in range(sk.N):
        basis = np.einsum("ji,fjk->fik", sk.rest_local[i][:3, :3], R[:, i])
        ang[:, i] = mu.mat_to_euler(basis)
    viol = []
    for jn, ax, lo, hi, lab in LIMITS:
        a = ang[:, sk.idx(jn), ax] / D
        if a.min() < lo - 0.5 or a.max() > hi + 0.5:
            viol.append(f"{jn}[{'XYZ'[ax]}] {a.min():.1f}..{a.max():.1f} hors [{lo},{hi}] ({lab})")
    # carpe (depuis la rectitude) et hyperextension des boulets (au-delà de la rectitude)
    ra = rest_anatomy(sk)
    for s in ("l", "r"):
        cf = ra[f"carpus_flex_{s}"] / D - ang[:, sk.idx(f"front_cannon_{s}"), 0] / D
        if cf.max() > 150.5 or cf.min() < -5.5:
            viol.append(f"carpe_{s} {cf.min():.1f}..{cf.max():.1f}° (flexion ≤150, ext ≤5)")
        for pre in ("front", "hind"):
            hy = ra[f"{pre}_fetlock_hyper_{s}"] / D + ang[:, sk.idx(f"{pre}_pastern_{s}"), 0] / D
            if hy.max() > 60.5:
                viol.append(f"boulet {pre}_{s} hyperextension max {hy.max():.1f}° (> 60°)")
            res.setdefault("fetlock_hyper_max_deg", {})[f"{pre}_{s}"] = round(float(hy.max()), 1)
        res.setdefault("carpus_flex_max_deg", {})[s] = round(float(cf.max()), 1)
        st = ang[:, sk.idx(f"gaskin_{s}"), 0]
        hk = ang[:, sk.idx(f"hind_cannon_{s}"), 0]
        res.setdefault("recip_dev_max_deg", {})[s] = round(float(np.abs(hk + st).max() / D), 2)
    head = ang[:, sk.idx("head"), 0] / D
    res["ao_flex_range_deg"] = [round(float(head.min()), 1), round(float(head.max()), 1)]
    if head.max() - head.min() > 85.5 or abs(head).max() > 60.5:
        viol.append(f"nuque (AO) {head.min():.1f}..{head.max():.1f}° (≈85° au total)")
    res["limit_violations"] = viol
    if viol:
        warn.append(f"{len(viol)} dépassement(s) d'amplitude")
    # --- continuité de boucle
    if loop and F > 3:
        Rw = W[..., :3, :3]
        pos = W[..., :3, 3]

        def step(a, b):
            return (mu.rot_angle_between(Rw[a], Rw[b]).max() / D, np.linalg.norm(pos[a] - pos[b], axis=1).max())
        steps = [step(k, (k + 1) % F) for k in range(F)]
        seam = steps[F - 1]
        others = steps[:F - 1]
        # « accélération » : différence seconde des positions des joints
        acc = np.array([np.linalg.norm(pos[(k + 1) % F] - 2 * pos[k] + pos[k - 1], axis=1).max() for k in range(F)])
        res["loop_seam_step"] = {"rot_deg": round(seam[0], 3), "pos_mm": round(seam[1] * 1000, 2)}
        res["loop_other_step_max"] = {"rot_deg": round(max(o[0] for o in others), 3),
                                      "pos_mm": round(max(o[1] for o in others) * 1000, 2)}
        res["loop_seam_acc_mm"] = round(float(max(acc[0], acc[F - 1]) * 1000), 2)
        res["loop_acc_max_other_mm"] = round(float(acc[1:F - 1].max() * 1000), 2)
        if seam[1] > 1.5 * max(o[1] for o in others) + 1e-3 or res["loop_seam_acc_mm"] > 1.5 * res["loop_acc_max_other_mm"] + 0.5:
            warn.append("discontinuité à la jointure de boucle")
    res["warnings"] = warn
    if verbose:
        print(format_result(res))
    return res


def format_result(r):
    s = (f"{r['name']:16s} F={r['frames']:3d} dur={r['duration']:.3f}s "
         f"slip={r['slip_max_mm']:.2f}mm/img stz={r.get('stance_toe_z_max_mm', 0):.1f}mm hoofz={r['hoof_min_z_mm']:.1f}mm "
         f"body_z={r['body_min_z_mm']:.0f}mm distal_z={r['distal_min_z_mm']:.0f}mm gap={r['hoof_gap_min_m']:.3f}m "
         f"quat={r['quat_norm_err']:.1e}")
    if "loop_seam_step" in r:
        s += (f" seam={r['loop_seam_step']['pos_mm']:.1f}mm/{r['loop_other_step_max']['pos_mm']:.1f}"
              f" acc={r['loop_seam_acc_mm']:.1f}/{r['loop_acc_max_other_mm']:.1f}")
    if r["limit_violations"]:
        s += "\n    " + "\n    ".join(r["limit_violations"])
    return s
