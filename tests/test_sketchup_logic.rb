# Unit tests for the SketchUp extension's pure logic (Format module).
# Runs with plain Ruby — the SketchUp glue is guarded and stays inert.
#
# Run: ruby tests/test_sketchup_logic.rb

require_relative "../Sketchup/OD_CopyPasteExternal"

Format = ODCopyPasteExternal::Format
REPO = File.expand_path("..", __dir__)
GOLDEN = File.join(REPO, "tests", "golden")

def assert(condition, message)
  abort("FAIL: #{message}") unless condition
end

# 1. serialize -> parse round-trip
data = {
  vertices: [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
  polygons: [{ indices: [0, 1, 2, 3], surface: "Steel" }],
  uv_samples: [[0.0, 0.0, 0, 0], [1.0, 0.0, 0, 1], [1.0, 1.0, 0, 2], [0.0, 1.0, 0, 3]],
}
parsed = Format.parse(Format.serialize(data))
assert(parsed[:vertices] == data[:vertices], "vertices round-trip")
assert(parsed[:polygons] == [{ indices: [0, 1, 2, 3], surface: "Steel" }], "polygons round-trip")
assert(parsed[:uv_maps]["UVMap"] == data[:uv_samples], "uv round-trip")

# 2. golden files parse (mixed UV forms; weights/morphs recorded as skipped)
golden = Format.parse(File.read(File.join(GOLDEN, "cube_uv.txt")))
assert(golden[:vertices].size == 8 && golden[:polygons].size == 6, "golden cube counts")
assert(golden[:uv_maps]["txuvmap"].size == 24, "golden cube uv samples")
assert(golden[:uv_maps]["txuvmap"].count { |s| s[2].nil? } == 8, "continuous samples detected")

golden = Format.parse(File.read(File.join(GOLDEN, "weighted_plane.txt")))
assert(golden[:skipped] == %w[edge_falloff left_side bump], "skipped maps recorded")

# 3. UV resolution: discontinuous beats continuous; incomplete -> nil
polygons = [{ indices: [0, 1, 2], surface: "a" }, { indices: [2, 3, 0], surface: "a" }]
samples = [[0.5, 0.5, nil, 0], [0.1, 0.1, nil, 1], [0.2, 0.2, nil, 2], [0.9, 0.9, 0, 0]]
resolved = Format.resolve_corner_uvs(polygons, samples)
assert(resolved[0] == [[0.9, 0.9], [0.1, 0.1], [0.2, 0.2]], "discontinuous override")
assert(resolved[1].nil?, "incomplete face -> nil")

# 4. Newell normal orientation (CCW square in XY plane -> +Z)
normal = Format.newell_normal([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]])
assert(normal[2] > 0 && normal[0].abs < 1e-9, "newell normal points +Z")

# 5. malformed input raises
[["POLYGONS:1\n0,1,2;;a;;FACE\n"], ["VERTICES:2\n0 0 0\n"],
 ["VERTICES:3\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS:1\n0,1,9;;a;;FACE\n"]].each do |bad|
  begin
    Format.parse(bad[0])
    abort("FAIL: should have raised for #{bad[0].inspect}")
  rescue ArgumentError
    # expected
  end
end

# 6. exchange path honors OD_CPE_PATH
ENV["OD_CPE_PATH"] = "/some/share"
assert(Format.data_file_path == "/some/share/ODVertexData.txt", "env override")
ENV.delete("OD_CPE_PATH")

puts "all sketchup logic tests OK"
