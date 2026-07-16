# Parser/writer for the ODVertexData interchange format.
#
# The format is specified in docs/FORMAT.md at the repository root; this
# module implements the reader-conformance checklist of that spec and the
# canonical writer output. It is deliberately free of any bpy import so it
# can be exercised outside Blender (unit tests, other Python hosts).

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"

POLY_TYPES = ("FACE", "SUBD", "CCSS")


class ODFormatError(ValueError):
    """Raised when a file (or an in-memory mesh) violates the format."""


def data_file_path():
    """Resolve the exchange file location.

    Uses the OD_CPE_PATH environment variable when set (network share /
    Dropbox use case), otherwise the system temp directory shared by all
    ODVertexData implementations.
    """
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


@dataclass
class ODPolygon:
    indices: list
    surface: str = "Default"
    ptype: str = "FACE"


@dataclass
class UVSample:
    u: float
    v: float
    polygon: int | None  # None => continuous (per-vertex) sample
    vertex: int


@dataclass
class ODMesh:
    vertices: list = field(default_factory=list)  # (x, y, z) file space
    polygons: list = field(default_factory=list)  # [ODPolygon]
    weight_maps: dict = field(default_factory=dict)  # name -> [float | None]
    morph_maps: dict = field(default_factory=dict)  # name -> [(dx,dy,dz) | None]
    uv_maps: dict = field(default_factory=dict)  # name -> [UVSample]


def _floats(token_line):
    return [float(t) for t in token_line.split()]


def _payload(lines, start, count, what):
    chunk = lines[start : start + count]
    if len(chunk) != count:
        raise ODFormatError(
            "truncated %s section: expected %d payload lines, found %d"
            % (what, count, len(chunk))
        )
    return chunk


def parse(text):
    """Parse ODVertexData text into an ODMesh.

    Accepts everything historical writers produce: LF or CRLF endings,
    `None` placeholders, mixed continuous/discontinuous UV samples, both
    VERTEXNORMALS dialects (skipped), any section order after VERTICES.
    """
    lines = text.splitlines()
    mesh = ODMesh()

    vert_at = None
    for i, line in enumerate(lines):
        if line.startswith("VERTICES:"):
            vert_at = i
            break
    if vert_at is None:
        raise ODFormatError("no VERTICES section found")
    vcount = int(lines[vert_at].split(":")[1].strip())
    for vline in _payload(lines, vert_at + 1, vcount, "VERTICES"):
        values = _floats(vline)
        if len(values) < 3:
            raise ODFormatError("bad vertex line: %r" % vline)
        mesh.vertices.append((values[0], values[1], values[2]))

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("VERTICES:"):
            if i != vert_at:
                raise ODFormatError("multiple VERTICES sections (one mesh per file)")
            i += 1 + vcount
        elif line.startswith("POLYGONS:"):
            count = int(line.split(":")[1].strip())
            for pline in _payload(lines, i + 1, count, "POLYGONS"):
                parts = pline.split(";;")
                indices = [int(t.strip()) for t in parts[0].split(",")]
                surface = parts[1].strip() if len(parts) > 1 else "Default"
                ptype = parts[2].strip() if len(parts) > 2 else "FACE"
                for idx in indices:
                    if not 0 <= idx < vcount:
                        raise ODFormatError("polygon vertex index %d out of range" % idx)
                mesh.polygons.append(ODPolygon(indices, surface, ptype))
            i += 1 + count
        elif line.startswith("WEIGHT:"):
            name = line.split(":", 1)[1].strip()
            values = []
            for wline in _payload(lines, i + 1, vcount, "WEIGHT"):
                token = wline.strip()
                values.append(None if token == "None" else float(token))
            mesh.weight_maps[name] = values
            i += 1 + vcount
        elif line.startswith("MORPH:"):
            name = line.split(":", 1)[1].strip()
            deltas = []
            for mline in _payload(lines, i + 1, vcount, "MORPH"):
                token = mline.strip()
                if token == "None":
                    deltas.append(None)
                else:
                    values = _floats(token)
                    if len(values) < 3:
                        raise ODFormatError("bad morph line: %r" % mline)
                    deltas.append((values[0], values[1], values[2]))
            mesh.morph_maps[name] = deltas
            i += 1 + vcount
        elif line.startswith("UV:"):
            head = line.split(":")
            if len(head) < 3:
                raise ODFormatError("bad UV header: %r" % line)
            name = head[1]
            count = int(head[2].strip())
            samples = []
            for uline in _payload(lines, i + 1, count, "UV"):
                fields = uline.split(":")
                uv = _floats(fields[0])
                if len(uv) < 2:
                    raise ODFormatError("bad UV line: %r" % uline)
                if len(fields) >= 5:  # u v:PLY:<poly>:PNT:<vert>  (discontinuous)
                    samples.append(
                        UVSample(uv[0], uv[1], int(fields[2].strip()), int(fields[4].strip()))
                    )
                elif len(fields) == 3:  # u v:PNT:<vert>  (continuous)
                    samples.append(UVSample(uv[0], uv[1], None, int(fields[2].strip())))
                else:
                    raise ODFormatError("bad UV line: %r" % uline)
            mesh.uv_maps[name] = samples
            i += 1 + count
        elif line.startswith("VERTEXNORMALS"):
            # Deprecated section, two incompatible dialects in the wild
            # (FORMAT.md paragraph 3.6); the payload count is the last header field
            # in both. Skip it.
            head = line.split(":")
            try:
                count = int(head[-1].strip())
            except (ValueError, IndexError):
                count = 0
            i += 1 + count
        else:
            i += 1
    return mesh


def _check_name(name, what):
    if not name or ":" in name or ";;" in name or "\n" in name or "\r" in name:
        raise ODFormatError("invalid %s name: %r" % (what, name))


def _num(value):
    return repr(float(value))


def serialize(mesh):
    """Serialize an ODMesh to canonical ODVertexData text (FORMAT.md)."""
    vcount = len(mesh.vertices)
    out = ["VERTICES:%d" % vcount]
    for v in mesh.vertices:
        out.append("%s %s %s" % (_num(v[0]), _num(v[1]), _num(v[2])))

    out.append("POLYGONS:%d" % len(mesh.polygons))
    for poly in mesh.polygons:
        surface = poly.surface or "Default"
        if ";;" in surface or "\n" in surface or "\r" in surface:
            raise ODFormatError("invalid surface name: %r" % surface)
        ptype = poly.ptype or "FACE"
        if ptype not in POLY_TYPES:
            raise ODFormatError("invalid polygon type: %r" % ptype)
        out.append(
            "%s;;%s;;%s" % (",".join(str(int(i)) for i in poly.indices), surface, ptype)
        )

    for name, values in mesh.weight_maps.items():
        _check_name(name, "weight map")
        if len(values) != vcount:
            raise ODFormatError("weight map %r has %d values for %d vertices" % (name, len(values), vcount))
        out.append("WEIGHT:" + name)
        for w in values:
            out.append("None" if w is None else _num(w))

    for name, deltas in mesh.morph_maps.items():
        _check_name(name, "morph map")
        if len(deltas) != vcount:
            raise ODFormatError("morph map %r has %d values for %d vertices" % (name, len(deltas), vcount))
        out.append("MORPH:" + name)
        for d in deltas:
            out.append("None" if d is None else "%s %s %s" % (_num(d[0]), _num(d[1]), _num(d[2])))

    for name, samples in mesh.uv_maps.items():
        _check_name(name, "UV map")
        out.append("UV:%s:%d" % (name, len(samples)))
        for s in samples:
            if s.polygon is None:
                out.append("%s %s:PNT:%d" % (_num(s.u), _num(s.v), s.vertex))
            else:
                out.append("%s %s:PLY:%d:PNT:%d" % (_num(s.u), _num(s.v), s.polygon, s.vertex))

    return "\n".join(out) + "\n"
