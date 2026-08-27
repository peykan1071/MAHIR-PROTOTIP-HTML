"use strict";

const assert = require("node:assert/strict");
const shared = require("../assets/js/mahir-shared-outcomes.js");

const questions = (scores, withOutcomes = false) => scores.map((maxScore, index) => ({
  number: index + 1,
  maxScore,
  outcomes: withOutcomes ? [{
    outcomeCode: `TDE${index + 1}`,
    outcomeDescription: `Çıktı ${index + 1}`,
    outcomeIndicators: [`Gösterge ${index + 1}`],
    outcomeTheme: "3. Tema",
    outcomeSkill: "Okuma",
    parentOutcomeCode: "TDE2",
    parentOutcomeDescription: "Üst çıktı",
    outcomeKey: `tema3-tde${index + 1}`,
    weight: 1
  }] : [],
  outcomeCode: withOutcomes ? `TDE${index + 1}` : "",
  outcomeDescription: withOutcomes ? `Çıktı ${index + 1}` : "",
  outcomeTheme: withOutcomes ? "3. Tema" : "",
  outcomeSkill: withOutcomes ? "Okuma" : "",
  parentOutcomeCode: withOutcomes ? "TDE2" : "",
  parentOutcomeDescription: withOutcomes ? "Üst çıktı" : "",
  outcomeKey: withOutcomes ? `tema3-tde${index + 1}` : ""
}));

const groups = [{
  exam: {
    course: "Türk Dili ve Edebiyatı",
    grade: "9",
    classSection: "9-A",
    examType: "Yazılı",
    componentType: "written"
  },
  questions: questions([40, 60], true),
  workflowStatus: "outcomes-complete"
}, {
  exam: {
    courseName: "Türk Dili ve Edebiyatı",
    classSection: "9-B",
    examType: "Yazılı"
  },
  questions: questions([40, 60]),
  workflowStatus: "checked"
}, {
  exam: {
    course: "Türk Dili ve Edebiyatı",
    classSection: "9-C",
    examType: "Dinleme"
  },
  questions: questions([40, 60]),
  workflowStatus: "checked"
}, {
  exam: {
    course: "Türk Dili ve Edebiyatı",
    classSection: "9-D",
    examType: "Yazılı"
  },
  questions: questions([50, 50]),
  workflowStatus: "checked"
}];

groups[0].questions[0].outcomes.push({
  ...groups[0].questions[0].outcomes[0],
  outcomeCode: "TDE1.2",
  outcomeDescription: "İkinci çıktı",
  outcomeKey: "tema3-tde1-2",
  weight: 0.5
});
groups[0].questions[0].outcomes[0].weight = 0.5;

assert.equal(shared.componentKey(groups[0].exam), "written");
assert.equal(shared.componentKey(groups[1].exam), "written");
assert.equal(
  shared.structureKey(groups[0], { grade: "9" }),
  shared.structureKey(groups[1], { grade: "9" }),
  "Teknik ve görünen sınav türü aynı paylaşım anahtarına dönüşmelidir."
);

assert.deepEqual(shared.applySharedOutcomes(groups, 0, { grade: "9" }), [1]);
assert.equal(groups[1].workflowStatus, "outcomes-complete");
assert.equal(groups[1].questions[0].outcomeCode, "TDE1");
assert.equal(groups[1].questions[0].outcomeTheme, "3. Tema");
assert.equal(groups[1].questions[0].outcomes.length, 2, "Bir soruya seçilen birden fazla çıktı birlikte aktarılmalıdır.");
assert.equal(groups[1].questions[0].outcomes[1].outcomeCode, "TDE1.2");
assert.deepEqual(groups[1].questions[0].outcomes[0].outcomeIndicators, ["Gösterge 1"]);
assert.deepEqual(groups[2].questions[0].outcomes, [], "Farklı sınav türüne çıktı taşınmamalıdır.");
assert.deepEqual(groups[3].questions[0].outcomes, [], "Farklı azami puan yapısına çıktı taşınmamalıdır.");

groups[1].questions[0].outcomes[0].outcomeIndicators.push("Yeni");
assert.deepEqual(
  groups[0].questions[0].outcomes[0].outcomeIndicators,
  ["Gösterge 1"],
  "Sınıflar arasında aynı nesne referansı paylaşılmamalıdır."
);

const legacyGroups = [{
  ...groups[0],
  questions: questions([40, 60], true),
  workflowStatus: "analyzed",
  analysis: { outcomes: [{ outcomeCode: "TDE1" }] }
}, {
  ...groups[1],
  questions: questions([40, 60]),
  workflowStatus: "analyzed",
  analysis: { outcomes: [] },
  trace: { agents: [] },
  reportApproved: true
}];
assert.deepEqual(
  shared.repairMissingSharedOutcomes(legacyGroups, { grade: "9" }),
  [{ sourceIndex: 0, candidateIndex: 1 }]
);
assert.equal(legacyGroups[1].workflowStatus, "outcomes-complete");
assert.equal(legacyGroups[1].questions[1].outcomeCode, "TDE2");
assert.equal(legacyGroups[1].analysis, null);
assert.equal(legacyGroups[1].trace, null);
assert.equal(legacyGroups[1].reportApproved, false);

console.log("shared-outcomes.test.js: ortak öğrenme çıktısı aktarımı doğrulandı.");
