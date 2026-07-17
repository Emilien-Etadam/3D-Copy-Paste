# OD_CopyPasteExternal — Copy To External (Maya 2022+, Python 3)
#
# OpenMaya 2.0 rewrite of the original script. Exports the selected mesh
# shapes to the ODVertexData exchange file (docs/FORMAT.md): vertices,
# polygons (n-gons included) with per-face surface-shader names, every UV
# set (canonical discontinuous samples), skin-cluster weights (one WEIGHT
# section per influence) and blend-shape targets (sparse MORPH sections).
#
# Maya's internal linear unit is centimeters and the file space is meters:
# coordinates are scaled by 0.01 regardless of the UI unit. Maya is Y-up
# right-handed with OBJ-style winding, so axes and winding map 1:1.

import os
import tempfile

import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
import maya.cmds as cmds

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"
CM_TO_M = 0.01


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _log(message):
    om.MGlobal.displayInfo("OD_CopyPasteExternal: " + message)


def _warn(message):
    om.MGlobal.displayWarning("OD_CopyPasteExternal: " + message)


def _num(value):
    return repr(float(value))


# ---- pure serialization (no Maya API) --------------------------------------

def serialize(data):
    """Serialize the collected mesh data to canonical ODVertexData text.

    data = {"vertices": [(x, y, z)], "polygons": [(indices, surface)],
            "weight_maps": {name: [value | None]},
            "morph_maps": {name: [(dx, dy, dz) | None]},
            "uv_maps": {name: [(u, v, face, vertex)]}}
    """
    vcount = len(data["vertices"])
    lines = ["VERTICES:%d" % vcount]
    for v in data["vertices"]:
        lines.append("%s %s %s" % (_num(v[0]), _num(v[1]), _num(v[2])))
    lines.append("POLYGONS:%d" % len(data["polygons"]))
    for indices, surface in data["polygons"]:
        surface = (surface or "Default").replace(";;", "__")
        lines.append("%s;;%s;;FACE" % (",".join(str(i) for i in indices), surface))
    for name, values in data["weight_maps"].items():
        lines.append("WEIGHT:" + name.replace(":", "_"))
        for w in values:
            lines.append("None" if w is None else _num(w))
    for name, deltas in data["morph_maps"].items():
        lines.append("MORPH:" + name.replace(":", "_"))
        for d in deltas:
            if d is None:
                lines.append("None")
            else:
                lines.append("%s %s %s" % (_num(d[0]), _num(d[1]), _num(d[2])))
    for name, samples in data["uv_maps"].items():
        lines.append("UV:%s:%d" % (name.replace(":", "_"), len(samples)))
        for u, v, face, vertex in samples:
            lines.append("%s %s:PLY:%d:PNT:%d" % (_num(u), _num(v), face, vertex))
    return "\n".join(lines) + "\n"


def expand_components(component_strings):
    """Expand Maya component strings ('vtx[3]', 'vtx[5:8]') to indices."""
    indices = []
    for comp in component_strings or []:
        inner = comp[comp.index("[") + 1 : comp.index("]")]
        if ":" in inner:
            start, end = inner.split(":")
            indices.extend(range(int(start), int(end) + 1))
        else:
            indices.append(int(inner))
    return indices


# ---- Maya adapters ----------------------------------------------------------

def selected_mesh_paths():
    sel = om.MGlobal.getActiveSelectionList()
    paths = []
    for i in range(sel.length()):
        try:
            dag = sel.getDagPath(i)
            dag.extendToShape()
        except RuntimeError:
            continue
        if dag.hasFn(om.MFn.kMesh):
            paths.append(dag)
    return paths


def surface_names(fn_mesh, dag):
    """Per-face surface-shader names for one mesh."""
    default = "Default"
    try:
        shaders, face_shader = fn_mesh.getConnectedShaders(dag.instanceNumber())
    except RuntimeError:
        return [default] * fn_mesh.numPolygons
    names = []
    for sg in shaders:
        sg_name = om.MFnDependencyNode(sg).name()
        connected = cmds.listConnections(sg_name + ".surfaceShader") or []
        names.append(connected[0] if connected else sg_name)
    return [names[s] if 0 <= s < len(names) else default for s in face_shader]


def skin_weight_maps(dag, vertex_count):
    """{influence name: [weight per vertex]} for the mesh's skinCluster."""
    history = cmds.listHistory(dag.fullPathName(), pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster")
    if not clusters:
        return {}
    cluster = clusters[0]
    sel = om.MSelectionList()
    sel.add(cluster)
    fn_skin = oma.MFnSkinCluster(sel.getDependNode(0))
    comp_fn = om.MFnSingleIndexedComponent()
    components = comp_fn.create(om.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(vertex_count)
    flat, influence_count = fn_skin.getWeights(dag, components)
    influences = [
        om.MFnDependencyNode(path.node()).name()
        for path in fn_skin.influenceObjects()
    ]
    maps = {}
    for j, name in enumerate(influences):
        maps[name] = [flat[v * influence_count + j] for v in range(vertex_count)]
    return maps


def blend_shape_morphs(dag, vertex_count):
    """{target alias: [delta | None]} from the mesh's blendShape nodes."""
    history = cmds.listHistory(dag.fullPathName(), pruneDagObjects=True) or []
    morphs = {}
    for bs in cmds.ls(history, type="blendShape"):
        aliases = cmds.listAttr(bs + ".w", multi=True) or []
        for ti, alias in enumerate(aliases):
            item = "%s.inputTarget[0].inputTargetGroup[%d].inputTargetItem[6000]" % (bs, ti)
            try:
                comps = cmds.getAttr(item + ".inputComponentsTarget")
                points = cmds.getAttr(item + ".inputPointsTarget")
            except (RuntimeError, ValueError):
                continue
            if not comps or not points:
                continue
            deltas = [None] * vertex_count
            for vid, point in zip(expand_components(comps), points):
                if 0 <= vid < vertex_count:
                    deltas[vid] = (
                        point[0] * CM_TO_M,
                        point[1] * CM_TO_M,
                        point[2] * CM_TO_M,
                    )
            morphs[alias] = deltas
    return morphs


def collect():
    """Gather all selected meshes into one exchange-file data dict."""
    paths = selected_mesh_paths()
    if not paths:
        _warn("select at least one mesh to copy.")
        return None

    data = {
        "vertices": [],
        "polygons": [],
        "weight_maps": {},
        "morph_maps": {},
        "uv_maps": {},
    }
    for dag in paths:
        fn = om.MFnMesh(dag)
        offset = len(data["vertices"])
        face_offset = len(data["polygons"])
        points = fn.getPoints(om.MSpace.kObject)
        for p in points:
            data["vertices"].append((p.x * CM_TO_M, p.y * CM_TO_M, p.z * CM_TO_M))

        counts, connects = fn.getVertices()
        surfaces = surface_names(fn, dag)
        cursor = 0
        local_faces = []
        for f, count in enumerate(counts):
            indices = [offset + connects[cursor + k] for k in range(count)]
            local_faces.append([connects[cursor + k] for k in range(count)])
            surface = surfaces[f] if f < len(surfaces) else "Default"
            data["polygons"].append((indices, surface))
            cursor += count

        for uv_set in fn.getUVSetNames():
            try:
                us, vs = fn.getUVs(uv_set)
                uv_counts, uv_ids = fn.getAssignedUVs(uv_set)
            except RuntimeError:
                continue
            if not uv_ids:
                continue
            samples = data["uv_maps"].setdefault(uv_set, [])
            uv_cursor = 0
            for f, count in enumerate(uv_counts):
                for k in range(count):
                    uv_id = uv_ids[uv_cursor + k]
                    samples.append(
                        (
                            us[uv_id],
                            vs[uv_id],
                            face_offset + f,
                            offset + local_faces[f][k],
                        )
                    )
                uv_cursor += count

        vertex_count_total = len(data["vertices"])
        for name, values in skin_weight_maps(dag, len(points)).items():
            merged = data["weight_maps"].setdefault(name, [None] * offset)
            merged.extend(values)
        for name, deltas in blend_shape_morphs(dag, len(points)).items():
            merged = data["morph_maps"].setdefault(name, [None] * offset)
            merged.extend(deltas)
        # pad maps that this mesh did not contribute to
        for maps in (data["weight_maps"], data["morph_maps"]):
            for name, values in maps.items():
                if len(values) < vertex_count_total:
                    values.extend([None] * (vertex_count_total - len(values)))
    return data


def export_to_external():
    data = collect()
    if data is None:
        return
    path = data_file_path()
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(serialize(data))
    except OSError as exc:
        _warn("cannot write %s: %s" % (path, exc))
        return
    _log(
        "copied %d vertices / %d polygons (%d weight, %d morph, %d UV maps) to %s"
        % (
            len(data["vertices"]),
            len(data["polygons"]),
            len(data["weight_maps"]),
            len(data["morph_maps"]),
            len(data["uv_maps"]),
            path,
        )
    )


def main():
    export_to_external()


if __name__ == "__main__":
    main()
