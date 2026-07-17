extends SceneTree
# Headless round-trip test for the Godot addon:
#   golden file -> parse -> build MeshInstance3D -> extract -> serialize ->
#   parse -> geometric comparison.
# Run from the repository root:
#   godot --headless --path Godot --script res://tests/roundtrip_test.gd
# Exit code 0 = pass.

const ODFormat := preload("res://addons/od_copy_paste_external/od_format.gd")
const ODCopyPaste := preload("res://addons/od_copy_paste_external/od_copy_paste.gd")

const EPS := 1e-4


func _init() -> void:
	var failures := 0
	var golden_dir := ProjectSettings.globalize_path("res://").path_join("../tests/golden")
	for file_name in ["cube_uv.txt", "weighted_plane.txt"]:
		if not _roundtrip(golden_dir.path_join(file_name), file_name):
			failures += 1
	if failures == 0:
		print("all godot round-trip tests OK")
	quit(1 if failures > 0 else 0)


func _roundtrip(path: String, label: String) -> bool:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		printerr("FAIL %s: cannot open %s" % [label, path])
		return false
	var golden := ODFormat.parse(f.get_as_text())
	f.close()
	if golden.is_empty():
		printerr("FAIL %s: golden parse failed" % label)
		return false

	var mesh_instance := ODCopyPaste.build_mesh_instance(golden)
	var extracted := ODCopyPaste.extract_data(mesh_instance)
	var reparsed := ODFormat.parse(ODFormat.serialize(extracted))
	if reparsed.is_empty():
		printerr("FAIL %s: serialized output does not reparse" % label)
		return false

	var ok := true

	# Triangle count: every n-gon fan-triangulated (sum of size-2 per polygon)
	var expected_tris := 0
	for poly in golden["polygons"]:
		expected_tris += poly["indices"].size() - 2
	if reparsed["polygons"].size() != expected_tris:
		printerr("FAIL %s: %d triangles, expected %d" % [label, reparsed["polygons"].size(), expected_tris])
		ok = false

	# Every original vertex position must survive (indices may differ:
	# SurfaceTool splits at UV seams and re-indexes)
	for v in golden["vertices"]:
		var found := false
		for w in reparsed["vertices"]:
			if v.distance_to(w) < EPS:
				found = true
				break
		if not found:
			printerr("FAIL %s: lost vertex %s" % [label, v])
			ok = false
			break

	# Surface names survive via material resource_name
	var golden_surfaces := {}
	for poly in golden["polygons"]:
		golden_surfaces[poly["surface"]] = true
	var out_surfaces := {}
	for poly in reparsed["polygons"]:
		out_surfaces[poly["surface"]] = true
	if golden_surfaces.keys() != out_surfaces.keys():
		printerr("FAIL %s: surfaces %s != %s" % [label, out_surfaces.keys(), golden_surfaces.keys()])
		ok = false

	# UVs: resolve golden per (position), compare against extracted
	# per-vertex UVs at the same position (both maps applied and V-flip
	# round-tripped). Only spot-check corner positions to stay robust to
	# vertex splitting.
	if not golden["uv_maps"].is_empty() and not reparsed["uv_maps"].is_empty():
		var golden_uv := _uvs_by_position(golden)
		var out_uv := _uvs_by_position(reparsed)
		var checked := 0
		for key in golden_uv:
			if out_uv.has(key):
				checked += 1
				if not _uv_sets_match(golden_uv[key], out_uv[key]):
					printerr("FAIL %s: UVs at %s: %s != %s" % [label, key, out_uv[key], golden_uv[key]])
					ok = false
					break
		if checked == 0:
			printerr("FAIL %s: no comparable UV positions" % label)
			ok = false

	if ok:
		print("PASS %s (%d verts -> %d, %d tris, surfaces %s)" % [
			label, golden["vertices"].size(), reparsed["vertices"].size(),
			reparsed["polygons"].size(), out_surfaces.keys()])
	return ok


func _uvs_by_position(data: Dictionary) -> Dictionary:
	# position (rounded) -> set of UVs used at that position, resolved
	# per polygon corner (discontinuous wins over continuous)
	var continuous := {}
	var discontinuous := {}
	for name in data["uv_maps"]:
		for s in data["uv_maps"][name]:
			if int(s["polygon"]) < 0:
				continuous[int(s["vertex"])] = Vector2(s["u"], s["v"])
			else:
				discontinuous[Vector2i(int(s["polygon"]), int(s["vertex"]))] = Vector2(s["u"], s["v"])
		break
	var result := {}
	var vertices: Array = data["vertices"]
	for p in data["polygons"].size():
		for idx in data["polygons"][p]["indices"]:
			var uv: Variant = discontinuous.get(Vector2i(p, idx), continuous.get(idx))
			if uv == null:
				continue
			var key := "%.4f,%.4f,%.4f" % [vertices[idx].x, vertices[idx].y, vertices[idx].z]
			if not result.has(key):
				result[key] = []
			result[key].append(uv)
	return result


func _uv_sets_match(a: Array, b: Array) -> bool:
	# every UV in a must appear in b (within EPS) and vice versa
	for uv in a:
		if not _uv_in(uv, b):
			return false
	for uv in b:
		if not _uv_in(uv, a):
			return false
	return true


func _uv_in(uv: Vector2, list: Array) -> bool:
	for other in list:
		if uv.distance_to(other) < EPS:
			return true
	return false
