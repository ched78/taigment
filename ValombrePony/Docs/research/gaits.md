# Equine locomotion & behaviour for procedural pony animation
Project: *Les Héritiers de Valombre*. Target: a pony about 1.30 m at the withers. Authoring: Blender 4.2 bpy (headless). Runtime: RealityKit (iOS/macOS 26).
Compiled: 2026-10-05

---

## 0. Read this first: how this was researched and how far to trust it

* **Tool limits during this session.**
  * **WebFetch was blocked by the network egress proxy for every domain tested:** journals.biologists.com (JEB), pmc/pubmed.ncbi.nlm.nih.gov, mdpi.com, nature.com, wikipedia, semanticscholar, madbarn, ebi.ac.uk, knowledge.lancashire.ac.uk, animres.edpsciences.org. `curl` got the same "organization policy" denial.
  * **The WebSearch budget for the session (200 calls, shared with other agents) ran out after about 37 of my searches.**
  * As a result, no full text was read. **Every item marked VERIFIED was confirmed only from the abstract or snippet of the cited source as the search engine returned it.** The numbers are as stated in those abstracts. Figure-level detail such as joint-angle curves could not be read.
* **Labels used throughout:**
  * **[V] VERIFIED.** The number or statement appeared in the abstract or snippet of the cited source (URL given).
  * **[V\*] PARTIALLY VERIFIED.** The statement appeared in search snippets, but the exact primary source is uncertain, or the snippet merged several sources.
  * **[D] DERIVED.** Computed by me from [V] numbers using stated physics or scaling. The arithmetic is shown.
  * **[U] UNVERIFIED / INFERRED.** Background knowledge, animation craft, or a design default. It was **not** verified in this session. Candidate references are named so someone can check them, but their existence and content were **not** confirmed here unless marked [V].
* **Coverage.**
  * Sections 1 and 1b (gait timing, speeds, scaling, Shetland) are reasonably well supported.
  * Section 2 (joint angles) is only thinly supported.
  * Sections 2c–4 (head, neck, back, tail, jumping, behaviours) are mostly [U].
  * Section 5 (animation practice) is mostly [D] maths plus [U] craft.
  * Section 7 lists what must be verified before these values are treated as fact.

Phase convention used everywhere: **phase φ ∈ [0,1) of one stride, with φ = 0 at left-hind (LH) ground contact**, unless stated otherwise. "Limb phase" in the Hildebrand sense is the fraction of the stride by which a forefoot's contact lags the contact of the hind foot on the same side [V: Hildebrand 1965 definition as quoted in Biancardi & Minetti 2012 and Clayton & Hobbs 2019, URLs below].

---

## 1. Gaits: footfalls, phase offsets, duty factor, frequency, length, suspension

### 1.1 Core definitions (VERIFIED)
* **Duty factor (DF)** is stance duration divided by stride duration. A DF above 0.5 in the fore pair or the hind pair rules out an aerial (suspension) phase. When DF is below 0.5, fore–hind coordination decides whether an aerial phase exists. [V] Clayton & Hobbs 2019, *Animals* 9(10):763, https://doi.org/10.3390/ani9100763
* **Limb phase** is the fraction of the stride between a hind footfall and the ipsilateral fore footfall, expressed from 0 to 1. [V] Clayton & Hobbs 2019 (same URL). Hildebrand's original wording: "percent of the stride interval that a footfall of a forefoot lags behind the strike of the ipsilateral hindfoot". [V] quoted in Biancardi & Minetti 2012, JEB 215:4144, https://journals.biologists.com/jeb/article/215/23/4144/11268/Biomechanical-determinants-of-transverse-and
* **Hildebrand (1965)** classified symmetrical gaits on two axes: hind DF and lateral advanced placement. Source: *Science* 150:701–708. [V] (metadata via Robilliard et al. 2007 and the snippets above)
* **Robilliard, Pfau & Wilson (2007)** classified gaits of 8 Icelandic horses from foot-mounted accelerometers. They used contact sequence, limb phase, DF and aerial-phase duration.
  * Walk has 2–3 or 3–4 limbs in contact and no aerial phase.
  * DF falls with speed in a similar way for all gaits, except tölt at low speed.
  * [V] JEB 210:187–197, https://journals.biologists.com/jeb/article/210/2/187/17107/Gait-characterisation-and-classification-in-horses (doi 10.1242/jeb.02611)
* **Starke et al. (2009)** reviewed the walk/run criteria: DF, Froude number, aerial phase, energy recovery, and the shape of the vertical ground-reaction force. They showed that multidimensional classification places tölt with the "running" gaits. [V] J R Soc Interface 6(33):335–342, https://royalsocietypublishing.org/doi/abs/10.1098/rsif.2008.0238
  * Note: "Starke et al." in the brief could also mean Sebastian Starke's quadruped neural-animation work (MANN, see §5).

### 1.2 Walk (four-beat, lateral sequence, no suspension)
* **Footfall order:** LH → LF → RH → RF. Two or three feet are always on the ground. [V] IFCE équipédia (https://equipedia.ifce.fr/en/equipedia-the-universe-of-the-horse-ifce/equestrian-instruction-and-teaching/didactics-and-equestrian-techniques/interdisciplinary-principles/the-horses-gaits-definitions-and-figures) and Robilliard 2007 (above).
* **Couplets:** footfalls can be evenly spaced, or form lateral or diagonal couplets. [V] Clayton & Hobbs 2019.
* **Lateral advanced placement (LAP), i.e. the hind-to-ipsilateral-fore lag:** **0.20–0.24 of the stride** for the walk.
  * [V] Renders & Vincelette, *Animals* 2023 13(16):2557, https://doi.org/10.3390/ani13162557
  * [V] IntechOpen chapter "Laterally Coordinated Gaits in the Modern Horse", https://www.intechopen.com/chapters/83285
  * Another study's snippet gave LAP = 21.6% for walk [V\*].
* **Rhythm-analysis corroboration:**
  * Ipsilateral hoof intervals at walk fall into **1:3 / 3:1** categories, which is equivalent to a hind→fore lag of about 0.25 of the stride.
  * Trot falls into **1:1**.
  * [V] Laffi et al. 2025, *J Anat*, https://onlinelibrary.wiley.com/doi/10.1111/joa.14200
* **Duty factor:**
  * Hind DF is **0.63**, with stride duration **1.16 s**. [V] Renders & Vincelette chapter (URL above).
  * In driven horses at walk, forelimb stance was 0.65 ± 0.06 s of a 1.08 ± 0.08 s stride, and hind stance 0.66 ± 0.04 s of 1.07 ± 0.08 s. **That is DF ≈ 0.60–0.62.** [V] *Animal Research* 2006, https://animres.edpsciences.org/articles/animres/pdf/2006/06/z205074.pdf
* **Speeds and strides in dressage horses (Clayton 1995):**
  * Collected walk: **1.37 m/s**, stride length 157 cm, stride duration 1159 ms.
  * Medium walk: **1.73 m/s**.
  * Extended walk: **1.82 m/s**, stride length 193 cm, stride duration 1064 ms.
  * [V] AJVR 56(7):849–852, https://pubmed.ncbi.nlm.nih.gov/7574149/
  * Walk stride length across breeds and walk types: 1.3–1.9 m. [V] Renders & Vincelette 2023.
* **IFCE teaching figures:** walk stride 1.37 s, i.e. 0.73 strides/s or 44 strides/min. Walk speed rises from about 1.2 m/s (collected) to 1.8 m/s (extended), mainly through longer strides. [V] IFCE (URL above).
* **Recommended phase offsets for the pony walk:** LH 0.00, LF 0.22–0.25, RH 0.50, RF 0.72–0.75. DF 0.60–0.65. [D from the V values above]

### 1.3 Trot (two-beat diagonal, suspension present)
* **Pattern:** diagonal pairs move together (LH+RF, then RH+LF). Limb phase is **≈0.50, range 0.44–0.56**. Collected trot, passage and piaffe sit at 0.52–0.53. [V] Clayton & Hobbs 2019.
* **Diagonal dissociation:** in collected trot the hind foot can land about 20–30 ms before its diagonal fore. [V\*] (snippet; source attribution uncertain, possibly the IFCE page or Clayton & Hobbs.)
* **Collected trot** still has limb phase ≈0.5, DF < 0.5 and clear aerial phases. **DF for medium and extended trot is significantly smaller than for collected and working trot.** [V] Clayton & Hobbs 2019.
* **Speeds and strides in dressage horses (Clayton 1994):**

  | Trot type | Speed (m/s) | Stride length (cm) |
  |---|---|---|
  | Collected | 3.20 | 250 |
  | Working | 3.61 | 273 |
  | Medium | 4.47 | 326 |
  | Extended | 4.93 | 355 |

  Stride duration tended to fall with speed, significantly so between collected and extended. [V] EVJ 26(3):230–234, https://pubmed.ncbi.nlm.nih.gov/8542844/
  * Stride durations implied by length ÷ speed: 0.781 / 0.756 / 0.729 / 0.720 s. [D]
* **IFCE teaching figure:** trot stride 0.88 s, i.e. 1.13 strides/s or 68 strides/min. [V] IFCE.
* **Trot DF value:** the numeric value was **not verified**. Design default: **≈0.45 collected, ≈0.40 working, ≈0.35 extended**. [U] These are consistent with the [V] statements "DF < 0.5" and "smaller in medium/extended".
* **Recommended phase offsets:** LH 0.00, RF 0.00 (or 0.00–0.03 for a slight hind-first dissociation), RH 0.50, LF 0.50. There are two suspensions per stride, one after each diagonal lifts off. [D/V]

### 1.4 Canter (three-beat asymmetric, one suspension)
* **Right lead:** LH (trailing hind), then RH + LF together (the diagonal pair), then RF (leading fore), then suspension.
* **Left lead:** RH, then LH + RF, then LF, then suspension.
* [V] Clayton, USDF "Canter rhythms, oddities and illusions", https://www.usdf.org/EduDocs/The-Horse/Canter_Oddities_Illusions1.pdf
* **Suspension:** about **1% of the stride in collected canter, up to about 15% in extended canter.** [V] same USDF document. Suspension duration and the associated vertical acceleration rise with speed. [V] Clayton 1994 canters (below).
* **Speed control:** dressage horses change canter speed **through stride length while stride duration stays constant.** The step between the two forelimbs shortens from collected to extended canter. [V] Clayton 1994, EVJ Suppl 17:16–19, https://beva.onlinelibrary.wiley.com/doi/abs/10.1111/j.2042-3306.1994.tb04866.x
* **Collected canter (elite dressage horses):** stride **0.629 s**, suspension **0.013 s**. [V] Burns & Clayton 1997, https://pubmed.ncbi.nlm.nih.gov/9354291/
* **IFCE teaching figure:** canter stride 0.65 s, i.e. 1.53 strides/s or 92 strides/min. [V\*] (IFCE-style snippet returned with the IFCE page.)
* **Leading vs trailing limbs:** the trailing forelimb's stance is significantly longer than the leading forelimb's. [V] Animals 2023 13(11):1755, https://doi.org/10.3390/ani13111755
* **Speed effects:** stride duration, stance time and DF all fall with speed, for both leads. [V\*] Snippets from the Animals 2023 paper and from PLOS ONE 2023, https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0286409
* **Stance on a circle:** inside leg about 0.21 s, outside about 0.20 s. [V\*] (attribution uncertain)
* **Rhythm:** canter beat intervals fall into small-integer ratios **1:1, 1:2, 2:1**. Ipsilateral intervals fall into 1:3 / 3:1. [V] Laffi et al. 2025, Ann NY Acad Sci, https://nyaspubs.onlinelibrary.wiley.com/doi/full/10.1111/nyas.15271 and J Anat (above).
* **Phase offsets derived from those ratios** (beats at 0, 0.25, 0.50; the 0.50 gap that follows contains leading-fore stance plus suspension):
  * Right lead: **LH 0.00 / RH 0.25 / LF 0.25 / RF 0.50.**
  * Left lead (mirror): **RH 0.00 / LH 0.25 / RF 0.25 / LF 0.50.**
  * Optionally land the leading hind 0.01–0.03 before the trailing fore (diagonal dissociation, as discussed by Clayton; the size is not verified).
  * [D]
* **Canter DF:** about **0.30–0.38**. [D] This is 0.20–0.21 s of stance ([V\*]) divided by a stride of about 0.6 s ([V]).

### 1.5 Canter pirouette, a reference for turning at canter (VERIFIED)
* The pirouette has **no suspension**. The leading-fore and trailing-hind stances overlap by 0.163 s.
* The leading hind always lands before the trailing fore, by 0.164 s, which gives a **four-beat** rhythm.
* Stride is **0.879 s** in the pirouette against 0.629 s in collected canter.
* [V] Burns & Clayton 1997, https://pubmed.ncbi.nlm.nih.gov/9354291/

### 1.6 Gallop (transverse; four-beat)
* **Transverse gallop:** the two hind feet land in sequence. The second hind foot is followed by the **contralateral** forefoot, then the remaining forefoot. The left–right order is the same in front and behind. [V] Biancardi & Minetti 2012 (URL above), which cites Hildebrand 1977.
  * Right lead: **LH → RH → LF → RF**, then suspension. Left lead: RH → LH → RF → LF.
* **Rotary gallop:** described as a double-suspension gait. Horses reportedly use it only for short bursts, for example during initial acceleration. [V\*] (search snippet; primary attribution unclear)
* **Single suspension for the horse transverse gallop**, after leading-fore lift-off: [U] (widely stated; not verified here).
* **Thoroughbred stride frequency:**
  * Rises linearly from **2.02 strides/s at 9 m/s to 2.41 at 17 m/s**, with no plateau. [V\*] (snippet; most likely Witte, Hirst & Wilson 2006, JEB 209:4389, https://journals.biologists.com/jeb/article/209/21/4389/16347/Effect-of-speed-on-stride-parameters-in-racehorses)
  * Japanese race data: 2.36 ± 0.12 Hz, 7.30 ± 0.39 m stride length, 17.2 ± 1.15 m/s. [V] https://pubmed.ncbi.nlm.nih.gov/41151162/
* **Gallop phase numbers** are **not verified**. Design default for right lead: LH 0.00, RH 0.10, LF 0.38, RF 0.50, DF 0.25–0.30. [U]

### 1.7 Rein-back (backing up)
* **FEI definition:** "a rearward diagonal movement with a two-beat rhythm but without a moment of suspension. Each diagonal pair of legs is raised and returned to the ground alternatively, with the forelegs aligned on the same track as the hindlegs." [V] FEI Dressage Rules, https://inside.fei.org/system/files/16.3_ANNEX_GA19_DRESSAGE%20RULES.pdf
* **What real horses do** (9 horses walking backwards in hand):
  * 4 used only synchronous diagonal pairs.
  * 1 used disintegrated, asynchronous steps throughout.
  * 4 switched between diagonal and non-diagonal stepping.
  * Sagittal back movement and lumbosacral flexion were greater than in forward walking.
  * The support area was larger.
  * [V] *Vet J* 2024, https://www.sciencedirect.com/science/article/pii/S1090023324001412
* **Recommended pattern:** LH+RF at 0.00, RH+LF at 0.50, moving backward. DF about 0.6–0.7, so there is no suspension. [D/U] Add extra lumbosacral flexion (tucked croup) and a slightly wider base. [V-based]

### 1.8 Turn on the haunches (walk pirouette) and turn on the forehand
* **Turn on the haunches / walk pirouette:**
  * The forefeet and the outside hind move around the inside hind.
  * "The inside hind foot is raised and put down almost in the same place." It is not a frozen pivot.
  * The **four-beat walk rhythm is kept.**
  * The horse is bent slightly toward the direction of travel.
  * [V] FEI Dressage Rules (above) and FEI pirouette guidelines, https://www.dressagensw.equestrian.org.au/sites/default/files/FEI_Guidelines_evaluation_pirouettes_contact_01July2011.pdf
* **Turn on the forehand:**
  * The hindquarters circle around the forehand.
  * **The inside hind crosses in front of the outside hind.**
  * It is ridden from a halt or a working walk.
  * [V\*] USDF movements document, https://www.usdf.org/edudocs/training/movements1.pdf, plus other snippets.
  * The forelegs stepping nearly in place, with the inside fore as a near-pivot, is [U].
* **Circle work:** on a circle the inside forelimb has a longer stance than the outside one at walk, trot and canter, and trot stride frequency is lower on circles. [V] *Sensors* 2023, https://doi.org/10.3390/s23094232
* **"Turn in place" for the game:** use a walk-sequence turn on the haunches with a 15–30° yaw per stride. [U] (design choice)

### 1.9 Size scaling and pony values
* **Walk–trot transition:**
  * Across 9 horses of **90–720 kg** with leg length **0.7–1.4 m**, the transition speed rose from **1.6 to 2.3 m/s**.
  * It happened at a nearly constant **Froude number Fr = v²/(gL) ≈ 0.35**.
  * [V] Griffin, Kram, Wickler & Hoyt 2004, JEB 207:4215, https://journals.biologists.com/jeb/article-abstract/207/24/4215/2679/Biomechanical-and-energetic-determinants-of-the
* **Dynamic similarity:** in 21 trotting horses (86–714 kg), relative stride length and DF at equal Froude number (0.5, 0.75, 1.0) did **not** depend on body mass. **Horses trot in a dynamically similar way.** [V] JEB 209(3):455 (2006), https://journals.biologists.com/jeb/article/209/3/455/16439/Dynamically-similar-locomotion-in-horses
  * Breed differences (e.g. walk stride length) linked to height and speed disappear once the data are scaled. [V] https://www.sciencedirect.com/science/article/pii/S0737080624000121
* **Allometry:**
  * Stride frequency at the trot–gallop transition scales as about M^-0.14. Frequency rises linearly with speed in trot and becomes almost independent of speed in gallop. [V] Heglund, Taylor & McMahon 1974, https://pubmed.ncbi.nlm.nih.gov/4469699/
  * Preferred, minimum and maximum trot and gallop speeds scale about M^0.2. Frequencies at equivalent speeds scale about M^-0.15. [V] Heglund & Taylor 1988, JEB 138:301, https://journals.biologists.com/jeb/article/138/1/301/5532/Speed-Stride-Frequency-and-Energy-Cost-Per-Stride
  * Note the TB gallop data above show frequency still rising at racing speeds.
* **Small horses choose energy-minimising speeds:** in three small horses (110–170 kg), oxygen cost per metre had a minimum within each gait, and that minimum matched the preferred speed. [V] Hoyt & Taylor 1981, *Nature* 292:239, https://www.nature.com/articles/292239a0 (The actual speeds were not verified.)

**Pony table [D].**
* Assumptions [U]:
  * The dressage horses in Clayton's studies were about 1.65 m at the withers.
  * The pony is geometrically similar, so the scale is s = 1.30/1.65 ≈ 0.79.
  * Under Froude scaling: speed × √s = ×0.888, stride length × s, stride period × √s.
* A cross-check with Heglund & Taylor's mass exponents, using mass ∝ s³ (mass ratio 0.49), gives frequency ×1.11 and speed ×0.87. That agrees with Froude scaling to within about 2%.

| Gait (source) | Horse v (m/s) | Horse SL (m) | Horse T (s) | **Pony v** | **Pony SL** | **Pony T (f)** |
|---|---|---|---|---|---|---|
| Collected walk (Clayton 1995) | 1.37 | 1.57 | 1.159 | **1.22** | **1.24** | **1.03 s (0.97 Hz)** |
| Medium walk | 1.73 | n/a | n/a | **1.54** | n/a | n/a |
| Extended walk | 1.82 | 1.93 | 1.064 | **1.62** | **1.52** | **0.94 s (1.06 Hz)** |
| Collected trot (Clayton 1994) | 3.20 | 2.50 | 0.781 | **2.84** | **1.98** | **0.69 s (1.44 Hz)** |
| Working trot | 3.61 | 2.73 | 0.756 | **3.21** | **2.16** | **0.67 s (1.49 Hz)** |
| Medium trot | 4.47 | 3.26 | 0.729 | **3.97** | **2.58** | **0.65 s (1.54 Hz)** |
| Extended trot | 4.93 | 3.55 | 0.720 | **4.38** | **2.80** | **0.64 s (1.56 Hz)** |
| Collected canter (Burns & Clayton) | n/a | n/a | 0.629 | n/a | n/a | **0.56 s (1.79 Hz)** |
| Canter (IFCE) | n/a | n/a | 0.65 | n/a | n/a | **0.58 s (1.73 Hz)** |
| Gallop (TB, 9 m/s) | 9.0 | 4.46 | 0.495 | **8.0** | **3.52** | **0.44 s (2.27 Hz)** |

* **Pony walk–trot transition** from Fr 0.35: v = √(0.35·9.81·L).
  * Example leg length L = 0.85 m [U; measure the rig, e.g. ground to hip joint] gives **≈1.7 m/s**.
  * L = 0.75 m gives 1.6 m/s.
  * This is consistent with Griffin's smallest horses. [D]
* **Canter speed is not verified.** Choose speed = SL × f. For example, a pony working canter at 4.0 m/s with f = 1.73 Hz needs SL ≈ 2.3 m. [D/U]
* **Thoroughbreds are not geometrically similar to ponies.** Treat the pony gallop as **≈6.5–9 m/s at ≈2.2–2.4 Hz** [U]. Do not scale TB racing speeds directly.

### 1.10 Shetland and other pony specifics (VERIFIED where marked)
* **Shetland vs Warmblood foals**, both at 4 months and trotting at the same 3 m/s (24 of each): ponies took **shorter strides with shorter stance and swing durations**. Their **relative stance durations (≈DF) were similar**, and **joint angle–time curve patterns were similar.** [V] Back et al. 1999, EVJ Suppl 30:240–244, https://pubmed.ncbi.nlm.nih.gov/10659260/
  * **Implication:** reuse the same joint-curve shapes and DF, and compress time.
* **23 Shetlands at trot (3 m/s, treadmill), measured at 4 and 30 months:**
  * Stride and stance duration grew with age. Swing duration and pro/retraction range stayed the same.
  * Mature ponies had **more maximal fore and hind joint flexion in swing**.
  * The elbow and shoulder were held more extended and the stifle more flexed. The scapula and pelvis were more vertical.
  * Feed-restricted, thin ponies had a **flatter gait**.
  * [V] https://pubmed.ncbi.nlm.nih.gov/12358002/
* **Shetland breed height cap** (≈107 cm / 42 in for UK registered stock) and conformation (proportionally shorter legs, heavier head and neck, dense mane and tail): [U]. Use Froude scaling with the rig's real leg length rather than withers height. For a 1.0 m Shetland, √s ≈ √(1.0/1.65) ≈ 0.78, so frequencies are about 1.28× horse values.

---

## 2. Limb kinematics

### 2.1 Verified data (sparse)
* **Forelimb mechanics at trot:** the **carpus snaps into overextension at the start of stance**, so the forelimb works as a propulsive strut. The **fetlock acts as an elastic spring** that stores energy and absorbs impact oscillations. Measured in 24 two-year-old Dutch Warmbloods at 4 m/s on a treadmill. [V] Back et al. 1995 "How the horse moves 1", EVJ 27:31, https://beva.onlinelibrary.wiley.com/doi/10.1111/j.2042-3306.1995.tb03029.x
* **Fetlock (MCP) extension patterns:**
  * At walk, stance extension is prolonged and tends to show **two extension peaks**.
  * At trot there is a **single extension cycle**.
  * Both gaits show **two distinct flexion peaks during swing**.
  * [V\*] Clayton, Sha, Stick & Elvin 2007, *VCOT* 20(2):86–91 (snippet only; URL not confirmed).
* **Coffin (DIP) flexion/extension range:** **46 ± 3° at walk, 47 ± 4° at trot**.
* **Pastern (PIP):** **13 ± 4° at walk, 14 ± 4° at trot**.
* Abduction/adduction and rotation of these joints are only 3–6°. Ranges are similar at walk and trot.
* [V] Clayton, Sha, Stick & Robinson 2007, *VCOT*, https://www.researchgate.net/publication/6443307_3D_kinematics_of_the_interphalangeal_joints_in_the_forelimb_of_walking_and_trotting_horses
* **Carpus at trot:** range of motion about **15 ± 6° in stance and 76 ± 13° in swing**. [V\*] (snippet; probably Clayton et al. 2004 "Three-dimensional carpal kinematics of trotting horses", EVJ, https://beva.onlinelibrary.wiley.com/doi/10.2746/0425164044848037)
* **Walk vs trot:** carpal motion increases by about 15–20° at trot, shoulder motion changes little, stifle motion rises to about 55°, and hip and hock motion stay similar to walk. [V\*] (snippet; **primary source not identified**)
* **Collected vs extended trot:** there is **less hock (tarsal) flexion and less fetlock extension in collected trot** than in extended trot. [V] Walker et al. 2013, EVJ, https://beva.onlinelibrary.wiley.com/doi/abs/10.1111/j.2042-3306.2012.00617.x
* **Breed differences at walk:** the biggest inter-breed differences were in carpal range and minimum fetlock angle. [V] Galisteo et al. 2001, https://pubmed.ncbi.nlm.nih.gov/11475902/ (no numbers retrieved)

### 2.2 NOT verified: joint curve shapes for keyframing [U]
Use these as **shape guides only**. Verify against Hodson, Clayton & Lanovaz 2000 (EVJ 32:287, walk forelimb), Back et al. 1995 parts 1 and 2 (EVJ 27:31 and 27:39, trot fore and hind), and Back & Clayton, *Equine Locomotion* (2nd ed., 2013). These have **not** been verified here.

* **Forelimb, stance:**
  * Carpus: near-locked, slightly hyperextended.
  * Fetlock: loads into dorsiflexion (sinks), with peak around mid-stance, then recoils before breakover.
  * Coffin: extends during breakover.
* **Forelimb, swing:**
  * Fetlock flexes twice ([V\*] two peaks).
  * Carpus flexion peaks early to mid-swing; the range is about 70–80° at trot ([V\*]).
  * Elbow and shoulder protract.
  * The limb unfolds before landing, heel-first or flat.
* **Hindlimb:**
  * Hock and stifle are coupled (reciprocal apparatus) and **must flex and extend together**. Rig them with a driver or constraint, not as independent keys. [U] (anatomy; well known but not verified here)
  * The fetlock sinks in stance as in the forelimb.
  * Hip extends through stance and flexes in swing.
* **Hoof flight arc** (no numeric data retrieved):
  * Forelimb: high and early after breakover, then a lower, flatter approach, landing with near-zero horizontal hoof velocity.
  * Hindlimb: lower and flatter.
  * Arc height grows with gait and with "action". Shetland and hackney-type ponies are higher.
  * Default arc heights as a fraction of the pony's leg length L [U]: walk fore 0.10–0.15 L, hind 0.08–0.12 L; trot fore 0.20–0.30 L, hind 0.15–0.20 L; canter/gallop leading fore up to about 0.35 L. **These are artistic placeholders, not data.**

### 2.3 Head, neck and trunk motion [mostly U]
* **Trot** [U; standard lameness-literature knowledge, e.g. Buchner et al. 1996 EVJ, not verified here]:
  * Head, withers and pelvis each oscillate vertically **twice per stride**.
  * Each is lowest around mid-stance of each diagonal and highest during suspension.
  * The head is fairly steady in pitch compared with walk.
  * Typical amplitudes in sound horses are several centimetres for the trunk and larger for the head. **Exact values are not verified.**
  * Design default for the pony [U]: withers ±2.5–3.5 cm, sacrum ±3–4 cm, head ±3–5 cm, all in phase with the diagonal stances.
* **Walk** [U]:
  * The head and neck "nod" **twice per stride** with a larger pitch amplitude than at trot. They act as a pendulum coupled to the forelimbs.
  * The trunk has a small vertical oscillation (≈ ±1–2 cm design default) and visible pelvic roll and yaw as each hind limb swings.
  * Exact phasing is not verified. Use reference video (e.g. Muybridge plates) to set the timing.
  * One verified related paper exists on asymmetric withers excursions at walk (PLOS ONE 2018, https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0204548); its content was not retrieved.
* **Canter** [U]:
  * **One** vertical oscillation and **one** pitch ("rocking-horse") cycle per stride.
  * The forehand rises while the hind limbs are in stance and drops onto the leading fore.
  * Head and neck counter-swing: they are raised or extended at hind contact and lowered during forelimb stance.
  * The trunk is highest during suspension.
* **Back motion:**
  * Backward walking increases sagittal back motion and lumbosacral flexion. [V] Vet J 2024 (above).
  * Otherwise [U]: Faber et al. (AJVR 2000 walk; AJVR 2001 trot; EVJ Suppl 2002 canter) reported thoracolumbar flexion/extension, lateral bending and axial rotation. The commonly cited qualitative picture is that the back is **stiffest at trot**, has **more lateral bending and axial rotation at walk**, and has the **largest flexion/extension at canter**. Not verified here.
  * Design default: pelvis roll ±3–5° at walk and ±1–2° at trot. Spine yaw follows hind protraction at walk. Canter lumbosacral flexion/extension ±5–8°. [U]
* **Tail** [U; ethological observation only]:
  * At rest and walk the tail hangs and swings passively with pelvic yaw.
  * At trot and canter it is carried slightly away from the buttocks and bounces with a phase lag behind the sacrum.
  * At high arousal (gallop, play, fear) it is carried high or arched.
  * When clamped it signals fear or discomfort.
  * Drive it with spring-damper secondary motion from the sacrum.

---

## 3. Jumping a 60–80 cm fence [U except for the physics; nothing verified this session]
Candidate references to verify (none read or verified here):
* Clayton & Barlow 1989 (*J Equine Vet Sci*, fence height/width and limb placements)
* Clayton 1989 (jumping terminology)
* Bobbert & Santamaría 2005 (JEB, fore- vs hindlimb contribution)
* Santamaría et al. 2004 (AJVR, jumping in young horses)
* Powers & Harrison (rider effects)

Commonly described sequence [U]:
1. **Approach.** Usually at canter. The last strides are adjusted, and the last stride is often shorter, with the head and neck lowering and lengthening as the horse looks at the fence.
2. **Take-off.**
   * The forelimbs land one after the other, the trailing fore first, then the leading fore. They brake and convert forward speed into upward rotation, raising the forehand.
   * The forelimbs leave the ground before the hind limbs land.
   * The hind limbs land **close together, nearly paired**, under the body and push off.
   * Neck and head rise and shorten on take-off.
3. **Flight / bascule.**
   * The forelimbs fold tightly (carpus fully flexed, forearms near horizontal).
   * The neck stretches forward and down over the fence and the back rounds.
   * The hind limbs then flex and trail over the rail.
4. **Landing.**
   * One forelimb lands first (usually the non-leading or trailing one), then the other, which becomes the leading limb of the departure canter.
   * The head and neck rise to rebalance.
   * The hind limbs land under the body and the horse cantering away.

Physics-based timing estimate [D]:
* Ballistic flight time is t = 2·√(2Δh/g), where Δh is the rise of the centre of mass above its canter level.
  * Δh = 0.30 m gives t ≈ 0.49 s; 0.40 m gives 0.57 s; 0.50 m gives 0.64 s.
* At a horizontal speed of 3.5–4.5 m/s the airborne distance is about 1.7–2.9 m.
* For a 60–80 cm fence with a 1.30 m pony, a design default is: **take-off stride about 0.35–0.45 s, flight about 0.5–0.6 s, landing stride about 0.35–0.45 s**, with the take-off point about 1.0–1.5 × fence height before the fence. [U/D] Verify against video.

---

## 4. Behaviours: keyframe guidance [U throughout; not verified]
Main candidate references to verify:
* McDonnell, *The Equid Ethogram* (2003)
* McDonnell & Haviland 1995 (agonistic ethogram)
* Wathan et al. 2015 (EquiFACS, PLOS ONE)
* Wathan & McComb 2014 (*Curr Biol*, ears and eyes signal attention)
* Dalla Costa et al. 2014 (Horse Grimace Scale, PLOS ONE)
* Merkies et al. 2019 (*Animals*, blink rates and stress)
* Briefer et al. 2015 (*Sci Rep*, whinnies)
* Stomp et al. 2018 (PLOS ONE, snorts)
* Bramble & Carrier 1983 (*Science*, running and breathing)
* Torcivia & McDonnell 2021 (Equine Discomfort Ethogram, *Animals*)

**None of these were read in this session.**

| Behaviour | Keyframe guidance (U) |
|---|---|
| **Grazing** | Neck lowered to ground. Usually one forelimb advanced ahead of the other ("staggered" or grazing stance; see van Heel et al. 2006 on foal grazing stance, not verified). Bite, lip and chew cycles. Step forward slowly every few bites (step-graze); lift and swing the head sideways. Ears loose or sideways, tail swishing. |
| **Rearing** | Weight shifts back; hocks and stifles flex deeply; forehand rises with neck up or back; forelimbs fold or paw. Hold briefly, then land forelimbs one after the other. Animate the centre of mass passing over the hind feet. |
| **Head shake / toss** | A fast rotation about the poll and neck axis (roll + yaw) or a vertical toss over about 0.3–0.6 s; ears and mane follow with lag. |
| **Neigh / whinny** | Head and neck raised, ears forward, nostrils flared, mouth slightly open; flank and abdomen contract rhythmically through the call. Whinny length: unverified (Briefer 2015 analysed acoustics). |
| **Snort / nostril flare** | Short forceful exhale with nostril flutter. Nostrils flare at arousal and after exercise. |
| **Pawing** | One forelimb lifts, reaches forward, then drags or strikes backward along the ground; repeat at about 1 Hz (placeholder). Head often low. |
| **Lying down** | Sniff or circle the ground, lower the head, flex both forelimbs and kneel onto the carpi, lower the hindquarters, then roll onto one side into **sternal recumbency** (legs folded under). Lateral recumbency (lying flat) for deep rest. |
| **Getting up** | From sternal recumbency: extend **forelimbs first** (one then the other, planted forward), swing the head and neck up and forward for momentum, then push with the hind limbs to lift the hindquarters. |
| **Rolling** | Lie down, roll onto the back with legs flexed, rub, may roll fully over or return. Get up (as above), then usually a **body shake**. |
| **Body shake** | Wave travelling from head and neck to trunk to tail. Feet planted, slight lowered stance. |
| **Fly response** | Tail swish (whole-tail sweep to flank), local skin twitch (panniculus), head swing toward flank, stamping a hind foot. |
| **Ears** | Both forward: attention or alert (Wathan & McComb 2014). Pinned flat back: threat or aggression (McDonnell & Haviland 1995). Loose or sideways: relaxed or dozing. Ears held stiffly back with tension: possible pain (Horse Grimace Scale). Independent swivel: monitoring sounds; rotate each ear toward its own sound source. |
| **Blink** | Rate not verified. Merkies et al. 2019 reported baseline blinks, half-blinks and eyelid twitches changing with stress. Placeholder: random interval of 3–10 s, about 0.15–0.25 s duration, with occasional half blinks. |
| **Breathing** | At rest about 8–16 breaths/min for adult horses (commonly cited clinical range; **not verified**). After work, rate and depth rise sharply, with flank heave and nostril flare. **At canter and gallop, breathing is locked 1:1 with the stride** (Bramble & Carrier 1983; not verified here). Drive the breath cycle from the gait phase at those gaits. |

---

## 5. Practical procedural-animation advice (maths [D], craft [U])

### 5.1 Hoof-trajectory + IK cycle generator
* **Phase clock:** φ(t) = frac(φ₀ + f·t), with stride frequency f = 1/T. Each limb has an offset Δᵢ (tables in §1) and duty factor DFᵢ. The limb is in stance when frac(φ − Δᵢ) < DFᵢ.
* **No foot sliding, by construction [D]:**
  * Stride length is SL = v·T.
  * During stance the hoof stays fixed in world space while the body moves v·DF·T. The hoof's travel relative to the body is therefore **DF·SL**, from about +DF·SL/2 ahead of its neutral point to −DF·SL/2 behind it.
  * During swing the hoof must cover **SL** in world space in (1−DF)·T, so the **mean hoof speed in swing is v/(1−DF)**. That is about 2.6·v at walk (DF 0.62), 1.67·v at trot (DF 0.40), and 1.33·v at gallop (DF 0.25).
  * Make the swing horizontal profile ease-in/ease-out (smoothstep or minimum-jerk), so hoof velocity is zero relative to the ground at lift-off and touchdown.
* **Swing arc:** vertical lift as a function of normalised swing time s ∈ [0,1].
  * Forelimb: early, higher peak (about s = 0.3–0.4) after breakover, then a flatter approach. [U]
  * Hindlimb: lower and more centred. [U]
  * Animate a toe-first breakover: the hoof pitches about the toe at the end of stance.
* **IK:**
  * Use a 2-bone or 3-bone IK chain per limb with a pole target, plus an explicit fetlock/pastern chain driven by a "load" curve (sinks in stance, recoils at breakover; §2.1).
  * Couple hock and stifle (reciprocal apparatus).
  * Lock the carpus straight in stance and flex it in swing; drive this from the phase, not from IK.
* **Body:** add pelvis and withers vertical bob, roll, pitch and yaw as functions of φ, using the §2.3 defaults. Two cycles per stride for symmetrical gaits, one per stride for canter and gallop.
* **Baking:** in Blender, bake pose bones with visual keying, then run a contact-lock pass. Use a sampled contact flag to pin hoof world positions and re-solve IK. This is the classic "footskate cleanup" idea: Kovar, Schreiner & Gleicher 2002 (reference not verified here).

### 5.2 Gait blending and transitions
* **Normalised phase sync:** all clips share φ = 0 at LH contact. Blend only between clips with **compatible footfall patterns**, for example walk speeds with each other, or trot speeds with each other. While blending, interpolate f and SL and advance one shared φ. This is registration or time-warp blending (Rose et al. 1998 "Verbs & Adverbs"; Kovar & Gleicher 2003 registration curves; not verified here).
* **Speed control within a gait** [V]:
  * Walk: both stride length and frequency change.
  * Trot: mainly stride length; duration falls slightly.
  * Canter: stride length only; duration constant.
  * TB gallop: frequency rises linearly with speed.
* **Transition speeds:**
  * Walk→trot at Fr ≈ 0.35 [V], which is ≈1.6–1.7 m/s for the pony [D].
  * Trot→canter: not verified. Use a design threshold around trot speed at Fr ≈ 2–2.5 (≈4.1–4.6 m/s for L = 0.85 m) [U]. Riders often canter much slower.
* **Transition clips:** author dedicated 1–2-stride clips rather than cross-fading different footfall patterns.
  * Walk→trot: diagonal pairs converge over one stride.
  * Trot→canter: dissociate one diagonal; the new trailing hind lands first.
  * Stop: shorten the last 1–2 strides, bring the hind limbs under the body, finish in a square halt.
  * All [U].
* **Lead choice:** on a turn, use the inside lead (left lead for a left turn) [U, riding convention]. A flying change swaps the offsets Δ during suspension.

### 5.3 Root motion and turning
* **Root motion:** author the cycles in place, store v_clip = SL·f per clip, and move the root in-engine. If game speed differs from v_clip, adjust playback rate only within about ±15–20%. Outside that range, switch to or blend toward the next clip (craft heuristic [U]).
* **Turning:**
  * Bend the spine laterally toward the turn (FEI: slight bend toward the direction of travel [V]).
  * Lengthen inside forelimb stance [V on circles].
  * Lean the whole body inward with roll θ ≈ atan(v²/(g·r)). That is the physics of the centre-of-mass lean, a simplification [D].
  * At walk, turn in place with the turn on the haunches pattern (§1.8).

### 5.4 Real-time procedural layers (RealityKit)
* **Head look-at:** distribute yaw and pitch across the neck vertebrae (more at the poll), clamp them, and smooth with a critically damped spring.
* **Ears:** a state machine using the §4 table, plus independent swivel toward sound sources.
* **Tail:** a spring chain driven by sacrum motion, plus a fly-swish impulse.
* **Blink:** random timer.
* **Breathing:** a scale or blend-shape on ribs and flank, at the resting rate, or phase-locked 1:1 to stride at canter and gallop.

All of these are craft recommendations [U].

---

## 6. Suggested default parameter set (pony, 1.30 m) [D/U]
```yaml
# phase offsets relative to LH contact; DF = duty factor; f = stride Hz
walk:   {f: 0.95-1.06, v: 1.2-1.6, DF: 0.62, LH: 0.00, LF: 0.23, RH: 0.50, RF: 0.73, suspension: none}
trot:   {f: 1.44-1.56, v: 2.8-4.4, DF: 0.45->0.35 (collected->extended), LH: 0.00, RF: 0.00-0.03, RH: 0.50, LF: 0.50, suspension: 2 per stride}
canter_R: {f: 1.73-1.79, v: ~3.5-5 (choose SL=v/f), DF: 0.32-0.38, LH: 0.00, RH: 0.24, LF: 0.25, RF: 0.50, suspension: ~1-15% stride}
canter_L: {mirror: canter_R, RH: 0.00, LH: 0.24, RF: 0.25, LF: 0.50}
gallop_R: {f: 2.2-2.4, v: 6.5-9, DF: 0.25-0.30, LH: 0.00, RH: 0.10, LF: 0.38, RF: 0.50, suspension: 1 (gathered)}  # offsets UNVERIFIED
rein_back: {f: ~0.8-1.0 (U), v: 0.3-0.6 (U), DF: 0.65, pairs: [LH+RF: 0.00, RH+LF: 0.50], suspension: none}
shetland_scale: {time: x sqrt(L_shet/L_pony), length: x (L_shet/L_pony)}  # same DF & curve shapes (Back 1999)
```

---

## 7. Open uncertainties and what to verify next (needs full-text access)
1. **Numeric DF for trot, canter and gallop**, and exact gallop phase offsets. Sources: Robilliard 2007 tables; Witte 2006; Hildebrand 1977.
2. **Joint angle–time curves**, i.e. peak carpal flexion, peak fetlock extension and hock/stifle ranges, at walk and trot. Sources: Hodson et al. 2000; Back et al. 1995 parts 1 and 2; Back & Clayton, *Equine Locomotion*.
3. **Hoof flight-arc heights and shapes.**
4. **Vertical displacement amplitudes and phases of head, withers and pelvis per gait**, plus head-nod phase at walk and neck motion at canter. Sources: Buchner et al. 1996; Pfau et al.
5. **Thoracolumbar ranges per gait.** Source: Faber et al. 2000–2002.
6. **Jumping phase timings and limb sequence.** Sources: Clayton & Barlow 1989; Bobbert & Santamaría 2005. Pony-specific data are probably scarce.
7. **All behaviour timings:** blink rate, resting respiratory rate for ponies, whinny duration, lying and rolling sequences, ear-meaning literature.
8. **Pony mass and leg length for Froude scaling.** Measure the rig. The withers height of Clayton's horses (≈1.65 m) is an assumption.
9. **The source of the snippet "carpus ROM 15±6° stance / 76±13° swing" and the walk-vs-trot ROM statement** (§2.1, [V\*]).
