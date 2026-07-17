# OD_CopyPasteExternal — SketchUp 2017+ extension (copy AND paste)
#
# Full Ruby rewrite of the upstream paste-only console snippet, which
# applied the axis conversion in the wrong direction (models arrived upside
# down), assumed centimeters (SketchUp's internal unit is inches) and only
# handled quads. Exchange format: docs/FORMAT.md in the repository.
#
# Install: copy this file into the SketchUp Plugins folder. Two entries
# appear under Extensions: "OD Copy To External" / "OD Paste From External".
#
# Conventions: SketchUp is Z-up right-handed with CCW faces, the format is
# Y-up right-handed with CCW winding — a pure rotation, (x, z, -y) on write
# and (x, -z, y) on read, winding unchanged. Internal inches convert to the
# format's meters. OD_CPE_PATH relocates the exchange file.

require "tmpdir"

module ODCopyPasteExternal
  FILE_NAME = "ODVertexData.txt".freeze
  ENV_VAR = "OD_CPE_PATH".freeze
  INCHES_PER_METER = 39.37007874015748

  # ---- pure logic (no SketchUp API — unit-tested with plain Ruby) ----------
  module Format
    module_function

    def data_file_path
      base = ENV[ENV_VAR]
      base = Dir.tmpdir if base.nil? || base.empty?
      File.join(base, FILE_NAME)
    end

    def num(value)
      ("%.9g" % value.to_f)
    end

    # -> { vertices: [[x,y,z]], polygons: [{indices:, surface:}],
    #      uv_maps: { name => [[u, v, poly_or_nil, vertex]] }, skipped: [names] }
    def parse(text)
      lines = text.split(/\r?\n/)
      data = { vertices: [], polygons: [], uv_maps: {}, skipped: [] }

      vert_at = lines.index { |l| l.start_with?("VERTICES:") }
      raise ArgumentError, "no VERTICES section found" if vert_at.nil?
      vcount = lines[vert_at].split(":")[1].to_i
      chunk = lines[vert_at + 1, vcount] || []
      raise ArgumentError, "truncated VERTICES section" if chunk.size != vcount
      chunk.each do |vline|
        tokens = vline.split
        raise ArgumentError, "bad vertex line: #{vline.inspect}" if tokens.size < 3
        data[:vertices] << [Float(tokens[0]), Float(tokens[1]), Float(tokens[2])]
      end

      i = 0
      while i < lines.size
        line = lines[i]
        if line.start_with?("VERTICES:")
          i += 1 + vcount
        elsif line.start_with?("POLYGONS:")
          count = line.split(":")[1].to_i
          chunk = lines[i + 1, count] || []
          raise ArgumentError, "truncated POLYGONS section" if chunk.size != count
          chunk.each do |pline|
            parts = pline.split(";;")
            indices = parts[0].split(",").map { |t| Integer(t.strip, 10) }
            indices.each do |idx|
              raise ArgumentError, "polygon index #{idx} out of range" unless idx.between?(0, vcount - 1)
            end
            surface = parts.size > 1 ? parts[1].strip : "Default"
            data[:polygons] << { indices: indices, surface: surface }
          end
          i += 1 + count
        elsif line.start_with?("WEIGHT:") || line.start_with?("MORPH:")
          data[:skipped] << line.split(":", 2)[1].to_s.strip
          i += 1 + vcount
        elsif line.start_with?("UV:")
          head = line.split(":")
          raise ArgumentError, "bad UV header: #{line.inspect}" if head.size < 3
          name = head[1]
          count = head[2].to_i
          chunk = lines[i + 1, count] || []
          raise ArgumentError, "truncated UV section" if chunk.size != count
          samples = chunk.map do |uline|
            fields = uline.split(":")
            uv = fields[0].split
            raise ArgumentError, "bad UV line: #{uline.inspect}" if uv.size < 2
            if fields.size >= 5
              [Float(uv[0]), Float(uv[1]), Integer(fields[2].strip, 10), Integer(fields[4].strip, 10)]
            elsif fields.size == 3
              [Float(uv[0]), Float(uv[1]), nil, Integer(fields[2].strip, 10)]
            else
              raise ArgumentError, "bad UV line: #{uline.inspect}"
            end
          end
          data[:uv_maps][name] = samples
          i += 1 + count
        elsif line.start_with?("VERTEXNORMALS")
          count = line.split(":").last.to_i
          i += 1 + count
        else
          i += 1
        end
      end
      data
    end

    # data: { vertices:, polygons: [{indices:, surface:}], uv_samples: [[u,v,poly,vertex]] }
    def serialize(data)
      out = ["VERTICES:#{data[:vertices].size}"]
      data[:vertices].each { |v| out << "#{num(v[0])} #{num(v[1])} #{num(v[2])}" }
      out << "POLYGONS:#{data[:polygons].size}"
      data[:polygons].each do |poly|
        surface = (poly[:surface].to_s.empty? ? "Default" : poly[:surface]).gsub(";;", "__")
        out << "#{poly[:indices].join(',')};;#{surface};;FACE"
      end
      samples = data[:uv_samples] || []
      unless samples.empty?
        out << "UV:UVMap:#{samples.size}"
        samples.each do |u, v, face, vertex|
          out << "#{num(u)} #{num(v)}:PLY:#{face}:PNT:#{vertex}"
        end
      end
      out.join("\n") + "\n"
    end

    # Per polygon: resolved [u, v] per corner (discontinuous wins), or nil.
    def resolve_corner_uvs(polygons, samples)
      continuous = {}
      discontinuous = {}
      samples.each do |u, v, poly, vertex|
        if poly.nil?
          continuous[vertex] = [u, v]
        else
          discontinuous[[poly, vertex]] = [u, v]
        end
      end
      polygons.each_with_index.map do |poly, p|
        uvs = poly[:indices].map { |idx| discontinuous[[p, idx]] || continuous[idx] }
        uvs.include?(nil) ? nil : uvs
      end
    end

    # Newell normal of a polygon given [[x,y,z], ...] — used to detect
    # SketchUp's automatic face flipping.
    def newell_normal(points)
      nx = ny = nz = 0.0
      points.each_with_index do |a, k|
        b = points[(k + 1) % points.size]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
      end
      [nx, ny, nz]
    end
  end

  # ---- SketchUp glue --------------------------------------------------------

  def self.copy_to_external
    model = Sketchup.active_model
    faces = model.selection.grep(Sketchup::Face)
    if faces.empty?
      UI.messagebox("OD_CopyPasteExternal: select at least one face (enter groups/components first).")
      return
    end

    scale = 1.0 / INCHES_PER_METER
    vertices = []
    index_of = {}
    polygons = []
    uv_samples = []
    tw = Sketchup.create_texture_writer

    faces.each do |face|
      surface = face.material ? face.material.display_name : "Default"
      corner_ids = face.outer_loop.vertices.map do |vertex|
        key = vertex.position.to_a
        index_of[key] ||= begin
          p = vertex.position
          # Z-up inches -> Y-up meters: (x, z, -y)
          vertices << [p.x * scale, p.z * scale, -p.y * scale]
          vertices.size - 1
        end
      end
      face_index = polygons.size
      polygons << { indices: corner_ids, surface: surface }
      if face.material && face.material.texture
        uvh = face.get_UVHelper(true, false, tw)
        face.outer_loop.vertices.each_with_index do |vertex, k|
          uvq = uvh.get_front_UVQ(vertex.position)
          q = uvq.z.to_f
          q = 1.0 if q.zero?
          uv_samples << [uvq.x / q, uvq.y / q, face_index, corner_ids[k]]
        end
      end
    end

    path = Format.data_file_path
    File.write(path, Format.serialize(vertices: vertices, polygons: polygons, uv_samples: uv_samples))
    puts "OD_CopyPasteExternal: copied #{vertices.size} vertices / #{polygons.size} faces to #{path}"
  rescue StandardError => e
    UI.messagebox("OD_CopyPasteExternal: copy failed — #{e.message}")
  end

  def self.paste_from_external
    path = Format.data_file_path
    unless File.exist?(path)
      UI.messagebox("OD_CopyPasteExternal: no data file at #{path} — copy something first.")
      return
    end
    data = Format.parse(File.read(path))
    if data[:polygons].empty?
      UI.messagebox("OD_CopyPasteExternal: file contains no polygons.")
      return
    end

    model = Sketchup.active_model
    model.start_operation("OD Paste From External", true)
    group = model.active_entities.add_group
    group.name = "ODCopy"
    entities = group.entities

    points = data[:vertices].map do |x, y, z|
      # Y-up meters -> Z-up inches: (x, -z, y)
      Geom::Point3d.new(x * INCHES_PER_METER, -z * INCHES_PER_METER, y * INCHES_PER_METER)
    end
    first_map = data[:uv_maps].values.first || []
    corner_uvs = Format.resolve_corner_uvs(data[:polygons], first_map)

    materials = {}
    skipped_faces = 0
    data[:polygons].each_with_index do |poly, p|
      indices = poly[:indices].uniq
      next if indices.size < 3
      corners = indices.map { |idx| points[idx] }
      faces = []
      begin
        faces << entities.add_face(corners)
      rescue StandardError
        # non-planar or degenerate n-gon: fall back to a fan
        (1..indices.size - 2).each do |k|
          begin
            faces << entities.add_face(corners[0], corners[k], corners[k + 1])
          rescue StandardError
            skipped_faces += 1
          end
        end
      end

      surface = poly[:surface].to_s.empty? ? "Default" : poly[:surface]
      material = materials[surface] ||= begin
        existing = model.materials[surface]
        existing || model.materials.add(surface)
      end
      intended = Format.newell_normal(corners.map(&:to_a))
      faces.compact.each do |face|
        n = face.normal
        dot = n.x * intended[0] + n.y * intended[1] + n.z * intended[2]
        face.reverse! if dot < 0  # SketchUp flips flat faces at will
        face.material = material
        uvs = corner_uvs[p]
        next unless uvs
        pairs = []
        corners.first(4).each_with_index do |pt, k|
          pairs << pt << Geom::Point3d.new(uvs[k][0], uvs[k][1], 0)
        end
        begin
          face.position_material(material, pairs, true)
        rescue StandardError
          nil # keep the face even if the mapping is rejected
        end
      end
    end

    model.commit_operation
    model.selection.clear
    model.selection.add(group)
    message = "OD_CopyPasteExternal: pasted #{points.size} vertices / #{data[:polygons].size} polygons"
    message += " (#{skipped_faces} degenerate faces skipped)" if skipped_faces > 0
    message += " — ignored maps: #{data[:skipped].join(', ')}" unless data[:skipped].empty?
    puts message
  rescue StandardError => e
    model&.abort_operation
    UI.messagebox("OD_CopyPasteExternal: paste failed — #{e.message}")
  end

  if defined?(Sketchup) && defined?(UI) && !@menu_installed
    @menu_installed = true
    menu = UI.menu("Extensions")
    menu.add_item("OD Copy To External") { copy_to_external }
    menu.add_item("OD Paste From External") { paste_from_external }
  end
end
