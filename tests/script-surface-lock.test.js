"use strict";

// script.js'in ÜST DÜZEY YÜZEYİNİ kilitler.
//
// Dosya bir zamanlar ilk 1.672 satırında `window.MAHIR` altında ikinci bir
// "ajan" katmanı taşıyordu (AIOrchestrator, DocumentAgent, StructuringAgent,
// gövdesi boş `class OCRService {}`...). O katman canlı akışın parçası
// DEĞİLDİ: tek dış kanalı `window.MAHIR` idi ve onu hiçbir yer okumuyordu;
// DOM'a, olaylara, depolamaya, ağa hiç dokunmuyordu. Yanıltıcıydı çünkü
// gerçek ajan hattıyla (backend/app/agents/) aynı isimleri taşıyor ama hiçbir
// iş yapmıyordu. 2026-09-24'te silindi.
//
// Bu test o katmanın geri sızmasını ve canlı yüzeyin bozulmasını engeller.

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");

// --- Silinen katman geri gelmemeli ---
const banned = [
  "window.MAHIR =",
  "class AIOrchestrator",
  "class BaseAgent",
  "class OCRService",
  "class LLMService",
  "createMockInput",
  "MAHIR.orchestrator",
  "MAHIR.agents"
];
for (const needle of banned) {
  assert.ok(
    !script.includes(needle),
    `script.js yeniden '${needle}' icermemeli - silinen window.MAHIR ajan katmani geri gelmis olabilir.`
  );
}

// --- Canlı yüzey yerinde durmalı ---
assert.ok(script.startsWith('"use strict";'), "script.js '\"use strict\";' ile baslamali.");

const surface = [
  "const preparationManager = (() => {",
  "const screenManager = (() => {",
  "const fileUploadBridge = (() => {",
  "const reportApprovalManager = (() => {"
];
for (const needle of surface) {
  assert.ok(script.includes(needle), `script.js '${needle}' icermeli - canli ust duzey modul kaybolmus.`);
}

// Tek giriş noktası ve dört init çağrısı
assert.ok(script.includes('document.addEventListener("DOMContentLoaded", () => {'), "DOMContentLoaded girisi kaybolmus.");
for (const call of ["preparationManager.init();", "screenManager.init();", "fileUploadBridge.init();", "reportApprovalManager.init();"]) {
  assert.ok(script.includes(call), `DOMContentLoaded blogunda '${call}' bulunmali.`);
}

// --- Silinen ölü dallar geri gelmemeli ---
// Bu data-* oznitelikleri hicbir yerde ATANMIYORDU; onlari okuyan dallar
// hic tetiklenmiyordu. Canli karsiliklari: data-analyze-next-group,
// data-view-saved-report, data-review-saved-group.
for (const needle of ["data-select-classified-group", "data-analyze-saved-group", "data-question-map-summary", "data-classified-groups"]) {
  assert.ok(!script.includes(needle), `script.js '${needle}' icermemeli - karsiliksiz secici geri gelmis.`);
}
// Cagrilmayan fonksiyonlar
for (const needle of ["createSavedOutcomeSummary", "const currentStudents ="]) {
  assert.ok(!script.includes(needle), `script.js '${needle}' icermemeli - cagrilmayan tanim geri gelmis.`);
}

// --- Dosya derlenebilir olmalı ---
assert.doesNotThrow(() => new vm.Script(script, { filename: "script.js" }), "script.js derlenemiyor.");

console.log("script-surface-lock.test.js: script.js ust duzey yuzey kilidi kontrolleri gecti.");
