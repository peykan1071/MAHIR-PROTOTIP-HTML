"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const catalog = require("../assets/js/mahir-program-catalog.js");

const curriculum = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "shared", "pilot", "tde9", "learning-outcomes-template.json"),
  "utf8"
)).learning_outcomes;

assert.equal(curriculum.length, 54);
assert.equal(curriculum.reduce((sum, outcome) => sum + outcome.processComponents.length, 0), 237);
assert.equal(curriculum.reduce((sum, outcome) => sum + outcome.processComponents.reduce(
  (componentSum, component) => componentSum + component.indicators.length,
  0
), 0), 614);
assert.deepEqual(
  new Set(catalog.filterOutcomes(curriculum, "listening").map((outcome) => outcome.skill)),
  new Set(["Dinleme/İzleme"])
);
assert.deepEqual(
  new Set(catalog.filterOutcomes(curriculum, "speaking").map((outcome) => outcome.skill)),
  new Set(["Konuşma"])
);
assert.deepEqual(
  new Set(catalog.filterOutcomes(curriculum, "written").map((outcome) => outcome.skill)),
  new Set(["Okuma", "Yazma"])
);

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
    processComponents: [{
      code: "TDE2.2.3",
      title: "Karşılaştırır.",
      indicators: ["Okuduğu metinleri belirlenen ölçütlere göre karşılaştırır."]
    }]
  }
], "written");
assert.equal(processes.length, 1);
assert.equal(processes[0].code, "TDE2.2.3");
assert.equal(processes[0].parentCode, "TDE2.2");
assert.deepEqual(processes[0].indicators, ["Okuduğu metinleri belirlenen ölçütlere göre karşılaştırır."]);
assert.equal(processes[0].processComponent, true);

console.log("program-catalog.test.js: all assertions passed");
