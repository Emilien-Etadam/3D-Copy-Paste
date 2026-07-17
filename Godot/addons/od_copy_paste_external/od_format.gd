# Parser/writer for the ODVertexData exchange format (docs/FORMAT.md).
# Pure GDScript, no editor dependencies — usable headless.
#
# Data dictionary shape:
#   { "vertices":   Array[Vector3]            (file space: Y-up right-handed),
#     "polygons":   Array[{indices, surface, ptype}],
#     "uv_maps":    { name: Array[{u, v, polygon (int or -1), vertex}] },
#     "weight_maps": { name: Array (float or null per vertex) },
#     "morph_maps":  { name: Array (Vector3 or null per vertex) } }

const FILE_NAME := "ODVertexData.txt"
const ENV_VAR := "OD_CPE_PATH"


static func data_file_path() -> String:
	var base := OS.get_environment(ENV_VAR)
	if base.is_empty():
		base = OS.get_temp_dir()
	return base.path_join(FILE_NAME)


static func parse(text: String) -> Dictionary:
	var lines := text.split("\n")
	for i in lines.size():
		lines[i] = lines[i].trim_suffix("\r")
	var data := {
		"vertices": [], "polygons": [],
		"uv_maps": {}, "weight_maps": {}, "morph_maps": {},
	}

	var vert_at := -1
	for i in lines.size():
		if lines[i].begins_with("VERTICES:"):
			vert_at = i
			break
	if vert_at < 0:
		push_error("ODVertexData: no VERTICES section found")
		return {}
	var vcount := int(lines[vert_at].get_slice(":", 1))
	if vert_at + vcount >= lines.size():
		push_error("ODVertexData: truncated VERTICES section")
		return {}
	for i in range(vert_at + 1, vert_at + 1 + vcount):
		var t := lines[i].split_floats(" ", false)
		if t.size() < 3:
			push_error("ODVertexData: bad vertex line %d" % i)
			return {}
		data["vertices"].append(Vector3(t[0], t[1], t[2]))

	var i := 0
	while i < lines.size():
		var line := lines[i]
		if line.begins_with("VERTICES:"):
			i += 1 + vcount
		elif line.begins_with("POLYGONS:"):
			var count := int(line.get_slice(":", 1))
			for k in range(i + 1, i + 1 + count):
				var parts := lines[k].split(";;")
				var indices: Array[int] = []
				for token in parts[0].split(","):
					var idx := int(token.strip_edges())
					if idx < 0 or idx >= vcount:
						push_error("ODVertexData: polygon index out of range")
						return {}
					indices.append(idx)
				var surface := parts[1].strip_edges() if parts.size() > 1 else "Default"
				var ptype := parts[2].strip_edges() if parts.size() > 2 else "FACE"
				data["polygons"].append({"indices": indices, "surface": surface, "ptype": ptype})
			i += 1 + count
		elif line.begins_with("WEIGHT:") or line.begins_with("MORPH:"):
			var is_weight := line.begins_with("WEIGHT:")
			var name := line.substr(7 if is_weight else 6).strip_edges()
			var values := []
			for k in range(i + 1, i + 1 + vcount):
				var token := lines[k].strip_edges()
				if token == "None":
					values.append(null)
				elif is_weight:
					values.append(float(token))
				else:
					var t := token.split_floats(" ", false)
					values.append(Vector3(t[0], t[1], t[2]) if t.size() >= 3 else null)
			data["weight_maps" if is_weight else "morph_maps"][name] = values
			i += 1 + vcount
		elif line.begins_with("UV:"):
			var name := line.get_slice(":", 1)
			var count := int(line.get_slice(":", 2))
			var samples := []
			for k in range(i + 1, i + 1 + count):
				var fields := lines[k].split(":")
				var uv := fields[0].split_floats(" ", false)
				if fields.size() >= 5:  # u v:PLY:p:PNT:v (discontinuous)
					samples.append({"u": uv[0], "v": uv[1],
						"polygon": int(fields[2]), "vertex": int(fields[4])})
				elif fields.size() == 3:  # u v:PNT:v (continuous)
					samples.append({"u": uv[0], "v": uv[1],
						"polygon": -1, "vertex": int(fields[2])})
			data["uv_maps"][name] = samples
			i += 1 + count
		elif line.begins_with("VERTEXNORMALS"):
			var count := int(line.get_slice(":", line.count(":")))
			i += 1 + count  # deprecated section, both dialects skipped
		else:
			i += 1
	return data


static func serialize(data: Dictionary) -> String:
	var out := PackedStringArray()
	var vertices: Array = data["vertices"]
	out.append("VERTICES:%d" % vertices.size())
	for v in vertices:
		out.append("%s %s %s" % [_num(v.x), _num(v.y), _num(v.z)])
	var polygons: Array = data["polygons"]
	out.append("POLYGONS:%d" % polygons.size())
	for poly in polygons:
		var tokens := PackedStringArray()
		for idx in poly["indices"]:
			tokens.append(str(idx))
		out.append("%s;;%s;;%s" % [",".join(tokens),
			str(poly.get("surface", "Default")).replace(";;", "__"),
			poly.get("ptype", "FACE")])
	for name in data.get("uv_maps", {}):
		var samples: Array = data["uv_maps"][name]
		out.append("UV:%s:%d" % [str(name).replace(":", "_"), samples.size()])
		for s in samples:
			if int(s["polygon"]) < 0:
				out.append("%s %s:PNT:%d" % [_num(s["u"]), _num(s["v"]), s["vertex"]])
			else:
				out.append("%s %s:PLY:%d:PNT:%d" % [_num(s["u"]), _num(s["v"]), s["polygon"], s["vertex"]])
	return "\n".join(out) + "\n"


static func _num(value: float) -> String:
	# Full float precision without scientific notation surprises
	return ("%.9g" % value)
