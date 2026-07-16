# OD_CopyPasteExternal — Paste From External (Maya 2022+, Python 3)
#
# OpenMaya 2.0 rewrite of the original script. Rebuilds a mesh from the
# ODVertexData exchange file (docs/FORMAT.md): polygons of any size are
# created natively (Maya supports n-gons), every UV map becomes a UV set
# with true per-face-vertex (discontinuous) assignment, surface names
# become lambert shaders, and morph maps become blend-shape targets.
# Weight maps have no free-standing Maya equivalent (skin weights need a
# joint hierarchy): they are listed in the script editor and skipped.
#
# The file space is meters, Y-up right-handed with OBJ winding; Maya's
# internal unit is centimeters with identical axes and winding, so the
# only conversion is a x100 scale. The historical 90-degree rotation of
# the old paste script (audit F16) is gone: copy and paste are now exact
# inverses.

import os
import re
import tempfile

import maya.api.OpenMaya as om
import maya.cmds as cmds

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"
M_TO_CM = 100.0


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _log(message):
    om.MGlobal.displayInfo("OD_CopyPasteExternal: " + message)


def _warn(message):
    om.MGlobal.displayWarning("OD_CopyPasteExternal: " + message)


# ---- pure parsing and array building (no Maya API) --------------------------

def _floats(token_line):
    return [float(t) for t in token_line.split()]


def parse(text):
    """Parse ODVertexData text (full format) into a plain dict."""
    lines = text.splitlines()
    data = {
        "vertices": [],
        "polygons": [],  # (indices, surface, ptype)
        "weight_maps": {},
        "morph_maps": {},
        "uv_maps": {},  # name -> [(u, v, poly | None, vertex)]
    }

    vert_at = None
    for i, line in enumerate(lines):
        if line.startswith("VERTICES:"):
            vert_at = i
            break
    if vert_at is None:
        raise ValueError("no VERTICES section found")
    vcount = int(lines[vert_at].split(":")[1].strip())
    chunk = lines[vert_at + 1 : vert_at + 1 + vcount]
    if len(chunk) != vcount:
        raise ValueError("truncated VERTICES section")
    for vline in chunk:
        values = _floats(vline)
        if len(values) < 3:
            raise ValueError("bad vertex line: %r" % vline)
        data["vertices"].append((values[0], values[1], values[2]))

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("VERTICES:"):
            if i != vert_at:
                raise ValueError("multiple VERTICES sections (one mesh per file)")
            i += 1 + vcount
        elif line.startswith("POLYGONS:"):
            count = int(line.split(":")[1].strip())
            chunk = lines[i + 1 : i + 1 + count]
            if len(chunk) != count:
                raise ValueError("truncated POLYGONS section")
            for pline in chunk:
                parts = pline.split(";;")
                indices = [int(t.strip()) for t in parts[0].split(",")]
                surface = parts[1].strip() if len(parts) > 1 else "Default"
                ptype = parts[2].strip() if len(parts) > 2 else "FACE"
                for idx in indices:
                    if not 0 <= idx < vcount:
                        raise ValueError("polygon vertex index %d out of range" % idx)
                data["polygons"].append((indices, surface, ptype))
            i += 1 + count
        elif line.startswith("WEIGHT:"):
            name = line.split(":", 1)[1].strip()
            chunk = lines[i + 1 : i + 1 + vcount]
            if len(chunk) != vcount:
                raise ValueError("truncated WEIGHT section")
            data["weight_maps"][name] = [
                None if t.strip() == "None" else float(t.strip()) for t in chunk
            ]
            i += 1 + vcount
        elif line.startswith("MORPH:"):
            name = line.split(":", 1)[1].strip()
            chunk = lines[i + 1 : i + 1 + vcount]
            if len(chunk) != vcount:
                raise ValueError("truncated MORPH section")
            deltas = []
            for mline in chunk:
                token = mline.strip()
                if token == "None":
                    deltas.append(None)
                else:
                    values = _floats(token)
                    if len(values) < 3:
                        raise ValueError("bad morph line: %r" % mline)
                    deltas.append((values[0], values[1], values[2]))
            data["morph_maps"][name] = deltas
            i += 1 + vcount
        elif line.startswith("UV:"):
            head = line.split(":")
            if len(head) < 3:
                raise ValueError("bad UV header: %r" % line)
            name, count = head[1], int(head[2].strip())
            chunk = lines[i + 1 : i + 1 + count]
            if len(chunk) != count:
                raise ValueError("truncated UV section")
            samples = []
            for uline in chunk:
                fields = uline.split(":")
                uv = _floats(fields[0])
                if len(uv) < 2:
                    raise ValueError("bad UV line: %r" % uline)
                if len(fields) >= 5:
                    samples.append((uv[0], uv[1], int(fields[2].strip()), int(fields[4].strip())))
                elif len(fields) == 3:
                    samples.append((uv[0], uv[1], None, int(fields[2].strip())))
                else:
                    raise ValueError("bad UV line: %r" % uline)
            data["uv_maps"][name] = samples
            i += 1 + count
        elif line.startswith("VERTEXNORMALS"):
            try:
                count = int(line.split(":")[-1].strip())
            except (ValueError, IndexError):
                count = 0
            i += 1 + count
        else:
            i += 1
    return data


def build_face_arrays(polygons):
    """(faceCounts, faceConnects, kept_polygons) for MFnMesh.create.

    Collapses consecutive duplicate indices (legacy tri-as-quad encoding)
    and drops degenerate polygons; kept_polygons maps new face index ->
    original polygon index so surfaces/UVs stay aligned.
    """
    counts, connects, kept = [], [], []
    for original, (indices, _surface, _ptype) in enumerate(polygons):
        unique = [indices[0]]
        for idx in indices[1:]:
            if idx != unique[-1]:
                unique.append(idx)
        if len(unique) > 1 and unique[0] == unique[-1]:
            unique.pop()
        if len(unique) < 3:
            continue
        counts.append(len(unique))
        connects.extend(unique)
        kept.append(original)
    return counts, connects, kept


def resolve_uv_assignment(polygons, kept, samples):
    """(uv_values, uv_counts, uv_ids) for MFnMesh.setUVs/assignUVs.

    Discontinuous samples override continuous ones. A face is assigned
    only when every corner has a UV; unassigned faces get count 0.
    """
    continuous = {}
    discontinuous = {}
    for u, v, poly, vertex in samples:
        if poly is None:
            continuous[vertex] = (u, v)
        else:
            discontinuous[(poly, vertex)] = (u, v)

    uv_values = []
    uv_index = {}
    uv_counts = []
    uv_ids = []
    for original in kept:
        indices = polygons[original][0]
        corner_uvs = []
        for vertex in indices:
            uv = discontinuous.get((original, vertex), continuous.get(vertex))
            if uv is None:
                break
            corner_uvs.append(uv)
        if len(corner_uvs) != len(indices):
            uv_counts.append(0)
            continue
        uv_counts.append(len(corner_uvs))
        for uv in corner_uvs:
            if uv not in uv_index:
                uv_index[uv] = len(uv_values)
                uv_values.append(uv)
            uv_ids.append(uv_index[uv])
    return uv_values, uv_counts, uv_ids


def sanitize(name):
    """Make a file-side map/surface name usable as a Maya node name."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name) or "Default"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


# ---- Maya adapters ----------------------------------------------------------

def assign_materials(transform, polygons, kept):
    by_surface = {}
    for face, original in enumerate(kept):
        by_surface.setdefault(polygons[original][1] or "Default", []).append(face)
    if list(by_surface) == ["Default"]:
        cmds.sets(transform, edit=True, forceElement="initialShadingGroup")
        return
    for surface, faces in by_surface.items():
        shader = sanitize(surface)
        if not cmds.objExists(shader):
            shader = cmds.shadingNode("lambert", asShader=True, name=shader)
        groups = cmds.listConnections(shader + ".outColor", type="shadingEngine") or []
        if groups:
            sg = groups[0]
        else:
            sg = cmds.sets(
                renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG"
            )
            cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
        cmds.sets(
            ["%s.f[%d]" % (transform, f) for f in faces], edit=True, forceElement=sg
        )


def apply_uv_sets(fn_mesh, transform, data, kept):
    first = True
    for name, samples in data["uv_maps"].items():
        uv_values, uv_counts, uv_ids = resolve_uv_assignment(
            data["polygons"], kept, samples
        )
        if not uv_values or not any(uv_counts):
            continue
        if first:
            uv_set = fn_mesh.currentUVSetName()
            first = False
        else:
            created = cmds.polyUVSet(transform, create=True, uvSet=sanitize(name))
            uv_set = created[0] if created else sanitize(name)
        fn_mesh.setUVs(
            [uv[0] for uv in uv_values], [uv[1] for uv in uv_values], uv_set
        )
        fn_mesh.assignUVs(uv_counts, uv_ids, uv_set)


def apply_morphs(transform, data, points):
    if not data["morph_maps"]:
        return
    targets = []
    for name, deltas in data["morph_maps"].items():
        dup = cmds.duplicate(transform, name=sanitize(name))[0]
        sel = om.MSelectionList()
        sel.add(dup)
        fn_dup = om.MFnMesh(sel.getDagPath(0))
        moved = om.MPointArray(points)
        for i, delta in enumerate(deltas):
            if delta is not None and i < len(moved):
                moved[i] = om.MPoint(
                    points[i].x + delta[0] * M_TO_CM,
                    points[i].y + delta[1] * M_TO_CM,
                    points[i].z + delta[2] * M_TO_CM,
                )
        fn_dup.setPoints(moved, om.MSpace.kObject)
        targets.append(dup)
    cmds.blendShape(*(targets + [transform]), name="ODCopyMorphs")
    cmds.delete(targets)


def paste_from_external():
    path = data_file_path()
    if not os.path.exists(path):
        _warn("no data file at %s — copy something first." % path)
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = parse(f.read())
    except (OSError, ValueError) as exc:
        _warn("cannot read %s: %s" % (path, exc))
        return

    counts, connects, kept = build_face_arrays(data["polygons"])
    if not counts:
        _warn("file contains no usable polygons.")
        return

    points = om.MPointArray(
        [om.MPoint(x * M_TO_CM, y * M_TO_CM, z * M_TO_CM) for x, y, z in data["vertices"]]
    )
    fn = om.MFnMesh()
    mesh_obj = fn.create(points, counts, connects)
    transform = om.MFnDependencyNode(mesh_obj).setName("ODCopy")

    apply_uv_sets(fn, transform, data, kept)
    assign_materials(transform, data["polygons"], kept)
    apply_morphs(transform, data, points)

    if data["weight_maps"]:
        _warn(
            "ignored %d weight maps (skin weights need a joint hierarchy): %s"
            % (len(data["weight_maps"]), ", ".join(data["weight_maps"]))
        )
    subd = sum(1 for _i, _s, ptype in data["polygons"] if ptype in ("SUBD", "CCSS"))
    if subd:
        _log("%d polygons are SUBD/CCSS cages; pasted as plain faces (use 3 to smooth)." % subd)

    cmds.select(transform, replace=True)
    _log(
        "pasted %d vertices / %d faces (%d UV maps, %d morphs) from %s"
        % (len(points), len(counts), len(data["uv_maps"]), len(data["morph_maps"]), path)
    )


def main():
    paste_from_external()


if __name__ == "__main__":
    main()
