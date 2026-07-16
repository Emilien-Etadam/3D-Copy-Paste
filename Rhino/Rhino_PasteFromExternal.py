#! python 3
# OD_CopyPasteExternal — Paste From External (Rhino 8, CPython ScriptEditor)
#
# Rebuilds a Rhino.Geometry.Mesh from the ODVertexData exchange file written
# by any supported application. The file format is specified in
# docs/FORMAT.md at the repository root; the parser accepts everything
# historical writers produce (mixed continuous/discontinuous UV samples,
# None placeholders, CRLF endings, any section order, n-gons, FACE/SUBD/CCSS
# polygon types, both deprecated VERTEXNORMALS dialects).
#
# Triangles and quads map to native mesh faces; n-gons are fan-triangulated
# and regrouped as Rhino ngons. Texture coordinates are applied per vertex
# (Rhino has a single TC per mesh vertex, so UV seams are collapsed with a
# console note). Weight and morph maps have no Rhino equivalent and are
# reported, then skipped.

import os
import tempfile

import Rhino
import scriptcontext as sc
import System

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"


def data_file_path():
    """OD_CPE_PATH directory override, else the shared system temp dir."""
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def _log(message):
    Rhino.RhinoApp.WriteLine("OD_CopyPasteExternal: " + message)


def _floats(token_line):
    return [float(t) for t in token_line.split()]


def parse(text):
    """Parse ODVertexData text into a plain dict (pure Python, no Rhino).

    Returns {"vertices": [(x, y, z)], "polygons": [(indices, surface, ptype)],
    "uv_maps": {name: [(u, v, poly | None, vert)]}, "ignored": [names]}.
    Raises ValueError on malformed input.
    """
    lines = text.splitlines()
    data = {"vertices": [], "polygons": [], "uv_maps": {}, "ignored": []}

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
        elif line.startswith("WEIGHT:") or line.startswith("MORPH:"):
            data["ignored"].append(line.split(":", 1)[1].strip())
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
                if len(fields) >= 5:  # u v:PLY:<poly>:PNT:<vert>  discontinuous
                    samples.append((uv[0], uv[1], int(fields[2].strip()), int(fields[4].strip())))
                elif len(fields) == 3:  # u v:PNT:<vert>  continuous
                    samples.append((uv[0], uv[1], None, int(fields[2].strip())))
                else:
                    raise ValueError("bad UV line: %r" % uline)
            data["uv_maps"][name] = samples
            i += 1 + count
        elif line.startswith("VERTEXNORMALS"):
            # Deprecated section, two dialects; payload count is the last
            # header field in both. Skip it.
            try:
                count = int(line.split(":")[-1].strip())
            except (ValueError, IndexError):
                count = 0
            i += 1 + count
        else:
            i += 1
    return data


def build_mesh(data, scale):
    """Build a Rhino Mesh from parsed data (file space -> Rhino space)."""
    mesh = Rhino.Geometry.Mesh()

    # File space is right-handed Y-up in meters; Rhino is right-handed Z-up
    # in document units. Pure rotation: winding is preserved.
    for x, y, z in data["vertices"]:
        mesh.Vertices.Add(x * scale, -z * scale, y * scale)

    subd_polys = 0
    for indices, _surface, ptype in data["polygons"]:
        if ptype in ("SUBD", "CCSS"):
            subd_polys += 1
        # Collapse consecutive duplicate indices (legacy writers encode some
        # triangles as quads with a repeated corner).
        unique = [indices[0]]
        for idx in indices[1:]:
            if idx != unique[-1]:
                unique.append(idx)
        if len(unique) > 1 and unique[0] == unique[-1]:
            unique.pop()
        if len(unique) < 3:
            continue
        if len(unique) == 3:
            mesh.Faces.AddFace(unique[0], unique[1], unique[2])
        elif len(unique) == 4:
            mesh.Faces.AddFace(unique[0], unique[1], unique[2], unique[3])
        else:
            fan = [
                mesh.Faces.AddFace(unique[0], unique[k], unique[k + 1])
                for k in range(1, len(unique) - 1)
            ]
            try:
                ngon = Rhino.Geometry.MeshNgon.Create(unique, fan)
                mesh.Ngons.AddNgon(ngon)
            except Exception:
                pass  # fan faces alone are a valid fallback

    # Rhino stores one texture coordinate per vertex: apply the first UV map,
    # continuous samples first so discontinuous ones win where both exist.
    if data["uv_maps"]:
        name = next(iter(data["uv_maps"]))
        samples = data["uv_maps"][name]
        tcs = [(0.0, 0.0)] * len(data["vertices"])
        touched = [False] * len(data["vertices"])
        seams = 0
        for poly in (None, "discontinuous"):
            for u, v, sample_poly, vert in samples:
                if (sample_poly is None) != (poly is None):
                    continue
                if 0 <= vert < len(tcs):
                    if touched[vert] and tcs[vert] != (u, v):
                        seams += 1
                    tcs[vert] = (u, v)
                    touched[vert] = True
        for u, v in tcs:
            mesh.TextureCoordinates.Add(u, v)
        if seams:
            _log(
                "UV map '%s' has %d seam samples; Rhino stores one UV per vertex, "
                "so seams were collapsed (last value wins)." % (name, seams)
            )
        if len(data["uv_maps"]) > 1:
            _log(
                "file has %d UV maps; only '%s' was applied."
                % (len(data["uv_maps"]), name)
            )

    if subd_polys:
        _log(
            "%d polygons are SUBD/CCSS subdivision cages; pasted as plain faces "
            "(use SubDFromMesh to re-subdivide)." % subd_polys
        )
    return mesh


def paste_from_external():
    path = data_file_path()
    if not os.path.exists(path):
        _log("no data file at %s — copy something first." % path)
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = parse(f.read())
    except (OSError, ValueError) as exc:
        _log("cannot read %s: %s" % (path, exc))
        return

    if data["ignored"]:
        _log(
            "ignored %d weight/morph maps (no Rhino equivalent): %s"
            % (len(data["ignored"]), ", ".join(data["ignored"]))
        )

    scale = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, sc.doc.ModelUnitSystem)
    mesh = build_mesh(data, scale)
    if mesh.Faces.Count == 0:
        _log("file contains no usable polygons.")
        return

    mesh.Normals.ComputeNormals()
    mesh.Compact()
    if not mesh.IsValid:
        _log("warning: pasted mesh reports as invalid (kept anyway — check it).")

    attributes = sc.doc.CreateDefaultAttributes()
    attributes.Name = "ODCopy"
    guid = sc.doc.Objects.AddMesh(mesh, attributes)
    if guid == System.Guid.Empty:
        _log("Rhino refused the mesh.")
        return
    sc.doc.Objects.Select(guid)
    sc.doc.Views.Redraw()
    _log(
        "pasted %d vertices / %d faces from %s"
        % (mesh.Vertices.Count, mesh.Faces.Count, path)
    )


if __name__ == "__main__":
    paste_from_external()
