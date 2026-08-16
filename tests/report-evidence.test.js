"use strict";

// mahir-report-export-common.js bir IIFE (module.exports vermiyor), bu yüzden
// window/document stub'ı içeren bir vm bağlamında yükleniyor. Denenen şey D
// bölümünün ürettiği METİN: rapordaki "Kanıtları Gör" gösteriminin öğretmene
// ve jüriye söylediği cümlelerin kendisi.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "assets/js/mahir-report-export-common.js"), "utf8");

const element = (tag) => ({
  tagName: tag,
  className: "",
  children: [],
  textContent: "",
  append(...items) { this.children.push(...items); },
  querySelector() { return null; }
});

const sandbox = {
  window: {},
  document: { createElement: element, querySelector: () => null },
  Intl, Number, Math, String, Array, Object, Boolean, JSON, Date, RegExp, console
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const outcomeBlock = (analysis) => {
  sandbox.window.MAHIRReportRuntime = {
    structuredData: { exam: {}, questions: [], students: [] },
    analysis
  };
  return sandbox.window.MAHIRReportExport.getReportModel(null).blocks
    .find((block) => block.heading.startsWith("D."));
};

const analysisWith = (evidence) => ({
  summary: { participatingStudentCount: 35, questionCount: 3 },
  questions: [
    { number: 2, outcomeCode: "TDE9.OB2", outcomeTheme: "Sözün İnceliği", maxScore: 10, earnedScore: 252, successRate: 0.72 },
    { number: 5, outcomeCode: "TDE9.OB2", outcomeTheme: "Sözün İnceliği", maxScore: 10, earnedScore: 213.5, successRate: 0.61 },
    { number: 8, outcomeCode: "TDE9.OB2", outcomeTheme: "Sözün İnceliği", maxScore: 10, earnedScore: 245, successRate: 0.7 }
  ],
  outcomes: [{
    outcomeCode: "TDE9.OB2",
    outcomeTheme: "Sözün İnceliği",
    outcomeSkill: "Okuma",
    successRate: 0.68,
    category: "",
    decision: "Gelişim ihtiyacı",
    ...(evidence ? { evidence } : {})
  }]
});

const fullEvidence = {
  questionNumbers: [2, 5, 8],
  questionCount: 3,
  participatingStudentCount: 35,
  earnedScore: 710.5,
  possibleScore: 1050,
  correctedCellCount: 2,
  questions: [
    { number: 2, successRate: 0.72 },
    { number: 5, successRate: 0.61 },
    { number: 8, successRate: 0.7 }
  ]
};

// --- Tablo yapısı: A4 genişliği için sütun sayısı 5'te kalmalı ---

const block = outcomeBlock(analysisWith(fullEvidence));
// vm bağlamı kendi Array intrinsic'ini kullandığı için deepEqual gerçek-eşitlikte
// takılıyor; sütunları metin olarak karşılaştırmak hem yeterli hem okunaklı.
assert.equal(
  block.tables[0][0].join(" | "),
  "Öğrenme Çıktısı | Hesaplama Dayanağı | Başarı % | Düzey | Kanıt / Kısa Yorum"
);
assert.equal(block.details.column, 1, "Açılır kanıt 2. sütunda olmalı.");

// --- Belgeye giden düz metin: dört sayının hepsini taşımalı ---

const cellText = block.tables[0][1][1];
assert.match(cellText, /3 sorudan hesaplandı/);
assert.match(cellText, /35 katılımcı öğrenci/);
assert.match(cellText, /2 hücre öğretmen tarafından düzeltildi/);
assert.match(cellText, /Soru 2: %72/);
assert.match(cellText, /Soru 5: %61/);
assert.match(cellText, /Soru 8: %70/);
assert.match(cellText, /710,50 \/ 1\.050 puan/, "Puan toplamı tr-TR biçiminde olmalı.");

// --- Ekran/belge tutarlılığı: açılır özet, düz metnin ÖN EKİ olmak zorunda ---
// evidenceCell() bu ön eke göre bölüyor; bozulursa hücre sessizce düz metne
// düşer ve "Kanıtları Gör" etkileşimi kaybolur.

const summary = block.details.summaries[0];
assert.ok(cellText.startsWith(summary), "Özet, hücre metninin ön eki olmalı.");
assert.ok(cellText.length > summary.length, "Açılacak bir ayrıntı kalmalı.");

// --- Düzeltme yokken olumsuzluk açıkça yazılmalı (sessizce atlanmamalı) ---

const clean = outcomeBlock(analysisWith({ ...fullEvidence, correctedCellCount: 0 }));
assert.match(clean.details.summaries[0], /öğretmen düzeltmesi yok/);
assert.doesNotMatch(clean.details.summaries[0], /hücre öğretmen tarafından düzeltildi/);

// --- Geriye dönük uyum: evidence taşımayan eski analizde eski davranış ---

const legacy = outcomeBlock(analysisWith(null));
assert.equal(legacy.tables[0][1][1], "S2, S5, S8", "Kanıt yoksa eski soru listesi gösterilmeli.");
assert.equal(legacy.details.summaries[0], "S2, S5, S8");

// --- Hiç çıktı yoksa çökmemeli ---

const empty = outcomeBlock({ summary: {}, questions: [], outcomes: [] });
assert.equal(empty.details.summaries.length, 0);
assert.equal(empty.tables[0].length, 1, "Yalnız başlık satırı kalmalı.");

console.log("report-evidence.test.js: tüm kontroller geçti.");
