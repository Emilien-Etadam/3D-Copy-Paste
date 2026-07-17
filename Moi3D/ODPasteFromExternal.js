// OD_CopyPasteExternal - Paste From External (Moi3D, pure JScript - no .exe)
//
// Replaces the compiled vertDataToObj.exe converter and its .htm dialog:
// this script converts the ODVertexData exchange file (docs/FORMAT.md) to
// OBJ text in JScript, writes a temp OBJ and lets Moi import it natively.
// Weight/morph sections have no OBJ equivalent and are dropped.
//
// Install: copy into Moi's "commands" folder next to ODCopyToExternal.js.
// Optionally set OD_CPE_PATH below to a shared folder.

var OD_CPE_PATH = "";  // optional: absolute folder for the exchange file

function odTrim(s) {
    return s.replace(/^\s+/, "").replace(/\s+$/, "");
}

function odExchangeDir() {
    if (OD_CPE_PATH != "") return OD_CPE_PATH;
    try {
        if (moi.filesystem.getTempDir) return moi.filesystem.getTempDir();
    } catch (e) {}
    return moi.filesystem.getCommandsDir();
}

function odJoinPath(dir, name) {
    var last = dir.charAt(dir.length - 1);
    if (last == "\\" || last == "/") return dir + name;
    return dir + "\\" + name;
}

function odReadFile(path) {
    var stream = moi.filesystem.openFileStream(path, "r");
    var lines = [];
    while (!stream.atEOF) lines.push(stream.readLine());
    stream.close();
    return lines.join("\n");
}

function odWriteFile(path, text) {
    var stream = moi.filesystem.openFileStream(path, "w");
    stream.write(text);
    stream.close();
}

// ---- pure conversion (no moi API - unit-tested with Node) ------------------

function exchangeTextToObj(text) {
    var lines = text.split("\n");
    var vertices = [], polygons = [], surfaces = [];
    var contUV = {}, discUV = {};
    var vertAt = -1;
    for (var s = 0; s < lines.length; s++) {
        if (lines[s].indexOf("VERTICES:") == 0) { vertAt = s; break; }
    }
    if (vertAt < 0) throw new Error("no VERTICES section found");
    var vcount = parseInt(lines[vertAt].split(":")[1], 10);
    for (var vi = vertAt + 1; vi <= vertAt + vcount; vi++) {
        var vline = vi < lines.length ? odTrim(lines[vi]) : "";
        var vtokens = vline.split(/\s+/);
        if (vtokens.length < 3 || isNaN(parseFloat(vtokens[0])) ||
            isNaN(parseFloat(vtokens[1])) || isNaN(parseFloat(vtokens[2]))) {
            throw new Error("truncated or bad VERTICES section at line " + vi);
        }
        vertices.push(vline);
    }

    var i = 0;
    while (i < lines.length) {
        var line = lines[i];
        if (line.indexOf("VERTICES:") == 0) {
            i += 1 + vcount;
        } else if (line.indexOf("POLYGONS:") == 0) {
            var pcount = parseInt(line.split(":")[1], 10);
            if (i + pcount >= lines.length) throw new Error("truncated POLYGONS section");
            for (var p = i + 1; p <= i + pcount; p++) {
                var parts = lines[p].split(";;");
                var tokens = parts[0].split(",");
                var indices = [];
                for (var t = 0; t < tokens.length; t++) {
                    var idx = parseInt(odTrim(tokens[t]), 10);
                    if (idx < 0 || idx >= vcount) throw new Error("polygon index out of range");
                    indices.push(idx);
                }
                polygons.push(indices);
                surfaces.push(parts.length > 1 ? odTrim(parts[1]) : "Default");
            }
            i += 1 + pcount;
        } else if (line.indexOf("WEIGHT:") == 0 || line.indexOf("MORPH:") == 0) {
            i += 1 + vcount;  // no OBJ equivalent; dropped
        } else if (line.indexOf("UV:") == 0) {
            var head = line.split(":");
            var ucount = parseInt(head[2], 10);
            for (var u = i + 1; u <= i + ucount && u < lines.length; u++) {
                var fields = lines[u].split(":");
                if (fields.length >= 5) {
                    discUV[fields[2] + "," + odTrim(fields[4])] = fields[0];
                } else if (fields.length == 3) {
                    contUV[odTrim(fields[2])] = fields[0];
                }
            }
            i += 1 + ucount;
        } else if (line.indexOf("VERTEXNORMALS") == 0) {
            var nparts = line.split(":");
            var ncount = parseInt(nparts[nparts.length - 1], 10);
            if (isNaN(ncount)) ncount = 0;
            i += 1 + ncount;
        } else {
            i += 1;
        }
    }

    var out = ["o ODVertexData"];
    for (var a = 0; a < vertices.length; a++) out.push("v " + vertices[a]);
    var vtIndex = {}, vtCount = 0, cornerVT = {};
    for (var b = 0; b < polygons.length; b++) {
        for (var c = 0; c < polygons[b].length; c++) {
            var vidx = polygons[b][c];
            var uv = discUV[b + "," + vidx];
            if (uv == null) uv = contUV["" + vidx];
            if (uv == null) continue;
            if (vtIndex[uv] == null) {
                vtCount++;
                vtIndex[uv] = vtCount;
                out.push("vt " + uv);
            }
            cornerVT[b + "," + vidx] = vtIndex[uv];
        }
    }
    var current = null;
    for (var d = 0; d < polygons.length; d++) {
        if (surfaces[d] != current) {
            out.push("usemtl " + surfaces[d]);
            current = surfaces[d];
        }
        var corners = [];
        for (var e = 0; e < polygons[d].length; e++) {
            var pidx = polygons[d][e];
            var vt = cornerVT[d + "," + pidx];
            corners.push(vt != null ? (pidx + 1) + "/" + vt : "" + (pidx + 1));
        }
        out.push("f " + corners.join(" "));
    }
    return out.join("\n") + "\n";
}

// ---- Moi glue ---------------------------------------------------------------

function odPasteMain() {
    var dir = odExchangeDir();
    var exchangePath = odJoinPath(dir, "ODVertexData.txt");
    var objPath = odJoinPath(dir, "OD_moi_temp.obj");
    var text;
    try {
        text = odReadFile(exchangePath);
    } catch (e) {
        moi.ui.alert("OD_CopyPasteExternal: no data file at " + exchangePath + " - copy something first.");
        return;
    }
    odWriteFile(objPath, exchangeTextToObj(text));
    moi.geometryDatabase.fileImport(objPath);
    moi.ui.alert("OD_CopyPasteExternal: pasted " + exchangePath);
}

if (typeof moi != "undefined") {
    odPasteMain();
}
