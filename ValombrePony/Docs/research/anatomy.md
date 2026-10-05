# Pony anatomy, conformation, range of motion and coat colours
## Reference report for the rigged RealityKit pony ("Les Héritiers de Valombre")

Date: 2026-10-05. Target: a procedural Blender 4.2 (bpy) mesh and rig exported to USDZ for RealityKit on iOS 26 / macOS 26.

---

## 0. How much of this is verified (read this first)

**Tool limits in this session.**
- **WebFetch was blocked for every domain I tried.** The egress proxy returned `EGRESS_BLOCKED` for frontiersin.org, ncbi.nlm.nih.gov, pmc.ncbi.nlm.nih.gov, europepmc.org, mdpi.com, en.wikipedia.org, vgl.ucdavis.edu and madbarn.com. I could not open any full-text paper.
- **WebSearch stopped after about 45 queries.** The session-wide cap of 200 searches is shared with sibling agents, and it was reached. The search for section 4 (coat colours) had not started yet.
- As a result, everything marked **[V]** below was checked only against the **search engine's extract** of the cited page (abstract or snippet). I did not read the full paper. Before you treat any number as final, check it against the original. The abstract-level numbers are generally reliable, but a number that comes from a summarised table may have been garbled.

**Labels used throughout**

| Tag | Meaning |
|---|---|
| **[V]** | Verified at snippet or abstract level against the URL given. |
| **[V-hist]** | Verified that the source says it, but the source is a historical artistic or veterinary canon, not measured data. |
| **[U]** | The source says it, but the attribution or the measurement convention is unclear, or it conflicts with another source. |
| **[I]** | Inferred or derived by me from verified numbers, for example ratios computed from published means. The derivation is shown. |
| **[A]** | Approximate or artistic estimate with no source. Calibrate it from reference photos. |
| **[NV]** | Standard textbook knowledge or my own knowledge that was **not verified in this session**. Candidate sources are listed so someone can verify them. |

---

## 1. Skeleton and joints for rigging

### 1.1 Vertebral formula
- **[V]** The horse has C7, T18, L6, S5 and Cd (coccygeal) 15–21. Sources: https://veterinaryanatomyguide.com/vertebral-formula-of-domestic-animals/ and https://vetstudyguides.com/horse-vertebral-column/ (this is the search result set; the extract stated C₇T₁₈L₆S₅Cy₁₅₋₂₁).
- **[NV]** Breed variation exists. Some Arabians have 17 thoracic and/or 5 lumbar vertebrae, and lumbar or sacral fusion is common. This is irrelevant for a game rig. *Verify in Getty/Sisson & Grossman, or Budras' "Anatomy of the Horse".*

### 1.2 Bones and joints relevant to the rig
**[NV]** The anatomy in this section is standard textbook material that I did not re-verify in this session. Candidate sources: WikiVet https://en.wikivet.net/Stay_Apparatus_-_Horse_Anatomy (the site itself was seen in search results), and the UMN open textbook "Large Animal Anatomy" https://open.lib.umn.edu/largeanimalanatomy/chapter/pelvic-limb/ (seen in search results).

| Region | Bones | Joint and common name | Rig notes |
|---|---|---|---|
| Head | skull, mandible | temporomandibular joint (jaw); atlanto-occipital joint (AO, "poll") | Jaw bone for chewing, bit and lip sync. The ears pivot on the scutiform cartilage: use 2 bones per ear plus rotation. |
| Neck | C1 (atlas), C2 (axis), C3–C7 | AO, atlanto-axial (AA), C2–C7 intervertebral joints, cervicothoracic joint (C7–T1) | **[NV]** The cervical column is S-shaped. It sits dorsally near the poll and drops ventrally, deep inside the base of the neck, at C6–C7. **Do not place neck bones along the crest.** |
| Thorax | T1–T18, ribs, sternum | thoracic intervertebral joints | The withers are the tall dorsal spinous processes of about T3–T8 (see 3.1 for the measurement definition). |
| Loins | L1–L6 | lumbar joints, lumbosacral joint (L6–S1) | **[V]** The lumbosacral joint is one of the main dorsoventral flexion sites (Townsend 1983, see 1.6). |
| Croup | sacrum (S1–S5 fused), pelvis (ilium, ischium, pubis) | sacroiliac (almost immobile) | The point of the hip is the tuber coxae, the point of the croup the tuber sacrale, and the point of the buttock the tuber ischiadicum. |
| Tail | Cd1–Cd15…21 | coccygeal joints | 6–10 rig bones are enough. Drive them with springs or dynamics. |
| Forelimb | scapula, humerus, radius (ulna reduced and fused), carpal bones (two rows plus accessory carpal), metacarpal III ("cannon") plus splint bones MC II/IV, P1, P2, P3, proximal sesamoids, navicular | **[NV]** No clavicle: the scapula is attached to the trunk by muscle only (synsarcosis), so it **slides and rotates on the thorax**. Then the shoulder (scapulohumeral), elbow, carpus ("knee") with antebrachiocarpal, middle carpal and carpometacarpal joints, fetlock (metacarpophalangeal, MCP), pastern (proximal interphalangeal, PIP) and coffin (distal interphalangeal, DIP) | Give the scapula its own bone, which translates and rotates over the ribcage. Consider 2 carpal bones; see 1.6, where the radiocarpal joint contributes most of the flexion. |
| Hindlimb | os coxae, femur, patella, tibia (fibula reduced), tarsal bones, metatarsal III plus splints, P1, P2, P3, sesamoids | hip (coxofemoral), stifle (femorotibial and femoropatellar, equivalent to the human knee), hock (tarsocrural is the main hinge; the distal tarsal joints are nearly rigid), fetlock (MTP), pastern, coffin | **Stifle and hock are mechanically coupled** (1.7). |

### 1.3 Classic proportions (normalised)

#### 1.3.1 The French veterinary canon, using head length as the unit [V-hist]
Source: "Normal Proportions of the Horse", https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10367726/. This is a reprint of a historical text describing the French school's canon (Bourgelat-style). It is an idealised artistic and veterinary canon, **not measured data**.

| Dimension | Heads | As a fraction of withers height (WH = 2.5 heads) [I] |
|---|---|---|
| Poll to ground (head up) | 3.0 | 1.20 |
| Withers to ground (WH) | 2.5 | 1.00 |
| Point of shoulder to point of buttock (body length) | 2.5 | 1.00 |
| Croup to ground | "2 38/100" (2.38) | 0.95 |
| Withers to lowest point of chest (chest depth) | 1.22 | 0.49 |
| Greatest breadth of belly | 1.0 | 0.40 |
| Depth from the lowest point of the back to the belly | 1.0 | 0.40 |
| Withers to stifle | 1.64 | 0.66 |
| Neck insertion at the withers to point of shoulder | 0.82 | 0.33 |
| Point of buttock to stifle; croup to stifle; stifle to hock; **hock to ground** | 0.82 each | 0.33 each |
| Head length | 1.0 | **0.40** |

- The same text describes Eclipse's head as "one-third instead of two-fifths of his height", which confirms that the canonical head length is 0.4 × WH [V-hist].

#### 1.3.2 Modern conformation guidance (extension and lay sources: rules of thumb, not measurements)
- **[V]** "Shoulder angle between 40 and 55 degrees". "The hoof-pastern axis should create an angle of about 45 to 50 degrees from the ground." The pastern angle should follow the shoulder angle. Source: University of Minnesota Extension, https://extension.umn.edu/horse-care-and-management/conformation-horse
- **[V]** Neck length is about 1.5 × head length, and head length (poll to upper lip) is about 2/3 of the neck topline. Height at withers is about equal to body length (point of shoulder to point of buttock). Leg length from elbow to fetlock is about equal to body depth from withers to girth. Source: EquiMed, a lay source, https://equimed.com/health-centers/lameness/articles/horse-conformation-head-neck-and-shoulders (via the search extract).
- **[U]** Measured scapular inclination depends on the convention used. Holmström et al. (1990) report a mean **scapula inclination of 65.3°** and a croup angle of 29.9° in Swedish Warmblood dressage horses (cited in https://aab.copernicus.org/articles/56/367/2013/aab-56-367-2013.pdf; original https://beva.onlinelibrary.wiley.com/doi/abs/10.1111/j.2042-3306.1990.tb04245.x). The "45–50°" folk figure and the UMN "40–55°" figure use a different reference line, so **the conventions differ**. For the rig, set the scapular spine at roughly 55–65° from horizontal [I] and check it against photos.

#### 1.3.3 Measured body indices of small "primitive" breeds of pony size (best available proxies)
No full-text morphometric study of Welsh B or Connemara ponies was reachable. The proxies below are breeds of similar size.

| Breed (n) | WH cm | Body length | Heart girth | Cannon circ. | Chest depth | Chest width | Source |
|---|---|---|---|---|---|---|---|
| Polish Konik mares (n = 284) | 135.0 ± 2.7 | n/a | 172.7 ± 6.8 | 17.56 ± 0.61 | n/a | n/a | **[V]** https://www.researchgate.net/publication/312072337 (Morphometric changes in Polish Konik mares) |
| Polish Konik (in Bulgaria) | 136.0 ± 1.3 | 149.0 ± 1.8 | n/a | n/a | 62.25 ± 0.85 | n/a | **[U]** search extract; attribution unclear (Bulgarian study) |
| Karakachan (n = 52), dataset 1 | 130.2 ± 0.8 | 140.6 ± 1.3 | 157.5 ± 1.5 | 17.67 ± 0.14 | n/a | n/a | **[V]** https://www.researchgate.net/publication/337547923 and https://www.researchgate.net/publication/324889624 |
| Karakachan, dataset 2 | "height at back" 126.1; croup 125.3 | 129.1 ± 3.9 | 143.3 ± 5.4 | 15.62 ± 1.05 | 59.3 ± 2.7 | 34.8 ± 3.7 | **[V]** same sources |
| Karakachan indices | body extension 108%, chest index 59.1%, massiveness 121%, compactness 112%, **leg length 54.2%**, body ratio 100.7%, **bone 13.56%** | | | | | | **[V]** same |
| Icelandic (n = 16) | 138 ± 4 | 145 ± 3 | n/a | measured, value not retrieved | breast depth 66 ± 2 | measured, value not retrieved | **[V]** https://pmc.ncbi.nlm.nih.gov/articles/PMC12180175 (Acta Vet Scand 2025); back length 77 ± 3 cm |

**Ratios to withers height derived from the table [I]**
- Body length / WH: 1.08 (Karakachan), 1.10 (Konik-BG), 1.05 (Icelandic). Use **1.05–1.10**.
- Heart girth / WH: 1.21 (Karakachan), 1.28 (Konik). Use **1.20–1.28**.
- Cannon circumference / WH: 0.130 (Konik), 0.136 (Karakachan). Use **0.13–0.136**.
- Chest depth / WH: 0.46 (Konik-BG), 0.48 (Icelandic); the Karakachan "leg length 54%" index implies 0.46. Use **0.46–0.48**. Ponies therefore have **slightly shallower chests than the 0.49 canon**, and their legs are about 52–54% of WH.
- Croup height / WH is about 1.0. The Karakachan body-ratio index is 100.7%. Ponies are often level or slightly croup-high.
- Chest width / chest depth is about 0.59 (Karakachan), so chest width / WH is about 0.27.

#### 1.3.4 Limb segment lengths (horse, measured externally) [V]
Jumping Thoroughbreds (WH about 166–168 cm): shoulder 69 ± 5, arm 34 ± 2.9, forearm 46 ± 2.4, fore cannon 28.7 ± 2.3, pelvis 51.4 ± 5.1, thigh 49.7 ± 5.1, gaskin 53.1 ± 4.8, hind cannon 37.4 ± 3.7 cm. Source: https://scialert.net/fulltext/?doi=ajas.2015.208.216
- **[I]** As fractions of WH (167): shoulder 0.41, arm 0.20, forearm 0.28, fore cannon 0.17, pelvis 0.31, thigh 0.30, gaskin 0.32, hind cannon 0.22. Landmark definitions were not visible, so the hind cannon was probably measured from the point of the hock.
- **[V]** Ponies and Koniks differ from horses. Koniks have longer scapulae and metacarpi than Huculs at a similar height (Komosa & Purzyc 2009, https://www.researchgate.net/publication/24241985). The Connemara standard asks for "short cannons, flat bone 18–21 cm" circumference (https://acps.org/inspections-criteria/). The Shetland standard asks for a "short balanced cannon bone" (https://www.shetlandponystudbooksociety.co.uk/about-the-breed/breed-standard/).

### 1.4 Starting template for joint-centre heights (fraction of WH, standing square) [I]
**Every value in this table is inferred.** I could not find a published table of joint-centre heights for ponies. The values combine the canon (1.3.1), the pony indices (1.3.3) and the segment ratios (1.3.4). Calibrate them against orthogonal side-view photos of a real Welsh B or Connemara standing square, with a scale bar.

| Joint centre (not the bony point) | Welsh B / Connemara template, WH = 1.30 m | Shetland template, WH = 1.00 m | Reasoning |
|---|---|---|---|
| Coffin joint (DIP) | 0.035 | 0.04 | Inside the hoof, just below the coronet. Pony hooves are relatively larger (see 2.4). |
| Pastern joint (PIP) | 0.06 | 0.065 | |
| Fore fetlock (MCP) | 0.10–0.11 | 0.10–0.11 | Short pastern and short cannon. |
| Carpus (radiocarpal) | 0.26–0.28 | 0.24–0.26 | Horse value is about 0.29 (fetlock 0.12 + cannon 0.17). Ponies have shorter cannons, and Shetlands shorter still. |
| Elbow joint | 0.52–0.55 | 0.48–0.51 | Below the 0.52–0.54 "leg length" level, because the olecranon projects above the joint. Shetlands have a deeper body and shorter legs. |
| Shoulder joint (point of shoulder) | 0.64–0.68 | 0.60–0.65 | Elbow plus the humerus (about 0.2 WH) set at about 50–60° from horizontal. |
| Top of scapula (cartilage) | 0.93–0.97 | 0.93–0.97 | |
| Withers (top of T4–T6 spines) | 1.00 | 1.00 | By definition. |
| Vertebral bodies at the withers (T4–T6) | 0.78–0.82 | 0.78–0.82 | The tall spinous processes at the withers sit above them. |
| Thoracolumbar vertebral bodies (mid-back) | 0.85–0.90 | 0.85–0.90 | The spinous processes are short behind about T15. |
| C7–T1 (base of neck) | 0.62–0.68, cranial to the scapula | same | **[NV]** The neck base is low and deep, at about the level of the point of shoulder. |
| Atlanto-occipital (poll) at rest | 1.05–1.20 | 1.00–1.15 | Depends on head carriage. The canon puts the poll at 1.20. |
| Hip joint (coxofemoral) | 0.70–0.75 | 0.68–0.73 | Well below the croup and level with the "point of the buttock" region. |
| Tuber coxae (point of hip) | 0.85–0.90 | 0.85–0.90 | |
| Croup (tuber sacrale) | 0.98–1.02 | 0.98–1.03 | Pony indices show croup ≈ WH. |
| Stifle joint | 0.58–0.63 | 0.55–0.60 | Canon: withers to stifle is 1.64 heads, giving about 0.34 below the withers line, or about 0.62 [I]. |
| Hock (tarsocrural) joint | 0.30–0.34 | 0.28–0.32 | Canon: hock to ground is 0.82 heads, or 0.33. |
| Point of hock (calcaneal tuber) | 0.36–0.40 | 0.34–0.37 | |
| Hind fetlock (MTP) | 0.11–0.12 | 0.11–0.12 | |

Horizontal (cranio-caudal) positions [I]: the point of shoulder is about 0.0 and the point of buttock is about +1.05–1.10 WH. The elbow joint sits about 0.10–0.15 WH caudal to the point of shoulder. The hip joint sits about 0.25 WH cranial to the point of buttock. The stifle lies about vertically below the tuber coxae.

### 1.5 Standing joint angles (bind pose reference) [V]
Jumping Thoroughbreds, lateral view: shoulder 99 ± 3.7°, elbow 138.4 ± 4.7°, carpus 177.7 ± 2.3°, fore fetlock 142.7 ± 6°; "croup" (hip) 144.6 ± 4.8°, stifle 114.9 ± 13°, hock 148.6 ± 5.3°, hind fetlock 149.8 ± 8°. Source: https://scialert.net/fulltext/?doi=ajas.2015.208.216
- **[V]** In 356 Warmbloods the dorsal MCP (fetlock) angle at stance was 136–168° (Holmström et al. 1990, as cited in https://www.researchgate.net/publication/273493548).
- **[I]** For the rig, model the bind pose standing square with these angles, not as a T-pose. The carpus is almost straight at about 178°. The fetlock is hyperextended, meaning dorsiflexed, by about 35–40°.

### 1.6 Range of motion (ROM)

**Angle conventions differ between papers.** "Joint angle" in goniometry usually means the included angle, where 180° is straight. "ROM" is the excursion. Fetlock angles are sometimes given on the palmar side, where more than 180° means hyperextension.

#### Distal forelimb
| Joint | Value | Context | Tag and source |
|---|---|---|---|
| Carpus, passive | flexion **20 ± 1°**, extension **170 ± 2°**, ROM **150 ± 2°** | 17 sedated horses, validated against radiographs | **[V]** Adair et al. 2016, VCOT 29:314; https://pubmed.ncbi.nlm.nih.gov/27124214/ |
| Carpus, passive | flexion 26 ± 10° (universal goniometer) vs 40 ± 12° (digital goniometer) | the two devices are not interchangeable | **[V]** https://doi.org/10.3390/ani10122436 |
| Fetlock, passive flexion | 116 ± 12° (universal) vs 106 ± 8° (digital) | convention unclear (probably the included dorsal angle) | **[V]/[U]** same source |
| Radiocarpal vs midcarpal | radiocarpal about 90–100° sliding and rolling; midcarpal hinge about 45° | | **[U]** search extract; source page not pinpointed |
| Fetlock (MCP), 3D | flexion/extension ROM 62 ± 7° (walk), 77 ± 5° (trot); add/abduction 13 ± 7 / 18 ± 7°; axial rotation 6 ± 3 / 9 ± 5° | in vivo | **[V]** https://pubmed.ncbi.nlm.nih.gov/17546207/ |
| Fetlock, palmar angle | 218° walk, 226° trot, **240° gallop**, i.e. up to about 60° of hyperextension past straight | | **[V]** https://www.researchgate.net/publication/273493548 |
| Coffin (DIP) | flexion/extension 46 ± 3° (walk), 47 ± 4° (trot) | | **[V]** https://www.researchgate.net/publication/6443307 |
| Swimming | carpus 99 ± 10°, front fetlock 68 ± 12°, stifle 68 ± 7°, tarsus 99 ± 6° | | **[V]** https://www.mdpi.com/1424-8220/23/21/8832 |
| Walk vs trot | every joint's ROM is larger at trot; the increase at elbow, carpus, stifle and tarsus comes from greater swing-phase flexion | | **[V]** Back et al. 1996, https://www.tandfonline.com/doi/pdf/10.1080/01652176.1996.9694699; Back 1995 fore/hind: https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.1995.tb03029.x and https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.1995.tb03030.x (numeric tables not retrieved) |

#### Proximal limb and hindlimb
| Joint | Value | Tag and source |
|---|---|---|
| Stifle at walk | about 35° flexion/extension, from 126.9° to 162° | **[U]** search extract from hindlimb walking studies, e.g. https://pubmed.ncbi.nlm.nih.gov/11191608/; exact attribution not pinpointed |
| Tarsus at walk | ROM 23–30° in one study, 35.6–37.6° in another | **[U]** same |
| Hip at walk | ROM between about 10° and 33°; hip flexion/extension drives protraction and retraction, and the motion is pendular about the acetabulum | **[U]/[V]** same; https://www.tandfonline.com/doi/pdf/10.1080/01652176.1996.9694699 |
| Shoulder and elbow, passive | **[NF]** No equine passive ROM found. The values that came up (shoulder 88–144°, elbow 34–145°) were from a **dog** study (VCOT Open 2020, 10.1055/s-0040-1713825) and **must not be used**. | — |

#### Neck, head, back
| Segment | Value | Tag and source |
|---|---|---|
| Whole cervical spine, ex vivo | lateral bending about 25–45° **per joint** except C1–C2 (mean 3.9°); dorsoventral flexion/extension is greatest at **AO: 86.4°, 32% of total** cervical DV motion (so the total is about 270° [I]) | **[V]** Clayton & Townsend 1989, EVJ 21:189; https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.2042-3306.1989.tb02139.x |
| Neck lateral bending at walk | 40% of cervical lateral bending occurs at C7–T1 | **[V]** Zsoldos et al. 2010, https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.2010.00265.x |
| In vivo, walk | most motion in the cranial neck (C1/2–C4/5); least at C5/6; flexion/extension and lateral bending peak at C4/C5 | **[V]** same (extract) |
| Mobilisation exercises (chin to girth, hip, tarsus) | largest intersegmental angle changes at C6; lateral bending also increases from T6 to S2 | **[V]** Clayton et al. 2012, AJVR; https://pubmed.ncbi.nlm.nih.gov/22849675/ |
| AO / AA details | AO about 10° flexion, 15° extension, 8–10° lateral per side; AA about 25–30° rotation per side; AA axial rotation at walk 7 ± 2° | **[U]** search extract attributed vaguely to "2024 research". The first two figures conflict with the 86.4° ex vivo AO amplitude, so **treat them as unreliable**. |
| Thoracolumbar at walk | flexion/extension about 7° per segment caudal to T10; lateral bending up to 5.6° (cranial thoracic and pelvic regions) | **[V]** Faber et al. 2000, https://pubmed.ncbi.nlm.nih.gov/10772104/ |
| Thoracolumbar, ex vivo | greatest dorsoventral motion at the lumbosacral and first thoracic joints; greatest axial rotation and lateral bending at T11–T12 | **[V]** Townsend et al. 1983, https://pubmed.ncbi.nlm.nih.gov/6873044/ |
| Tail | **[NF]** no ROM data found | — |

#### Recommended rig limits for a game [I]
These are design values. They extrapolate from the data above so the pony can rear, roll and buck while staying anatomical.

| Joint | Flexion | Extension / hyperextension | Other axes |
|---|---|---|---|
| Carpus | up to 150° from straight (Adair ROM) | 0–5° | ±3° varus/valgus |
| Fore fetlock | about 100–110° of flexion from the bind pose (hoof can touch the forearm in a tight tuck) | up to 60° dorsiflexion past straight (gallop) | ±9° abduction, ±5° rotation |
| Coffin + pastern | combined about 50° | about 15° | |
| Elbow | about 60–70° beyond the bind pose (to about 70° included angle) | about 10° | |
| Shoulder | about 40° | about 20° | small abduction (no clavicle) |
| Scapula | rotation ±15°; slide ±0.05 WH | | |
| Hip | about 40° | about 25° | ±10° abduction |
| Stifle → hock | **coupled** (1.7) | | |
| Neck | per segment: lateral 25–30° (C2–C7), C7–T1 up to about 18–20° (see Zsoldos above) | | AO: about 85° flexion/extension in total; AA: rotation (value uncertain) |
| Thoracolumbar | about 5–7° per rig bone | | lateral 5°, rotation 5° |

### 1.7 Mechanical couplings the rig must reproduce
- **[V] Reciprocal apparatus.** On the cranial side is the peroneus (fibularis) tertius, and on the caudal side the superficial digital flexor with the gastrocnemius. This "causes the stifle, hock and fetlock to flex in unison"; "you cannot bend one without bending the other". Sources: https://open.lib.umn.edu/largeanimalanatomy/chapter/pelvic-limb/, https://en.wikivet.net/Stay_Apparatus_-_Horse_Anatomy, https://www.merckvetmanual.com/musculoskeletal-system/tendon-and-ligament-disorders-in-horses/rupture-of-the-peroneus-tertius-in-horses (rupture lets the hock extend while the stifle is flexed, which demonstrates the coupling).
  - **[I] Rig recommendation:** drive the hock angle with a driver or constraint from the stifle angle, for example Δhock ≈ k·Δstifle with k ≈ 1. Calibrate k from video. Bake the result into the animation, because RealityKit does not evaluate Blender drivers on export.
- **[V] Stay apparatus and patellar locking.** The patella hooks over the medial femoral trochlear ridge so the horse can doze standing. Source: WikiVet as above, and https://madbarn.com/locking-stifle-in-horses/ (title seen only). Use this for the idle "resting one hind leg" pose: one hip dropped, that hind hoof tipped onto its toe, the opposite stifle locked.
- **[NV] Distal coupling.** The coffin and pastern joints flex together with the fetlock through the deep digital flexor and the suspensory apparatus. Use a single "digit curl" control that drives P1, P2 and P3.

---

## 2. Surface anatomy and modelling landmarks

### 2.1 Landmark checklist [NV]
This list is my anatomical knowledge, not verified in this session. Candidate source: WikiVet horse anatomy pages, https://en.wikivet.net.
- **Head:** facial crest (zygomatic ridge), the large flat **masseter** cheek, the TMJ, the infraorbital region, the nasal bone, the **nostrils** (the alar cartilage forms a C-shape and there is a dorsal "false nostril" pocket, so the nostrils flare when blowing), upper and lower lips with tactile vibrissae, the chin, the intermandibular space ("jowl"), the poll, the forelock base and the orbital rim (supraorbital fossa above the eye, which hollows with age).
- **Neck:** crest (nuchal ligament and fat, cresty in stallions; **[V]** the Welsh B standard describes the neck as "inclined to be cresty in the case of mature stallions", https://www.wpcs.uk.com/welsh-pony-1), jugular groove, brachiocephalicus, splenius.
- **Trunk:** withers, back, loins, the croup and tail head, the point of hip, point of buttock, ribs (visible at a thin body condition), the girth groove, belly, the **flank** (paralumbar fossa) and stifle fold, and the sheath or udder.
- **Forelimb:** shoulder (supraspinatus, infraspinatus, deltoid), point of shoulder, **triceps** mass behind the arm, pectorals (the "V" between the forelegs), forearm extensor and flexor bellies, the flat bony knee with the accessory carpal bone protruding behind it, cannon tendons, fetlock, pastern, coronet and hoof.
- **Hindlimb:** gluteals (round croup), tensor fasciae latae, **hamstrings** (biceps femoris and semitendinosus "pants"), the gaskin (gastrocnemius belly), the calcaneal tendon, the point of hock, the hind cannon and the fetlock.

### 2.2 Chestnuts and ergots [V]
- Chestnuts on the **forelimb are above the knee** (medial side) and on the **hindlimb below the hock**. Ergots are on the back (palmar or plantar side) of the fetlock and are smaller than chestnuts. Both are keratinous, and are thought to be vestigial pads or digits. **Icelandic horses, donkeys and zebras typically have chestnuts on the front limbs only.** Sources: https://www.petmd.com/horse/chestnuts-and-ergots-horses, https://ker.com/equinews/chestnut-not-just-coat-color/, https://en.wikipedia.org/wiki/Chestnut_(horse_anatomy)
- **[I]** Model them as separate small meshes or decals using a dark grey-brown horn material.

### 2.3 Eyes [V unless tagged]
| Group | Axial globe length | Source |
|---|---|---|
| Adult horses | 40.52 ± 2.67 mm (correlated with body weight, height and age) | https://avmajournals.avma.org/view/journals/ajvr/71/6/ajvr.71.6.677.xml (AJVR 2010) |
| Miniature Horses | 39.23 ± 1.26 mm | https://pubmed.ncbi.nlm.nih.gov/12828248/ |
| "Pony" group | 38.85 ± 3.13 mm | **[U]** search extract; probably Laus et al. 2014 Vet Rec short communication, https://static1.squarespace.com/static/52f6e70ae4b09d0c250122c6/t/53446a3de4b0c080fcf969a6/1753373795788/Veterinary+Record-2014-Laus-326.pdf |
| **Shetland ponies** | **37.21 ± 1.50 mm** | **[U]** same |
| CT of cadaver eyes | axial 50.9 ± 1.7 mm; globe height 51.9 mm > width 42.8 mm (oval globe) | **[U]** https://pmc.ncbi.nlm.nih.gov/articles/PMC12607728/ — the axial value conflicts with the ultrasound values (likely a CT or definition difference) |

- **[I] Consequence for modelling.** The eye barely shrinks with body size: 37 mm in a 1.0 m Shetland against 40.5 mm in a 1.6 m horse. **Relative to the head, pony eyes are larger.** Heck et al. (2019, PeerJ, https://peerj.com/articles/7678/) **[V]** tested paedomorphic traits such as "large eyes, large braincase-to-face relationship, and large head-to-body relationship". They found that ponies reach a horse-like skull shape at an older age, and that Falabella and Shetland ponies have "particularly large crania relative to withers height". Add a "relative eye size" slider, but keep it anatomical.
- **[NV]** The eyes are lateral, so the field of view is wide. The visible palpebral opening is much smaller than the globe. The horizontal pupil is a dark brown, horizontally elongated oval with corpora nigra (granula iridica) on the upper margin. **[NF]** I found no measurements of the palpebral fissure.
- **[V] Breed standards.** Shetland: "bold, dark, intelligent eyes" on a broad forehead (https://www.shetlandponystudbooksociety.co.uk/about-the-breed/breed-standard/). Welsh B: "eyes bold" (https://www.wpcs.uk.com/welsh-pony-1).

### 2.4 Ears, muzzle, hooves
- **[V] Ears.** Shetland: "small and erect, wide set but pointing well forward". Welsh B: "small and pointed, well up on the head, proportionately close". Sources: the SPSBS and WPCS URLs above. **[NF]** I found no published pinna-length data (the only number found was a bridle-fitting method).
- **[V] Muzzle.** Shetland: "broad with nostrils wide and open". Welsh B head: "small, clean-cut… tapering to the muzzle".
- **[V] Pony hooves.** A radiographic study of 81 ponies (WH 81.5–148 cm) found that linear hoof measures correlate strongly with WH while angles correlate weakly. **Pony hooves are relatively larger than Warmblood hooves for their height.** Source: https://www.sciencedirect.com/science/article/abs/pii/S1090023315004025. The same extract states that the front feet were "more upright than the hind". **[U]** This contradicts the usual horse rule that hind feet are steeper, so verify it.
- **[V] Dorsal hoof wall angle (horses).** Front about 45–55°, hind about 50–58° (warmbloods). The modern view is that the hoof-pastern axis should be straight, not a fixed number. Sources: https://horse-canada.com/magazine/hoof-care/assessing-hoof-angles/ (lay source). One study suggests an aligned hoof-pastern axis with a dorsal hoof wall angle of about 50°: https://pmc.ncbi.nlm.nih.gov/articles/PMC11444133/
- **[A] Hoof width (front, at the ground).** About 10–12 cm for a 1.30 m pony and about 7.5–9 cm for a 1.0 m Shetland. These are not sourced; measure them from reference photos.

### 2.5 Mane, forelock, tail and feathering
- **[V] Shetland.** "At all times the mane and tail hair should be long, straight and profuse." In winter there is a double coat with guard hairs, and in summer a short, silky coat (https://www.shetlandponystudbooksociety.co.uk/about-the-breed/breed-standard/).
- **[A] Lengths.** Natural, unpulled lengths:

| Breed | Mane | Forelock | Tail |
|---|---|---|---|
| Welsh B / Connemara | 20–40 cm | 20–30 cm | dock to at least hock level, often 70–90 cm of hair |
| Shetland | 30–50 cm and very dense, can cover both sides of the neck | to the nostrils | often reaches the ground |

- **[NV] Feathering.** Shetlands have fetlock hair and a heavier winter coat on the legs but are not heavily feathered like Fell, Dales or Clydesdale horses. Welsh B and Connemara have fine legs with little feather. *Verify with photos and breed standards.*
- **[I] Implementation.** Use cards or strands for the mane and tail, and a winter-coat "fluff" shell or fins toggled by season. RealityKit has no built-in groom system, so plan for hair cards (see the realitykit.md report).

---

## 3. Measurements for the two target ponies

### 3.1 Measurement definitions [V]
- **Height at withers:** "the highest point of the spinous processes of thoracic vertebrae 3–8" (interscapular region).
- **Heart girth:** around the chest "between the 5th rib at the elbow and the spinous processes of T11–13".
- **Cannon circumference:** midway along the cannon, or at its thinnest point.
- **Body length:** from the point of shoulder (intermediate tubercle of the humerus) to the point of buttock (ischial tuberosity).

Sources: search extracts of https://www.researchgate.net/figure/Morphometric-measurements-centimetres-made-for-each-recruited-horse-adapted-from_fig2_263738943 and https://www.frontiersin.org/journals/veterinary-science/articles/10.3389/fvets.2024.1332207/full

### 3.2 Breed frames [V]
| Breed | Height | Source |
|---|---|---|
| Shetland (SPSBS) | **must not exceed 42 in (107 cm)**; typical 90–110 cm and 100–300 kg | standard: https://www.shetlandponystudbooksociety.co.uk/about-the-breed/breed-standard/; typical range from a lay source: https://madbarn.com/shetland-pony-breed-profile/ |
| Shetland study | median body weight **136.9 kg** (n = 19 Shetlands) | https://pubmed.ncbi.nlm.nih.gov/41624284/ |
| Welsh section B | **≤ 13.2 hh (137.2 cm)**; most are 12.2–13.2 hh | https://www.wpcs.uk.com/welsh-pony-1 (extract) |
| Welsh section A | ≤ 122 cm (extract) | |
| Welsh section D | 137–155 cm (extract) | |
| Connemara | **128–148 cm**; cannon **18–21 cm** | https://acps.org/inspections-criteria/, https://www.britishconnemaras.co.uk/breeding-owning/about-the-breed/ |
| Konik standard | 130–140 cm | Konik search extract (1.3.3) |

- **[V] Avoid chondrodysplastic features.** ACAN dwarfism (the D3* allele occurs in Shetlands) produces short limbs and neck, bowed forelegs, a compressed face, bulging eyes and an underbite. This is a **disease phenotype, not normal Shetland conformation.** Sources: https://www.nature.com/articles/s41598-020-72192-3 and https://pubmed.ncbi.nlm.nih.gov/27942904/. Normal small Shetland size is partly explained by an HMGA2 variant, i.e. proportionate small size (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4608717/, title only).

### 3.3 Target measurement sheet
"WH ×" means a ratio applied to withers height. Values for the 1.30 m pony come from the proxy ratios in 1.3.3. **The Shetland column is mostly inferred** (no full-text Shetland morphometric study was accessible).

| Measure | 1.30 m pony (Welsh B / Connemara type) | Tag | 1.00 m Shetland | Tag |
|---|---|---|---|---|
| Croup height | 128–132 cm (WH × 0.98–1.02) | [I] from Karakachan index | 99–103 cm | [I] |
| Body length (point of shoulder to buttock) | 137–143 cm (×1.05–1.10) | [I] from Konik/Karakachan/Icelandic | 105–115 cm (×1.05–1.15) | [I] |
| Heart girth | 157–166 cm (×1.21–1.28) | [I] same | 120–135 cm (×1.20–1.35) | [I]; see the cross-check below |
| Cannon circumference (fore) | 17–18 cm (×0.13–0.136); breed standard 18–21 cm for Connemara | [I] / [V] | 13–14.5 cm | [I] |
| Chest depth (withers to sternum) | 60–62 cm (×0.46–0.48) | [I] | 48–52 cm (×0.48–0.52; deeper body) | [I]; "deeper body" is your premise and is consistent with "short but strong limbs" (lay source), not measured |
| Chest width (between the points of shoulder) | 34–36 cm (×0.27) | [I] from Karakachan 34.8 cm | 28–32 cm | [I] |
| Head length (poll to upper lip) | 49–54 cm (×0.38–0.42; canon 0.40) | [I] | 42–46 cm (×0.42–0.46) | [I] from Heck 2019 "large crania relative to WH" |
| Neck length (poll to withers, topline) | 60–75 cm | [A] | 45–55 cm | [A] |
| Back length | about 72 cm (×0.56, Icelandic 77/138) | [I] (definition unknown) | about 55 cm | [A] |
| Ear length (pinna, base to tip) | 12–15 cm | [A] no source | 8–11 cm ("small") | [A] |
| Eye, axial globe length | about 38.9 mm ("pony") | [U] | **37.2 ± 1.5 mm** | [U] |
| Visible eye opening (horizontal) | about 35–45 mm | [A] | about 32–40 mm | [A] |
| Front hoof width | 10–12 cm | [A] | 7.5–9 cm | [A] |
| Body mass (for physics) | about 250–330 kg | [A] (Konik and Icelandic are 330–390 kg at 135–140 cm; Icelandic 386 ± 32 kg is [V]) | about 137 kg (median) | [V] |

**Cross-check of the Shetland numbers [I].** The weight formula weight ≈ girth² × length / 11 900 (cm, kg) is from memory (Carroll & Huntington 1988, EVJ 20:41) **[NV]**. With girth 125 cm and length 105 cm it gives about 138 kg, which matches the 136.9 kg median. So a girth of about 125 cm and a length of about 105 cm are self-consistent for a 1.0 m Shetland.

---

## 4. Coat colour system

**Status: [NV] for this whole section.** The search budget ran out before this section could be researched, so none of it was verified this session. It is written from my knowledge of the primary literature. The primary references are listed with full citations. **DOIs are from memory: verify them before publishing.** Candidate secondary sources (not fetched): UC Davis VGL horse coat colour pages (https://vgl.ucdavis.edu/, test pages such as https://vgl.ucdavis.edu/test/cream; the domain exists but was blocked here) and the IFCE French nomenclature ("robes", "signalement") on https://equipedia.ifce.fr/.

### 4.1 Genotype → phenotype layering (recommended shader architecture) [I]
1. **Base pigment.** Extension (MC1R): `E/_` allows black pigment; `e/e` gives red only, i.e. chestnut. Agouti (ASIP): `A/_` restricts black to the points (bay); `a/a` gives black.
   - Primary refs [NV]: Marklund et al. 1996, *Mammalian Genome* 7:895 (MC1R chestnut); Rieder et al. 2001, *Mammalian Genome* 12:450 (ASIP).
2. **Dilutions**, which can stack:
   - Cream (SLC45A2): `Cr/n`, `Cr/Cr`. Mariat et al. 2003, *Genet Sel Evol* 35:119.
   - Pearl, an allele of the same gene. *[NV, verify]*
   - Dun (TBX3): wild-type dun dilutes and adds primitive markings. Imsland et al. 2016, *Nat Genet* 48:152, doi:10.1038/ng.3475.
   - Silver (PMEL17): dilutes **black pigment only**. Brunberg et al. 2006, *BMC Genet* 7:46.
   - Champagne (SLC36A1). Cook et al. 2008, *PLoS Genet* 4:e1000195.
   - **Mushroom (MFSD12, Shetland-specific; dilutes chestnut).** Tanaka et al. 2019, *Genes* 10:826. *[NV, verify]*
3. **Modifiers** (genes unknown or polygenic): sooty (dark overlay on the topline), pangaré / mealy (pale muzzle, eyes, belly, flanks, inner legs), flaxen (pale mane and tail on chestnut), dapples (seasonal and condition-dependent).
4. **White and depigmentation overlays:**
   - Grey (STX17 duplication), progressive with age. Pielberg et al. 2008, *Nat Genet* 40:1004.
   - Roan (KIT region), stable through life. Marklund et al. 1999; Voß et al. 2020, *Genes* 11:680. *[verify]*
   - Tobiano (KIT inversion). Brooks et al. 2007, *Cytogenet Genome Res* 119:225.
   - Frame overo (EDNRB; homozygotes have lethal white foal syndrome). Metallinos, Santschi and Yang, all 1998, *Mammalian Genome*.
   - Sabino-1 (KIT). Brooks & Bailey 2005, *Mammalian Genome* 16:893.
   - Splashed white (MITF/PAX3). Hauswirth et al. 2012, *PLoS Genet* 8:e1002653.
   - Dominant white (KIT, W alleles). Haase et al. 2007, *PLoS Genet* 3:e195.
   - Leopard complex (TRPM1 "LP" plus PATN1 / RFWD3). Bellone et al. 2013, *PLoS ONE* 8:e78280; Holl et al. 2016, *Anim Genet* 47:91.
5. **Markings** (face and legs), as decal masks.
6. **Derived outputs:**
   - Skin colour: pink under any white hair; dark elsewhere; mottled with LP or champagne.
   - Hoof colour: follows the coronet skin.
   - Eye colour: comes from the genotype and from whether a white pattern covers the eye.

**[I] Implementation in RealityKit.** Compute the final albedo in a ShaderGraph (MaterialX) material. Use a few RGBA mask textures in UV space:
- mask 1: points / pangaré / sooty / dorsal stripe
- mask 2: tobiano / frame / sabino / splash
- mask 3: LP spots
- mask 4: face and leg markings

Add a procedural noise for roan and grey flecks, and pass parameters for the genotype, the grey age (0–1) and the season. Author the colours below in **sRGB** and convert them to linear before lighting.

### 4.2 Colour table with French UI names
**All hex values are [A]: artistic approximations** with no published spectrophotometric source. Calibrate them from photographs taken with a colour checker, then convert to linear for PBR.

| UI (FR) | English | Genotype (simplified) | Body hex range [A] | Mane, tail, legs | Skin / eyes / notes [NV] |
|---|---|---|---|---|---|
| Alezan (clair / foncé / brûlé) | Chestnut (light / dark / liver) | e/e | #C8843F → #9A4E1F → #5A2E1A | same as body, or **crins lavés** (flaxen) #E6D3A8 | dark skin, brown eyes |
| Bai (clair / cerise / brun) | Bay (light / blood / dark) | E/_ A/_ | #B06A32 → #8B4A22 → #3D2216 | **black points** #17120F on mane, tail, lower legs and ear rims | |
| Noir | Black | E/_ a/a | #1A1716 → #0E0D0D (sun-faded #3A2A20) | black | |
| Palomino | Palomino | e/e Cr/n | #E3C27A → #C99A4A | mane and tail #F2EBDD | brown eyes, dark skin |
| Isabelle | Buckskin | E/_ A/_ Cr/n | #D8B47E → #B48A4E | black points | |
| "Smoky black" (FR UI term to verify; descriptive option: "noir porteur crème") | Smoky black | E/_ a/a Cr/n | #2A221D → #3B2E26 | black | often indistinguishable from black |
| Crème (cremello) | Cremello | e/e Cr/Cr | #F2E8D4 → #E6D6B8 | same | **pink skin, blue eyes** #8FB7D8 |
| Crème (perlino) | Perlino | E/_ A/_ Cr/Cr | #EFE3CC → #E2CFAE | points slightly darker, rusty #D2B48C | pink skin, blue eyes |
| Crème (smoky cream) | Smoky cream | E/_ a/a Cr/Cr | #E8D8C0 | similar | pink skin, blue eyes |
| Souris | Grullo / mouse dun | E/_ a/a D/_ | #8A8178 → #6B645E | black; **dorsal stripe, leg barring, shoulder bar** | dark skin |
| Bai dun / isabelle dun | Bay dun | E/_ A/_ D/_ | #C9A877 → #B08E5E | black points and primitive markings | |
| Alezan dun (dun rouge) | Red dun | e/e D/_ | #D9A577 → #C08455 | red-brown points; dorsal stripe #9A5A2E | |
| Silver (noir silver / "chocolat") | Silver dapple on black | E/_ a/a Z/_ | #4A3B33 → #6E5F57, often dappled | mane and tail #E8DCCB → #C9BBA8 | silver does not show on chestnut |
| Bai silver | Silver bay | E/_ A/_ Z/_ | bay body, slightly lighter | lower legs chocolate; mane and tail flaxen | |
| Champagne (doré / ambré / classique) | Gold / amber / classic champagne | e/e or E/_ A/_ or E/_ a/a, plus Ch/_ | #D8B37A / #C8A270 / #9C8A7A | gold mane flaxen; amber points chocolate | **freckled pink skin, amber/hazel eyes** #B07A2A |
| Champignon / "mushroom" | Mushroom (Shetland) | e/e plus mushroom | #A89A82 → #B8A890 | similar or flaxen | Shetland-specific [verify] |
| Gris (fer / pommelé / truité / blanc) | Grey (iron / dapple / fleabitten / white) | G/_ + age t | t ≈ 0: base colour → #7A7A78 → dapple #B8B8B5 with #7E7E7C rings → #ECEBE6; fleabitten flecks #8B5A3C | mane and tail grey sooner | **skin stays dark**; brown eyes; foals are born coloured |
| Rouan / aubère / rouan noir | Bay roan / red ("strawberry") roan / blue roan | Rn/_ | white hairs over the body: bay roan #9C7468, red roan #B08070, blue roan #6F7480 | **head and lower legs stay solid**; mane and tail solid | colour does not progress with age |
| Pie tobiano | Tobiano | To/_ | white patches #F3F0EA **crossing the topline**, legs usually white, head usually coloured | mixed | pink skin under white |
| Pie overo (frame) | Frame overo | O/n | horizontal white on the sides; **does not cross the back**; legs usually coloured; face often white | | blue eyes common |
| Pie sabino | Sabino | Sb1 or polygenic | roan-edged white; high white on the legs; belly spots; wide blaze | | |
| Splashed white | Splashed white | SW alleles | white from below, "as if dipped"; wide blaze; white legs and belly | | **blue eyes** typical |
| Blanc dominant | Dominant white | W alleles | white to near-white | | pink skin, brown eyes usually |
| Appaloosa / tacheté: couverture, léopard, peu tacheté, marmoré | Leopard complex: blanket, leopard, few-spot, varnish roan | LP/_ (+ PATN1) | white areas with dark oval spots (spot diameter about 2–10 cm [A]) | | **white sclera, mottled skin (muzzle, eyes, genitals), striped hooves**; LP/LP: congenital stationary night blindness. **Not allowed in Shetland studbooks [V].** |
| Pangaré | Pangaré / mealy | modifier | pale #E0C89E muzzle, eye rings, belly, flanks, inner legs | | Exmoor-typical [NV] |
| Charbonné / pommelé | Sooty / dapples | modifier | sooty: darker topline overlay; dapples: rings of about 3–8 cm [A] | | |

### 4.3 Face and leg markings [NV]
Candidate sources: FEI/Weatherbys identification guidelines; IFCE "Le signalement"; AQHA marking definitions.
- **Face, from small to large:**
  - Star (FR: *en tête*): on the forehead.
  - Stripe or strip (*liste* étroite): narrow white along the nasal bones.
  - Blaze (*liste*): wider, but does not reach the eyes.
  - **Bald or white face** (*belle face*): white extends over or past the eyes toward the cheeks.
  - **Snip** (FR term to verify): white between the nostrils.
  - **Lip markings**: white on the upper or lower lip (*boit dans son blanc* when the white reaches the lips).
  - The skin under a facial marking is pink (*ladre*).
- **Legs, from low to high, with typical heights as a fraction of the distance from ground to carpus or hock [I]:**
  - Coronet (*trace de balzane*): just above the hoof, about 0.03 WH.
  - Pastern / half-pastern (*petite balzane*): up to about 0.06 WH.
  - Fetlock / sock (*balzane*): to the fetlock, or up to mid-cannon, about 0.10–0.18 WH.
  - Stocking (*grande balzane*): to the knee or hock, about 0.27–0.33 WH.
  - High white (*balzane haut-chaussée*): above the knee or hock.
  - "Ermine marks": dark spots inside the white at the coronet.
- **Rules [NV]:**
  1. The hoof wall copies the pigment of the coronet skin above it. White coronet gives an unpigmented, horn-coloured hoof (#D9C8A8 → #C8B48C [A]). Pigmented coronet gives a dark hoof (#2E2A27 [A]). Partial white, or ermine spots, give a **vertically striped** hoof.
  2. Leopard complex gives striped hooves even without leg white.
  3. The skin under any white hair is pink (#E8B4A8 → #D99A8E [A]). Pigmented skin is dark grey-black (#2B2525 [A]).
  4. Eye colour:
     - Brown (#3B2414 → #5A3A1E) by default.
     - Blue with Cr/Cr, often with splashed white, and possible when frame, sabino or dominant white covers the eye (partial or "wall" eye).
     - Amber or hazel with champagne.
     - Pearl combined with cream gives light eyes.
     - LP gives a visible white sclera.
- **Breed colour rules for UI presets:**
  - Shetland: any colour except spotted **[V]**.
  - Connemara: grey, black, bay, brown, dun/buckskin, palomino, dark-eyed and blue-eyed cream, and occasionally roan or chestnut **[V]** (https://www.britishconnemaras.co.uk/breeding-owning/about-the-breed/).
  - Welsh: any colour except piebald and skewbald **[NV]**.
  - Exmoor: bay, brown or dun with pangaré and no white **[NV]**.

---

## 5. Recommendations for the Blender → USDZ → RealityKit pipeline [I]
1. **Morphology sliders backed by evidence.**
   - Brooks et al. 2010 (1215 horses, 65 breeds, 35 measurements): **PC1 = 65.9% of variance, a coordinated overall size scaling.** PC2 is 6.4%. Source: https://pubmed.ncbi.nlm.nih.gov/21070291/
   - Makvandi-Nejad et al. 2012: a separate PC4 **separates the smallest breeds (Miniature, Falabella, Shetland)** from other small breeds. Source: https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0039929
   - Heck et al. 2019: 42% of skull shape variation is allometric, and Shetland and Falabella have large crania relative to WH.
   - Suggested sliders:
     1. global size: drive bone scales and keep proportions
     2. "Shetland-ness": shorter cannon and forearm, deeper chest, larger head, smaller ears, broader muzzle, thicker mane
     3. head size relative to body
     4. face length (paedomorphic ↔ long)
     5. neck length and crest
     6. back length
     7. body condition (fat blend shapes: crest, ribs, tail head, shoulder)
     8. bone (cannon circumference index 0.12–0.15)
     9. hoof size
2. **Proportion changes as bone scales and translations.** Do these with bone length changes in the bind pose and re-skin, or with joint offsets. Use blend shapes for surface changes such as muscle, fat and head shape. **[NV]** RealityKit skinned meshes support blend weights, but changing the skeleton's rest pose at runtime is limited (see the realitykit.md / usd.md reports). Prefer baking a few skeleton variants, or driving proportions with joint *translations* on top of the rest pose.
3. **Bind pose.** Standing square at the angles in 1.5. Start joint placement from the 1.4 template. **Calibrate against measured photographs before freezing the rig.**
4. **ROM limits** from 1.6. Bake the stifle–hock coupling and the digit curl into the animation clips. RealityKit will not evaluate Blender drivers or constraints.
5. **Colour.** Use the genotype-layered shader in 4.1. Store all of a pony's colour state as a small genotype plus parameters struct, so saves are compact and the player's choices remain biologically plausible. Offer a "free paint" mode separately if desired.

---

## 6. Open uncertainties and what to verify next
1. **No full-text access.** Every [V] item is at abstract or snippet level. Priority checks: the Adair 2016 fetlock and tarsus passive values (not retrieved); the Back 1995 trot ROM tables; Clayton & Townsend 1989 per-joint values.
2. **No pony-specific joint-centre data.** Table 1.4 is inferred. Calibrate it with orthogonal photos of real Welsh B, Connemara and Shetland ponies, or with a CC-licensed 3D skeleton scan.
3. **No Shetland morphometric study with means was reachable** apart from body weight (median 136.9 kg) and eye axial length (37.2 mm, attribution uncertain). Every other Shetland number is inferred.
4. **Shoulder, elbow, hip and stifle passive ROM in horses was not found.** The only passive values that came up were from dogs and were discarded.
5. **AO/AA per-side values are unreliable**, because the snippet conflicts with the ex vivo 86.4° AO amplitude.
6. **Ear length, mane and tail lengths, palpebral fissure size and hoof width** are unsourced [A].
7. **The whole coat colour section is [NV]** for this session. Gene and paper citations are from memory, and all hex values are artistic [A]. The French nomenclature (aubère / rouan, *souris*, *crème*, *tacheté* terms, marking terms) needs a check against IFCE / SIRE.
8. **Pony front-versus-hind hoof steepness** ("front more upright") conflicts with the usual rule.

---

## 7. Sources consulted (snippet / abstract level)
- Vertebral formula: https://veterinaryanatomyguide.com/vertebral-formula-of-domestic-animals/ ; https://vetstudyguides.com/horse-vertebral-column/
- Reciprocal and stay apparatus: https://open.lib.umn.edu/largeanimalanatomy/chapter/pelvic-limb/ ; https://en.wikivet.net/Stay_Apparatus_-_Horse_Anatomy ; https://www.merckvetmanual.com/musculoskeletal-system/tendon-and-ligament-disorders-in-horses/rupture-of-the-peroneus-tertius-in-horses
- Goniometry: https://pubmed.ncbi.nlm.nih.gov/27124214/ ; https://doi.org/10.3390/ani10122436 ; https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.2010.00254.x
- Distal limb kinematics: https://pubmed.ncbi.nlm.nih.gov/17546207/ ; https://www.researchgate.net/publication/6443307 ; https://www.researchgate.net/publication/273493548 ; https://www.mdpi.com/1424-8220/23/21/8832
- Gait kinematics: https://www.tandfonline.com/doi/pdf/10.1080/01652176.1996.9694699 ; https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.1995.tb03029.x ; https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.1995.tb03030.x ; https://pubmed.ncbi.nlm.nih.gov/11191608/
- Neck and back: https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.2042-3306.1989.tb02139.x ; https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.2010.00265.x ; https://pubmed.ncbi.nlm.nih.gov/22849675/ ; https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.2010.00196.x ; https://www.mdpi.com/2076-2615/15/15/2259 ; https://pubmed.ncbi.nlm.nih.gov/10772104/ ; https://pubmed.ncbi.nlm.nih.gov/6873044/
- Conformation: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10367726/ ; https://extension.umn.edu/horse-care-and-management/conformation-horse ; https://equimed.com/health-centers/lameness/articles/horse-conformation-head-neck-and-shoulders ; https://scialert.net/fulltext/?doi=ajas.2015.208.216 ; https://beva.onlinelibrary.wiley.com/doi/abs/10.1111/j.2042-3306.1990.tb04245.x ; https://aab.copernicus.org/articles/56/367/2013/aab-56-367-2013.pdf
- Morphometrics: https://www.researchgate.net/publication/312072337 ; https://www.researchgate.net/publication/24241985 ; https://doi.org/10.3390/ani16081190 ; https://www.researchgate.net/publication/337547923 ; https://www.researchgate.net/publication/324889624 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC12180175 ; https://pubmed.ncbi.nlm.nih.gov/21070291/ ; https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0039929 ; https://peerj.com/articles/7678/ ; https://pubmed.ncbi.nlm.nih.gov/41624284/
- Breed standards: https://www.shetlandponystudbooksociety.co.uk/about-the-breed/breed-standard/ ; https://www.wpcs.uk.com/welsh-pony-1 ; https://acps.org/inspections-criteria/ ; https://www.britishconnemaras.co.uk/breeding-owning/about-the-breed/
- Dwarfism and size: https://www.nature.com/articles/s41598-020-72192-3 ; https://pubmed.ncbi.nlm.nih.gov/27942904/ ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4608717/
- Eyes: https://avmajournals.avma.org/view/journals/ajvr/71/6/ajvr.71.6.677.xml ; https://pubmed.ncbi.nlm.nih.gov/12828248/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC12607728/
- Hooves: https://www.sciencedirect.com/science/article/abs/pii/S1090023315004025 ; https://pubmed.ncbi.nlm.nih.gov/41177197/ ; https://horse-canada.com/magazine/hoof-care/assessing-hoof-angles/ ; https://pmc.ncbi.nlm.nih.gov/articles/PMC11444133/
- Chestnuts and ergots: https://www.petmd.com/horse/chestnuts-and-ergots-horses ; https://ker.com/equinews/chestnut-not-just-coat-color/ ; https://en.wikipedia.org/wiki/Chestnut_(horse_anatomy)
