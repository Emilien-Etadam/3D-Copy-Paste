#! python 3
# OD_CopyPasteExternal — Copy To External (Rhino 8, CPython ScriptEditor)
#
# Writes the selected mesh objects to the ODVertexData exchange file so they
# can be pasted in any other supported application. The file format is
# specified in docs/FORMAT.md at the repository root; this script emits the
# canonical writer output (VERTICES first, discontinuous UV samples, 0-based
# indices, right-handed Y-up coordinates in meters).
#
# Breps, extrusions and SubDs are copied through their existing render mesh,
# with an explicit console warning — nothing is meshed silently.

import os
import tempfile

import Rhino
import scriptcontext as sc

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    """OD_CPE_PATH directory override, else the shared system temp dir."""
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _log(message):
    Rhino.RhinoApp.WriteLine("OD_CopyPasteExternal: " + message)


def _num(value):
    return repr(float(value))


def gather_selection():
    """Return [(RhinoObject, Mesh)] for the selection (prompting if empty).

    Mesh objects are used as-is. Breps/extrusions/SubDs contribute their
    existing render mesh (with a console warning); objects that have no
    render mesh yet are skipped with an explanation.
    """
    objects = list(sc.doc.Objects.GetSelectedObjects(False, False))
    if not objects:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("Select meshes to copy (Breps/SubDs use their render mesh)")
        go.GeometryFilter = (
            Rhino.DocObjects.ObjectType.Mesh
            | Rhino.DocObjects.ObjectType.Brep
            | Rhino.DocObjects.ObjectType.Extrusion
            | Rhino.DocObjects.ObjectType.SubD
        )
        go.SubObjectSelect = False
        go.GetMultiple(1, 0)
        if go.CommandResult() != Rhino.Commands.Result.Success:
            return []
        objects = [objref.Object() for objref in go.Objects()]

    result = []
    for obj in objects:
        name = obj.Name or str(obj.Id)
        geometry = obj.Geometry
        if isinstance(geometry, Rhino.Geometry.Mesh):
            result.append((obj, geometry))
            continue
        render_meshes = obj.GetMeshes(Rhino.Geometry.MeshType.Render)
        if render_meshes:
            combined = Rhino.Geometry.Mesh()
            for m in render_meshes:
                combined.Append(m)
            _log(
                "'%s' is not a mesh — using its render mesh (%d faces). "
                "Run the Mesh command first if you want to control the meshing."
                % (name, combined.Faces.Count)
            )
            result.append((obj, combined))
        else:
            _log(
                "skipped '%s': no render mesh available yet "
                "(display it in a shaded viewport once, or use the Mesh command)." % name
            )
    return result


def surface_name(obj):
    try:
        material = obj.GetMaterial(True)
        if material and material.Name:
            return material.Name.replace(";;", "__")
    except Exception:
        pass
    return "Default"


def copy_to_external():
    selection = gather_selection()
    if not selection:
        _log("nothing to copy.")
        return

    # File space is right-handed Y-up in meters (OBJ convention); Rhino is
    # right-handed Z-up in document units. The axis mapping is a pure
    # rotation, so face winding is preserved.
    scale = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Meters)

    vertices = []  # file-space coordinate strings
    faces = []  # (index list, surface name)
    uv_samples = []  # (u, v, face index, vertex index)

    for obj, mesh in selection:
        offset = len(vertices)
        surface = surface_name(obj)
        for i in range(mesh.Vertices.Count):
            v = mesh.Vertices[i]
            x, y, z = v.X * scale, v.Y * scale, v.Z * scale
            vertices.append("%s %s %s" % (_num(x), _num(z), _num(-y)))

        has_uvs = mesh.TextureCoordinates.Count == mesh.Vertices.Count > 0
        for fi in range(mesh.Faces.Count):
            face = mesh.Faces[fi]
            if face.IsQuad:
                corners = [face.A, face.B, face.C, face.D]
            else:
                corners = [face.A, face.B, face.C]
            indices = [offset + c for c in corners]
            file_face_index = len(faces)
            faces.append((indices, surface))
            if has_uvs:
                for c in corners:
                    tc = mesh.TextureCoordinates[c]
                    uv_samples.append((tc.X, tc.Y, file_face_index, offset + c))

    if not vertices or not faces:
        _log("selection contains no mesh geometry.")
        return

    lines = ["VERTICES:%d" % len(vertices)]
    lines.extend(vertices)
    lines.append("POLYGONS:%d" % len(faces))
    for indices, surface in faces:
        lines.append("%s;;%s;;FACE" % (",".join(str(i) for i in indices), surface))
    if uv_samples:
        lines.append("UV:UVMap:%d" % len(uv_samples))
        for u, v, face_index, vertex_index in uv_samples:
            lines.append(
                "%s %s:PLY:%d:PNT:%d" % (_num(u), _num(v), face_index, vertex_index)
            )

    path = data_file_path()
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
    except OSError as exc:
        _log("cannot write %s: %s" % (path, exc))
        return
    _log(
        "copied %d vertices / %d polygons (%d objects) to %s"
        % (len(vertices), len(faces), len(selection), path)
    )


if __name__ == "__main__":
    copy_to_external()
