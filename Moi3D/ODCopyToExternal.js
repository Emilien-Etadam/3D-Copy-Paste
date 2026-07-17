// OD_CopyPasteExternal - Copy To External (Moi3D, pure JScript - no .exe)
//
// Replaces the compiled objToVertData.exe converter: Moi exports the
// selection as OBJ natively (NoUI), and this script converts the OBJ text
// to the ODVertexData exchange file (docs/FORMAT.md) in JScript itself.
// Moi and the format share the OBJ conventions (right-handed Y-up, CCW
// winding), so the conversion is purely structural.
//
// Install: copy into Moi's "commands" folder, run via shortcut key or the
// custom UI. Optionally set OD_CPE_PATH below to a shared folder.
//
// The Moi script engine is ECMAScript-3-era: this file sticks to var/for
// syntax on purpose. The conversion functions are shared with
// ODPasteFromExternal.js and unit-tested with Node in the repository.

var OD_CPE_PATH = "";  // optional: absolute folder for the exchange file

function odTrim(s) {
    return s.replace(/^\s+/, "").replace(/\s+$/, "");
}

function odExchangeDir() {
    if (OD_CPE_PATH != "") return OD_CPE_PATH;
    try {
        if (moi.filesystem.getTempDir) return moi.filesystem.getTempDir();
    } catch (e) {}
    return moi.filesystem.getCommandsDir();  // fallback; see README
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

function objTextToExchange(text) {
    var lines = text.split("\n");
    var vertices = [], uvs = [], polygons = [], samples = [];
    var surface = "Default";
    for (var i = 0; i < lines.length; i++) {
        var line = odTrim(lines[i]);
        if (line == "" || line.charAt(0) == "#") continue;
        var parts = line.split(/\s+/);
        if (parts[0] == "v" && parts.length >= 4) {
            vertices.push(parts[1] + " " + parts[2] + " " + parts[3]);
        } else if (parts[0] == "vt" && parts.length >= 3) {
            uvs.push(parts[1] + " " + parts[2]);
        } else if (parts[0] == "usemtl" && parts.length >= 2) {
            surface = parts.slice(1).join(" ").replace(/;;/g, "__");
        } else if (parts[0] == "f" && parts.length >= 4) {
            var indices = [];
            var faceIndex = polygons.length;
            for (var k = 1; k < parts.length; k++) {
                var fields = parts[k].split("/");
                var vi = parseInt(fields[0], 10);
                vi = vi > 0 ? vi - 1 : vertices.length + vi;
                indices.push(vi);
                if (fields.length > 1 && fields[1] != "") {
                    var ti = parseInt(fields[1], 10);
                    ti = ti > 0 ? ti - 1 : uvs.length + ti;
                    if (ti >= 0 && ti < uvs.length) {
                        samples.push(uvs[ti] + ":PLY:" + faceIndex + ":PNT:" + vi);
                    }
                }
            }
            polygons.push(indices.join(",") + ";;" + surface + ";;FACE");
        }
    }
    var out = ["VERTICES:" + vertices.length];
    for (var a = 0; a < vertices.length; a++) out.push(vertices[a]);
    out.push("POLYGONS:" + polygons.length);
    for (var b = 0; b < polygons.length; b++) out.push(polygons[b]);
    if (samples.length > 0) {
        out.push("UV:UVMap:" + samples.length);
        for (var c = 0; c < samples.length; c++) out.push(samples[c]);
    }
    return out.join("\n") + "\n";
}

// ---- Moi glue ---------------------------------------------------------------

function odCopyMain() {
    var dir = odExchangeDir();
    var objPath = odJoinPath(dir, "OD_moi_temp.obj");
    var exchangePath = odJoinPath(dir, "ODVertexData.txt");
    // Export selection (or everything if nothing selected) as n-gon OBJ
    moi.geometryDatabase.fileExport(objPath, "NoUI=true;Output=ngons");
    var objText = odReadFile(objPath);
    odWriteFile(exchangePath, objTextToExchange(objText));
    moi.ui.alert("OD_CopyPasteExternal: copied to " + exchangePath);
}

if (typeof moi != "undefined") {
    odCopyMain();
}
