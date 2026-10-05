# Blender 4.2 (`bpy` 4.2.0 pip module) headless pipeline experiments for a rigged pony

Every number below was measured in this container: headless Linux, 4 shared CPUs, 15 GB RAM, no GPU, `bpy.app.background == True`, Python 3.11. Nothing in this report comes from documentation alone.

- **Scripts:** `scratchpad/experiments/blender/*.py`. `common.py`, `sdf_pony.py`, `rig.py`, `uvutil.py` and `heatweights.py` are helpers. Each experiment script is called `expN*.py`.
- **Outputs:** `scratchpad/experiments/blender/out/` holds .blend files, PNG renders, bakes and GLBs.
- **Test subject:** a rough pony built as an SDF, about 1.8 m tall including the head, in meters, with +Y forward and +Z up. Most experiments reuse its QuadriFlow quad mesh (18,212 verts / 18,210 quads).
- **Installs:**
  - `pip install scikit-image` worked (0.26.0, plus networkx, imageio, tifffile).
  - `pip install pypng` worked. I used it only to check PNG bit depth.
  - **`apt-get install -y --no-install-recommends libegl1 libegl-mesa0` worked and is required for Workbench and EEVEE** (see section 6).

---

## 0. Background-mode basics (all verified)

```python
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)   # clean scene (fast, ~0.1 s)
# bpy import itself: 0.4 s

def make_active(ob):
    bpy.context.view_layer.update()                 # needed after bpy.data.objects.remove(): iteration can yield None
    for o in bpy.context.view_layer.objects:
        if o is not None: o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
```

- In background mode, `bpy.context.window` exists but `bpy.context.area` is `None`.
- **None of the object, mesh or UV operators I tested needed `temp_override`**, as long as the target object was active and selected in the view layer. This covers `voxel_remesh`, `quadriflow_remesh`, `modifier_apply`, `modifier_apply_as_shapekey`, `parent_set`, `uv.smart_project`, `uv.unwrap`, `uv.pack_islands`, `uv.lightmap_pack`, `object.bake`, `datalayout_transfer`, `surfacedeform_bind`, `vertex_group_limit_total`, `convert`, `modifier_convert` and `export_scene.gltf`.
- `temp_override` also works when you want to act on an object that is not active. This was verified with QuadriFlow and voxel remesh:

```python
with bpy.context.temp_override(object=a, active_object=a, selected_objects=[a], selected_editable_objects=[a]):
    bpy.ops.object.quadriflow_remesh(target_faces=1000)     # {'FINISHED'} 0.69 s, the active object is untouched
```

- **The only failure caused by background mode** was `bpy.ops.uv.export_layout`, which raises `SystemError: GPU functions for drawing are not available in background mode`. This happens even with EGL installed. A PIL replacement is in `uvutil.draw_uv_layout`.
- **Fast mesh creation from numpy** (`common.mesh_from_numpy`): 55k triangles in 0.03 s.

```python
me = bpy.data.meshes.new(name)
me.vertices.add(len(V)); me.vertices.foreach_set("co", V.astype(np.float32).ravel())
me.loops.add(F.size);    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
me.polygons.add(len(F)); me.polygons.foreach_set("loop_start", np.arange(0, F.size, F.shape[1], dtype=np.int32))
me.update(calc_edges=True); me.validate()
```

---

## 1. Implicit/SDF body → marching cubes → voxel remesh → QuadriFlow (`exp1*.py`)

### What was run

The body is a smooth-min (polynomial `smin`) union of about 20 primitives: ellipsoids (Inigo Quilez approximation) and round cones/capsules. They make up the barrel, chest, rump, neck, skull, muzzle, ears, 2×3 leg segments and the tail dock. The SDF is sampled on a numpy grid and meshed with `skimage.measure.marching_cubes`.

| Step | Result | Time |
|---|---|---|
| numpy SDF sampling, res 128 (0.7 M pts) | | 1.16 s |
| numpy SDF sampling, res 160 (1.3 M pts, voxel 1.5 cm) | | 2.92 s |
| numpy SDF sampling, res 256 (5.4 M pts) | peak RSS 0.86 GB | 16.85 s |
| `marching_cubes` res 160 | 27,568 v / 55,132 tris, 1 component, 0 non-manifold edges, outward normals | 0.03 s |
| `marching_cubes` res 256 | 70,358 v / 140,712 tris | 0.09 s |
| `bpy.ops.object.voxel_remesh()` (`remesh_voxel_size=0.012`) | 44,030 v / 44,028 quads, closed | 0.28 s |
| **`quadriflow_remesh(target_faces=20000)`** after the cleanup below | **18,210–18,436 faces, 100% quads, manifold, 1 component** | **19.9–23.8 s** |
| `quadriflow_remesh` on a primitive (cube or ico → 2000 faces) | works | 1.0–1.2 s |

SDF sampling is the bottleneck. It costs about 3 µs per point per primitive set in plain numpy. Marching cubes is effectively free.

### Pitfall: QuadriFlow silently does nothing on voxel-remesh or marching-cubes output

On this geometry QuadriFlow printed `Warning: QuadriFlow: The mesh needs to be manifold and have face normals that point in a consistent direction` and returned **`{'FINISHED'}`**, but left the mesh unchanged.

- This happened for:
  - raw skimage MC output;
  - `voxel_remesh` output (operator or REMESH modifier);
  - even a voxel-remeshed icosphere.
- My numpy re-implementation of the manifold check found nothing wrong: no edge with more than 2 faces, no flipped edges, no wire edges, no zero-length edges at `FLT_EPSILON`.
- Bisecting showed the trigger is **very short edges**:
  - Voxel and MC output contain a few edges between 8e-6 and 3e-5 m.
  - After merging with `remove_doubles(dist=1e-4)`, the shortest edge was 1.87e-4 m and QuadriFlow worked. 4e-4 also worked.
  - `dist=1e-5` (which merged nothing) did **not** fix it.
  - Rebuilding the mesh from numpy or triangulating it did not help. Deleting loose verts did not help either (there were none).
  - 5 iterations of a SMOOTH modifier also fixed it.
- I did not find the exact threshold. Somewhere between 3e-5 and 1.9e-4 m works on this mesh.

**Working pattern:**

```python
import bmesh
bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=4e-4)       # kills micro-edges; essential before QuadriFlow
bm.to_mesh(ob.data); bm.free(); ob.data.update()
make_active(ob)
r = bpy.ops.object.quadriflow_remesh(target_faces=20000, mode='FACES', use_mesh_symmetry=True,
                                     use_preserve_sharp=False, use_preserve_boundary=False,
                                     preserve_attributes=False, smooth_normals=False, seed=0)
# r is {'FINISHED'} even on failure -> ALWAYS verify that len(ob.data.polygons) changed / all quads
```

- QuadriFlow runs blocking when called from Python, with no job system. Its result looks good: see `out/exp6_pony_cycles64_oidn.png`.
- `use_mesh_symmetry=True` gave no measurable speed difference (20.7 s vs 19.9 s).

### Alternatives tested

- **Metaballs → mesh.**
  - Building the elements works: `mb.elements.new(type='ELLIPSOID'|'CAPSULE')`, with `size_x/y/z`, `radius`, `rotation`, `stiffness`.
  - Conversion works both with `bpy.data.meshes.new_from_object(ob.evaluated_get(dg))` and with `bpy.ops.object.convert(target='MESH')`. Both took under 0.01 s at `resolution=0.02`.
  - My layout came out as 6 separate components: the legs did not merge at threshold 0.6. Blending control is coarse (one global threshold, per-element stiffness) compared with the numpy SDF.
- **Joined primitives → `voxel_remesh`.**
  - Join (`bpy.ops.object.join`) followed by `voxel_remesh(0.012)` took 0.08 s and gave 30k quads in 1 component.
  - The unions have **hard creases**: no smooth blend.
- **Recommendation:** numpy SDF + skimage MC, then `remove_doubles`, then optionally `voxel_remesh` (any of the three meshers needs this cleanup), then QuadriFlow. If grid resolution above 200 becomes slow, evaluate the SDF in chunks or only in a narrow band.

---

## 2. Skin modifier on a branching edge skeleton + Subdivision (`exp2*.py`)

The skeleton is about 20 vertices: spine, neck, head, 4 three-segment legs and the tail. Radii are set via `me.skin_vertices[0].data[i].radius`, and the root via `.use_root = True`. The modifier is followed by a Subsurf modifier at level 2. Evaluation and apply are instant (under 0.01 s). It works headless.

| Variant (body/branch-node radius) | Result after subsurf 2 | Non-manifold edges | Components | Self-overlapping face pairs (BVH) |
|---|---|---|---|---|
| 0.26 (realistic barrel) | 2,912 quads | **32**, plus 16 boundary edges | **3** | 152 |
| 0.18 | 3,296 quads | 4 | 1 | 78 |
| 0.18, `branch_smoothing=1` | 3,296 quads | 4 | 1 | 22 |
| 0.12 | 3,456 quads | 0 | 1 | 52 |
| 0.12, leg roots moved 4 cm outward | 3,472 quads | 0 | 1 | 24 |

- **The skin modifier breaks at branch nodes whose radius is larger than the distance to the neighbouring (limb) nodes.**
  - The result has non-manifold flaps, holes and loose pieces, and the cage gets valence 7–9 poles.
  - No error is reported anywhere. The modifier RNA has no error field.
- Clean output requires thin branch nodes, which gives a "tube" animal (`out/exp2_skin_compare.png`).
- **Verdict:** use it for limbs or as an armature-like base cage only. It is not suitable for a realistic barrel-bodied pony. The SDF route is better.

---

## 3. UV unwrapping headless (`exp3*.py`, `uvutil.py`)

It works in plain edit mode without overrides:

```python
make_active(ob); bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.003, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.005)  # 4.2 methods: ANGLE_BASED, CONFORMAL only
bpy.ops.uv.average_islands_scale(); bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
```

All timings are on the 18,210-quad pony:

| Method | Time | Islands | UV coverage | Area-distortion ratio p5–p95 (1 = none) |
|---|---|---|---|---|
| `smart_project` (66°) | 0.04 s | 62 | 0.369 | 0.80–1.20 |
| Naive coordinate-threshold seams + `unwrap` | 1.8 s | 244 (garbage fragments) | 0.013 | 0–27 |
| **Dijkstra landmark seams + `unwrap` ANGLE_BASED** | 0.10 s seams + **5.1 s** unwrap | **1 (pelt)** | 0.423 | 0.16–1.72 |
| Same seams + CONFORMAL | 0.57 s | 1 | 0.714 | 0.01–2.03 |
| `average_islands_scale` + `pack_islands` | 0.11 s | | | |
| `lightmap_pack` | 0.25 s | | | |

### Procedural seams that work (`exp3b_uv_geodesic_seams.py`)

1. Pick landmark vertices with a `scipy.spatial.cKDTree` query: chin, chest-bottom, groin, tail tip, the 4 hoof bottoms, and the ear tips and bases.
2. Run `scipy.sparse.csgraph.dijkstra` on the edge graph with *biased* edge costs:
   - ventral path cost: `L*(1 + 6*(n_z+1)/2 + 20*|x|)`;
   - medial leg path cost: `L*(1 + 6*(n_x*sign(x)+1)/2)`.
3. Write the result as seams with `me.edges.foreach_set("use_seam", mask)`.

This produced a clean single-island "pelt" (`out/exp3b_uv_abf.png`). The head, ears and hooves are compressed: area ratio p5 is 0.16. For production, add ring seams to cut the head and hooves into separate islands, then use `average_islands_scale` and `pack`.

**UV layout image:** `bpy.ops.uv.export_layout` **fails** in background mode (GPU drawing). Draw the layout with PIL instead (`uvutil.draw_uv_layout`).

---

## 4. Armature + weights (`exp4*.py`, `rig.py`, `heatweights.py`)

**Building the armature** uses edit bones: `bpy.ops.object.mode_set(mode='EDIT')` on the armature object, then `arm.edit_bones.new()`. This works headless. The test rig has 27 bones, 26 of them deform bones.

**Parenting:**

```python
make_active(rig); mesh.select_set(True)               # mesh selected, armature ACTIVE
bpy.ops.object.parent_set(type='ARMATURE_AUTO')       # or 'ARMATURE_ENVELOPE' / 'ARMATURE_NAME'
```

| Method | Time (18,212 verts) | Unweighted verts | Influences/vertex | Deformation (`out/exp4c_pose_compare.png`) |
|---|---|---|---|---|
| **`ARMATURE_AUTO` (bone heat), meter scale** | **0.83–0.85 s** | 0 | mean 3.03, **max 9** | clean |
| `ARMATURE_AUTO` on the broken skin mesh (non-manifold, 3 components) | 0.08 s | 0 | max 8 | (worked) |
| `ARMATURE_AUTO` with an overlapping duplicated head shell | 0.96 s | 0 | | worked |
| **`ARMATURE_AUTO`, mesh and rig scaled to 0.01 or 0.001** | 0.23 s | **18,212 / 18,212 (all)** | | prints `Warning: Bone Heat Weighting: failed to find solution for one or more bones` and **still returns `{'FINISHED'}`** |
| `ARMATURE_AUTO` at scale 100 | 0.81 s | 0 | | works |
| `ARMATURE_ENVELOPE` (distance 0.12) | 0.05 s | 5,754 | 1.25 | tears the body |
| Custom heat diffusion (numpy/scipy), no visibility test | 0.32 s | 0 | | bad: belly glued to legs |
| **Custom heat + BVH visibility test, continuous top-4 limit** | **0.38–0.48 s** (+0.1 s writing groups) | 0 | 3.79 | clean, close to Blender (`out/exp4c_heat4_cont.png`) |
| Custom heat + visibility, naive hard top-4 | same | 0 | 3.84 | **visible creases** (`out/exp4c_heat4.png`) |

### Findings

- **Auto weights work headless.** Failure depends on scale: at centimetre scale it fails completely.
  - The operator still returns `FINISHED`. Always check that no vertex has a zero weight sum after the call.
  - Workaround: build in meters, or scale up ×100, weight, then scale back.
- **The custom heat weights** (`heatweights.heat_weights`) follow Baran–Popović.
  - The system is the cotangent Laplacian plus lumped mass: `(L + M·H) w_j = M·H·p_j`, with `H = 1/d²` to the nearest *visible* bone. It is factorized once with `scipy.sparse.linalg.factorized` and solved for 26 right-hand sides.
  - Visibility is checked with `mathutils.bvhtree.BVHTree.ray_cast` from the closest point on the bone to the vertex: 20,955 rays in about 0.2 s.
  - **Without the visibility test the result is unusable.**
  - The custom weights agree with Blender's on the dominant bone for 86.9% of vertices. The mean L1/2 difference is 0.17.
- **Limiting to 4 influences** (glTF `JOINTS_0`): naive top-k truncation creates creases.
  - **Continuous top-k** removes them: subtract the (k+1)-th largest weight from all weights, clip at 0, renormalize.
  - Blender's own auto weights (max 9 influences, 2,881 vertices with more than 4) also show a mild crease after `vertex_group_limit_total(limit=4)` (`out/exp10_auto_limit4_pose.png`).
  - **The glTF exporter does the same hard top-4 truncation.** Its log says: "There are more than 4 joint vertex influences. The 4 with highest weight will be used (and normalized)."
  - Prefer to limit weights yourself, continuously, before export.

```python
bpy.ops.object.vertex_group_limit_total(group_select_mode='BONE_DEFORM', limit=4)       # works headless (hard limit)
bpy.ops.object.vertex_group_normalize_all(group_select_mode='BONE_DEFORM', lock_active=False)
```

- Writing groups: `vertex_group.add([i], w, 'REPLACE')` takes a single weight per call. For 18k vertices with about 4 weights each this took 0.1 s, so it is not a bottleneck.

---

## 5. Cycles CPU baking headless (`exp5*.py`)

- **Low mesh:** QuadriFlow pony with Dijkstra-seam UVs, 18,210 faces.
- **High mesh:** the low mesh with Subsurf level 2 and a Displace modifier (CLOUDS texture, 8 mm), giving **291,360 faces**. Evaluating it took 0.25 s.

```python
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = 1
img = bpy.data.images.new("normal", 2048, 2048, alpha=False, float_buffer=True); img.colorspace_settings.name = 'Non-Color'
node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = img
mat.node_tree.nodes.active = node            # bake target = ACTIVE image node of the low mesh's material
make_active(low); high.select_set(True)      # active = low, selected = high
bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', use_selected_to_active=True,
                    cage_extrusion=0.02, max_ray_distance=0.0, margin=8, use_clear=True)
img.filepath_raw = path; img.file_format = 'PNG'; img.save()     # float image -> 16-bit PNG
```

| Bake | Time |
|---|---|
| Normal, selected→active, 1024², 1 spp | **2.15 s** |
| Normal, 2048², 1 spp | **6.70 s** |
| Normal, 1024², 16 spp | 2.33 s; **identical result** (mean abs diff 4.5e-6), so samples do not matter for normal bakes |
| AO, 1024², 32 spp (low mesh only) | 5.28 s |
| Object-space position via EMIT, 1024² float → EXR | 0.37 s |

- The normal map looks correct (`out/exp5_normal_1024_preview.png`).
- **Position bake:** a material of TexCoord `Object` → Emission → output, with `bake(type='EMIT')` into a float, Non-Color image, saved with `file_format='OPEN_EXR'`.
  - Baked range: x ±0.298, y −0.878…1.246, z up to 1.769. The mesh bounding box is x ±0.298, y −0.878…1.249, z 0.016…1.809.
  - The values are linear object-space meters. Empty texels are 0.
  - Thin, compressed UV regions (ear tips) lose their extremes.
- **Bit depth:**
  - `img.save()` on a **float** image with `file_format='PNG'` writes **16-bit** PNG. `img.save_render(path, scene=sc)` with `image_settings.color_depth='16'` also writes 16-bit.
  - Both were verified by reading the header with pypng.
  - **PIL and imageio read these RGB16 PNGs back as uint8**, which looks like an 8-bit file. Check with pypng.
  - Non-Color data was written linearly (a test gradient gave 0/85/170/255) even with the AgX view transform active.
- **Pitfall: zero-user images are dropped when saving the .blend.** The 1024 normal image vanished after I reassigned its node. Save images to disk immediately, or set `use_fake_user`.

---

## 6. Preview rendering headless (`exp6_render.py`)

The scene is 640×640: the 18k-quad pony, a ground plane, a sun light and a world colour.

| Engine | Result | Time per frame |
|---|---|---|
| **Cycles CPU, 32 spp + OpenImageDenoise** | works; OIDN available (`_cycles.with_openimagedenoise == True`) | **5.1 s** (includes sync and "Loading denoising kernels") |
| Cycles CPU, 64 spp + OIDN | works, clean | **8.0 s** |
| Cycles, 480², 32 spp, hair cards with alpha | works | 2.7 s |
| **Workbench, before installing EGL** | **the process aborts** with `Couldn't open libEGL.so.1: libEGL.so.1: cannot open shared object file` → SIGABRT, exit 134. **Cannot be caught with try/except** and kills the Python process. | n/a |
| EEVEE Next (`'BLENDER_EEVEE_NEXT'`), before EGL | same abort (GPU backend) | n/a |
| **Workbench, after `apt-get install libegl1 libegl-mesa0`** | works with Mesa llvmpipe (software). It prints a harmless `EGL Error (0x3009): EGL_BAD_MATCH`. | first frame 5.0 s cold; later runs 0.54 s first and **0.16–0.27 s** per frame after |
| **EEVEE Next, after EGL**, 16 TAA samples | works, looks close to Cycles | 27.2 s first-ever frame (shader compile); 9.2 s first frame once the Mesa cache is warm; **6.5 s** later frames |

- **Run Workbench and EEVEE in a subprocess** (or guarantee libEGL is present) so an abort cannot kill the pipeline. Cycles needs no EGL.
- In Workbench, `color_type='MATERIAL'` uses `material.diffuse_color` (viewport display colour), not the Principled node colour.

---

## 7. Shape keys, Data Transfer, Surface Deform (`exp7_shapekeys_transfer.py`)

```python
# shape key from an evaluated modifier stack (disable the armature modifier first, or the pose leaks in)
arm_mod.show_viewport = False
dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg)
co = np.empty(len(ev.data.vertices) * 3, np.float32); ev.data.vertices.foreach_get("co", co)
body.shape_key_add(name="Basis", from_mix=False)
body.shape_key_add(name="Breathe", from_mix=False).data.foreach_set("co", co)     # 0.01 s
# operator variant also works headless:
bpy.ops.object.modifier_apply_as_shapekey(modifier="Bulge", keep_modifier=False)  # {'FINISHED'}
```

- `modifier_apply_as_shapekey` printed the harmless line `RNA_boolean_get: OBJECT_OT_modifier_apply_as_shapekey.use_selected_objects not found.`
- It also printed `Info: Applied modifier was not first, result may not be as expected`, because the Armature modifier was first in the stack.
- Shape keys built purely in numpy (Basis plus a normal offset) work too.

**Accessory test:** a saddle pad built from body faces offset 12 mm and subdivided, so its topology differs from the body: 7,593 v.

```python
dt = pad.modifiers.new("DT", 'DATA_TRANSFER'); dt.object = body
dt.use_vert_data = True; dt.data_types_verts = {'VGROUP_WEIGHTS'}; dt.vert_mapping = 'POLYINTERP_NEAREST'
dt.layers_vgroup_select_src = 'ALL'; dt.layers_vgroup_select_dst = 'NAME'
make_active(pad)
bpy.ops.object.datalayout_transfer(modifier="DT")   # creates destination groups (required!)
bpy.ops.object.modifier_apply(modifier="DT")        # 0.04 s total -> 27 groups

sd = pad.modifiers.new("SD", 'SURFACE_DEFORM'); sd.target = body
bpy.ops.object.surfacedeform_bind(modifier="SD")    # 0.05 s, sd.is_bound == True (bind with all body keys at 0)
# then for each body key: set value=1, read pad.evaluated_get(dg) coords -> pad.shape_key_add(...).data.foreach_set
```

- **Data Transfer:**
  - Transferred weights sum to 0.93–0.99 per vertex, so renormalize them.
  - The mean L1/2 difference to the nearest body face's weights was 0.011.
- **Surface Deform:**
  - Under the body key `Inflate=1` (+25 mm), the pad keeps its 12.0 mm gap with Surface Deform. Without it, the gap shrinks to 6.7 mm (body pushes into the pad).
  - Baking the body's keys into pad shape keys through Surface Deform works: max offset 0.025 m, as expected. Keys that don't touch the pad region correctly give 0.
- After the transfer, I removed Surface Deform and gave the pad its own Armature modifier and the transferred weights. It exports fine (section 9).

---

## 8. Hair cards and curve/hair → mesh (`exp8*.py`)

- **Procedural strand alpha texture:** 256×1024 RGBA, 40 tapered, swaying Gaussian strands, built in numpy. `img.pixels.foreach_set(rgba.ravel())` (rows go bottom→top) then `img.save()`. Took 0.31 s.
- **Procedural cards:** 60 mane cards × 8 segments.
  - Each root is snapped to the body surface with `BVHTree.find_nearest`. The guide grows along the normal and then droops.
  - The ribbon width tapers, and U runs across the card, V along it.
  - Build: `from_pydata`, then `uv_layers.new()`, then a per-loop UV `foreach_set`. 0.03 s, 1,080 v / 480 quads.
  - Material: image Color → Base Color, Alpha → Alpha, `blend_method='HASHED'`.
  - The Cycles render shows alpha strands correctly (`out/exp8_cards_cycles.png`). Making them look good still needs art work.
- **Legacy Curve with `extrude` (ribbon) → mesh:** `new_from_object` or `bpy.ops.object.convert(target='MESH')` produce faces **with a `UVMap`**: 26 v / 12 f.
- **New hair Curves** (`bpy.data.hair_curves.new`, `add_curves([6]*200)`, `position_data.foreach_set("vector", ...)`):
  - `bpy.ops.object.convert(target='MESH')` works, but gives **wire edges only** (0 faces).
  - It produces 12,200 verts because the default Catmull-Rom resolution is applied.
- **Curves + Geometry Nodes "Curve to Mesh"** (line profile → flat ribbons), with the node tree built in Python via `ng.interface.new_socket` and `nodes.new`:
  - `bpy.data.meshes.new_from_object()` and `evaluated.to_mesh()` on the Curves object **fail** with `RuntimeError: Error: Object does not have geometry data`.
  - `bpy.ops.object.convert(target='MESH')` **works**: 24,400 v / 12,000 faces, but **no UVs**.
  - Alternative that also works: put the GN modifier on an empty *mesh* object and read the curves through an `Object Info` node. Then `new_from_object` works (6,100 v / 3,000 f).
- **Legacy particle hair → mesh:** `bpy.ops.object.modifier_convert(modifier="Hair")` works (0.01 s, 500 strands → 2,500 v / 2,000 edges, wire only).
- **Recommendation:** generate cards directly in numpy. It is fully controllable, gives proper UVs and costs 30 ms.

---

## 9. glTF export headless (`exp9*.py`)

**Content:** an armature (27 bones), the body (Armature modifier, 3 shape keys), the saddle pad (transferred weights, 3 shape keys), and 3 armature actions (Walk 1–25, Graze 1–41, Idle 1–49). Each action was pushed to its own NLA track. A shape-key action sits on the body's Key, in an NLA track.

```python
bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', export_animations=True,
    export_animation_mode='ACTIONS',          # also tested 'NLA_TRACKS' (same output here)
    export_skins=True, export_influence_nb=4, export_def_bones=False,
    export_morph=True, export_morph_normal=True, export_morph_animation=True,
    export_apply=False,                        # keep False, or shape keys are lost
    export_yup=True, export_force_sampling=True, export_optimize_animation_size=True)
```

- **Works headless:** 0.70–0.89 s.
- **Result:** 1 skin with 27 joints. Each mesh has `JOINTS_0`/`WEIGHTS_0` (u8 joints), 3 morph targets with `extras.targetNames`, `NORMAL` and `TEXCOORD_0`. There are 3 animations, each sampled as 27×(translation, rotation, scale) = 81 channels.
- **Merging shape-key animation into a skeletal clip:**
  - When the shape-key NLA track is named `"Idle"`, the same as the armature action and track, the exporter **merges** its `weights` channel into animation `Idle` (82 channels).
  - When the track is named `"BreathTrack"`, it becomes a **separate** glTF animation `BreathTrack` with 1 channel, in both ACTIONS and NLA_TRACKS modes.
  - Name the tracks the same to get one clip per behaviour.
  - Each mesh needs its own Key NLA track. The pad's keys were not animated here.
- **Re-import** with `bpy.ops.import_scene.gltf` took 0.61 s. Both meshes come back with 3 keys and 27 groups. Actions: `Graze_PonyRig`, `Idle_PonyRig`, `Idle_PonyMC.001`, `Walk_PonyRig`.
- **Pitfall: flat shading.** The QuadriFlow output was flat-shaded, which split every vertex per face: 72,838 glTF vertices instead of 18,212, and **10.35 MB**. After `mesh.shade_smooth()` the export has 18,658 vertices (seam splits only) and is **2.78 MB**.
- **Other export messages:**
  - The exporter always prints `ERROR Draco mesh compression is not available because library could not be found at .../libextern_draco.so`. The pip bpy wheel has no Draco. This is harmless unless you enable Draco.
  - It also warns about more than 4 influences (see section 4).

---

## Recommended pipeline (from what was measured)

1. **Model:** numpy SDF (smooth-min primitives) at res 160–256, 3–17 s. Then skimage marching cubes, `mesh_from_numpy`, `remove_doubles(4e-4)`, and `voxel_remesh(0.012)` (0.3 s).
2. **Retopo:** `remove_doubles(4e-4)`, then `quadriflow_remesh(20000)` (about 20 s). Check that the face count changed, then `shade_smooth()`.
3. **UV:** Dijkstra landmark seams, then `uv.unwrap(ANGLE_BASED)` (5 s), then average scale and pack.
4. **Rig:** edit-bones armature, then `parent_set('ARMATURE_AUTO')` at meter scale (0.85 s). Verify there are no zero-weight vertices. The fallback is `heatweights.heat_weights` (0.5 s). Limit to 4 influences *continuously* before export.
5. **Shape keys:** numpy or an evaluated modifier stack. Accessories get weights via Data Transfer and keys via Surface Deform evaluation.
6. **Bake:** high-res displaced mesh → normal map (2048: 7 s), AO (1024: 5 s), position EXR (0.4 s).
7. **Preview:** Cycles 32 spp + OIDN (about 5 s per frame). Workbench (0.2–0.5 s per frame) and EEVEE (about 6.5 s per frame) need libEGL and should run in a subprocess.
8. **Export:** GLB via `export_scene.gltf` (under 1 s). Use one NLA track name per clip, shared between armature and shape-key tracks.
