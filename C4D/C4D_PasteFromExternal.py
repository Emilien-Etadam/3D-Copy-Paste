# OD_CopyPasteExternal — Paste From External (Cinema 4D R23+/2024+, Python 3)
#
# Native c4d rewrite replacing the historical OBJ-dialog wrapper (upstream
# #57/#66). Rebuilds the ODVertexData exchange file (docs/FORMAT.md) as a
# PolygonObject: tris/quads native, n-gons fan-triangulated, UV maps as a
# UVW tag (discontinuous samples override continuous ones), weight maps as
# Vertex Map tags, one material per surface name (with polygon selections
# when there are several). Morph maps have no straightforward C4D target
# and are reported in the console, then skipped.
#
# Axis/UV conventions are the mirror of the copy script: Z negated, winding
# reversed, V flipped; the format's meters convert to the document scale.
#
# Install: Extensions > Script Manager, load this file, run.

import os
import tempfile

import c4d

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def document_scale_to_meters(doc):
    try:
        unit_data = doc[c4d.DOCUMENT_DOCUNIT]
        scale, unit = unit_data.GetUnitScale()
        meters_per_unit = {
            c4d.DOCUMENT_UNIT_KM: 1000.0,
            c4d.DOCUMENT_UNIT_M: 1.0,
            c4d.DOCUMENT_UNIT_CM: 0.01,
            c4d.DOCUMENT_UNIT_MM: 0.001,
            c4d.DOCUMENT_UNIT_MICRO: 1e-6,
        }.get(unit)
        if meters_per_unit is not None:
            return scale * meters_per_unit
    except Exception:
        pass
    return 0.01


def _floats(token_line):
    return [float(t) for t in token_line.split()]


def parse(text):
    """Full-format parser; returns a plain dict (pure Python, no c4d)."""
    lines = text.splitlines()
    data = {"vertices": [], "polygons": [], "weight_maps": {}, "morph_maps": {}, "uv_maps": {}}

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
            is_weight = line.startswith("WEIGHT:")
            name = line.split(":", 1)[1].strip()
            chunk = lines[i + 1 : i + 1 + vcount]
            if len(chunk) != vcount:
                raise ValueError("truncated WEIGHT/MORPH section")
            if is_weight:
                data["weight_maps"][name] = [
                    None if t.strip() == "None" else float(t.strip()) for t in chunk
                ]
            else:
                data["morph_maps"][name] = True  # presence only; skipped on paste
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


def build_faces(polygons):
    """Fan-triangulate n-gons, reverse winding; return (faces, kept).

    faces: list of corner lists (3 or 4 indices, file winding reversed for
    C4D's left-handed convention); kept: original polygon index per face.
    """
    faces, kept = [], []
    for original, (indices, _surface) in enumerate(polygons):
        unique = [indices[0]]
        for idx in indices[1:]:
            if idx != unique[-1]:
                unique.append(idx)
        if len(unique) > 1 and unique[0] == unique[-1]:
            unique.pop()
        if len(unique) < 3:
            continue
        if len(unique) <= 4:
            faces.append(list(reversed(unique)))
            kept.append(original)
        else:
            for k in range(1, len(unique) - 1):
                faces.append([unique[k + 1], unique[k], unique[0]])
                kept.append(original)
    return faces, kept


def resolve_corner_uvs(polygons, faces, kept, samples):
    """Per built face: list of (u, v) per corner, or None if incomplete."""
    continuous, discontinuous = {}, {}
    for u, v, poly, vertex in samples:
        if poly is None:
            continuous[vertex] = (u, v)
        else:
            discontinuous[(poly, vertex)] = (u, v)
    result = []
    for face, original in zip(faces, kept):
        corner_uvs = []
        for idx in face:
            uv = discontinuous.get((original, idx), continuous.get(idx))
            if uv is None:
                corner_uvs = None
                break
            corner_uvs.append(uv)
        result.append(corner_uvs)
    return result


def main():
    doc = c4d.documents.GetActiveDocument()
    path = data_file_path()
    if not os.path.exists(path):
        c4d.gui.MessageDialog(
            "OD_CopyPasteExternal: no data file at %s — copy something first." % path
        )
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = parse(f.read())
    except (OSError, ValueError) as exc:
        c4d.gui.MessageDialog("OD_CopyPasteExternal: cannot read %s\n%s" % (path, exc))
        return

    faces, kept = build_faces(data["polygons"])
    if not faces:
        c4d.gui.MessageDialog("OD_CopyPasteExternal: file contains no usable polygons.")
        return

    scale = document_scale_to_meters(doc)
    obj = c4d.PolygonObject(len(data["vertices"]), len(faces))
    obj.SetName("ODCopy")
    points = [
        c4d.Vector(x / scale, y / scale, -z / scale)  # file RH -> C4D LH
        for x, y, z in data["vertices"]
    ]
    obj.SetAllPoints(points)
    for fi, face in enumerate(faces):
        if len(face) == 4:
            obj.SetPolygon(fi, c4d.CPolygon(face[0], face[1], face[2], face[3]))
        else:
            obj.SetPolygon(fi, c4d.CPolygon(face[0], face[1], face[2]))

    # UVW tag from the first UV map
    if data["uv_maps"]:
        name = next(iter(data["uv_maps"]))
        corner_uvs = resolve_corner_uvs(data["polygons"], faces, kept, data["uv_maps"][name])
        uvw_tag = c4d.UVWTag(len(faces))
        for fi, uvs in enumerate(corner_uvs):
            if uvs is None:
                continue
            vectors = [c4d.Vector(u, 1.0 - v, 0.0) for u, v in uvs]  # V flip back
            while len(vectors) < 4:
                vectors.append(vectors[-1])
            uvw_tag.SetSlow(fi, vectors[0], vectors[1], vectors[2], vectors[3])
        obj.InsertTag(uvw_tag)

    # Weight maps -> Vertex Map tags
    for name, values in data["weight_maps"].items():
        tag = c4d.VariableTag(c4d.Tvertexmap, len(points))
        tag.SetName(name)
        tag.SetAllHighlevelData([0.0 if w is None else float(w) for w in values])
        obj.InsertTag(tag)

    # Materials: one per surface, polygon selections when several
    surfaces = {}
    for face_index, original in enumerate(kept):
        surfaces.setdefault(data["polygons"][original][1] or "Default", []).append(face_index)
    doc.StartUndo()
    for surface, face_list in surfaces.items():
        material = None
        for existing in doc.GetMaterials():
            if existing.GetName() == surface:
                material = existing
                break
        if material is None:
            material = c4d.BaseMaterial(c4d.Mmaterial)
            material.SetName(surface)
            doc.InsertMaterial(material)
            doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, material)
        texture_tag = c4d.TextureTag()
        texture_tag[c4d.TEXTURETAG_MATERIAL] = material
        texture_tag[c4d.TEXTURETAG_PROJECTION] = c4d.TEXTURETAG_PROJECTION_UVW
        if len(surfaces) > 1:
            selection = c4d.SelectionTag(c4d.Tpolygonselection)
            selection.SetName(surface)
            baseselect = selection.GetBaseSelect()
            for face_index in face_list:
                baseselect.Select(face_index)
            obj.InsertTag(selection)
            texture_tag[c4d.TEXTURETAG_RESTRICTION] = surface
        obj.InsertTag(texture_tag)

    obj.Message(c4d.MSG_UPDATE)
    doc.InsertObject(obj)
    doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, obj)
    doc.EndUndo()
    doc.SetActiveObject(obj)
    c4d.EventAdd()

    if data["morph_maps"]:
        print(
            "OD_CopyPasteExternal: ignored %d morph maps (no direct C4D target): %s"
            % (len(data["morph_maps"]), ", ".join(data["morph_maps"]))
        )
    print(
        "OD_CopyPasteExternal: pasted %d vertices / %d polygons (%d weight maps) from %s"
        % (len(points), len(faces), len(data["weight_maps"]), path)
    )


if __name__ == "__main__":
    main()
