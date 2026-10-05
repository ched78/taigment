# Equestrian accessories (tack) reference for a real-time 3D pony
**Project:** *Les Héritiers de Valombre*, RealityKit on iOS 26 / macOS 26, procedural modelling in Blender (bpy)
**Reference animal:** riding pony 1.30 m at the withers, with a morph down to a 1.00 m Shetland
**Compiled:** 2026-10-05

---

## 0. Method, limits and confidence tags

**How the facts were gathered.** Every fact comes from WebSearch result extracts. WebFetch could not open the pages because this environment's egress proxy blocked every domain tried (Wikipedia, FEI, manufacturers). The session's web-search quota (200 calls, shared with sibling agents) also ran out before some details could be checked; these are listed in §13. **Before using a number for production, open the cited page and check it.**

| Tag | Meaning |
|---|---|
| **[V]** | **Verified**: the search extract attributes the statement to the cited page. |
| **[V\*]** | **Verified, attribution loose**: the statement is in a search extract, but the extract did not name which of the cited pages said it. I list the result set. |
| **[A]** | **Approximate**: my unit conversion, interpolation or scaling of [V] data, or general domain knowledge that I did not check this session. |
| **[I]** | **Inferred**: a modelling or engineering recommendation for the game. It is not a fact about the real world. |

Units: 1 inch = 2.54 cm, and 1 hand (hh) = 4 in = 10.16 cm. Heights are given in hands.inches, so 12.2 hh means 12 hands and 2 inches.

A companion report on RealityKit APIs exists at `research/realitykit.md`, written by another agent in this session. Points it verified against Apple docs are marked "(→ realitykit.md)". I did not re-check them.

---

## 1. Reference animal, size classes and why tack must not be scaled uniformly

### 1.1 Heights
- 1.30 m = 51.2 in ≈ **12.3 hh** [A, conversion].
- 1.00 m = 39.4 in ≈ **9.3 hh** [A].
- British show-pony height sections are: up to 12.2 hh (127 cm); 12.2–13.2 hh (127–137 cm); 13.2–14.2 hh (147 cm) [V] ([Wikipedia – Riding pony](https://en.wikipedia.org/wiki/Riding_pony)). **The 1.30 m pony is in the "12.2–13.2 hh" class.**
- Shetland ponies range from about 71 cm (28 in) to an official maximum of 11 hh (112 cm). Most are about 40 in (≈102 cm) [V\*] ([American Shetland Pony – Wikipedia](https://en.wikipedia.org/wiki/American_Shetland_Pony), [extension.org – Shetland](https://horses.extension.org/shetland-pony-breed/)). The UK Shetland Pony Stud-Book Society limit of 42 in (107 cm) is from memory [A].
- French FFE pony categories (A/B/C/D by height) were not checked [A]. Confirm them on ffe.com if gameplay uses them.

### 1.2 Commercial size classes
Tack is sold in **discrete sizes**: Mini/Shetland → (Small) Pony → Cob → Full → X-Full. It does not scale with height.

**Proportions do not scale linearly.** Going from 1.30 m to 1.00 m is a 0.77 ratio in height, but:

| Item | Shetland | Pony | Ratio | Source |
|---|---|---|---|---|
| Browband | 32 cm | 34 cm | **0.94** | [V\*] |
| Bit width | 10–10.5 cm | 11.5 cm | **≈0.89** | [V\*] |
| Rug A–B length | 4'3"–4'9" (130–145 cm) | 5'3" (160 cm) | **≈0.81–0.91** | [V] |

Shetlands have relatively large heads and deep, stocky bodies.

→ **[I] Do not scale tack uniformly with the pony's root scale.** Give every skinned tack mesh the **same morph targets (shape keys) as the body**, so the Shetland morph refits the tack. Keep rigid metal parts (bit, stirrup irons, buckles) at real size, or let them switch between two discrete size variants.

### 1.3 Size table for the two morph extremes

| Item | 1.30 m pony (12.2–13.2 hh) | 1.00 m Shetland | Tag / source |
|---|---|---|---|
| English seat size | 15"–16" (38–41 cm). Pony saddles run 14"–16.5" | 12"–13" (30–33 cm). Felt-padded Shetland saddles come in 12" and 14" | [V] (§2.1) |
| Western seat | Youth 12"–13" (10" also exists) | 10"–12" | [V\*] / [A] |
| Bridle size | "Pony" (browband ≈ 34 cm) | "Shetland" (browband ≈ 32 cm; one brand: 37 cm) | [V\*] |
| Bit width | 4.5" / 11.5 cm | 4" / 10–10.5 cm | [V\*] |
| Reins | 48" (122 cm) | ≈ 42"–48" | [V] / [A] |
| Halter noseband (rope halter) | Pony 54 cm | Shetland 50 cm (Mini 46 cm) | [V] Pilgrimsrep |
| Rug (UK feet) | 5'3" (A–B 160 cm, backseam 110 cm) | 4'3"–4'9" (A–B 130–145 cm) | [V] Horseware / Sellerie-Plus |
| Rug (FR cm "longueur de dos") | 115 (1.20–1.30 m) to 125 (1.30–1.50 m) | 95–105 | [V] Sellerie-Plus |
| English girth | ≈ 38"–44" (97–112 cm) | ≈ 30"–36" (76–91 cm) | [A] (no reputable chart found) |
| Western cinch | 26"–28" for 13–14.2 hh. Smaller ponies: 20"–24" | 20"–24" | [V\*] |
| Brushing boots | "Pony": 24 cm high × 28 cm wide (Shires) | "Small Pony": 21 × 25 cm | [V\*] |
| Polo wraps | Pony: 3.5"–4" wide × 5–7 ft (9–10 cm × 1.5–2.1 m) | Same or shorter | [V\*] |
| Lead rope | 2 m standard | 2 m (1.8–2.2 m) | [V] |

---

## 2. English general-purpose saddle — *selle mixte / selle anglaise*

### 2.1 Structure and French names

| English | French | Notes |
|---|---|---|
| Tree | **arçon** | Rigid frame [V]. Traditionally laminated wood reinforced with steel. A "spring tree" has spring steel between the bars. Modern trees are synthetic moulded, fibreglass or carbon [V]. |
| Seat | **siège** | [V] |
| Pommel (front arch) | **pommeau** | The withers must clear it [V]. |
| Cantle (back of seat) | **troussequin** | [V] |
| Flaps | **quartiers** | Protect the rider's leg from the billets/buckles [V]. |
| Sweat flaps | **faux-quartiers** | Carry the knee/thigh blocks and protect the horse from the billet buckles [V]. |
| Knee rolls / blocks | **taquets** | Semi-rigid blocks on the faux-quartiers that hold the rider's leg [V]. |
| Panels (underside) | **panneaux** (also *matelassures* [A]) | Stuffed with wool flock (best saddles) or foam/fibre [V]. |
| Billets / girth straps | **contre-sanglons** | Usually 3 per side; the girth buckles onto 2 of them [V\*]. |
| Stirrup bars | **porte-étrivières** | Metal hooks that hold the leathers [V]. |
| Stirrup leathers | **étrivières** | [A] |
| Stirrup irons | **étriers** | [A] |
| Girth | **sangle** | [V] |
| Skirt (over the stirrup bar) | *petit quartier* | [A] |
| Saddle nail | *clou de selle* | The reference point for measuring seat size [V]. |
| D-rings (front) | *dés / anneaux de selle* | Breastplate attachment [V]. |
| Gullet / channel | *gorge / chambre (gouttière)* | [A] |

FR sources: [Wikipédia – Selle (équitation)](https://fr.wikipedia.org/wiki/Selle_(%C3%A9quitation)), [Wikiversité – Selle](https://fr.wikiversity.org/wiki/Utilisation_et_entretien_du_mat%C3%A9riel_%C3%A9questre/Selle), [Lexique du cheval](https://www.lexiqueducheval.net/lexique_materiel_engl.html), [Haras national suisse – fiche selle (PDF)](https://www.tierspital.uzh.ch/wp-content/uploads/2023/03/AgrTransfer2020_Selle_F.pdf). EN construction: [Wikipedia – English saddle](https://en.wikipedia.org/wiki/English_saddle).

### 2.2 Dimensions

**Seat size** is measured from the saddle nail (button) to the centre of the cantle. **Flap length** is measured from the stirrup bar straight down to the bottom of the flap [V] ([Riding Warehouse – How to measure](https://www.ridingwarehouse.com/lc/training/tack/how-to-measure-a-saddle.html), [Farmhouse Tack](https://www.farmhousetack.com/blogs/barn-blog/how-to-measure-for-an-english-saddle)).

Pony seat sizes:
- Pony saddles run **14"–16.5"**. Stock usually starts at 15" (suits most ponies of 13 hh and up), and 14" is often made to order [V] ([The Saddle Bank](https://www.thesaddlebank.com/blog/saddle-sizing-and-why-it-so-important/)).
- **The rider's size determines seat size, not the pony's**, though the pony's back length limits it [V] (same source).

Product data:

| Product | Seat sizes | Other details | Source |
|---|---|---|---|
| Thorowgood T4 Pony | 15", 15½", 16", 16½" | Changeable gullet N/M→XXW; 100% British wool flocking; short panel for short-backed ponies [V] | [Thorowgood T4 Pony](https://thorowgood.com/products/t4-pony-saddle), [Cheshire Horse](https://www.cheshirehorse.com/p/thorowgood-t4-all-purpose-pony-saddle/KW81593.html) |
| Wintec 500 Pony AP | 14", 15", 16" | Easy-Change gullet Narrow→Extra Wide [V] | [Saddle Bank – Wintec 500 Pony](https://www.thesaddlebank.com/brands/wintec/500-pony-ap-all-purpose-saddles/) |
| WintecLite Pony | — | **6.6 lb (3.0 kg)** [V] | [Riding Warehouse](https://www.ridingwarehouse.com/WintecLite_Pony_All_Purpose_Saddle/descpage-WLPA.html) |
| Pony Saddle Company First Saddle | 13"–16" | 12" to order [V] | [Pony Saddle Co.](https://www.theponysaddle.co.uk/products/our-pony-saddles/pony-saddle-company-first-saddle/) |
| Cwell Shetland "cub" saddle | 12", 14" | Treeless, felt-padded, with aluminium stirrups and a synthetic girth [V] | [Cwell Equine](https://www.cwellequine.com/shop/for-horse/pony-cub-saddles/cwell-equine-leather-treeless-felt-padded-shetland-pony-cub-saddle-choice-of-sizes-brown/) |

- Children up to about 7 years often fit a 12.5" seat [V\*] ([Equiniction – Shetland saddle guide](https://www.equiniction.com/choosing-the-perfect-saddle-for-your-shetland-pony-a-complete-fitting-guide/), retailer blog).

Modelling dimensions for a 15.5" pony GP saddle [A]:
- Overall length (pommel to cantle back): ≈ 48–52 cm.
- Width across the panels: ≈ 30–34 cm.
- Flap length: ≈ 32–38 cm.
- Cantle rise above the seat's lowest point: ≈ 6–8 cm.
- Panel thickness: 3–5 cm.
- Knee roll: ≈ 18–22 cm long × 3–4 cm thick.

### 2.3 Stirrup leathers and irons — *étrivières, étriers*
- **Leather lengths** are 48", 54", 58", 60" and 62". Young riders typically use **48" (122 cm)**, and the smallest children sometimes 42". The average adult uses 54" (137 cm); dressage riders often use 60" [V] ([Riding Warehouse – Stirrup leathers](https://www.ridingwarehouse.com/lc/training/tack/how-to-choose-riding-stirrup-leathers.html), [Strathorn Farm](https://www.strathornfarm.co.uk/equipment/what-size-stirrup-leathers-do-i-need/)).
- Leather width ≈ 2.2–2.5 cm, thickness 4–6 mm [A].
- **Iron sizing:**
  - The iron should be about **1" wider than the boot** at the ball of the foot, leaving ½" each side [V].
  - Sizes: 4" for shoe sizes 3–3½, 4¼" for 4–4½, 4½" for 5–5½, 4¾" for 6–7½. Very small children use smaller irons [V] ([Dover – About stirrup irons](https://www.doversaddlery.com/about-stirrup-irons/a/388/), [Schneider – measuring irons](https://www.sstack.com/blogs/product-guides/how-to-measure-english-stirrup-irons)).
  - **Game: a child rider on a 1.30 m pony → 4"–4¼" (10–10.8 cm inside tread width)** [A].
- Iron geometry [A]: height ≈ 12–13 cm, tread depth ≈ 3–4 cm, and an eye slot for a ≈ 2.5 cm leather. "Peacock" safety irons have a rubber band on the outer side.

### 2.4 Girth — *sangle*
- Materials: leather, synthetic webbing, fleece, neoprene. Common features: elastic at one or both ends, roller buckles, an anatomic (cut-back) shape, and a centre D-ring for the breastplate. It buckles to 2 of the 3 billets on each side [V\*] ([Wikipedia – Girth](https://en.wikipedia.org/wiki/Girth_(tack)), [Mad Barn – Girths](https://madbarn.com/girths-for-horses/), [Riding Warehouse – girths](https://www.ridingwarehouse.com/catpage-EGIRTHS.html)).
- Length: no reputable pony girth chart was found. Forum users report 38"–46" for 13–14.2 hh ponies, which is anecdotal. Estimate from geometry instead: **≈ ⅔ of heart girth minus 2"** [A]. For a heart girth of about 150–160 cm on a 1.30 m pony, that gives ≈ 38"–40" (97–102 cm). Width ≈ 10–12 cm at the centre, tapering to ≈ 5 cm at the buckles [A].

### 2.5 Placement (anatomical landmarks)
- **Tree points sit behind the scapula** (*omoplate*). The saddle must sit in the "saddle support area" and go **no further back than the 18th thoracic vertebra (last rib)**, found by following the flank hair-whorl line up to the spine [V] ([dvm360 – Saddle fit](https://www.dvm360.com/view/saddle-fit), [Horse Journals – 9 points of saddle fit](https://www.horsejournals.com/riding-training/tack-gear/english/9-points-saddle-fit)).
- Pommel clearance over the withers (*garrot*) is about 2–3 fingers. The girth lies in the **girth groove** (*passage de sangle*) about a hand's width behind the elbow (*coude*) [A].

### 2.6 Materials and PBR (see §11 for the master table)
- Seat, flaps and skirts: cowhide (pigskin is also used) [V]. Smooth oiled leather, roughness 0.35–0.55. Seat inserts are often suede or grip leather, roughness 0.75–0.9 [A].
- Synthetic saddles (Wintec etc.): roughness 0.45–0.6, plus a finer "pebbled" normal map [A].
- Hardware: stainless steel (nail, D-rings, buckles, stirrup bars) [A].
- Stitching: thread (roughness 0.6–0.7) as a normal map plus a trim sheet [I].

### 2.7 Rig and deformation [I]

| Part | Method |
|---|---|
| Tree, seat, pommel, cantle | **Rigid** on a `saddle_anchor` helper joint parented to the thoracic spine (≈T10–T14 region). Drive it by a constraint that averages 2–3 spine joints, so it pitches with the back but does not bend. |
| Panels | Mostly rigid. Optionally skinned at their lower edges to the rib/scapula joints so they hug the back. |
| Flaps and sweat flaps | **Skinned**: 60–80% `saddle_anchor`, the rest the ribcage/scapula joint, so they slide over the shoulder in extension. |
| Stirrup leathers | **2–4 joint chain** per side (pendulum: secondary motion or a simple spring in a System). |
| Stirrup iron | **Rigid** on the last chain joint. |
| Girth | **Skinned** to the sternum/ribcage joints. It must follow belly breathing and leg swing. |
| Billets and buckles | Buckles rigid (pinned); straps skinned. |

### 2.8 Exclusivity and stacking
- **Stacks:** girth (required); saddle pad (*tapis*) under; optional half-pad (*amortisseur*) between pad and saddle; optional breastplate (D-rings + girth); optional quarter sheet (under flaps or behind the cantle).
- **Exclusive with:** Western saddle, stable rug, fly sheet [A: you do not ride in a rug].

### 2.9 Customisation slots [I]
- Leather colour: black / havana / brown / tan, plus fantasy colours.
- Seat insert (suede) colour.
- Stitching colour.
- Knee-roll colour or patent leather.
- Metal finish: stainless / brass / rose-gold / black.
- Optional monogram or crest decal on the rear of the cantle or the flap (UV2).

---

## 3. Western saddle — *selle western*

### 3.1 Structure

| English | French [A unless noted] | Notes |
|---|---|---|
| Tree | arçon | Bars + fork + cantle [V] |
| Horn | corne / pommeau western | Built for dallying a rope; also a handhold [V] |
| Fork / swells / pommel | fourche (swells) | Raised front that carries the horn. "Swell" forks are wide, "slick" forks narrow [V] |
| Gullet | gorge | [V] |
| Seat | siège | [V] |
| Cantle | troussequin | [V] |
| Seat jockey / back jockey | jockeys | Flat leather panels covering the rigging [V] |
| Skirts | jupes / skirts | Large flat leather under the bars [V] |
| Fenders | fenders / quartiers d'étrivières | Broad leather panels carrying the stirrups [V] |
| Rigging, latigo, off billet | rigging, latigo, contre-sanglon | Latigo wraps through the D-ring and cinch buckle [V] |
| Front cinch / rear (flank) cinch | sangle western (cinch) / sangle arrière | Rear cinch has its own billets [V] |
| Stirrups | étriers western | Wood, aluminium, leather-covered [V] |
| Breast collar | collier / bricole western | Western equivalent of the breastplate [A] |

Sources: [Buffalo Bill Center of the West – Parts of a western saddle](https://centerofthewest.org/2021/08/20/parts-of-a-western-saddle-and-the-variations/), [IEA – Parts of a Western saddle (PDF)](https://www.rideiea.org/wp-content/uploads/2019/11/Bobs_Parts_of_a_Western_Saddle.pdf), [CoolHorse](https://www.coolhorse.com/blogs/saddles/parts-of-a-western-saddle), [Riding Warehouse – Western saddle guide](https://www.ridingwarehouse.com/lc/training/tack/western-saddle-guide.html).

### 3.2 Dimensions
- **Seat size:** children's/youth saddles are 12"–13"; youth/pony saddles are also sold in 10" [V\*] ([Schneider – Fitting a western saddle](https://sstack.com/resource/how-to-pick-the-best-fitting-western-saddle/R0101), [Double D Trailers – Western saddle size](https://www.doubledtrailers.com/saddle-size/)).
- **Horn:**
  - Height is measured from the top of the fork to the front of the cap; 2½"–4" is common [V\*].
  - Example: 3" neck, 2¼" cap [V\*] ([StateLine Tack – How to measure a western saddle](https://www.statelinetack.com/pages/how-to-measure-western-saddles), [NRS – western saddle fit](https://nrsworld.com/blogs/learning-center/how-to-fit-a-western-saddle-for-your-horse)).
  - Youth saddle: horn ≈ 2.5"–3" high, cap ≈ 2"–2.5" [A].
- **Swell width** on adult trail saddles is about 12.5"; youth saddles ≈ 10"–11" [V\*]/[A].
- **Weight:** youth Western saddles ≈ 15–25 lb (6.8–11.3 kg); adult saddles 25–45 lb [V\*].
- **Cinch:**
  - Small ponies and minis 20"–24"; 13–14.2 hh 26"–28"; sold in 2" steps [V\*] ([AQHA – Guide to cinches and latigos](https://www.aqha.com/-/the-guide-to-cinches-and-latigos), [Weaver – right size cinch](https://www.weaverequine.com/blogs/blog/do-you-have-the-right-size-cinch-for-your-horse), [Horse&Rider – cinches](https://horseandrider.com/how-to/best-horse-cinch/)).
  - Materials: mohair or string, neoprene, fleece-lined, felt; roller buckles [A].
- **Stirrups:** Weaver aluminium oxbow = 3" neck, 1½" tread, 5" high, 5½" wide. Wooden oxbow = 1" tread, 5" wide [V] ([Weaver – aluminium oxbow](https://www.weaverleathersupply.com/products/aluminum-stirrups-oxbow), [Weaver – wooden oxbow](https://www.weaverleathersupply.com/products/wooden-stirrups-oxbow-1-tread)). Youth stirrups ≈ 4"–4.5" wide [A].
- Western skirts for a youth saddle ≈ 20"–23" long front to back (≈ 50–58 cm) [A].

### 3.3 Placement
- Same principle as English: bars behind the scapula, ending before the last rib [V for the principle, §2.5].
- The front cinch lies in the girth groove. The rear cinch sits further back, under the belly, connected to the front cinch by a strap [A].

### 3.4 Materials and PBR
- Heavy tooled skirting leather with floral tooling, roughness 0.4–0.6. Rough-out leather (suede side out), roughness 0.85–0.95 [A].
- Conchos in silver or nickel: metallic 1, roughness 0.15–0.3 [A].
- Rawhide-covered horn, roughness 0.5–0.65 [A].
- Mohair cinch: fibrous strands as a normal map; roughness 0.8 with sheen [A].
- **Bake the tooling into the normal/height map. Do not model it** [I].

### 3.5 Rig [I]
- Tree, seat, horn and swells: **rigid** on `saddle_anchor`.
- Skirts: rigid or lightly skinned.
- **Fenders: skinned** to a 2–3 joint chain per side (they twist with the rider's leg). The stirrup is rigid at the end of the chain.
- Latigo: skinned. Cinch: skinned to the ribcage.

### 3.6 Exclusivity
- Exclusive with the English saddle, girth and English pad. Uses a Western pad or blanket.
- The English breastplate is replaced by a breast collar [A].

### 3.7 Customisation [I]
Leather tone, tooling pattern (normal-map swap), concho metal (silver/brass/copper), lacing colour, seat colour (suede/padded), cinch colour, horn wrap.

---

## 4. Saddle pad / numnah — *tapis de selle*, half-pad — *amortisseur*

### 4.1 Types [V\*/A]

| English | French | Description |
|---|---|---|
| GP / square pad | tapis (de selle) | Square-ish quilted cotton/polyester with piping |
| Numnah | tapis forme / "numnah" | Saddle-shaped, often fleece |
| Half-pad | amortisseur | Gel, foam or (synthetic) sheepskin, placed between the pad and the saddle [V] ([Sellerie du Golfe – guide tapis](https://selleriedugolfe.fr/tapis-de-selle-le-guide-complet-pour-choisir-utiliser-et-entretenir-le-votre/)) |
| Western pad / blanket | tapis western | Quilted with a 20 mm foam core and synthetic sheepskin underside (example product) [V] ([Equinoxe – Westride poney & shetland](https://equinoxe-shop.com/equinoxe-shop/cheval/tapis-bonnets-amortisseurs/tapis-western/westride-tapis-western-matelasse-poney-et-shetland/)) |

### 4.2 Dimensions
- Pony GP pad: **52 cm along the spine × 43 cm drop** in one brand's table. Another pony numnah is 60 cm along the spine × 92 cm side to side. A GP "S/M" for 13–15 hh is A 47 / B 63 / C 54 / D 48 cm. Brands differ by ±2 cm [V\*] ([Chelford – LeMieux saddle pad size guide](https://www.chelfordfarmsupplies.co.uk/blog/lemieux-saddle-pad-size-guide), [Milrey size chart](https://milrey.com/pages/saddle-pad-size-guide)).
- Shetland pad: 50 × 42 cm; typically 40–48 cm along the spine with a 30–36 cm drop. Western Shetland pad ≈ 50 × 52 cm [V\*] ([Equi-clic – tapis shetland](https://equi-clic.com/fr/1691-tapis-shetland), [Normandie Horse Shop](https://www.normandie-horse-shop.com/tapis-de-selle-shetland)).
- Thickness: quilted cotton 8–15 mm; fleece numnah 15–25 mm; gel/foam half-pad 10–20 mm [A].

### 4.3 Placement
- **Under the saddle.** It extends 3–5 cm beyond the saddle panels all round, lifted into the gullet over the withers and spine [A].
- Small straps loop around the billets, plus a loop to the girth [A].

### 4.4 Competition colour rules (useful for a "realistic/legal" preset)
- **FEI dressage:** white or off-white pads; contrast colouring and piping allowed; no stripes or multicolour [V\*] ([FEI Tack Rules – Dressage (PDF)](https://inside.fei.org/sites/default/files/Tack%20%20Equipment%20Requirements%20-%20Dressage_3.pdf), [Pink Equine – FEI rules](https://www.pinkequine.com/fei-rules-for-dressage/)).
- **UK Pony Club branches:** numnahs and saddlecloths **white, cream, navy, brown or black, single colour**; plain browbands [V\*] ([PC Eridge – Dress & tack rules](https://branches.pcuk.org/eridge/dress-and-tack-rules/), [PC Essex & Suffolk (PDF)](https://branches.pcuk.org/essexsuffolk/wp-content/uploads/sites/368/2024/08/Dress-and-Tack-rules-and-guidance-2024.pdf)).

### 4.5 Rig [I]
- **Skinned** to the same thoracic joints as the saddle, with a larger falloff to the ribcage.
- The pad edge (piping) must bend over the ribcage; the top stays under the saddle.
- Add a 1–2 mm "pad compressed" blend shape under the saddle.

### 4.6 Customisation [I]
Primary fabric colour, piping/binding colour, quilting thread colour (quilt pattern: diamond/square as a normal map), logo or number patch (decal on UV2), fleece trim colour (numnah/half-pad).

---

## 5. Snaffle bridle — *filet* (FR: *filet* = snaffle bridle; *bride* = double bridle with curb [A])

### 5.1 Structure (top to bottom)

| English | French | Fit / landmark |
|---|---|---|
| Headpiece / crownpiece | **têtière** | Over the poll (*nuque*) [V] |
| Browband | **frontal** | In the hollow about 2 fingers below the base of the ears; a finger should fit under it [V] |
| Throatlatch | **sous-gorge** | A fist should fit between it and the cheek [V] |
| Cheekpieces | **montants** | Join the bit (and noseband) to the headpiece [V] |
| Noseband: cavesson | **muserolle** (muserolle française [A]) | ≈ 2 fingers below the facial crest (cheekbone); 2 fingers between noseband and face [V] |
| Flash strap | muserolle combinée / sous-muserolle [A] | Passes through a loop at the cavesson centre and buckles **below the bit in the chin groove**; one finger under it [V] |
| Bit | **mors** (filet à anneaux [A]) | Two wrinkles at the corners of the mouth [V] |
| Reins | **rênes** | [V] |
| Keepers and runners | passants [A] | — |

Sources:
- FR: [Wikipédia – Filet (équitation)](https://fr.wikipedia.org/wiki/Filet_(%C3%A9quitation)), [Petit Galop – parties du filet](https://www.petit-galop.fr/conseils/filet/), [Horseee – parties du filet](https://www.horseee.fr/parties-du-filet/).
- Fit: [Horse Canada – Bridle fitting basics](https://horse-canada.com/magazine/equine-ownership/bridle-fitting-basics/), [Riding Warehouse – Fit an English bridle](https://www.ridingwarehouse.com/lc/training/tack/how-to-measure-fit-english-bridle.html), [Strathorn Farm – fit a snaffle bridle](https://www.strathornfarm.co.uk/equipment/how-to-fit-a-snaffle-bridle/).
- Flash: [Horse & Hound – noseband guide](https://www.horseandhound.co.uk/features/types-of-noseband-for-horses-34808), [Cavaletti Collection – fit a flash](https://www.cavaletticollection.co.uk/news/post/how-to-fit-a-flash-noseband-the-welfare-checklist).

### 5.2 Dimensions
- **Browband:** Shetland 32 cm (12½"), Pony 34 cm (13½"), Cob 37 cm (14½"), Full 39 cm (15½"), X-Full 42 cm (16½") [V\*] ([Shires size guide via GS Equestrian](https://gsequestrian.co.uk/pages/size-guide-shires-cavesson-and-flash-bridles)). Brands vary: another Shetland bridle lists headpiece 86–98 cm, browband 37 cm, noseband 42–54 cm [V\*] ([Just Horse Riders – Shetland bridle](https://www.justhorseriders.co.uk/blogs/news/discovering-the-ideal-bridle-a-guide-to-ensuring-comfort-and-style-for-your-shetland-pony)). A Cob bridle lists head (bit ring to bit ring) 93–114 cm, browband 40 cm, throatlatch 64–84.5 cm [V\*] ([Bridlery size chart](https://www.bridlery.com/en/size-chart/), [Schleese](https://schleese.com/bridle-measurement-guidelines/)).
- **Strap widths** (pony) [A]: cheekpieces and headpiece 16 mm (5/8"); cavesson 20–25 mm; flash 12–16 mm; browband 16–25 mm.
- **Reins:** 48" pony, 52" cob/small horse, 54" average horse, 60" oversize. Snaffle reins are 5/8" (16 mm) or 3/4" (19 mm) wide. Types: plain, laced, rubber-grip, web with hand stops [V] ([Dover – Reins for English disciplines](https://www.doversaddlery.com/pages/reins-for-english-riding-disciplines)).
- **Bit width:** Shetland/small pony 4" (10–10.5 cm); pony 4.5" (11.5 cm); cob 5" (12.5 cm); full 5.5" (13.5–14 cm). Measure lip to lip and add ¼" [V\*] ([Aussie Saddlery – Bit guide](https://aussiesaddlery.com.au/bit-guide/), [Top Saddlery – bit size chart](https://www.topsaddlery.com.au/pages/horse-bit-size-chart), [The Bit and Bridle](https://thebitandbridle.com/horse-advice/gear-advice/how-to-measure-for-a-bit-a-step-by-step-guide-1781/)).
- **Bit thickness:** 10–23 mm range, most about 15 mm, with a trend to 12–16 mm. About 12 mm is recommended for Shetlands [V\*] ([Picadera – loose ring](https://picadera.de/en/loose-ring), [Neue Schule – how to measure](https://nsbits.com/knowledge_base/how-to-measure)).
- **Loose rings:** usually 2.5"–3" (6.4–7.6 cm). Pony bits are about 6.5 cm; one pony example has a 13 mm mouthpiece and 70 mm rings [V\*] ([Wikipedia – Bit ring](https://en.wikipedia.org/wiki/Bit_ring), [Tom Balding loose ring](https://tombalding.com/products/s19-baseline-loose-ring-snaffle)).
- **Ring types:**
  - Loose ring: rings rotate.
  - Eggbutt (*mors à olives* [A]): fixed.
  - D-ring: fixed, lateral guidance.
  - Full cheek: cheek bars held by keepers.
  - Materials: stainless, sweet iron, copper, "Aurigan" alloy [V] ([Kentucky Horse Council – Types of snaffle bits (PDF)](https://afs.mgcafe.uky.edu/files/typessnafflebits_2.pdf), [Wikipedia – Snaffle bit](https://en.wikipedia.org/wiki/Snaffle_bit)).

### 5.3 Competition notes
- FEI dressage requires a browband. Apart from the parts attaching to the crownpiece, it need not be leather [V\*] (FEI tack PDF above).
- UK Pony Club competitions want **plain browbands**; "bling" browbands are refused [V\*] (PC Eridge).

### 5.4 Rig [I]

| Part | Method |
|---|---|
| Headpiece, browband, cheekpieces, noseband | **Skinned** to `head` (≈95%). The throatlatch also takes weight from `neck_top` (the first cervical joint), so it slackens and tightens with head flexion. |
| Ear area | Small weight to `ear_L/R` roots so the headpiece does not clip when the ears rotate. |
| Bit | **Rigid**, pinned to a `bit` helper joint under `jaw` (a mouth-open blend shape or jaw joint drives it). Use `Entity.attach(_:to:)` with a `GeometricPin` on the joint, iOS 26 (→ realitykit.md). Loose rings: two extra small joints, or a rigid pose. |
| Reins | **Joint chain** (10–20 joints) from the bit rings. **Mounted:** IK to the rider's hands. **Unmounted:** draped over the neck (a baked pose on neck joints) or hanging. Skinned tube or flat strip, 16 mm wide. |

### 5.5 Stacking and exclusivity
- **Exclusive with the halter** in the "head" slot. In real life a halter can be worn under a bridle (trail/endurance "bridle-headcollar" combos) [A]; for gameplay make it an option, not the default [I].
- **Stacks with:** fly bonnet (under the headpiece and browband), mosquero or pompons on the browband, plume on the headpiece.

### 5.6 Customisation [I]
Leather colour; padding colour (patent / contrast padding on the noseband and browband); stitching colour; browband style (plain, clincher, crystal, ribbon "rosette" browband); metal finish (bit + buckles: stainless / brass / rose-gold / black); rein type (plain/laced/rubber) and rubber colour.

---

## 6. Halter (headcollar) + lead rope — *licol + longe*

### 6.1 Structure
- **Parts:** crownpiece (*têtière*), cheekpieces (*montants*), noseband (*muserolle*), throatlatch (*sous-gorge*), connecting/throat strap, tie ring under the chin (*anneau d'attache*) [V for EN parts] ([Mad Barn – Halters](https://madbarn.com/halters-for-horses/), [Grewal – Parts of a halter](https://www.grewalequestrian.com/blogs/all-things-equine/parts-of-a-halter)). FR names [A].
- **Types:** flat nylon webbing with brass or nickel hardware; leather; rope halter (*licol éthologique*) [A]. Pony nylon halter example: double-thickness polypropylene, synthetic suede lining, "yellow metal" hardware [V] ([Alliance Élevage – licol longe poney](https://www.alliance-elevage.com/dept62_62_01_004_0620910_fiche_licol_longe_poney.html)).

### 6.2 Dimensions
- **Rope halter noseband circumference:** Mini Shetland 46 cm, Shetland 50 cm, Pony 54 cm, Cob 60 cm [V] ([Pilgrimsrep size guide](https://www.pilgrimsrep.se/en/size-guide)). Full 66 cm, X-Full 72 cm, XX-Full 78 cm [V\*] ([Smartwag halter size guide](https://smartwag.com/en/blog/ideal-halter-for-your-horse)). The noseband sits a few cm below the cheekbones [V] (Pilgrimsrep).
- **Lead rope:**
  - The standard is 2 m (e.g. the Horseware 2 m polypropylene lead with trigger clip) [V] ([Horseware lead rope](https://www.horse.com/products/horseware-lead-rope)).
  - FR retailers: 2 m for daily use, 3.70 m for groundwork, "between 2 and 3 m" recommended [V\*] ([Horse Village – licol et longe](https://horse-village.com/choisir-son-licol-et-sa-longe-2/), [Terres & Eaux](https://www.terreseteaux.fr/cavaliers/equipements-du-cheval-au-repos/licols-et-longes/longes-de-licol.html)).
  - Diameter: 16 mm cotton leads exist [V\*]; pony leads are typically 12–16 mm [A].
  - Snaps: trigger clip, bolt snap, **anti-panic snap** (*mousqueton anti-panique*), which releases under strong pull [V] ([West Cheval – longe Waldhausen anti-panique](https://westcheval.fr/licols-et-longes/15545-longe-de-licol-waldhausen-avec-mousqueton-anti-panique-4057962188938.html)).
- Webbing width, pony [A]: 19–25 mm; rings ≈ 30–40 mm.

### 6.3 Rig [I]
- Halter: **skinned** to `head`, like the bridle without a bit.
- Tie ring: rigid on a `chin_ring` helper.
- Lead rope: **joint chain** (12–24 joints) or a spline mesh, driven by the handler's hand IK, or tied to a ring with a hanging pose. Use a rope tube of 6–8 sides plus a twist normal map.

### 6.4 Exclusivity
- Exclusive with the bridle (see §5.5).
- Compatible with a **fly mask** (not in scope). A fly bonnet is designed for the bridle, but bonnets for rope halters exist [V\*] ([Equestra – bonnet pour licol étho](https://www.equestra.fr/bonnet-anti-mouche-cheval/20444-bonnet-anti-mouche-cheval-ergonomique-antifly-protect.html)).
- Compatible with the rug, fly sheet, stable bandages and bell boots (stable "at rest" outfit).

### 6.5 Customisation [I]
Webbing colour, fleece/suede lining colour, hardware finish (brass / nickel / black), rope colour (two-tone twist), snap type (visual).

---

## 7. Leg protection

### 7.1 Brushing boots — *guêtres* (and related)

| English | French | Coverage |
|---|---|---|
| Brushing boots (also called splint boots) | **guêtres** | From below the knee/hock to just below the inside of the fetlock, wrapping the whole cannon [V] |
| Open-front tendon boots | guêtres ouvertes / protège-tendons | Hard shell over the flexor tendons, open front; **front legs only** [V] |
| Fetlock boots | **protège-boulets** | Inside of the fetlock, open front; often worn **behind** with front tendon boots [V] |

Sources: [FEI – Leg protection ultimate guide](https://www.fei.org/stories/lifestyle/teach-me/leg-protection-your-horse-ultimate-guide), [Equestrian Stockholm – boots](https://equestrianstockholm.com/blogs/stories/horse-boots-what-are-they-and-what-is-their-function). FR: [Decathlon – protections](https://www.decathlon.fr/tous-les-sports/equitation/protections-du-cheval), [Kramer FR – protections](https://www.kramer.fr/conseils/protection-travail-types-pour-cheval), [Horseee – protections](https://www.horseee.fr/les-protections-du-cheval/) ("guêtres protect the fetlock and about ¾ of the cannon"; "cloches protect the hoof") [V].

- **Dimensions (Shires):** Small Pony 21 cm high × 25 cm wide (flat); Pony 24 × 28 cm. Pony boots have **2 hook-and-loop straps**. Typically 7 mm closed-cell neoprene with a padded strike pad on the inside [V\*] ([Shires brushing boots size guide](https://gsequestrian.co.uk/pages/size-guide-shires-brushing-boots), [Jeffers – Shires neoprene boots](https://jefferspet.com/products/neoprene-brushing-boots-size-cob-color-black)).
- **Straps** fasten on the **outside** of the leg, pointing **backwards** [A, standard practice; not checked this session].
- **Materials and PBR** [A]:
  - Neoprene outer (roughness 0.6–0.8, subtle knit normal).
  - Strike pad in PU/TPU (roughness 0.35–0.5).
  - Hook-and-loop straps (roughness 0.85).
  - Optional faux-leather outer (roughness 0.45).
  - Sheepskin-lined "show jumping" boots: fleece edge, roughness 0.95, sheen.
- **Rig [I]:** **Skinned** to `cannon` (≈ 85%) and `fetlock/pastern` (≈ 15%) at the bottom edge. Inflate 3–8 mm off the skin. Add a corrective blend shape at full fetlock flexion so the boot does not crush.
- **Stacking:** one per leg segment. **Exclusive with polo wraps or bandages on the same leg.** Stacks with bell boots (different segment) [I].
- **Customisation [I]:** shell colour, strap colour, lining or fleece colour, logo.

### 7.2 Bell boots / overreach boots — *cloches*
- Protect the **hoof, coronet band and heel bulbs** from overreach and pulled shoes. Worn under saddle and at turnout [V] ([Your Horse – over reach boots](https://www.yourhorse.co.uk/buying-guides/over-reach-boots/), [Dover – bell boots](https://www.doversaddlery.com/collections/bell-boots)).
- **Materials:**
  - Rubber, PVC or neoprene; leather also exists [V].
  - Pull-on or double hook-and-loop. Pre-moulded PVC boots have **heel-bulb shaping to reduce spinning** [V].
  - Pony sizes XS and S exist (Davis PVC) [V] ([Just for Ponies – Davis bell boots](https://justforponies.com/davis-bell-boots-xs-s/)).
  - "Petal" overreach boots: separate hanging petals [A].
- **Geometry [A]:** a bell-shaped cone from the pastern to just past the heel bulbs. Pony height ≈ 9–12 cm; wall 3–5 mm.
- **PBR [A]:** rubber, roughness 0.6–0.8; glossy PVC 0.2–0.35; neoprene 0.7.
- **Rig [I]:** **skinned** mostly to `pastern`, with some weight on `hoof` (to stop the bell clipping into the hoof at break-over). If bones are short, make it rigid on `pastern` with a flare that clears the hoof.
- **Stacking:** with brushing boots, polo wraps or stable bandages above [A].
- **Customisation [I]:** colour, fleece trim (neoprene version).

### 7.3 Stable bandages and polo wraps — *bandes de repos* & *bandes de polo*

| Type | French | Use | Structure |
|---|---|---|---|
| Stable (standing) bandage | **bandes de repos** + **sous-bandes** / leg quilts | In the stable, for recovery and oedema | Tightly knit synthetic, little stretch, over a cotton quilt that covers from just below the knee/hock to the bottom of the fetlock [V] |
| Polo wrap | **bandes de polo** | Light work, tendon support and shock absorption | Fleece, wrapped directly [V] |
| Exercise bandage | **bandes de travail** | Intensive work | More rigid, worn over **sous-bandes** [V] |

Sources: [Dover – Overview of wraps & bandages](https://blog.doversaddlery.com/an-overview-of-wraps-bandages-for-horses/), [Dover – exercise wraps](https://blog.doversaddlery.com/an-overview-of-exercise-wraps-for-horses/), FR: [Decathlon](https://www.decathlon.fr/tous-les-sports/equitation/protections-du-cheval), [Chevaleo](https://www.chevaleo.com/15-protection-des-membres).

- **Dimensions:**
  - Leg quilts are 12", 14" or 16" tall (and 10"–18" wide) [V] (Dover).
  - Polo wraps, pony: 3.5"–4" wide × 5–7 ft (Big Dee's 3.5" × 5 ft; Vac's 4" × 6 ft; Centaur 3.75" × 7 ft) [V\*].
  - Polo wraps, horse: 4"–5" × 9–11 ft [V\*] ([Vac's polo wraps](https://www.fourstarbrand.com/product/vacs-bandage-polo-wraps/), [Big Dee's pony polos](https://www.bigdweb.com/pony-polo-bandages)).
  - For a 1.30 m pony: quilt ≈ 12" (30 cm) tall; stable bandage ≈ 10 cm × 2.5–3 m [A].
- **Placement:**
  - Polo: from below the knee/hock down around the fetlock (cupping the sesamoids) and back up [A].
  - Stable bandage: knee/hock to coronet. It ends just above the coronet band and covers the fetlock [A].
- **Wrapped geometry [I]:** do **not** model the spiral. Use a smooth sleeve 6–10 mm thick, with a spiral-overlap normal map plus a slight height step on the silhouette. The end tab (hook-and-loop) is a small mesh patch.
- **PBR [A]:** fleece polo, roughness 0.9–1.0, sheen 0.4–0.8 (RealityKit `PhysicallyBasedMaterial` has a sheen parameter, → realitykit.md). Knit stable bandage: roughness 0.8, sheen 0.2.
- **Rig [I]:** skinned to `cannon` + `fetlock` + `pastern`.
- **Exclusivity:** exclusive with brushing boots on the same leg. Stable bandages are **stable-only**: not with a saddle in realistic mode [A]. Polo wraps are fine under saddle.
- **Customisation [I]:** fabric colour, optional two-tone, tab colour. **Matchy sets** (pad + bonnet + polos in one colour) are a strong real-world trend [V\*] ([Riding Warehouse – tack colour](https://www.ridingwarehouse.com/lc/training/tack/how-to-choose-tack-color-for-horse-coat-color.html)).

---

## 8. Head and grooming accessories

### 8.1 Fly bonnet / ear bonnet — *bonnet (anti-mouches)*
- **What it is:** a crocheted cotton (or mesh/synthetic) forehead panel with **two fabric ear covers**, often with a fringe. It is **worn under the bridle, held by the browband and crownpiece**, and lies flat on the forehead [V] ([Mad Barn – Ear bonnets](https://madbarn.com/ear-bonnets-for-horses/), [Chicks Saddlery – pony crocheted bonnet](https://www.chicksaddlery.com/crocheted-pony-fly-bonnet)).
- **FR:**
  - Placed under the headstall (*sous la têtière*). Crocheted cotton with fringes; ears in fabric for durability [V].
  - Some have a small strap under the headpiece so the bonnet does not slide or turn [V] ([Equestra – bonnet crochet](https://www.equestra.fr/bonnets-et-frontaux-anti-mouches-cheval/14874-bonnet-anti-mouche-crochet-cheval.html), [Tout pour votre cheval – modèle](https://tout-pour-votre-cheval.fr/modele-bonnet-cheval-crochet/), [Kentucky Horsewear – à quoi servent les bonnets](https://www.kentucky-horsewear.com/lu-fr/eur/blog/a-quoi-servent-les-bonnets)).
- **FEI:** ear hoods are allowed at all events; they **must not cover the eyes**, must be **discreet in colour and design**, and **must not be attached to the noseband** [V\*] (FEI Dressage tack PDF above).
- **Dimensions [A]:** for a pony, ear covers ≈ 14–18 cm tall; forehead panel from poll to ≈ 3–5 cm above the eyes; fringe 2–5 cm.
- **PBR [A]:**
  - Crochet cotton: roughness 0.85–0.95, sheen 0.3.
  - Satin ear fabric (show bonnets): roughness 0.3, anisotropic.
  - Cord trim: roughness 0.6.
  - Crystals or diamanté on the brow edge [I]: fake them with high-metallic dots plus sparkle in the normal map.
- **Rig [I]:** forehead panel skinned to `head`; ear covers **skinned to `ear_L/R`** (they must follow ear rotation). Fringe: alpha cards or geometry (see §12.4).
- **Stacking:** requires a bridle (or a halter-specific bonnet). Sits **under** the crownpiece and browband. Compatible with the mosquero/pompons on the browband [A].
- **Customisation [I]:** crochet colour, ear fabric colour, cord/trim colour, crystal edge on/off, embroidered logo.

### 8.2 Mane braids — *tresses / nattes*, *pions* (button braids)

| Style | Count and size | Source |
|---|---|---|
| Hunter braids (small and flat) | **30–45** braids on a short mane of 4–6"; sections 1.5–2" wide [V\*] | [Horse Rookie – hunter vs dressage](https://horserookie.com/hunter-dressage-braiding-manes/), [Horse Journals – braiding](https://www.horsejournals.com/how/how-braid-hunter-jumper-dressage) |
| Dressage button braids | **9–17**, traditionally an **odd number** [V\*] | [USDF – "Braids? Polo wraps?" (PDF)](https://www.usdf.org/edudocs/grooming/dressage_riders_how_to1.pdf), Horse Rookie |
| FR *tresse à pions* | Small braids folded into "pions"; an **odd number**, not counting the forelock; "18 to 25 pions" in general. The forelock (*toupet*) is braided and folded in three [V\*] | [Petit Galop – tresser](https://www.petit-galop.fr/conseils/tresser-cheval/), [Le site cheval – pions](http://www.le-site-cheval.com/toilettage/criniere_pion.php), [Unihorse](http://www.unihorse.fr/articles/5-1-1-toiletter-son-cheval.php) |
| Tail | Can be braided; an unbraided clean tail (*queue à tous crins*) is acceptable [V\*] | [Wikipédia – Soins des équidés](https://fr.wikipedia.org/wiki/Soins_des_%C3%A9quid%C3%A9s) |

- Braiding is done for dressage and breeding shows [V\*]. UK Pony Club branches require plaiting when representing the branch [V\*]. The French national horse institute (IFCE) documents show presentation grooming ([IFCE Equipédia – préparation à une présentation](https://equipedia.ifce.fr/equitation/autres-disciplines/epreuves-shf/preparation-a-une-presentation)).
- **Pony crest length:** ≈ 55–70 cm [A] → ≈ 11–15 dressage buttons or ≈ 25–35 hunter braids [I]. Button diameter ≈ 3–4 cm; hunter braid ≈ 1–1.5 cm wide × 8–10 cm folded [A].
- **Rig and modelling [I]:**
  - A braided mane is a **separate mane variant**, not an add-on: hide or swap the loose mane cards.
  - Place the button meshes along a crest spline, each **rigid on the nearest `mane_xx` or `neck_xx` joint**. Use low-poly spheres or lumps with a braid normal map.
  - Yarn or rubber-band ties are part of the texture.
  - The braided forelock is a small mesh on `head`.
- **PBR:** the hair material (see the mane spec). Yarn ties: roughness 0.9.
- **Customisation [I]:** braid style (none / hunter / buttons / running braid / Iberian "trenza"), yarn colour (white yarn or tape on dark horses is a show tradition [A]).

### 8.3 Ribbons and tail bows — *rubans, nœud de queue*
- **Hunting/safety code:** a **red ribbon at the top of the tail = kicks**; **green = young or inexperienced**. Both should stay at the back of the field. The custom comes from English foxhunting [V] ([Vine & Craven Hunt – Hunting etiquette](https://www.vineandcravenhunt.co.uk/about-us/hunting-etiquette/), [NW Horse Source – tail ribbons](https://nwhorsesource.com/all-about-tail-ribbons/)). FR, same meaning [V] ([Sellerie Sylvie – ruban rouge cheval qui tape](https://sellerie-sylvie-equitation.com/sse-accessoires-de-pansage/1462-ruban-rouge-queue-hfi.html), [Soon a horse – signification des rubans](http://soon-a-horse.blogspot.com/2021/12/signification-ruban-queue-cheval.html)).
- **Products:** "nœud de queue" show tail bows exist [V] ([La Sellerie Française – nœud de queue](https://laselleriefrancaise.com/products/noeud-de-queue), [Bel Étrier – nœud de queue pour concours](https://www.beletrier.com/page-d-articles/n%C5%93ud-de-queue-pour-concours), [PADD – ruban de queue Norton](https://www.padd.fr/nattage-et-toilettage/26760-ruban-de-queue-norton.html)).
- **Gameplay idea [I]:** the red and green ribbons could carry **meaning** (temperament, young horse), not only cosmetics.
- **Geometry [A/I]:** bow ≈ 10–15 cm wide, tails 15–25 cm. **Rigid on `tail_01/02`** with the ribbon tails on 2–3 small joints, or skinned to the tail chain.
- **PBR [A]:** satin roughness 0.25–0.35 with anisotropy (→ realitykit.md: `PhysicallyBasedMaterial` supports anisotropy); grosgrain 0.6.
- **Exclusivity:** the rug or fly-sheet tail flap covers the dock → hide the bow, or forbid both [I].

### 8.4 Flowers
- Horses are decorated with flowers in parades: the Rose Parade has equestrian units, and Hawaiian **Pāʻū riders** decorate horse and rider with leis and many flowers [V\*] ([Wikipedia – Parade horse](https://en.wikipedia.org/wiki/Parade_horse), [Tournament of Roses – About](https://tournamentofroses.com/about/about-rose-parade/)). Flowers can be tucked into braids for fun shows and special occasions [V\*] ([Braid Secrets](https://braidsecrets.com/braided-horse-mane-guide/)).
- **Not competition-legal** [I, consistent with the plain-tack rules above].
- **Geometry [I]:** small instanced flower meshes (5–8 petals, 60–200 tris), pinned to braid buttons or the browband. Alternatively a lei/garland as a skinned tube along the neck base.
- **PBR [A]:** petals roughness 0.5–0.7. Subsurface is iOS 27-only (→ realitykit.md), so fake translucency with a slightly emissive back-light term or a lighter base colour.

### 8.5 Plume — *plumet*
- Ornamental feather plume used on **driving/presentation harness** and show tack. Example product: **white 30 cm or red 15 cm** [V] ([Sellerie du Meneur – Plumet](https://www.selleriedumeneur.fr/brides-licols-et-accessoires/1530-plumet.html)). Presentation harness context: [IFCE – types de harnais](https://equipedia.ifce.fr/infrastructure-et-equipement/materiel/les-differents-types-de-harnais).
- **Placement:** on the top of the headpiece at the poll, in a holder or socket (FR: *porte-plumet*) [A].
- **Rig [I]:** **rigid** pinned to `head` (or the `poll` helper), plus 1–2 joints for sway. Feathers as 4–8 crossed cards with `opacityThreshold`.
- **Exclusivity:** requires a bridle (or a harness bridle) [A].

### 8.6 Pompons, mosquero (Iberian tradition)
- **Mosquero:** a fly fringe of leather strips, horsehair or silk tassels, tied to the **centre of the browband**. It swings to keep flies off the eyes [V] ([BAPSH – Spanish equestrian terms](https://bapsh.co.uk/spanish-equestrian-terms-explained/), [Equitrekking – Vaquero tack](https://equitrekking.com/articles/entry/spanish_tack_-_vaquero_spanish-cowboys), [Lazypony – vaquero bridle with mosquero](https://lazypony.es/product/leather-bridle-vaquero-with-mosquero-lazypony/)).
- **Mane and tail pompons:** sold as **"atacrines"** (wool mane pompoms, **sets of 8**) and **"atacola"** (tail pompom), in several colours [V] ([Sellerie Ibérique – ensemble pompons laine](https://www.sellerie-iberique.com/catalog/fr/mosqueros/1171-ensemble-pompons-en-laine-criniere-et-queue.html), [Sellerie Ibérique – mosqueros](https://sellerie-iberique.com/catalog/fr/30-bonnets-mosqueros)).
- **Geometry [A/I]:** pompom ≈ 4–7 cm. Model as a low-poly sphere (80–150 tris) with a fuzzy normal map and a high-roughness wool material, or as a shell with a few alpha cards for the fuzzy silhouette. Pin them along the mane joints (8 on the crest) and at the tail root.
- **PBR [A]:** wool roughness 0.95, sheen 0.6–1.0.
- **Exclusivity:** pompons go on a loose or Iberian-braided mane; they conflict with hunter/dressage braids in realistic mode [A]. A mosquero needs a browband (bridle or halter).

---

## 9. Body rugs and sheets

### 9.1 Stable rug — *couverture d'écurie*
- **Parts:**

  | English | French | Tag |
  |---|---|---|
  | Front chest straps (buckles/clips) | attaches de poitrail | [A] |
  | Cross surcingles | **sursangles croisées** | [V] |
  | Leg straps | **courroies de cuisses** | [V] |
  | Shoulder gussets | plis d'aisance | [V] |
  | Tail flap | **rabat de queue** | [V] |
  | Fillet string / tail cord | **courroie / ficelle de queue** | [V] |
  | Wither relief / fleece wither pad | — | [V] |
  | Neck cover (optional) | **couvre-cou** | [V] |

  Sources: [Horse & Hound – stable rugs](https://www.horseandhound.co.uk/buyers-guides/best-medium-weight-stable-rugs-478822), [Your Horse – stable rugs](https://yourhorse.co.uk/buying-guides/stable-rugs-for-this-winter); FR: [Kramer – types de couvertures](https://www.kramer.fr/conseils/types-de-couvertures-chevaux), [Sellerie Plus – Equithème Tyrex 1680D couvre-cou](https://www.sellerie-plus.fr/couverture-tyrex-1680d-avec-couvre-cou-220g-equitheme-6582).
- **Fill weight:**
  - Lightweight ≤ 150 g, medium 150–300 g, heavy > 300 g. Examples: 240 g body + 120 g tail flap; 360 g polyfill [V\*].
  - **Outer fabric:** 600D polyester is common for stable rugs; 300D on lightweights; 210D ripstop. Turnout rugs reach 1680D (e.g. the Equithème Tyrex 1680D) [V\*].
- **Sizes:**
  - **Horseware:** measure from the centre of the chest (A), around the point of the shoulder, to the centre of the tail (B), then **subtract 10 cm** [V]:

    | Size | A–B | Backseam |
    |---|---|---|
    | 3'9" | 114 cm | 75 cm |
    | 4'0" | 122 cm | 80 cm |
    | 4'3" | 130 cm | 85 cm |
    | 4'6" | 137 cm | 90 cm |
    | 4'9" | 145 cm | 95 cm |
    | **5'0"** | **152 cm** | **100 cm** |
    | **5'3"** | **160 cm** | **110 cm** |
    | 5'6" | 168 cm | 115 cm |
    | 5'9" | 175 cm | 125 cm |

    ([Horseware size guide](https://www.horseware.com/en-eu/size-guide), [Horseware Amigo Bug Rug Pony](https://www.horseware.com/en-eu/amigo-bug-rug-pony-fly-sheet)).
  - **FR (Sellerie-Plus):** withers 1.00–1.10 m → 4'9" (back 105 cm, total 145 cm); 1.20–1.30 m → **5'3"** (back ≈ 115 cm, total 160 cm, "115" size, "Poney – Small"); 1.30–1.50 m → 5'9" (125/175) [V] ([Sellerie-Plus – tableaux d'équivalence](https://www.sellerie-plus.fr/blog/tableaux-d-equivalence-des-tailles-des-couvertures-n3)). French shops size by back length in cm, measured **withers → tail root** [V] (same source).
  - **Ideal Equestrian (cm system):** withers 101–115 cm → size 135 [V\*] ([Ideal Equestrian – measurement charts](https://www.idealequestrian.com/en/metric-conversion-table/)).
- **Fit landmarks:**
  - The rug sits **forward, in front of the withers**, without pressing the shoulders.
  - The chest strap allows about 4 fingers.
  - Surcingles **cross in an "X" under the belly** with a hand's width of slack.
  - **The top of the tail flap is at the top of the tail.** The tail goes over the fillet string [V\*] ([WeatherBeeta – How to fit your rug](https://www.weatherbeeta.co.uk/how-to-fit-your-rug), [PONY mag – put a rug on your pony](https://www.ponymag.com/pony-know-how/how-to-put-a-rug-on-your-pony/), [Equus – how to put on a rug](https://www.equus.co.uk/blogs/community/how-to-put-on-a-horses-rug)).
- **PBR [A]:**
  - Outer polyester: roughness 0.45–0.65, slight sheen; ripstop grid in the normal map.
  - Fleece/cotton lining (visible at the edges): roughness 0.9.
  - Binding tape: roughness 0.5.
  - Metal T-bar/clips: stainless, roughness 0.3.
  - Quilting stitch lines as a normal map.
- **Rig [I]:**
  - **Fully skinned** to spine, scapula, ribcage and pelvis/femur joints, plus `tail_01` for the tail flap. Surcingles skinned to the ribcage; leg straps to the femur/stifle.
  - Offset 10–25 mm from the coat. Weight-paint **smooth falloffs over the shoulder and hip** to avoid hard creases.
  - Use **corrective blend shapes** for the grazing pose (head down) and lying down.
  - **Hide body polygons under the rug** (body mask, see §12.3).
  - RealityKit cloth simulation (`ClothBody`/`ClothSimulation`) was introduced at **WWDC26**. It is likely tied to the 2026–27 SDK, so do not rely on it with an iOS 26 deployment target [I] ([WWDC26 – Explore advances in RealityKit](https://developer.apple.com/videos/play/wwdc2026/279/)). A skinned rug plus 2–4 secondary "skirt" joints per side for sway is the safe route.
- **Exclusivity:** exclusive with saddle, saddle pad, quarter sheet and fly sheet [A]. Compatible with the halter, stable bandages, bell boots and tail bandage. Hides the tail bow and dock area.
- **Customisation [I]:** outer colour; binding/trim colour; lining colour; pattern (check, stars, camo, tartan); embroidered name or initials (decal); neck cover on/off; fill weight as a "puffiness" blend shape.

### 9.2 Fly sheet — *chemise anti-mouches*
- **Structure:**
  - Lightweight poly/nylon **mesh** body, attached or detachable **neck cover**, **belly wrap/guard** closing the flank gap, full **tail flap**.
  - Some brands claim > 75% UV blocking [V\*] ([Riding Warehouse – best fly sheets](https://www.ridingwarehouse.com/lc/buying_guides/horse_care/best-fly-sheets.html), [Schneider – fly sheets](https://www.sstack.com/collections/horse-fly-sheets)).
  - FR: [Esprit Équitation – chemise anti-mouches](https://www.esprit-equitation.com/180-chemise-anti-mouches), [Kramer FR](https://www.kramer.fr/conseils/types-de-couvertures-chevaux).
- **Sizes:** same system as rugs. The Horseware Amigo **Bug Rug Pony** uses the pony table above [V].
- **Mesh rendering [I]:** an **opaque base with mesh normal and roughness, plus `opacityThreshold` only if you want see-through**. Apple advises using geometry instead of alpha-clipped cards and limiting semi-transparent materials (→ realitykit.md, quoting [Creating USD files for Apple devices](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)). On a TBDR GPU, large alpha-tested surfaces disable hidden-surface removal benefits (§12.4). **Recommendation:** render the mesh opaque, with the coat colour faintly "showing through" by multiplying a darkened mesh pattern over a semi-neutral base. Do not make it truly transparent.
- **Rig and exclusivity:** as the stable rug. Not ridden in. Exclusive with the rug.
- **Customisation [I]:** mesh colour, trim colour, pattern (zebra-stripe fly sheets exist commercially [A]).

### 9.3 Quarter sheet / exercise sheet — *couvre-reins*
- **What and where:** worn while riding in cold weather to warm the hindquarters.
  - It fits under the saddle (secured under the flaps) **or** has a cut-out to sit behind the saddle.
  - It covers **from the cantle over the whole hindquarters**.
  - Some attach to the girth or with hook-and-loop near the pommel. Often a fillet string.
  - Wool, fleece or waterproof [V\*] ([Schneider – quarter sheets](https://www.sstack.com/quarter-sheets/c/1306/), [Dover – quarter sheets](https://www.doversaddlery.com/quarter-sheets/c/4405/), [Bit of Britain – quarter sheets](https://www.bitofbritainusa.com/horse-care/horse-blankets-sheets-or-coolers/quarter-sheets)). FR term *couvre-reins* [V] ([Kramer FR](https://www.kramer.fr/conseils/types-de-couvertures-chevaux)).
- **Dimensions for a pony [A]:** ≈ 110–130 cm side to side × 70–85 cm from the cantle to below the point of the buttock.
- **Rig [I]:** skinned to the lumbar spine, pelvis and upper femur joints. Its front edge sits under the saddle flaps (render order: sheet under flap). Add a fillet string. A hip-swing corrective shape is useful.
- **Exclusivity:** requires a saddle (or a lunging surcingle). Exclusive with the rug and fly sheet. Stacks with the saddle pad (the pad sits on top at the front) [A].
- **Customisation [I]:** fabric (wool tartan / fleece / waterproof), trim colour, embroidered initials or crest.

### 9.4 Breastplate — *collier de chasse* (optional)
- **EN structure (hunting breastplate):**
  - A **yoke** with a neck strap and a **wither strap**.
  - A **breast strap** that runs between the front legs to the **girth**.
  - **Two straps from the top of the yoke to the saddle D-rings**.
  - Adjustment buckles; optional **elastic inserts** in the yoke.
  - A **ring at the chest** for a running/standing martingale attachment [V] ([Wikipedia – Breastplate (tack)](https://en.wikipedia.org/wiki/Breastplate_(tack))).
- **FR:**
  - The *collier de chasse* stops the saddle sliding back. It has a central part at the chest linked to the **sangle** between the forelegs, an upper part round the neck with a **pont** over the withers, and two strong straps to the **anneaux (dés) de selle**. A removable *fourche de martingale* can be added [V].
  - The **bricole** (elastic breastgirth) is *not* attached to the girth between the legs and leaves the shoulders freer [V\*] ([Devoucoux – collier de chasse élastique](https://eu.devoucoux.com/fr/accessoires/6306-collier-de-chasse-elastique.html), [Kramer FR – colliers de chasse & martingales](https://www.kramer.fr/Cheval/Briderie-accessoires/Colliers-de-chasse-martingales), [Sellerie Fouilloux](https://www.sellerie-fouilloux.fr/43-colliers-de-chasse-et-bricoles)).
- **Dimensions for a pony [A]:** strap width 16–22 mm; chest ring ≈ 5–6 cm; elastic inserts ≈ 8–12 cm long.
- **Placement:** yoke around the base of the neck in front of the shoulders, ring at the centre of the chest (in front of the sternum, between the points of the shoulder), strap down between the forelegs to the girth centre D [V/A].
- **Rig [I]:**
  - Skinned to `neck_base`/`chest` (yoke), to the sternum and ribcage (girth strap), and to the saddle anchor (D-ring straps).
  - The ring is rigid on a `chest_ring` helper.
  - **Watch the forelegs:** the girth strap must not intersect the inner forearm at full protraction. Use a corrective shape or a slight forward offset.
- **Exclusivity:** requires a saddle with a girth. The Western equivalent is a breast collar.
- **Customisation [I]:** leather colour, elastic insert colour, padding colour, metal finish.

---

## 10. Stacking and exclusivity matrix [I, from the [V] placement facts above]

### 10.1 Slots
```
HEAD:        Bridle | Halter            (exclusive)
  ├─ HEAD_UNDER:  Fly bonnet          (requires Bridle, or a halter-specific bonnet)
  ├─ BROWBAND_DECOR: Mosquero | Pompons | Flowers | Crystal browband   (requires a browband)
  ├─ POLL_DECOR:  Plume               (requires Bridle)
  ├─ BIT:         Snaffle (loose ring | eggbutt | D | full cheek)  (Bridle only)
  ├─ REINS:       Plain | Laced | Rubber  (Bridle only)
  └─ LEAD:        Lead rope            (Halter only)
BACK:        English saddle | Western saddle | Stable rug | Fly sheet | (none)   (exclusive)
  ├─ PAD:         English pad/numnah | Western pad       (must match the saddle type)
  ├─ HALF_PAD:    Amortisseur          (English; between pad and saddle)
  ├─ GIRTH:       Girth (English) | Cinch (Western)     (auto, required)
  ├─ CHEST:       Breastplate (English) | Breast collar (Western)
  └─ HINDQUARTER: Quarter sheet        (requires a saddle; exclusive with rug/fly sheet)
LEGS (×4, per leg):  Brushing boot | Polo wrap | Stable bandage | (none)   (exclusive per leg)
  └─ HOOF (×4):   Bell boot            (stacks with any of the above)
MANE:        Loose | Hunter braids | Button braids (pions) | Iberian       (exclusive styles)
  └─ MANE_DECOR:  Flowers (on braids) | Pompons/atacrines (loose/Iberian)
TAIL:        Loose | Braided
  └─ TAIL_DECOR:  Ribbon (red/green) | Show bow | Pompom (atacola)   (hidden by a rug/fly-sheet tail flap)
```

### 10.2 Key rules
- **Saddle ↔ rug / fly sheet:** exclusive. A pony is not ridden in a stable rug.
- **Saddle pad requires a saddle.** The half-pad goes between the pad and the saddle [V].
- **Fly bonnet goes under the bridle crownpiece and browband** [V]. FEI: it must not cover the eyes [V\*].
- **Halter ↔ bridle:** exclusive by default. The halter-under-bridle variant is optional [A].
- **Boots vs bandages:** exclusive per leg. Bell boots stack. Stable bandages belong to the "stable/rest" outfit.
- **Braids replace the loose mane mesh.** Flowers go on braids.
- **Rug, fly sheet or quarter sheet hide the tail decoration** at the dock. Ribbons sit "at the top of the tail" [V].
- **"Competition-legal" preset** (optional realism mode) [V\*]:
  - Single-colour white/cream/navy/brown/black pads (Pony Club), or white/off-white (FEI dressage).
  - Plain browband; braided mane; discreet ear bonnet.
  - No flowers, pompons or plume.

---

## 11. Materials and PBR master table

**Verified anchors:**
- Dielectrics use **F0 ≈ 0.04 (4%) reflectance** when metallic = 0 [V] ([Adobe – The PBR Guide part 1](https://helpx.adobe.com/substance-3d-designer/how-to/the-pbr-guide-part-1.html)).
- Raw metal reflectance is **≈ 70–100%**. Substance's validator flags albedo darker than **30–50 sRGB** for non-metals and metal reflectance outside 70–100% (or 60–100%) [V] ([Adobe – PBR BaseColor/Metallic Validate](https://experienceleague.adobe.com/en/docs/substance-3d-designer/using/substance-graphs/nodes-reference-for-substance-graphs/node-library/material-filters/pbr-utilities/pbr-basecolor-metallic-validate)).
- Measured metal base colours (linear): **iron (0.560, 0.570, 0.580), silver (0.972, 0.960, 0.915), chromium (0.550, 0.556, 0.554)** [V\*] ([Epic – Physically Based Materials (UE 4.27)](https://dev.epicgames.com/documentation/en-us/unreal-engine/physically-based-materials?application_version=4.27)). The same table lists gold ≈ (1.0, 0.766, 0.336) and copper ≈ (0.955, 0.637, 0.538) [A, from memory of that table]. More values: [Physically Based database](https://80.lv/articles/physically-based-a-database-of-pbr-values-for-real-world-materials).
- Roughness ranges from texturing references [V\*] ([Roblox – material reference](https://create.roblox.com/docs/art/modeling/material-reference), [3D Footwear Academy – leather/suede/rubber](https://3dfootwearacademy.com/en/blog/pbr-materials-textures-footwear)):
  - glossy leather 0.2–0.4; worn leather 0.5–0.7; leather ≈ 0.3–0.45;
  - suede 0.75–0.90;
  - cotton/canvas/denim 0.8–0.9.

| Material | Used on | Metallic | Roughness | Base colour hints | Extras |
|---|---|---|---|---|---|
| Smooth oiled leather | saddle, bridle, breastplate | 0 | 0.35–0.55 [A] | Black: keep ≥ 30–50 sRGB [V threshold]. Havana ≈ #3B2418; tan ≈ #9A6234 [A] | Grain normal; edge-paint strip; stitch trim; slightly glossier wear on contact zones |
| Patent / show leather | browband, noseband padding | 0 | 0.08–0.2 [A] | — | Clearcoat 0.6–1 (RK `clearcoat`, → realitykit.md) |
| Suede / nubuck / rough-out | seat inserts, Western rough-out | 0 | 0.8–0.95 [V\*/A] | — | Sheen 0.2 |
| Synthetic leather | Wintec-type saddles | 0 | 0.45–0.6 [A] | — | Pebbled normal |
| Cotton quilt (pads) | saddle pad | 0 | 0.8–0.95 [V\*/A] | Any colour | Quilting normal/AO; sheen 0.2–0.4 |
| Fleece / synthetic sheepskin | numnah, half-pad, polos, boot lining | 0 | 0.9–1.0 [A] | — | Sheen 0.5–1.0; fibre normal; fuzzy silhouette edge loop |
| Neoprene | brushing boots, girths | 0 | 0.6–0.8 [A] | — | Fine knit normal on the outer face |
| PU/TPU strike pads, PVC | boot shells, bell boots | 0 | 0.2–0.5 [A] | — | — |
| Rubber | bell boots, rubber reins | 0 | 0.6–0.8 [A] | — | Pebble normal for reins |
| Nylon / PP webbing | halter, straps, surcingles | 0 | 0.4–0.6 [A] | — | Anisotropy along the strap; weave normal |
| Cotton rope / PP rope | lead rope | 0 | Cotton 0.85; PP 0.4–0.55 [A] | — | Twist normal |
| Polyester outer (600D / ripstop) | rugs, fly sheets | 0 | 0.45–0.65 [A] | — | Ripstop grid normal; slight sheen |
| Wool (tartan, pompoms) | quarter sheet, pompons | 0 | 0.9–1.0 [A] | — | Sheen 0.6–1.0 |
| Satin ribbon | tail bow, ribbons, bonnet ears | 0 | 0.25–0.35 [A] | — | Anisotropy |
| Crochet cotton | fly bonnet | 0 | 0.85–0.95 [A] | — | Crochet normal + AO; optional threshold-alpha holes |
| Stainless steel (polished) | bit, irons, buckles, D-rings | 1 | 0.1–0.25 [A] | Iron/chromium values ≈ 0.55–0.58 linear [V\*] | Brushed variant 0.25–0.4 |
| Brass (yellow metal) | halter hardware, show buckles | 1 | 0.15–0.35; aged 0.35–0.5 [A] | ≈ (0.91, 0.78, 0.42) linear [A] | Tarnish mask |
| Silver / nickel | show bridles, conchos | 1 | 0.1–0.3 [A] | Silver (0.972, 0.960, 0.915) [V\*] | — |
| Copper (inlay) | bit mouthpiece inlay | 1 | 0.2–0.35 [A] | ≈ (0.955, 0.637, 0.538) [A] | — |
| Sweet iron (blued) | bit mouthpiece | 1 (0 where rusted) | 0.3–0.5 [A] | Darker than iron (≈ 0.25–0.35 linear) [A] | Rust mask = dielectric |
| Horsehair | mosquero, fringes | 0 | Same as mane | Same as mane | Cards; `faceCulling = .none` (→ realitykit.md) |
| Feather | plume | 0 | 0.5–0.7 [A] | — | Cards with `opacityThreshold` |

**RealityKit notes (→ realitykit.md):**
- `PhysicallyBasedMaterial` has baseColor (tint × texture), roughness, metallic, normal, clearcoat, sheen, anisotropy and `opacityThreshold`.
- The USD importer gives **2 UV sets maximum**, "a single packed texture per material", OpenGL-convention normal maps, and **no double-sided import**.
- **Subsurface is iOS 27-only.**

---

## 12. Real-time / game-ready modelling guidance

### 12.1 What platforms and other games tell us
- **Apple budgets:**
  - The DTS answer on the forums gives **no fixed numbers** and recommends an iterative profile-and-optimise cycle [V] ([Apple forum 751764](https://developer.apple.com/forums/thread/751764)).
  - WWDC24 "Optimize your 3D assets for spatial computing" (visionOS): **≤ 500k triangles for an immersive scene, ≤ 250k in the shared space; ~100k triangles in view is a safe target**. It also recommends baking fine detail into normal/ORM maps and splitting geometry for culling [V\*] ([WWDC24 10186](https://developer.apple.com/videos/play/wwdc2024/10186/)).
  - AR Quick Look guidance, as reported by third parties, is ≈ 100k polygons with 2048² textures [V\*] ([Netguru – AR Quick Look](https://www.netguru.com/blog/ar-quick-look-and-usdz)).
- **TBDR:** Apple GPUs are tile-based deferred renderers with **hidden-surface removal**. Draw opaque, then alpha-tested, then translucent; avoid interleaving them. `discard`/alpha test weakens HSR, so prefer blending or geometry over many alpha-tested layers [V\*] ([WWDC20 – Harness Apple GPUs with Metal](https://developer.apple.com/videos/play/wwdc2020/10602/), [PowerVR – Do not use discard](https://docs.imgtec.com/starter-guides/powervr-architecture/html/topics/rules/do-not-use-discard.html)). Apple's USD guidance: "Use geometry instead of alpha-clipped cards … limit semi-transparent materials" (→ realitykit.md).
- **Star Stable Online:**
  - Tack slots are **bridle, saddle, saddle pad, saddle bag**. Blankets, bareback pads and more decorations were planned [V\*].
  - Star Stable could already give colour and material variations of tack; adding new *meshes* was the bottleneck.
  - "Retrofitting" (fitting each tack mesh to each breed) took **3 people about 3 weeks per 3 breeds**, mostly hunting clipping bugs.
  - Their new tack system re-skins all tack so one mesh fits all horses, at **about 1 day per horse to port** [V] ([Star Stable – May 2025 Extra: New tack system](https://www.starstable.com/en/article/blog-may-extra-2025), [March 2024 – Retrofit & MyStable](https://www.starstable.com/en/article/blog-march-2024), [Aug 2025 – Andalusian & retrofitting](https://www.starstable.com/en/article/blog-august-2025)).
  - **Lesson for Valombre [I]:** build every tack mesh on **one shared skeleton plus the body's morph targets** from day one.
- **Equestrian: The Game:** the store sells saddles, saddle pads, bridles, polo wraps, ear nets, etc. [V\*, fan wiki] ([Equestrian the Game wiki – Store](https://equestrianthegame.fandom.com/wiki/Store), [Steam guide – Tack & cosmetics](https://steamcommunity.com/sharedfiles/filedetails/?id=3114597701)).
- **Rival Stars Horse Racing (PikPok):**
  - Themed **tack sets** (Easter, Lunar New Year, "fashion").
  - Pipeline: **ZBrush → high-to-low in Maya → Substance Painter** [V] ([ArtStation – PikPok Art Dept: Horse Tack](https://www.artstation.com/artwork/R323oW), [The Mane Quest – interview with art lead V. Smith](https://www.themanequest.com/blog/2021/8/13/most-horse-games-lack-visual-polish-behind-the-scenes-of-rival-stars-horse-racing-with-art-lead-victoria-smith)).
  - **Lesson [I]:** themed "sets" (pad + bonnet + boots in one colourway) are good content units. Allow per-piece mixing too.

### 12.2 Polygon budget proposal (LOD0, triangles) [I]
Assumptions: the pony fills 30–60% of a phone screen, the target is about 100k triangles **in view** for pony, rider and tack, and the environment is budgeted separately.

| Item | LOD0 tris | Notes |
|---|---|---|
| Pony body | 25–35k | Plus mane/tail cards 6–12k |
| English saddle (tree, seat, flaps, panels, knee rolls) | 3–5k | Stitching and grain in maps |
| Stirrup leathers ×2 / irons ×2 | 2×150–250 / 2×300–500 | Irons: 12–16-sided tread bar |
| Girth | 600–1,000 | Elastic ends in normal map |
| Western saddle | 5–8k | Tooling baked |
| Fenders ×2 / cinch / W. stirrups ×2 | 2×300–500 / 600 / 2×300–500 | — |
| Saddle pad / numnah | 600–1,200 | Piping = 1–2 edge loops |
| Half-pad (amortisseur) | 400–800 | — |
| Bridle (straps + buckles + keepers) | 2–4k | Buckles as instanced micro-meshes, removed at LOD1 |
| Bit | 400–800 | Rings 16–24 segments |
| Reins | 300–600 | Strip on 12–20 joints |
| Halter / lead rope | 1–2k / 400–800 | Rope 6–8 sides |
| Brushing boots ×4 | 4×400–800 | — |
| Bell boots ×4 | 4×300–500 | — |
| Polo wraps / bandages ×4 | 4×300–600 | Spiral in normal map |
| Fly bonnet | 800–1,500 | + fringe 40–100 cards |
| Button braids (×13) / hunter braids (×30) | 13×60–120 / 30×40–80 | Instanced |
| Tail bow / ribbon | 300–600 | — |
| Flowers (set) | 600–2,000 | Instanced petals |
| Plume | 100–300 | Crossed cards |
| Pompons (×8 + 1) | 9×80–150 | Fuzzy normal + roughness |
| Mosquero | 300–800 | Cards or strips |
| Stable rug / fly sheet | 3–5k | Straps included |
| Quarter sheet | 1–2k | — |
| Breastplate | 1–2k | — |

LOD1 ≈ 50% and LOD2 ≈ 20–25%. Drop buckles, keepers, stitching geometry and the inner faces of straps from LOD1 onward.

Mesh LOD switching by camera distance or screen area is shown in WWDC26 ([WWDC26 279](https://developer.apple.com/videos/play/wwdc2026/279/)). Check its minimum OS before using it with a 26 target [I]. Otherwise swap meshes manually in a System.

### 12.3 Fitting, clipping and body masking [I]
1. **Author on the 1.30 m base mesh in its bind pose.**
   - Skin weights: Blender **Data Transfer** (vertex groups, nearest-face-interpolated) from the body, then clean up by hand.
   - Morphs: transfer each body shape key (Shetland, stocky, etc.) to the tack with **Surface Deform**, binding at the base shape and applying as shape keys, so the tack refits under the same `BlendShapeWeights`.
2. **Offsets from the skin:**

   | Item | Offset |
   |---|---|
   | Straps | 2–5 mm |
   | Boots | 3–8 mm |
   | Pads | 8–25 mm (thickness) |
   | Rugs | 10–25 mm |

   Add the offset with a Displace or Solidify modifier along the normals **before** the shape-key transfer.
3. **Influences:** ≤ 4 per vertex, normalised (→ realitykit.md: no documented RealityKit limit; plan ≤ 4).
4. **Corrective blend shapes** for extreme poses:
   - grazing (head down): throatlatch, rug neck, reins;
   - full fetlock flexion: boots, bandages;
   - forearm protraction: breastplate strap, girth;
   - lying down: rug.
5. **Body hide masks:** split the pony body into regions (back, barrel, neck, cannons ×4, pasterns ×4). An item that fully covers a region **hides that body region**. This kills clipping and saves fill-rate on a TBDR GPU.
   - In RealityKit, all meshes under one SkelRoot become **one ModelComponent** (community report, → realitykit.md). Either (a) export each accessory as its **own SkelRoot with identical joint names** and sync poses, or (b) rebuild `MeshResource.Contents` without the hidden parts.
   - For **rigid** items (bit, stirrup irons, plume, chest ring, bow) use `Entity.attach(_:to:)` with a `GeometricPin` on a skeletal joint. This is the iOS 26 API an Apple engineer called "the new, recommended way" (→ realitykit.md).
6. **Helper joints** to add to the pony rig now, so tack never needs a skeleton change:
   - Tack anchors: `saddle_anchor`, `girth_ring`, `stirrupLeather_L/R_01..03`, `stirrup_L/R`, `bit`, `rein_L/R_01..n`, `chin_ring`, `chest_ring`, `poll` (plume).
   - Rug sway: `rugSkirt_L/R_01..02`, `tailFlap` (or reuse `tail_01`).
   - Already present: `ear_L/R` (bonnet), `mane_01..n` (braids, pompons).

### 12.4 Which parts may use alpha cards [I, guided by the Apple advice above]

| Part | Recommendation |
|---|---|
| Mane, tail, forelock, mosquero horsehair | Cards with `opacityThreshold` + `faceCulling = .none`; opaque root layer (→ realitykit.md, Apple's character hair advice) |
| Fly bonnet fringe and tassels | Few cards (or thin strips of geometry) with threshold alpha |
| Fly bonnet crochet holes | **Opaque**, with the crochet pattern in normal/AO. Optional threshold only on the lace edge |
| Fly sheet mesh | **Opaque** pattern (see §9.2); never large alpha surfaces |
| Plume feathers | Crossed cards with threshold |
| Fleece edges (numnah rim, polo edge) | **Geometry** (a fuzzy edge loop) + normal map; no alpha |
| Pompom fuzz | Sphere + fuzzy normal; optional 3–6 small shell cards |
| Ribbons, bows, flowers | **Geometry** (cheap and crisp) |
| Stitching, quilting, tooling, buckle holes | Normal/height maps on a shared **trim sheet** |

Order: draw opaque tack first, then alpha-tested cards. Keep translucent blending for VFX only.

### 12.5 Textures and material slots for customisation [I]
- **One "strap trim sheet"** (1024×512) shared by all leather straps (bridle, halter, breastplate, billets, leathers): edges, stitching rows, holes, keepers. **One "hardware atlas"** (512²) for buckles, rings and the bit.
- Large items (saddle, rug, pad) get their own 1024² set (BaseColor + Normal + packed ORM). Use 2048² only for hero close-ups. Small items (boots, bonnet, bow) use 512².
- **Colour customisation**, two routes:
  - **(a) Simplest:** split each item into ≤ 4 material parts (`leather`, `fabric`, `trim`, `metal`) and set `baseColor.tint` per part on a greyscale base texture. Cost: one draw call per part.
  - **(b) Fewer draws:** a single `ShaderGraphMaterial` (iOS 18+) that reads an **RGBA region mask** (R = primary, G = secondary/trim, B = stitching, A = metal) and takes colour parameters via `setParameter` (→ realitykit.md).
  - Patterns and logos go in **UV1**: two UV sets maximum on import (→ realitykit.md).
- **Metal finish:** swap the tint and roughness parameters (stainless / brass / rose-gold / black). Keep metallic = 1. Use the black finish (e.g. coated) as a dielectric with metallic 0 and roughness 0.4 [A].

### 12.6 Customisation slots summary [I]

| Item | Leather/primary colour | Fabric/secondary | Trim / piping / binding | Stitching | Metal finish | Pattern / decal |
|---|---|---|---|---|---|---|
| English saddle | ✓ (seat insert separate) | — | knee-roll colour | ✓ | ✓ | crest on cantle |
| Western saddle | ✓ + tooling style | seat colour | lacing | ✓ | conchos | tooling map |
| Saddle pad / numnah | — | ✓ | ✓ piping + binding | quilting thread | — | ✓ logo, number |
| Half-pad | — | fleece colour | ✓ | — | — | — |
| Bridle | ✓ | padding colour | browband style | ✓ | ✓ bit + buckles | crystal browband |
| Reins | ✓ | rubber grip colour | — | — | — | laced/plain |
| Halter + lead | webbing colour | lining | — | — | ✓ | rope two-tone |
| Brushing / bell boots | shell colour | lining / fleece | strap colour | — | — | logo |
| Polos / bandages | — | ✓ | tab colour | — | — | two-tone |
| Fly bonnet | — | crochet colour | cord / ear colour | — | crystals | embroidery |
| Braids / ribbons / bows / pompons / flowers / plume | — | yarn / ribbon / pompom / flower / feather colour | — | — | — | style variant |
| Stable rug / fly sheet / quarter sheet | — | outer colour | binding colour | — | hardware | ✓ check, tartan, stars, name |
| Breastplate | ✓ | elastic colour | padding | ✓ | ✓ | — |

**Matched "sets"** (Rival Stars-style themes) can be defined as presets over these slots.

---

## 13. Gaps and items to verify (not checked this session)
1. **Girth lengths for ponies:** no manufacturer chart was found, only forum figures. The ⅔-heart-girth rule is [A]. Check Shires, LeMieux or Kieffer size guides.
2. **Brushing-boot strap direction**, bell-boot fit rules (e.g. "just touches the ground"), and the bandaging direction (anticlockwise on left legs, clockwise on right legs). These are standard practice [A] and need a source (BHS or Pony Club manuals).
3. **Brass PBR base colour, and stainless steel specifically:** check on physicallybased.info. The UE values for iron and chromium are [V\*]; brass, gold and copper are from memory [A].
4. **FFE pony height categories** and French competition tack rules (FFE règlements). Not fetched.
5. **FEI rules:** the extracts came from the FEI dressage tack PDF result set. Read the current FEI Dressage Rules (2025/2026 edition) for exact wording on ear hoods, saddle pad colour and browbands.
6. **Pony saddle pad, quarter sheet, plume and pompom dimensions** beyond the cited products are [A].
7. **RealityKit LOD and cloth simulation availability** for an iOS 26 deployment target. They were shown at WWDC26; check each symbol's minimum OS in the docs.
8. **Shetland seat size** (12"–13") comes from product listings and a retailer blog, not a federation source.
