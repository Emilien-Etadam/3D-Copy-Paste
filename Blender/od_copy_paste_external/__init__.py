# OD Copy Paste External — Blender extension (Blender 4.2+ LTS)
#
# Copies/pastes mesh geometry between 3D applications through the
# ODVertexData.txt exchange file (see docs/FORMAT.md in the repository).
# Rewrite of the original scripts by Oliver Hotz for the Blender
# extensions platform.

import os

import bpy

from . import odformat

class ODCopyPasteExternalPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    exchange_dir: bpy.props.StringProperty(
        name="Exchange Directory",
        description=(
            "Directory for the ODVertexData.txt exchange file (e.g. a network "
            "share shared with other machines). Leave empty to use the "
            "OD_CPE_PATH environment variable or the system temp directory"
        ),
        subtype='DIR_PATH',
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "exchange_dir")
        layout.label(text="Exchange file: " + _data_file_path(), translate=False)


def _data_file_path():
    """Resolve the exchange file: OD_CPE_PATH > addon preference > temp dir.

    The environment variable wins so that pipelines and headless tests keep
    a deterministic location regardless of per-user preferences.
    """
    if os.environ.get(odformat.ENV_VAR):
        return odformat.data_file_path()
    addon = bpy.context.preferences.addons.get(__package__)
    if addon is not None:
        directory = getattr(addon.preferences, "exchange_dir", "")
        if directory:
            return os.path.join(bpy.path.abspath(directory), odformat.FILE_NAME)
    return odformat.data_file_path()


# File space is right-handed Y-up (OBJ convention); Blender is Z-up.
# The mapping is a pure rotation, so polygon winding is unchanged.


def _to_file_space(co):
    return (co[0], co[2], -co[1])


def _from_file_space(v):
    return (v[0], -v[2], v[1])


class OBJECT_OT_od_copy_to_external(bpy.types.Operator):
    """Copy the active mesh to the ODVertexData exchange file"""

    bl_idname = "object.od_copy_to_external"
    bl_label = "OD Copy To External"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        od = odformat.ODMesh()

        for vert in mesh.vertices:
            od.vertices.append(_to_file_space(vert.co))

        for poly in mesh.polygons:
            surface = "Default"
            if obj.material_slots:
                slot = obj.material_slots[poly.material_index]
                if slot.name:
                    surface = slot.name
            od.polygons.append(odformat.ODPolygon(list(poly.vertices), surface, "FACE"))

        # Weight maps: one section per vertex group, None for unassigned
        # vertices (FORMAT.md paragraph 3.3; fixes audit F12's dense export).
        if obj.vertex_groups:
            names = [g.name for g in obj.vertex_groups]
            maps = {name: [None] * len(mesh.vertices) for name in names}
            for vert in mesh.vertices:
                for g in vert.groups:
                    if g.group < len(names):
                        maps[names[g.group]][vert.index] = g.weight
            od.weight_maps = maps

        # Morph maps: shape keys relative to the basis key.
        keys = mesh.shape_keys
        if keys and len(keys.key_blocks) > 1:
            basis = keys.key_blocks[0].data
            for key in keys.key_blocks[1:]:
                deltas = []
                for j, kv in enumerate(key.data):
                    delta = kv.co - basis[j].co
                    deltas.append(_to_file_space(delta))
                od.morph_maps[key.name] = deltas

        # UV maps: one discontinuous sample per polygon loop, in polygon
        # order (canonical writer form).
        for layer in mesh.uv_layers:
            samples = []
            for poly in mesh.polygons:
                for li in poly.loop_indices:
                    uv = layer.data[li].uv
                    samples.append(
                        odformat.UVSample(uv[0], uv[1], poly.index, mesh.loops[li].vertex_index)
                    )
            od.uv_maps[layer.name] = samples

        path = _data_file_path()
        try:
            text = odformat.serialize(od)
        except odformat.ODFormatError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as exc:
            self.report({'ERROR'}, "Cannot write %s: %s" % (path, exc))
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            "Copied %d vertices / %d polygons to %s" % (len(od.vertices), len(od.polygons), path),
        )
        return {'FINISHED'}


class OBJECT_OT_od_paste_from_external(bpy.types.Operator):
    """Paste the mesh from the ODVertexData exchange file"""

    bl_idname = "object.od_paste_from_external"
    bl_label = "OD Paste From External"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        path = _data_file_path()
        if not os.path.exists(path):
            self.report({'ERROR'}, "No data file at %s" % path)
            return {'CANCELLED'}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                od = odformat.parse(f.read())
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, "Cannot read %s: %s" % (path, exc))
            return {'CANCELLED'}

        verts = [_from_file_space(v) for v in od.vertices]
        faces = [poly.indices for poly in od.polygons]

        # Reuse the active mesh object (preserving its transform and
        # animation, as the original add-on did) or create a new one.
        obj = context.active_object
        if obj is not None and obj.type == 'MESH':
            if obj.data.shape_keys:
                obj.shape_key_clear()
            mesh = obj.data
            mesh.clear_geometry()
        else:
            mesh = bpy.data.meshes.new("ODCopy")
            obj = bpy.data.objects.new("ODCopy", mesh)
            context.collection.objects.link(obj)
        mesh.from_pydata(verts, [], faces)

        # Materials, one slot per distinct surface name.
        mesh.materials.clear()
        slot_of = {}
        for p, poly in enumerate(od.polygons):
            name = poly.surface or "Default"
            if name not in slot_of:
                material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
                mesh.materials.append(material)
                slot_of[name] = len(mesh.materials) - 1
            mesh.polygons[p].material_index = slot_of[name]

        # Weight maps -> vertex groups (None = vertex not in the group).
        for group in list(obj.vertex_groups):
            obj.vertex_groups.remove(group)
        for name, values in od.weight_maps.items():
            group = obj.vertex_groups.new(name=name)
            for i, weight in enumerate(values):
                if weight is not None and i < len(mesh.vertices):
                    group.add([i], weight, 'REPLACE')

        # Morph maps -> shape keys (deltas on top of a basis key).
        if od.morph_maps:
            obj.shape_key_add(name="Basis", from_mix=False)
            for name, deltas in od.morph_maps.items():
                key = obj.shape_key_add(name=name, from_mix=False)
                for i, delta in enumerate(deltas):
                    if delta is not None and i < len(key.data):
                        offset = _from_file_space(delta)
                        base = mesh.vertices[i].co
                        key.data[i].co = (
                            base[0] + offset[0],
                            base[1] + offset[1],
                            base[2] + offset[2],
                        )

        # UV maps: honor PLY/PNT indices for discontinuous samples, then fill
        # remaining loops from continuous samples (fixes audit F4).
        if od.uv_maps:
            loop_of = {}
            loops_of_vert = {}
            for poly in mesh.polygons:
                for li in poly.loop_indices:
                    vi = mesh.loops[li].vertex_index
                    loop_of[(poly.index, vi)] = li
                    loops_of_vert.setdefault(vi, []).append(li)
            for name, samples in od.uv_maps.items():
                layer = mesh.uv_layers.new(name=name)
                if layer is None:  # 8-layer limit reached
                    self.report({'WARNING'}, "Could not create UV map %r" % name)
                    continue
                assigned = set()
                deferred = []
                for s in samples:
                    if s.polygon is None:
                        deferred.append(s)
                        continue
                    li = loop_of.get((s.polygon, s.vertex))
                    if li is not None:
                        layer.data[li].uv = (s.u, s.v)
                        assigned.add(li)
                for s in deferred:
                    for li in loops_of_vert.get(s.vertex, ()):
                        if li not in assigned:
                            layer.data[li].uv = (s.u, s.v)

        # SUBD/CCSS cages degrade to faces plus a subdivision modifier.
        if any(poly.ptype in ("SUBD", "CCSS") for poly in od.polygons):
            if not any(m.type == 'SUBSURF' for m in obj.modifiers):
                obj.modifiers.new("Subdivision", 'SUBSURF')

        mesh.validate()
        mesh.update()
        context.view_layer.objects.active = obj
        obj.select_set(True)

        self.report(
            {'INFO'},
            "Pasted %d vertices / %d polygons from %s" % (len(verts), len(faces), path),
        )
        return {'FINISHED'}


def _menu_copy(self, context):
    self.layout.operator(OBJECT_OT_od_copy_to_external.bl_idname)


def _menu_paste(self, context):
    self.layout.operator(OBJECT_OT_od_paste_from_external.bl_idname)


_classes = (
    ODCopyPasteExternalPreferences,
    OBJECT_OT_od_copy_to_external,
    OBJECT_OT_od_paste_from_external,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object.append(_menu_copy)
    bpy.types.VIEW3D_MT_object.append(_menu_paste)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(_menu_paste)
    bpy.types.VIEW3D_MT_object.remove(_menu_copy)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
