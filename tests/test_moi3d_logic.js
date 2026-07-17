// Unit tests for the Moi3D scripts' pure conversion logic, run with Node.
// The moi API guard keeps the scripts inert outside Moi; the conversion
// functions are evaluated in a sandbox and exercised directly.
//
// Run: node tests/test_moi3d_logic.js

"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO = path.resolve(__dirname, "..");
const GOLDEN = path.join(REPO, "tests", "golden");

function loadFunctions(file, names) {
    const code = fs.readFileSync(path.join(REPO, "Moi3D", file), "utf8");
    const sandbox = {};
    vm.runInNewContext(code, sandbox, { filename: file });
    const out = {};
    for (const name of names) {
        if (typeof sandbox[name] !== "function") {
            throw new Error(`${file}: function ${name} not found`);
        }
        out[name] = sandbox[name];
    }
    return out;
}

function assert(condition, message) {
    if (!condition) {
        console.error("FAIL: " + message);
        process.exit(1);
    }
}

const { objTextToExchange } = loadFunctions("ODCopyToExternal.js", ["objTextToExchange"]);
const { exchangeTextToObj } = loadFunctions("ODPasteFromExternal.js", ["exchangeTextToObj"]);

// 1. golden cube: exchange -> OBJ -> exchange preserves geometry and UVs
const cube = fs.readFileSync(path.join(GOLDEN, "cube_uv.txt"), "utf8");
const objText = exchangeTextToObj(cube);
assert((objText.match(/^v /gm) || []).length === 8, "8 obj vertices");
assert((objText.match(/^f /gm) || []).length === 6, "6 obj faces");
assert(objText.includes("usemtl Default"), "surface name kept");
const back = objTextToExchange(objText);
assert(back.startsWith("VERTICES:8\n"), "round-trip vertex count");
assert(back.includes("POLYGONS:6"), "round-trip polygon count");
assert(back.includes("UV:UVMap:24"), "all 24 corners have UVs after resolution");

// 2. weighted plane: weight/morph sections dropped, material kept
const plane = fs.readFileSync(path.join(GOLDEN, "weighted_plane.txt"), "utf8");
const planeObj = exchangeTextToObj(plane);
assert(planeObj.includes("usemtl Checker"), "plane material");
assert((planeObj.match(/^f /gm) || []).length === 4, "plane faces");
assert(!planeObj.includes("WEIGHT") && !planeObj.includes("MORPH"), "maps dropped");

// 3. OBJ parsing: comments, negative indices, v//vn corners, n-gons
const obj = [
    "# comment", "v 0 0 0", "v 1 0 0", "v 1 1 0", "v 0 1 0",
    "vt 0 0", "vt 1 1",
    "usemtl Mat A",
    "f 1/1 2/2 3/1",
    "f -4//1 -2//1 -1//1",
    "f 1 2 3 4",
].join("\n");
const exchange = objTextToExchange(obj);
assert(exchange.includes("VERTICES:4"), "obj vertices parsed");
assert(exchange.includes("0,2,3;;Mat A;;FACE"), "negative indices resolved");
assert(exchange.includes("0,1,2,3;;Mat A;;FACE"), "ngon preserved");
assert(exchange.includes("UV:UVMap:3"), "uv samples only where vt present");

// 4. malformed exchange input throws
for (const bad of ["POLYGONS:1\n0,1,2;;a;;FACE\n", "VERTICES:2\n0 0 0\n",
                   "VERTICES:3\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS:1\n0,1,9;;a;;FACE\n"]) {
    let threw = false;
    try { exchangeTextToObj(bad); } catch (e) { threw = true; }
    assert(threw, "should throw for " + JSON.stringify(bad.slice(0, 20)));
}

console.log("all moi3d logic tests OK");
