# OD_CopyPasteExternal — Copy To External (3ds Max 2021+, Python 3 + pymxs)
#
# pymxs rewrite replacing the MaxPlus scripts (MaxPlus was removed in Max
# 2020, upstream #56). Writes the selected objects to the ODVertexData
# exchange file (docs/FORMAT.md): world-space triangle meshes (via
# snapshotAsMesh, so modifiers and transforms are baked), per-object
# material names, map channel 1 as discontinuous UV samples.
#
# 3ds Max is Z-up right-handed like Blender: coordinates map to the
# format's Y-up as (x, z, -y), a pure rotation, winding unchanged. System
# units convert to the format's meters.
#
# Run: Scripting > Run Script... (or wrap in a macroscript for a button).

import os
import tempfile

from pymxs import runtime as rt

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _num(value):
    return repr(float(value))


def system_scale_to_meters():
    """Meters per Max system unit (best effort; Max defaults to inches)."""
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


def serialize(data):
    """data: {vertices, polygons: [(indices, surface)], uv_samples}"""
    lines = ["VERTICES:%d" % len(data["vertices"])]
    for v in data["vertices"]:
        lines.append("%s %s %s" % (_num(v[0]), _num(v[1]), _num(v[2])))
    lines.append("POLYGONS:%d" % len(data["polygons"]))
    for indices, surface in data["polygons"]:
        surface = (surface or "Default").replace(";;", "__")
        lines.append("%s;;%s;;FACE" % (",".join(str(i) for i in indices), surface))
    if data["uv_samples"]:
        lines.append("UV:UVMap:%d" % len(data["uv_samples"]))
        for u, v, face, vertex in data["uv_samples"]:
            lines.append("%s %s:PLY:%d:PNT:%d" % (_num(u), _num(v), face, vertex))
    return "\n".join(lines) + "\n"


def collect():
    selection = list(rt.selection)
    if not selection:
        return None
    scale = system_scale_to_meters()
    data = {"vertices": [], "polygons": [], "uv_samples": []}
    for node in selection:
        try:
            mesh = rt.snapshotAsMesh(node)  # world-space TriMesh, modifiers baked
        except RuntimeError:
            print("OD_CopyPasteExternal: skipped '%s' (cannot mesh it)" % node.name)
            continue
        offset = len(data["vertices"])
        face_offset = len(data["polygons"])
        surface = "Default"
        if node.material is not None and node.material.name:
            surface = str(node.material.name).replace(";;", "__")

        for vi in range(1, int(mesh.numVerts) + 1):  # MAXScript is 1-based
            p = rt.getVert(mesh, vi)
            # Z-up Max -> Y-up file: (x, z, -y)
            data["vertices"].append((p.x * scale, p.z * scale, -p.y * scale))

        has_uv = False
        try:
            has_uv = bool(rt.meshop.getMapSupport(mesh, 1))
        except RuntimeError:
            pass
        for fi in range(1, int(mesh.numFaces) + 1):
            face = rt.getFace(mesh, fi)
            corners = [int(face.x) - 1, int(face.y) - 1, int(face.z) - 1]
            data["polygons"].append(([offset + c for c in corners], surface))
            if has_uv:
                map_face = rt.meshop.getMapFace(mesh, 1, fi)
                map_ids = [int(map_face.x), int(map_face.y), int(map_face.z)]
                for k, c in enumerate(corners):
                    uvw = rt.meshop.getMapVert(mesh, 1, map_ids[k])
                    data["uv_samples"].append(
                        (uvw.x, uvw.y, face_offset + fi - 1, offset + c)
                    )
        rt.free(mesh)
    return data if data["vertices"] else None


def main():
    data = collect()
    if data is None:
        rt.messageBox("OD_CopyPasteExternal: select at least one geometric object.")
        return
    path = data_file_path()
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(serialize(data))
    except OSError as exc:
        rt.messageBox("OD_CopyPasteExternal: cannot write %s (%s)" % (path, exc))
        return
    print(
        "OD_CopyPasteExternal: copied %d vertices / %d triangles to %s"
        % (len(data["vertices"]), len(data["polygons"]), path)
    )


if __name__ == "__main__":
    main()
