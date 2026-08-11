"use strict";

const assert = require("node:assert/strict");
const corrections = require("../assets/js/mahir-score-corrections.js");

const student = (technicalId, scores) => ({ technicalId, scores });

// --- Tek hücre kuralları ---

assert.equal(corrections.isCorrection(8, 6), true, "Makine değerini değiştirmek düzeltmedir.");
assert.equal(corrections.isCorrection(8, 8), false, "Aynı değer düzeltme sayılmaz.");
assert.equal(
  corrections.isCorrection(null, 9),
  false,
  "Makine okuyamadıysa hücreyi doldurmak 'öğretmen doldurdu'dur, düzeltme değil."
);
assert.equal(corrections.isCorrection(undefined, 9), false);
assert.equal(corrections.isCorrection("", 9), false);
assert.equal(corrections.isCorrection(8, null), true, "Dolu bir hücreyi boşaltmak düzeltmedir.");
assert.equal(corrections.isCorrection(8, ""), true);
assert.equal(corrections.isCorrection("7,5", 7.5), false, "Ondalık virgül aynı sayıyı ifade eder.");
assert.equal(corrections.isCorrection(7.1, "7,10"), false);
assert.equal(corrections.isCorrection("7,5", 7.6), true);

// --- Satır/soru bazında dağılım ---

const original = [
  student("Ö-001", [10, 8, 6]),
  student("Ö-002", [9, 7, 5])
];
const approved = [
  student("Ö-001", [10, 9, 6]),   // yalnız 2. soru düzeltildi
  student("Ö-002", [4, 7, 5])     // yalnız 1. soru düzeltildi
];
const diff = corrections.diffScores(original, approved);
assert.equal(diff.total, 2);
assert.deepEqual(diff.byQuestionIndex, { 0: 1, 1: 1 }, "Sayım soru indeksine göre dağılmalı.");

// Aynı soruda birden çok satır düzeltilirse tek indekste toplanır.
const sameQuestion = corrections.diffScores(original, [
  student("Ö-001", [3, 8, 6]),
  student("Ö-002", [2, 7, 5])
]);
assert.deepEqual(sameQuestion.byQuestionIndex, { 0: 2 });
assert.equal(sameQuestion.total, 2);

// Hiç düzeltme yoksa boş sonuç.
const untouched = corrections.diffScores(original, original.map((item) => ({ ...item })));
assert.equal(untouched.total, 0);
assert.deepEqual(untouched.byQuestionIndex, {});

// --- Elle giriş: tüm özgün değerler null, düzeltme sayısı 0 olmalı ---

const manualOriginal = [student("Ö-001", [null, null, null])];
const manualApproved = [student("Ö-001", [10, 9, 8])];
assert.equal(
  corrections.diffScores(manualOriginal, manualApproved).total,
  0,
  "Elle giriş modunda hiçbir hücre 'düzeltilmiş' sayılmamalı."
);

// --- Satır eşleştirme teknik kimliğe göre, sıraya göre değil ---

const reordered = corrections.diffScores(original, [
  student("Ö-002", [9, 7, 5]),   // sıra değişti ama değerler aynı
  student("Ö-001", [10, 8, 6])
]);
assert.equal(reordered.total, 0, "Satırlar technicalId ile eşleşmeli, dizideki sırayla değil.");

// Teknik kimlik yoksa indekse düşülür (tek gruplu akışta sıra birebir aynı).
const withoutIds = corrections.diffScores(
  [{ scores: [10, 8] }],
  [{ scores: [10, 5] }]
);
assert.equal(withoutIds.total, 1);
assert.deepEqual(withoutIds.byQuestionIndex, { 1: 1 });

// Onaylı listede özgünü olmayan satır (sonradan eklenmiş) sayıma girmez.
const extraRow = corrections.diffScores([], [student("Ö-009", [5, 5])]);
assert.equal(extraRow.total, 0);

// --- Bozuk/eksik girdiler çökertmemeli ---

assert.deepEqual(corrections.diffScores(null, null), { total: 0, byQuestionIndex: {} });
assert.deepEqual(corrections.diffScores(undefined, [{}]), { total: 0, byQuestionIndex: {} });

// --- Grup toplama ---

const merged = corrections.mergeCorrections(
  { total: 2, byQuestionIndex: { 0: 2 } },
  { total: 1, byQuestionIndex: { 0: 1, 3: 1 } },
  null
);
assert.equal(merged.total, 4);
assert.deepEqual(merged.byQuestionIndex, { 0: 3, 3: 1 });
assert.deepEqual(corrections.mergeCorrections(), { total: 0, byQuestionIndex: {} });

console.log("score-corrections.test.js: tüm kontroller geçti.");
