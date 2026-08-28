"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");

const extractArrowFunction = (name) => {
  const marker = `    const ${name} = `;
  const start = script.indexOf(marker);
  assert.notEqual(start, -1, `${name} bulunamadı.`);
  const expressionStart = start + marker.length;
  const expressionEnd = script.indexOf("\n    };", expressionStart);
  assert.notEqual(expressionEnd, -1, `${name} sonu bulunamadı.`);
  const expression = script.slice(expressionStart, expressionEnd + 6);
  return Function(`"use strict"; return (${expression});`)();
};

const normalizeClassSection = extractArrowFunction("normalizeClassSection");
const normalizeExamType = extractArrowFunction("normalizeExamType");

[
  "9-A",
  "9/A",
  "9 A",
  "9A",
  "9 – A",
  "9‑A",
  "9. Sınıf A",
  "9-A Şubesi"
].forEach((value) => assert.equal(normalizeClassSection(value), "9-A", value));
assert.equal(normalizeClassSection("9-B"), "9-B");

assert.equal(normalizeExamType("Dinleme"), "listening");
assert.equal(normalizeExamType("Dinleme/İzleme Sınavı"), "listening");
assert.equal(normalizeExamType("Yazılı Sınav"), "written");
assert.equal(normalizeExamType("YAZILI"), "written");
assert.equal(normalizeExamType("Konuşma"), "speaking");
assert.equal(normalizeExamType("□ Yazılı □ Dinleme □ Konuşma"), "");

assert.doesNotMatch(script, /const examTypeFromFileName/);
assert.doesNotMatch(script, /examTypeSource:\s*["']file-name["']/);
assert.match(script, /const attachOriginalFileMetadata =/);
assert.match(script, /documentRef: originalFileName/);
assert.match(script, /sourceFile: originalFileName/);
assert.match(script, /sourceFile: files\[index\]\?\.name \|\| student\.sourceFile \|\| ""/);

const groupingStart = script.indexOf("const consolidatedGroupMap = new Map()");
const keyStart = script.indexOf("const key =", groupingStart);
const keyEnd = script.indexOf(";", keyStart);
const groupingKey = script.slice(keyStart, keyEnd);
assert.match(groupingKey, /normalizedClassSection/);
assert.doesNotMatch(groupingKey, /normalizedExamType/);
assert.doesNotMatch(groupingKey, /course|courseName|questionShape|originalFileName|file-name/);
assert.match(script, /course: currentCourseName\(\) \|\| exam\.course/);

console.log("ocr-content-grouping.test.js: içerik temelli OCR gruplama kontrolleri geçti.");
