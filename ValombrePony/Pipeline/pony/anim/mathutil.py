"""Outils mathématiques (numpy pur) : rotations, profils temporels, interpolation de clés.

Convention d'angles des joints (choix d'ingénierie [I]) : pour chaque joint, trois angles en radians
dans son repère LOCAL de repos (axe Y le long de l'os, X = droite du poney, cf. SPEC §1) :
    ang[..., 0] = flexion/extension autour de X local (plan sagittal),
    ang[..., 1] = torsion autour de Y local (axe de l'os),
    ang[..., 2] = inclinaison latérale / abduction autour de Z local.
Rotation de base (matrix_basis Blender) : R = Rz(lat) · Rx(flex) · Ry(twist).
Signe : rotation positive autour de +X = sens trigonométrique vu de la droite du poney
(un os pendant vers le bas voit son extrémité partir vers l'avant).
"""
from __future__ import annotations

import numpy as np

TAU = 2.0 * np.pi
DEG = np.pi / 180.0


# --- Rotations élémentaires (vectorisées) ---------------------------------------------------------
def rx(a):
    a = np.asarray(a, dtype=np.float64)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros(a.shape + (3, 3))
    m[..., 0, 0] = 1.0
    m[..., 1, 1] = c
    m[..., 1, 2] = -s
    m[..., 2, 1] = s
    m[..., 2, 2] = c
    return m


def ry(a):
    a = np.asarray(a, dtype=np.float64)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros(a.shape + (3, 3))
    m[..., 1, 1] = 1.0
    m[..., 0, 0] = c
    m[..., 0, 2] = s
    m[..., 2, 0] = -s
    m[..., 2, 2] = c
    return m


def rz(a):
    a = np.asarray(a, dtype=np.float64)
    c, s = np.cos(a), np.sin(a)
    m = np.zeros(a.shape + (3, 3))
    m[..., 2, 2] = 1.0
    m[..., 0, 0] = c
    m[..., 0, 1] = -s
    m[..., 1, 0] = s
    m[..., 1, 1] = c
    return m


def euler_to_mat(ang):
    """ang (..., 3) = (flex X, twist Y, lat Z) -> (..., 3, 3) = Rz · Rx · Ry."""
    ang = np.asarray(ang, dtype=np.float64)
    return rz(ang[..., 2]) @ rx(ang[..., 0]) @ ry(ang[..., 1])


def mat_to_euler(m):
    """Inverse de `euler_to_mat`. Deux branches existent (flex et 180° − flex) : on garde celle dont la
    torsion et l'inclinaison latérale sont les plus petites (les articulations sont surtout des
    charnières), ce qui permet de relire des flexions > 90° (carpe, jarret replié)."""
    m = np.asarray(m, dtype=np.float64)
    # R = Rz(c) Rx(a) Ry(b) ; R[2,1] = sin(a) ; R[2,0] = -cos(a) sin(b) ; R[2,2] = cos(a) cos(b)
    # R[0,1] = -sin(c) cos(a) ; R[1,1] = cos(c) cos(a)
    a1 = np.arcsin(np.clip(m[..., 2, 1], -1.0, 1.0))
    b1 = np.arctan2(-m[..., 2, 0], m[..., 2, 2])
    c1 = np.arctan2(-m[..., 0, 1], m[..., 1, 1])
    a2 = np.where(a1 >= 0, np.pi - a1, -np.pi - a1)
    b2 = np.arctan2(m[..., 2, 0], -m[..., 2, 2])
    c2 = np.arctan2(m[..., 0, 1], -m[..., 1, 1])
    use2 = (np.abs(b2) + np.abs(c2)) < (np.abs(b1) + np.abs(c1))
    a = np.where(use2, a2, a1)
    b = np.where(use2, b2, b1)
    c = np.where(use2, c2, c1)
    return np.stack([a, b, c], axis=-1)


def axis_angle(axis, angle):
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s = np.cos(angle), np.sin(angle)
    C = 1.0 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def make_tf(R=None, t=None):
    """Matrice 4x4 (ou lot (..., 4, 4)) à partir de R (..., 3, 3) et t (..., 3)."""
    if R is None:
        R = np.eye(3)
    R = np.asarray(R, dtype=np.float64)
    shape = R.shape[:-2]
    m = np.zeros(shape + (4, 4))
    m[..., :3, :3] = R
    if t is not None:
        m[..., :3, 3] = t
    m[..., 3, 3] = 1.0
    return m


def mat_to_quat(m):
    """(..., 3|4, 3|4) -> quaternions (..., 4) [x, y, z, w], w >= 0."""
    m = np.asarray(m, dtype=np.float64)[..., :3, :3]
    shp = m.shape[:-2]
    mm = m.reshape(-1, 3, 3)
    q = np.empty((mm.shape[0], 4))
    for i, r in enumerate(mm):
        tr = r[0, 0] + r[1, 1] + r[2, 2]
        if tr > 0:
            s = np.sqrt(tr + 1.0) * 2
            w = 0.25 * s
            x = (r[2, 1] - r[1, 2]) / s
            y = (r[0, 2] - r[2, 0]) / s
            z = (r[1, 0] - r[0, 1]) / s
        elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
            s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            w = (r[2, 1] - r[1, 2]) / s
            x = 0.25 * s
            y = (r[0, 1] + r[1, 0]) / s
            z = (r[0, 2] + r[2, 0]) / s
        elif r[1, 1] > r[2, 2]:
            s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            w = (r[0, 2] - r[2, 0]) / s
            x = (r[0, 1] + r[1, 0]) / s
            y = 0.25 * s
            z = (r[1, 2] + r[2, 1]) / s
        else:
            s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            w = (r[1, 0] - r[0, 1]) / s
            x = (r[0, 2] + r[2, 0]) / s
            y = (r[1, 2] + r[2, 1]) / s
            z = 0.25 * s
        qq = np.array([x, y, z, w])
        if qq[3] < 0:
            qq = -qq
        q[i] = qq
    return q.reshape(shp + (4,))


def rot_angle_between(Ra, Rb):
    """Angle (rad) de la rotation relative Ra^T Rb (lots acceptés)."""
    Rr = np.swapaxes(Ra, -1, -2) @ Rb
    tr = np.clip((np.trace(Rr, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)
    return np.arccos(tr)


def orthonormalize(R):
    """Projection sur SO(3) (SVD) — lots acceptés."""
    U, _, Vt = np.linalg.svd(R)
    d = np.sign(np.linalg.det(U @ Vt))
    U[..., :, -1] *= d[..., None]
    return U @ Vt


# --- Profils temporels -------------------------------------------------------------------------
def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def smootherstep(x):
    """Profil « minimum jerk » (5e degré) : vitesse et accélération nulles aux bornes."""
    x = np.clip(x, 0.0, 1.0)
    return x * x * x * (x * (6.0 * x - 15.0) + 10.0)


def bump(x, peak: float = 0.5, sharp: float = 1.0):
    """Bosse lisse sur [0,1], nulle (pente nulle) aux bornes, maximum 1 à `peak`.

    Construite comme sin²(π·u) où u = x déformé pour placer le maximum en `peak` (u(peak) = 0.5)."""
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    peak = float(np.clip(peak, 0.05, 0.95))
    g = np.log(0.5) / np.log(peak)          # x**g vaut 0.5 en x = peak
    u = x ** g
    b = np.sin(np.pi * u) ** 2
    return b ** sharp


def hermite(p0, v0, p1, v1, s):
    """Interpolation cubique de Hermite sur s ∈ [0,1] (v en unités par intervalle)."""
    s = np.asarray(s, dtype=np.float64)
    h00 = 2 * s ** 3 - 3 * s ** 2 + 1
    h10 = s ** 3 - 2 * s ** 2 + s
    h01 = -2 * s ** 3 + 3 * s ** 2
    h11 = s ** 3 - s ** 2
    return h00 * p0 + h10 * v0 + h01 * p1 + h11 * v1


def wrap01(x):
    return np.mod(x, 1.0)


def circ_smooth(x, sigma_frames: float, axis: int = 0):
    """Lissage gaussien circulaire (signal périodique) le long de `axis`."""
    x = np.asarray(x, dtype=np.float64)
    if sigma_frames <= 0:
        return x.copy()
    n = x.shape[axis]
    k = np.arange(n)
    k = np.minimum(k, n - k)
    g = np.exp(-0.5 * (k / sigma_frames) ** 2)
    g /= g.sum()
    X = np.fft.rfft(np.moveaxis(x, axis, -1), axis=-1)
    G = np.fft.rfft(g)
    y = np.fft.irfft(X * G, n=n, axis=-1)
    return np.moveaxis(y, -1, axis)


def lin_smooth(x, sigma_frames: float, axis: int = 0):
    """Lissage gaussien non périodique (bords répliqués)."""
    from scipy.ndimage import gaussian_filter1d
    if sigma_frames <= 0:
        return np.asarray(x, dtype=np.float64).copy()
    return gaussian_filter1d(np.asarray(x, dtype=np.float64), sigma_frames, axis=axis, mode="nearest")


def periodic_spline(times, values, period: float):
    """Spline cubique périodique passant par (times, values) ; renvoie une fonction t -> valeurs."""
    from scipy.interpolate import CubicSpline
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(times)
    t = times[order]
    v = values[order]
    t = np.concatenate([t, [t[0] + period]])
    v = np.concatenate([v, v[:1]], axis=0)
    cs = CubicSpline(t, v, bc_type="periodic", axis=0)
    t0 = t[0]
    return lambda q: cs(t0 + np.mod(np.asarray(q, dtype=np.float64) - t0, period))


def key_spline(times, values, kind: str = "pchip"):
    """Interpolation de clés non périodique, tangentes nulles aux extrémités.

    kind = "pchip" (monotone, pas de dépassement) ou "cubic" (C2, tangentes nulles aux bornes)."""
    from scipy.interpolate import CubicSpline, PchipInterpolator
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if len(times) == 1:
        v0 = values[0]
        return lambda q: np.broadcast_to(v0, np.shape(q) + np.shape(v0)).copy()
    if kind == "pchip":
        f = PchipInterpolator(times, values, axis=0, extrapolate=False)
    else:
        f = CubicSpline(times, values, axis=0, bc_type="clamped")
    t0, t1 = times[0], times[-1]
    v0, v1 = values[0], values[-1]

    def ev(q):
        q = np.asarray(q, dtype=np.float64)
        out = f(np.clip(q, t0, t1))
        return out
    return ev


def ease_keys(times, values):
    """Interpolation par segments « ease in/out » (smootherstep) : arrêt doux sur chaque clé."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)

    def ev(q):
        q = np.atleast_1d(np.asarray(q, dtype=np.float64))
        out = np.empty((len(q),) + values.shape[1:])
        for k, t in enumerate(q):
            if t <= times[0]:
                out[k] = values[0]
            elif t >= times[-1]:
                out[k] = values[-1]
            else:
                i = np.searchsorted(times, t) - 1
                s = (t - times[i]) / (times[i + 1] - times[i])
                w = smootherstep(s)
                out[k] = values[i] * (1 - w) + values[i + 1] * w
        return out
    return ev


def quat_to_mat(q):
    """Quaternions (..., 4) [x, y, z, w] -> matrices (..., 3, 3)."""
    q = np.asarray(q, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (y * y + z * z)
    m[..., 0, 1] = 2 * (x * y - z * w)
    m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w)
    m[..., 1, 1] = 1 - 2 * (x * x + z * z)
    m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w)
    m[..., 2, 1] = 2 * (y * z + x * w)
    m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def blend_locals(La, Lb, w):
    """Fondu de poses locales (N,4,4) : nlerp des quaternions (plus court chemin) + lerp des translations
    — même principe qu'un fondu de clips au runtime [I]."""
    qa, qb = mat_to_quat(La), mat_to_quat(Lb)
    s = np.sign(np.sum(qa * qb, axis=-1, keepdims=True))
    s[s == 0] = 1.0
    q = (1 - w) * qa + w * s * qb
    out = np.array(La, dtype=np.float64, copy=True)
    out[..., :3, :3] = quat_to_mat(q)
    out[..., :3, 3] = (1 - w) * La[..., :3, 3] + w * Lb[..., :3, 3]
    return out
