#!/usr/bin/env python3
"""Vérification SYNTAXIQUE des fichiers Swift (tree-sitter), faute de compilateur Swift dans l'environnement
de génération. Ne détecte PAS les erreurs de typage ni d'API : c'est un garde-fou minimal, pas un compilateur.

Usage : python3 Tools/swift_syntax_check.py [dossier_ou_fichiers...]   (défaut : PonyKit/)
Dépendance : pip install tree-sitter-language-pack
"""
import sys
from pathlib import Path

from tree_sitter_language_pack import get_parser


def errors(node, out):
    if node.type == "ERROR" or node.is_missing:
        out.append(node)
    for c in node.children:
        errors(c, out)
    return out


def main(argv):
    root = Path(__file__).resolve().parent.parent
    targets = [Path(a) for a in argv] or [root / "PonyKit"]
    files = []
    for t in targets:
        files += sorted(t.rglob("*.swift")) if t.is_dir() else [t]
    parser = get_parser("swift")
    bad = 0
    for f in files:
        src = f.read_bytes()
        errs = errors(parser.parse(src).root_node, [])
        if errs:
            bad += 1
            lines = src.decode("utf-8", "replace").splitlines()
            for e in errs[:8]:
                r, c = e.start_point
                kind = "MISSING " + e.type if e.is_missing else "ERROR"
                ctx = lines[r].strip() if r < len(lines) else ""
                print(f"{f}:{r + 1}:{c + 1}: {kind}: {ctx[:120]}")
    print(f"{len(files)} fichier(s) Swift analysé(s), {bad} avec erreur(s) de syntaxe.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
