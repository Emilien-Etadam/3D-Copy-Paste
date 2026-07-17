# OD_CopyPasteExternal — Copy To External (Cinema 4D R23+/2024+, Python 3)
#
# Native c4d rewrite replacing the historical OBJ-dialog wrapper (upstream
# #57/#66): no export requester, no compiled converters. Writes the selected
# polygon objects to the ODVertexData exchange file (docs/FORMAT.md):
# world-space vertices, polygons with per-object material names, UVW tags as
# discontinuous UV samples, Vertex Map tags as weight maps.
#
# Cinema 4D is left-handed Y-up and the format (like OBJ) is right-handed:
# Z is negated and polygon winding reversed. C4D's UV origin is top-left,
# the format's bottom-left: V is flipped. Document scale converts to the
# format's meters.
#
# Install: Extensions > Script Manager, load this file, run (or assign a
# shortcut via Customize Commands).

import os
import tempfile

import c4d

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _num(value):
    return repr(float(value))


def document_scale_to_meters(doc):
    """Meters per document unit (best effort; 0.01 for the cm default)."""
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
    return 0.01  # C4D's historical 1 unit = 1 cm default


def serialize(data):
    """data: {vertices, polygons: [(indices, surface)], weight_maps, uv_samples}"""
    lines = ["VERTICES:%d" % len(data["vertices"])]
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
    if data["uv_samples"]:
        lines.append("UV:UVMap:%d" % len(data["uv_samples"]))
        for u, v, face, vertex in data["uv_samples"]:
            lines.append("%s %s:PLY:%d:PNT:%d" % (_num(u), _num(v), face, vertex))
    return "\n".join(lines) + "\n"


def object_surface(obj):
    for tag in obj.GetTags():
        if tag.GetType() == c4d.Ttexture:
            material = tag[c4d.TEXTURETAG_MATERIAL]
            if material is not None and material.GetName():
                return material.GetName().replace(";;", "__")
    return "Default"


def polygon_corners(poly):
    """CPolygon corner indices: triangle when c == d."""
    if poly.c == poly.d:
        return [poly.a, poly.b, poly.c]
    return [poly.a, poly.b, poly.c, poly.d]


def collect(doc):
    objects = [
        obj for obj in doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)
        if obj.IsInstanceOf(c4d.Opolygon)
    ]
    if not objects:
        return None

    scale = document_scale_to_meters(doc)
    data = {"vertices": [], "polygons": [], "weight_maps": {}, "uv_samples": []}
    for obj in objects:
        offset = len(data["vertices"])
        face_offset = len(data["polygons"])
        matrix = obj.GetMg()
        points = obj.GetAllPoints()
        for p in points:
            world = matrix * p
            # left-handed C4D -> right-handed file: negate Z
            data["vertices"].append(
                (world.x * scale, world.y * scale, -world.z * scale)
            )

        surface = object_surface(obj)
        uvw_tag = obj.GetTag(c4d.Tuvw)
        polygons = obj.GetAllPolygons()
        for fi, poly in enumerate(polygons):
            corners = polygon_corners(poly)
            reversed_corners = list(reversed(corners))  # mirror flips winding
            data["polygons"].append(
                ([offset + c for c in reversed_corners], surface)
            )
            if uvw_tag is not None:
                uvw = uvw_tag.GetSlow(fi)
                keys = ["a", "b", "c", "d"]
                per_corner = {corners[k]: uvw[keys[k]] for k in range(len(corners))}
                for c in reversed_corners:
                    uv = per_corner[c]
                    # C4D V origin is top-left; the format's is bottom-left
                    data["uv_samples"].append(
                        (uv.x, 1.0 - uv.y, face_offset + fi, offset + c)
                    )

        for tag in obj.GetTags():
            if tag.GetType() == c4d.Tvertexmap:
                name = tag.GetName().replace(":", "_") or "VertexMap"
                values = data["weight_maps"].setdefault(name, [None] * offset)
                values.extend(tag.GetAllHighlevelData())
        total = len(data["vertices"])
        for values in data["weight_maps"].values():
            if len(values) < total:
                values.extend([None] * (total - len(values)))
    return data


def main():
    doc = c4d.documents.GetActiveDocument()
    data = collect(doc)
    if data is None:
        c4d.gui.MessageDialog(
            "OD_CopyPasteExternal: select at least one polygon object.\n"
            "(Parametric objects: press C to make them editable first.)"
        )
        return
    path = data_file_path()
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(serialize(data))
    except OSError as exc:
        c4d.gui.MessageDialog("OD_CopyPasteExternal: cannot write %s\n%s" % (path, exc))
        return
    print(
        "OD_CopyPasteExternal: copied %d vertices / %d polygons (%d weight maps) to %s"
        % (len(data["vertices"]), len(data["polygons"]), len(data["weight_maps"]), path)
    )


if __name__ == "__main__":
    main()
