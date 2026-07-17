# OD_CopyPasteExternal — Paste From External (3ds Max 2021+, Python 3 + pymxs)
#
# pymxs rewrite replacing the MaxPlus scripts (upstream #56). Rebuilds the
# ODVertexData exchange file (docs/FORMAT.md) as an editable mesh:
# triangulated faces (Max TriMesh), map channel 1 from the first UV map
# (discontinuous samples override continuous), one material per surface
# name — a MultiMaterial with per-face material IDs when there are several.
# Weight and morph maps have no free-standing Max target and are reported,
# then skipped.
#
# Axis handling mirrors the copy script: file Y-up -> Max Z-up as
# (x, -z, y), winding unchanged; the format's meters convert to system
# units.
#
# Run: Scripting > Run Script...

import os
import tempfile

from pymxs import runtime as rt

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def system_scale_to_meters():
    try:
        per_unit = {
            rt.Name("inches"): 0.0254,
            rt.Name("feet"): 0.3048,
            rt.Name("miles"): 1609.344,
            rt.Name("millimeters"): 0.001,
            rt.Name("centimeters"): 0.01,
            rt.Name("meters"): 1.0,
            rt.Name("kilometers"): 1000.0,
        }.get(rt.units.SystemType)
        if per_unit is not None:
            return float(rt.units.SystemScale) * per_unit
    except Exception:
        pass
    return 1.0


def _floats(token_line):
    return [float(t) for t in token_line.split()]


def parse(text):
    """Full-format parser; returns a plain dict (pure Python, no pymxs)."""
    lines = text.splitlines()
    data = {"vertices": [], "polygons": [], "weight_maps": [], "morph_maps": [], "uv_maps": {}}

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
            i += 1 + vcount
        elif line.startswith("POLYGONS:"):
            count = int(line.split(":")[1].strip())
            chunk = lines[i + 1 : i + 1 + count]
            if len(chunk) != count:
                raise ValueError("truncated POLYGONS section")
            for pline in chunk:
                parts = pline.split(";;")
                indices = [int(t.strip()) for t in parts[0].split(",")]
                for idx in indices:
                    if not 0 <= idx < vcount:
                        raise ValueError("polygon index %d out of range" % idx)
                surface = parts[1].strip() if len(parts) > 1 else "Default"
                data["polygons"].append((indices, surface))
            i += 1 + count
        elif line.startswith("WEIGHT:") or line.startswith("MORPH:"):
            name = line.split(":", 1)[1].strip()
            key = "weight_maps" if line.startswith("WEIGHT:") else "morph_maps"
            data[key].append(name)  # names only; skipped on paste
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


def triangulate(polygons):
    """Fan-triangulate to Max TriMesh faces; return (triangles, kept).

    triangles: corner triples (file winding, unchanged for Max);
    kept: original polygon index per triangle.
    """
    triangles, kept = [], []
    for original, (indices, _surface) in enumerate(polygons):
        unique = [indices[0]]
        for idx in indices[1:]:
            if idx != unique[-1]:
                unique.append(idx)
        if len(unique) > 1 and unique[0] == unique[-1]:
            unique.pop()
        if len(unique) < 3:
            continue
        for k in range(1, len(unique) - 1):
            triangles.append([unique[0], unique[k], unique[k + 1]])
            kept.append(original)
    return triangles, kept


def resolve_corner_uvs(polygons, triangles, kept, samples):
    """Per triangle: [(u, v)] * 3, or None when a corner has no UV."""
    continuous, discontinuous = {}, {}
    for u, v, poly, vertex in samples:
        if poly is None:
            continuous[vertex] = (u, v)
        else:
            discontinuous[(poly, vertex)] = (u, v)
    result = []
    for tri, original in zip(triangles, kept):
        corner_uvs = []
        for idx in tri:
            uv = discontinuous.get((original, idx), continuous.get(idx))
            if uv is None:
                corner_uvs = None
                break
            corner_uvs.append(uv)
        result.append(corner_uvs)
    return result


def main():
    path = data_file_path()
    if not os.path.exists(path):
        rt.messageBox("OD_CopyPasteExternal: no data file at %s — copy something first." % path)
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = parse(f.read())
    except (OSError, ValueError) as exc:
        rt.messageBox("OD_CopyPasteExternal: cannot read %s (%s)" % (path, exc))
        return

    triangles, kept = triangulate(data["polygons"])
    if not triangles:
        rt.messageBox("OD_CopyPasteExternal: file contains no usable polygons.")
        return

    scale = system_scale_to_meters()
    verts = rt.Array()
    for x, y, z in data["vertices"]:
        # file Y-up -> Max Z-up: (x, -z, y)
        rt.append(verts, rt.Point3(x / scale, -z / scale, y / scale))
    faces = rt.Array()
    for tri in triangles:
        rt.append(faces, rt.Point3(tri[0] + 1, tri[1] + 1, tri[2] + 1))  # 1-based

    node = rt.mesh(vertices=verts, faces=faces)
    node.name = "ODCopy"
    mesh = node.mesh

    # Map channel 1 from the first UV map
    if data["uv_maps"]:
        name = next(iter(data["uv_maps"]))
        corner_uvs = resolve_corner_uvs(data["polygons"], triangles, kept, data["uv_maps"][name])
        rt.meshop.setMapSupport(mesh, 1, True)
        rt.meshop.setNumMapVerts(mesh, 1, max(1, 3 * len(triangles)), True)
        rt.meshop.setNumMapFaces(mesh, 1, len(triangles), True)
        next_id = 1
        for fi, uvs in enumerate(corner_uvs, start=1):
            if uvs is None:
                rt.meshop.setMapFace(mesh, 1, fi, rt.Point3(1, 1, 1))
                continue
            ids = []
            for u, v in uvs:
                rt.meshop.setMapVert(mesh, 1, next_id, rt.Point3(u, v, 0.0))
                ids.append(next_id)
                next_id += 1
            rt.meshop.setMapFace(mesh, 1, fi, rt.Point3(ids[0], ids[1], ids[2]))

    # Materials: one per surface; MultiMaterial + face IDs when several
    surfaces = {}
    for face_index, original in enumerate(kept, start=1):
        surfaces.setdefault(data["polygons"][original][1] or "Default", []).append(face_index)
    if len(surfaces) == 1:
        surface = next(iter(surfaces))
        if surface != "Default":
            material = rt.StandardMaterial(name=surface)
            node.material = material
    elif surfaces:
        multi = rt.MultiMaterial(numsubs=len(surfaces))
        for sub_id, (surface, face_list) in enumerate(surfaces.items(), start=1):
            multi.materialList[sub_id - 1] = rt.StandardMaterial(name=surface)
            for face_index in face_list:
                rt.setFaceMatID(mesh, face_index, sub_id)
        node.material = multi

    rt.update(mesh)
    rt.select(node)
    rt.redrawViews()

    skipped = data["weight_maps"] + data["morph_maps"]
    if skipped:
        print(
            "OD_CopyPasteExternal: ignored %d weight/morph maps (no free-standing Max target): %s"
            % (len(skipped), ", ".join(skipped))
        )
    print(
        "OD_CopyPasteExternal: pasted %d vertices / %d triangles from %s"
        % (len(data["vertices"]), len(triangles), path)
    )


if __name__ == "__main__":
    main()
