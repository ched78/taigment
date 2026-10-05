#!/usr/bin/env python3
"""Affiche la déclaration exacte, les plateformes et le résumé d'un symbole de la documentation Apple
(source : le JSON qui alimente developer.apple.com). Sert à vérifier les signatures Swift faute de compilateur.

Usage :
  python3 Tools/apple_doc.py realitykit/material/name
  python3 Tools/apple_doc.py "realitykit/entity/init(contentsof:withname:)"
  python3 Tools/apple_doc.py realitykit/skeletalposescomponent --members   # liste les membres
Le chemin est celui de l'URL https://developer.apple.com/documentation/<chemin> (en minuscules).
"""
import json
import sys
import urllib.request

BASE = "https://developer.apple.com/tutorials/data/documentation/"


def fetch(path):
    url = BASE + path.strip("/").lower() + ".json"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"ERREUR {url}: {e}")
        return None


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path, members = argv[0], "--members" in argv
    d = fetch(path)
    if d is None:
        return 1
    md = d.get("metadata", {})
    print("titre      :", md.get("title"))
    print("plateformes:", ", ".join(f"{p.get('name')} {p.get('introducedAt')}" + (" (déprécié " + p['deprecatedAt'] + ")" if p.get('deprecatedAt') else "")
                                    for p in md.get("platforms", [])))
    for s in d.get("primaryContentSections", []):
        if s.get("kind") == "declarations":
            for dec in s["declarations"]:
                print("déclaration:", "".join(t.get("text", "") for t in dec.get("tokens", [])))
    print("résumé     :", "".join(a.get("text", "") for a in d.get("abstract", [])))
    if members:
        refs = d.get("references", {})
        for sec in d.get("topicSections", []):
            print(f"\n[{sec.get('title')}]")
            for ident in sec.get("identifiers", []):
                r = refs.get(ident, {})
                frag = "".join(t.get("text", "") for t in r.get("fragments", []))
                url = r.get("url", "").replace("/documentation/", "")
                print(f"  {frag or r.get('title')}    -> {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
