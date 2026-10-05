"""Catalogue des clips du SPEC §7 : nom -> (générateur, durée cible du SPEC, type de source).

Ordre = priorité du brief (allures et repos, puis comportements, puis saut).
"""
from __future__ import annotations

from . import behaviours, gait, jump
from .skeleton import Skeleton

# nom : (fonction (sk) -> Clip, durée cible SPEC (s), catégorie)
CLIPS = {
    "idle": (lambda sk: behaviours.make(sk, "idle"), 6.0, "repos"),
    "walk": (lambda sk: gait.make_gait_clip(sk, gait.walk_spec()), 1.05, "allure"),
    "trot": (lambda sk: gait.make_gait_clip(sk, gait.trot_spec()), 0.66, "allure"),
    "canter_left": (lambda sk: gait.make_gait_clip(sk, gait.canter_spec("left")), 0.57, "allure"),
    "canter_right": (lambda sk: gait.make_gait_clip(sk, gait.canter_spec("right")), 0.57, "allure"),
    "gallop": (lambda sk: gait.make_gait_clip(sk, gait.gallop_spec()), 0.46, "allure"),
    "back": (lambda sk: gait.make_gait_clip(sk, gait.back_spec()), 1.2, "allure"),
    "turn_left": (lambda sk: gait.make_gait_clip(sk, gait.turn_spec("left")), 1.4, "allure"),
    "turn_right": (lambda sk: gait.make_gait_clip(sk, gait.turn_spec("right")), 1.4, "allure"),
    "idle_rest_hind": (lambda sk: behaviours.make(sk, "idle_rest_hind"), 6.0, "repos"),
    "graze_down": (lambda sk: behaviours.make(sk, "graze_down"), 1.5, "comportement"),
    "graze_loop": (lambda sk: behaviours.make(sk, "graze_loop"), 5.0, "comportement"),
    "graze_up": (lambda sk: behaviours.make(sk, "graze_up"), 1.2, "comportement"),
    "head_shake": (lambda sk: behaviours.make(sk, "head_shake"), 1.2, "comportement"),
    "neigh": (lambda sk: behaviours.make(sk, "neigh"), 2.2, "comportement"),
    "paw": (lambda sk: behaviours.make(sk, "paw"), 1.6, "comportement"),
    "rear": (lambda sk: behaviours.make(sk, "rear"), 2.6, "comportement"),
    "lie_down": (lambda sk: behaviours.make(sk, "lie_down"), 3.0, "comportement"),
    "lying": (lambda sk: behaviours.make(sk, "lying"), 6.0, "comportement"),
    "get_up": (lambda sk: behaviours.make(sk, "get_up"), 2.5, "comportement"),
    "roll": (lambda sk: behaviours.make(sk, "roll"), 4.5, "comportement"),
    "body_shake": (lambda sk: behaviours.make(sk, "body_shake"), 1.5, "comportement"),
    "jump_takeoff": (lambda sk: jump.make(sk, "jump_takeoff"), 0.5, "saut"),
    "jump_air": (lambda sk: jump.make(sk, "jump_air"), 0.4, "saut"),
    "jump_land": (lambda sk: jump.make(sk, "jump_land"), 0.6, "saut"),
}

# GIF animés demandés par le brief (+ un GIF combiné du saut : appel → vol balistique → réception)
GIF_CLIPS = ["walk", "trot", "canter_left", "gallop", "rear", "roll"]


def generate(sk: Skeleton, name: str):
    fn, target, cat = CLIPS[name]
    clip = fn(sk)
    clip.extra_meta.setdefault("specTargetDuration", target)
    return clip
