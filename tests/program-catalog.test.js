"use strict";

const assert = require("node:assert/strict");
const catalog = require("../assets/js/mahir-program-catalog.js");

assert.equal(catalog.resolve("Türk Dili ve Edebiyatı", "9").id, "tde-9-tymm");
assert.equal(catalog.resolve("Seçmeli Türk Dili ve Edebiyatı", "9. sınıf").id, "tde-9-tymm");
assert.equal(catalog.resolve("Türk Dili ve Edebiyatı", "10"), null);
assert.equal(catalog.resolve("Matematik", "9"), null);
assert.deepEqual(catalog.skillsForComponent("written"), ["Okuma", "Yazma"]);
assert.deepEqual(
  catalog.filterOutcomes([
    { id: "o", skill: "Okuma" },
    { id: "d", skill: "Dinleme/İzleme" },
    { id: "k", skill: "Konuşma" }
  ], "listening").map((item) => item.id),
  ["d"]
);
const processes = catalog.filterOutcomes([
  {
    id: "tema1-tde2-2",
    code: "TDE2.2",
    title: "Anlam oluşturabilme",
    skill: "Okuma",
    processComponents: [{ code: "TDE2.2.3", title: "Karşılaştırır." }]
  }
], "written");
assert.equal(processes.length, 1);
assert.equal(processes[0].code, "TDE2.2.3");
assert.equal(processes[0].parentCode, "TDE2.2");
assert.equal(processes[0].processComponent, true);

console.log("program-catalog.test.js: all assertions passed");
