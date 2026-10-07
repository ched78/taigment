# Ressources du poney (dossier produit par le pipeline)

Ce fichier est un **témoin versionné** : git ne suit pas les dossiers vides, or `Package.swift` déclare
`resources: [.copy("Resources")]`. Sans ce fichier, un clone propre n'aurait pas de dossier `Resources/` et
SwiftPM/Xcode refuseraient le paquet (ressource déclarée introuvable). Ne pas le supprimer.

Contenu écrit par `python3 Pipeline/stages/s09_export.py` (ne pas éditer à la main) :

- `Pony.usdz`, `Pony_QuickLook.usdz`, `PonyRig.json`, `PonyClips.bin`
- `coat_shading.png`, `coat_regions.png`, `coat_params.png`, `coat_patterns.png`, `hair_strands.png`
- `Parts/<id>.usdz` (crins et accessoires, `Docs/SPEC.md` §6)

Si seul ce fichier est présent, PonyKit se rabat sur le squelette synthétique, la bibliothèque de clips vide et
le substitut primitif (`Docs/INTEGRATION.md` §4.4). Ce fichier est copié dans le bundle avec le reste du
dossier ; aucun code ne le lit.
