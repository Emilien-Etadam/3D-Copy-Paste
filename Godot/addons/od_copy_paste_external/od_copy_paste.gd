# Core copy/paste logic for OD_CopyPasteExternal (docs/FORMAT.md).
# No editor dependencies — the editor plugin (plugin.gd) is a thin wrapper,
# and the headless test drives these functions directly.
#
# Conventions: both Godot and the exchange file are right-handed Y-up, so
# coordinates pass through unchanged. Godot's front faces wind clockwise
# while the format (like OBJ) winds counter-clockwise: polygon vertex order
# is reversed in both directions. Godot's UV origin is top-left (V down);
# the format's is bottom-left (V up): V is flipped both ways.

const ODFormat := preload("od_format.gd")


static func extract_data(mesh_instance: MeshInstance3D) -> Dictionary:
	"""Convert a MeshInstance3D to exchange-file data (verts, polys, UVs)."""
	var data := {
		"vertices": [], "polygons": [],
		"uv_maps": {}, "weight_maps": {}, "morph_maps": {},
	}
	var mesh := mesh_instance.mesh
	if mesh == null:
		return data
	var uv_samples := []
	for s in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(s)
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uvs = arrays[Mesh.ARRAY_TEX_UV]  # PackedVector2Array or null
		var indices = arrays[Mesh.ARRAY_INDEX]  # PackedInt32Array or null
		var offset: int = data["vertices"].size()

		for v in verts:
			data["vertices"].append(v)
		if uvs != null and uvs.size() == verts.size():
			for vi in verts.size():
				uv_samples.append({"u": uvs[vi].x, "v": 1.0 - uvs[vi].y,
					"polygon": -1, "vertex": offset + vi})

		var surface := _surface_name(mesh_instance, mesh, s)
		if indices == null or indices.size() == 0:
			indices = PackedInt32Array(range(verts.size()))
		for t in range(0, indices.size() - 2, 3):
			# reversed: Godot clockwise -> format counter-clockwise
			var tri: Array[int] = [
				offset + indices[t + 2], offset + indices[t + 1], offset + indices[t]]
			data["polygons"].append({"indices": tri, "surface": surface, "ptype": "FACE"})
	if not uv_samples.is_empty():
		data["uv_maps"]["UVMap"] = uv_samples
	return data


static func _surface_name(mesh_instance: MeshInstance3D, mesh: Mesh, s: int) -> String:
	var material := mesh_instance.get_active_material(s)
	if material != null and not material.resource_name.is_empty():
		return material.resource_name.replace(";;", "__")
	if mesh is ArrayMesh:
		var surface_name := (mesh as ArrayMesh).surface_get_name(s)
		if not surface_name.is_empty():
			return surface_name.replace(";;", "__")
	return "Default"


static func build_mesh_instance(data: Dictionary) -> MeshInstance3D:
	"""Build a MeshInstance3D from exchange-file data."""
	# Resolve UVs per (polygon, vertex): discontinuous samples win.
	var continuous := {}
	var discontinuous := {}
	for name in data.get("uv_maps", {}):
		for s in data["uv_maps"][name]:
			if int(s["polygon"]) < 0:
				continuous[int(s["vertex"])] = Vector2(s["u"], 1.0 - float(s["v"]))
			else:
				discontinuous[Vector2i(int(s["polygon"]), int(s["vertex"]))] = \
					Vector2(s["u"], 1.0 - float(s["v"]))
		break  # Godot meshes carry one UV set here; apply the first map

	# One surface per distinct surface name.
	var by_surface := {}
	var polygons: Array = data["polygons"]
	for p in polygons.size():
		var surface: String = polygons[p].get("surface", "Default")
		if not by_surface.has(surface):
			by_surface[surface] = []
		by_surface[surface].append(p)

	var vertices: Array = data["vertices"]
	var array_mesh := ArrayMesh.new()
	for surface in by_surface:
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		for p in by_surface[surface]:
			var indices: Array = polygons[p]["indices"]
			if indices.size() < 3:
				continue
			# fan-triangulate, reversing to Godot's clockwise winding
			for k in range(1, indices.size() - 1):
				for idx in [indices[k + 1], indices[k], indices[0]]:
					var key := Vector2i(p, idx)
					if discontinuous.has(key):
						st.set_uv(discontinuous[key])
					elif continuous.has(idx):
						st.set_uv(continuous[idx])
					st.add_vertex(vertices[idx])
		st.index()
		st.generate_normals()
		var surface_index := array_mesh.get_surface_count()
		st.commit(array_mesh)
		array_mesh.surface_set_name(surface_index, surface)
		var material := StandardMaterial3D.new()
		material.resource_name = surface
		array_mesh.surface_set_material(surface_index, material)

	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = "ODCopy"
	mesh_instance.mesh = array_mesh
	return mesh_instance


static func copy_selection(nodes: Array) -> String:
	"""Copy the first MeshInstance3D found in nodes; return a status string."""
	for node in nodes:
		if node is MeshInstance3D:
			var data := extract_data(node)
			if data["vertices"].is_empty():
				return "selected mesh is empty"
			var path := ODFormat.data_file_path()
			var f := FileAccess.open(path, FileAccess.WRITE)
			if f == null:
				return "cannot write %s" % path
			f.store_string(ODFormat.serialize(data))
			f.close()
			return "copied %d vertices / %d triangles to %s" % [
				data["vertices"].size(), data["polygons"].size(), path]
	return "select a MeshInstance3D first"


static func paste_from_file() -> Variant:
	"""Read the exchange file; return a MeshInstance3D or an error string."""
	var path := ODFormat.data_file_path()
	if not FileAccess.file_exists(path):
		return "no data file at %s — copy something first" % path
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return "cannot read %s" % path
	var data := ODFormat.parse(f.get_as_text())
	f.close()
	if data.is_empty() or data["polygons"].is_empty():
		return "exchange file contains no usable polygons"
	var skipped := []
	skipped.append_array(data["weight_maps"].keys())
	skipped.append_array(data["morph_maps"].keys())
	if not skipped.is_empty():
		push_warning("OD_CopyPasteExternal: ignored weight/morph maps: %s" % ", ".join(skipped))
	return build_mesh_instance(data)
