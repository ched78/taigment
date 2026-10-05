"""Transpileur minimal Swift -> Python scalaire (float32) — OUTIL DE VÉRIFICATION du système de robes.

Faute de compilateur Swift dans l'environnement de génération, on traduit MÉCANIQUEMENT (expressions régulières,
sans interprétation humaine) le code Swift de `PonyKit/Sources/PonyCore/Coat/` en Python, puis on l'exécute en
float32 (numpy) pour le comparer à l'implémentation de référence `Pipeline/pony/coat_reference.py`
(cf. `test_coat_swift_equivalence.py`). Ce n'est PAS un compilateur : il ne vérifie ni les types ni les API, et
ne couvre que le sous-ensemble de Swift utilisé par ces fichiers — func (surcharges par indice), let/var,
if / else if / else, if let / guard let, switch (entiers, chaînes, tuples, `_`), for-in sur 0..<n ou un tableau,
return (implicite pour une seule expression), ternaires, &&, ||, !, .rounded(.down), .squareRoot(), membres
.x/.y/.z/.w, tuples .0/.1/.2, .cas d'énumération -> 'cas', nil -> None, &* et &+.
"""
from __future__ import annotations

import re

import numpy as np

F = np.float32


def split_ternary(expr: str) -> str:
    """Convertit récursivement a ? b : c en (b if a else c) au niveau de parenthèses 0."""
    expr = expr.strip()
    # descend dans les parenthèses d'abord
    out = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth = 1
            j = i + 1
            while depth:
                if expr[j] == "(":
                    depth += 1
                elif expr[j] == ")":
                    depth -= 1
                j += 1
            inner = expr[i + 1:j - 1]
            # arguments séparés par des virgules
            parts = split_top(inner, ",")
            out.append("(" + ", ".join(split_ternary(p) for p in parts) + ")")
            i = j
        elif ch == "[":
            depth = 1
            j = i + 1
            while depth:
                if expr[j] == "[":
                    depth += 1
                elif expr[j] == "]":
                    depth -= 1
                j += 1
            out.append("[" + split_ternary(expr[i + 1:j - 1]) + "]")
            i = j
        else:
            out.append(ch)
            i += 1
    e = "".join(out)
    q = find_top(e, "?")
    if q < 0:
        return e
    c = find_top(e, ":", q + 1)
    cond, a, b = e[:q], e[q + 1:c], e[c + 1:]
    return f"(({split_ternary(a)}) if ({split_ternary(cond)}) else ({split_ternary(b)}))"


def find_top(s, ch, start=0):
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == ch and depth == 0:
            return i
    return -1


def split_top(s, ch):
    parts, depth, cur = [], 0, ""
    for c in s:
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        if c == ch and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    parts.append(cur)
    return parts


DOUBLE_MODE = [False]


def conv_expr(e: str) -> str:
    e = e.strip()
    e = re.sub(r"(\w+)\.rounded\(\.down\)", r"_floor_(\1)", e)
    e = re.sub(r"(?<![\w)\]])\.([a-z]\w*)", r"'\1'", e)       # .caseName -> 'caseName'
    e = re.sub(r"\bnil\b", "None", e)
    e = re.sub(r"\bDouble\(", "float(", e)
    e = re.sub(r"\(([^()]*)\)\.squareRoot\(\)", r"sq(\1)", e)
    e = re.sub(r"(\w+)\.squareRoot\(\)", r"sq(\1)", e)
    e = re.sub(r"\bCoatNoise\.", "cn_", e)
    e = re.sub(r"\bUInt32\(", "U32(", e)
    e = re.sub(r"\bFloat\(", "F(", e)
    e = re.sub(r"\bInt\(", "int(", e)
    e = re.sub(r"(?<=[A-Za-z_])\.(\d)\b", r"[\1]", e)             # tuples
    e = e.replace("&*", "*").replace("&+", "+")
    e = e.replace("SIMD4<Float>(", "V4(").replace("SIMD3<Float>(", "V3(")
    e = re.sub(r"(\w+): ", r"\1=", e)                # arguments nommés (periodX: 160)
    e = e.replace("&&", " and ").replace("||", " or ")
    e = re.sub(r"!(?!=)", " not ", e)
    e = re.sub(r"\btrue\b", "True", e)
    e = re.sub(r"\bfalse\b", "False", e)
    if not DOUBLE_MODE[0]:
        e = re.sub(r"(?<![\w.])(\d+\.\d+(?:e-?\d+)?)", r"F(\1)", e)    # littéraux flottants -> float32
    e = re.sub(r"\.(x|y|z|w)\b", lambda m: "[%d]" % "xyzw".index(m.group(1)) if True else m.group(0), e)
    return split_ternary(e)


def transpile(src: str, names, rename=None) -> str:
    """Transpile les fonctions `names` trouvées dans src."""
    rename = rename or {}
    out = []
    for name in names:
        occ = 0
        alias = None
        if isinstance(name, tuple):
            name, occ, alias = name
        ms = list(re.finditer(r"\bfunc " + name + r"\(", src))
        assert ms, name
        m = ms[occ]
        start = src.rfind("\n", 0, m.start()) + 1
        # corps : du '{' de la signature à l'accolade fermante correspondante
        brace = src.index("{", m.end())
        depth = 0
        i = brace
        while True:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        sig = src[m.start():brace]
        body = src[brace + 1:i]
        for a, b in rename.items():
            body = re.sub(r"(?<![\w.])" + a + r"\(", b + "(", body)
        plist = sig[sig.index("(") + 1:sig.rindex(")")]
        out.append(f"def {alias or rename.get(name, name)}({conv_params(plist)}):")
        bl = transpile_body(body, 1)
        if len(bl) == 1 and not re.match(r"^\s*(return|if|for|\w+ = )", bl[0]):
            bl = ["    return " + bl[0].strip()]
        out += bl
        out.append("")
    return "\n".join(out)


def conv_params(plist: str) -> str:
    params = []
    for part in split_top(plist, ","):
        part = part.strip()
        if not part:
            continue
        m2 = re.match(r"(?:\w+ )?(\w+): (.+?)(?: = (.+))?$", part)
        params.append(m2.group(1) + (f"={conv_expr(m2.group(3))}" if m2.group(3) else ""))
    return ", ".join(params)


def transpile_body(body: str, level: int):
    # joindre les lignes de continuation (opérateur en début de ligne ou parenthèses ouvertes)
    raw = [l for l in body.split("\n")]
    lines = []
    for l in raw:
        s = re.sub(r"//.*$", "", l).strip()
        if not s:
            continue
        if lines and (s[0] in "*+-/" and s[1] == " " or open_parens(lines[-1]) > 0):
            lines[-1] += " " + s
        else:
            lines.append(s)
    out = []
    ind = level
    switch_stack = []
    for s in lines:
        pad = "    " * ind
        if s.startswith("@inline") or s.startswith("typealias "):
            continue
        m = re.match(r"^func (\w+)\((.*)\) -> [\w.<>\[\]]+ \{ (.+) \}$", s)
        if m:
            out.append(pad + f"def {m.group(1)}({conv_params(m.group(2))}): return {conv_expr(m.group(3))}")
            continue
        m = re.match(r"^func (\w+)\((.*)\) -> [\w.<>\[\]]+ \{$", s)
        if m:
            out.append(pad + f"def {m.group(1)}({conv_params(m.group(2))}):")
            ind += 1
            continue
        m = re.match(r"^guard let (\w+) = (.+?) else \{ (.+) \}$", s)
        if m:
            out.append(pad + f"{m.group(1)} = {conv_expr(m.group(2))}")
            out.append(pad + f"if {m.group(1)} is None:")
            out.append(pad + "    " + stmt(m.group(3)))
            continue
        m = re.match(r"^if let (\w+) = (.+?) \{ (.+) \}$", s)
        if m:
            out.append(pad + f"{m.group(1)} = {conv_expr(m.group(2))}")
            out.append(pad + f"if {m.group(1)} is not None:")
            out.append(pad + "    " + stmt(m.group(3)))
            continue
        m = re.match(r"^if let (\w+) = (.+?) \{$", s)
        if m:
            out.append(pad + f"{m.group(1)} = {conv_expr(m.group(2))}")
            out.append(pad + f"if {m.group(1)} is not None:")
            ind += 1
            continue
        if s == "}":
            ind -= 1
            if switch_stack and switch_stack[-1][1] == ind:
                switch_stack.pop()
            continue
        m = re.match(r"^switch (.+) \{$", s)
        if m:
            switch_stack.append([conv_expr(m.group(1)), ind, 0])
            out.append(pad + "if False: pass")
            continue
        m = re.match(r"^case (.+):\s*(.*)$", s)
        if m and switch_stack:
            sw = switch_stack[-1]
            if sw[2]:
                ind -= 1
            sw[2] = 1
            pats = split_top(m.group(1), ",")
            if len(pats) > 1:
                out.append("    " * sw[1] + f"elif {sw[0]} in ({', '.join(conv_expr(x) for x in pats)},):")
            else:
                out.append("    " * sw[1] + f"elif {sw[0]} == {conv_expr(m.group(1))}:")
            ind = sw[1] + 1
            if m.group(2):
                out.append("    " * ind + stmt(m.group(2)))
            continue
        if s == "default:" and switch_stack:
            sw = switch_stack[-1]
            out.append("    " * sw[1] + "else:")
            ind = sw[1] + 1
            continue
        if s == "break":
            out.append(pad + "pass")
            continue
        m = re.match(r"^\} else if (.+) \{$", s)
        if m:
            ind -= 1
            out.append("    " * ind + f"elif {conv_expr(m.group(1))}:")
            ind += 1
            continue
        if s == "} else {":
            ind -= 1
            out.append("    " * ind + "else:")
            ind += 1
            continue
        m = re.match(r"^if (.+?) \{ (.+) \}$", s)
        if m:
            out.append(pad + f"if {conv_expr(m.group(1))}:")
            out.append(pad + "    " + stmt(m.group(2)))
            continue
        m = re.match(r"^if (.+) \{$", s)
        if m:
            out.append(pad + f"if {conv_expr(m.group(1))}:")
            ind += 1
            continue
        m = re.match(r"^for (\w+) in (\w+)\.\.<(.+) \{$", s)
        if m:
            out.append(pad + f"for {m.group(1)} in range({conv_expr(m.group(2))}, {conv_expr(m.group(3))}):")
            ind += 1
            continue
        m = re.match(r"^for (\w+) in (\w+) \{$", s)
        if m:
            out.append(pad + f"for {m.group(1)} in {m.group(2)}:")
            ind += 1
            continue
        out.append(pad + stmt(s))
    return out


def open_parens(s):
    return s.count("(") - s.count(")") + s.count("[") - s.count("]")


def stmt(s: str) -> str:
    s = s.strip()
    if s == "break":
        return "pass"
    m = re.match(r"^(?:let|var) (\w+)(?:: [\w.<>\[\]]+)?$", s)
    if m:
        return f"{m.group(1)} = None"
    m = re.match(r"^(?:let|var) (\w+)(?:: [\w.<>\[\]]+)? = (.+)$", s)
    if m:
        return f"{m.group(1)} = {conv_expr(m.group(2))}"
    m = re.match(r"^return (.+)$", s)
    if m:
        return f"return {conv_expr(m.group(1))}"
    m = re.match(r"^([\w.\[\] +*]+?) = (.+)$", s)
    if m:
        return f"{conv_expr(m.group(1))} = {conv_expr(m.group(2))}"
    return conv_expr(s)
