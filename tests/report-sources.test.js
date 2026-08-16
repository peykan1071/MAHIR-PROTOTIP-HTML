"use strict";

// mahir-report-export-common.js bir IIFE (module.exports vermiyor), bu yüzden
// window/document stub'ı içeren bir vm bağlamında yükleniyor - report-evidence
// testiyle aynı desen. Denenen şey F bölümünün ürettiği METİN: müfredat temelli
// teşhisin hangi belgenin hangi sayfasına dayandığı.

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
  Intl, Number, Math, String, Array, Object, Boolean, JSON, Date, RegExp, Set, console
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const needsBlock = (outcomes) => {
  sandbox.window.MAHIRReportRuntime = {
    structuredData: { exam: {}, questions: [], students: [] },
    analysis: {
      summary: { participatingStudentCount: 30, questionCount: outcomes.length },
      questions: [],
      outcomes
    }
  };
  return sandbox.window.MAHIRReportExport.getReportModel(null).blocks
    .find((block) => block.heading.startsWith("F."));
};

const weak = (extra = {}) => ({
  outcomeCode: "TDE2.2",
  outcomeTheme: "1. Tema: Sözün İnceliği",
  successRate: 0.35,
  decision: "İlave desteğe ihtiyaç vardır.",
  ragContext: "'Sözün İnceliği' temasında örtük iletiyi belirleme bileşeninde tıkanma var.",
  ragSources: [],
  ...extra
});

// --- Kaynak, teşhisin ardına ekleniyor (ayrı sütun DEĞİL) ---
// A4 genişliğinde tablo zaten beş sütun; altıncısı okunabilirliği bozardı.

const cited = needsBlock([weak({ ragSources: [{ documentName: "tdeogr.pdf", pages: [66] }] })]);
assert.equal(
  cited.tables[0][0].join(" | "),
  "Sıra | Tespit Edilen İhtiyaç | Değerlendirme Sonucu | Öncelik Düzeyi | Kavramsal Bağlam"
);
const cell = cited.tables[0][1][4];
assert.match(cell, /örtük iletiyi belirleme/, "Teşhis metni korunmalı.");
assert.match(cell, /\(Kaynak: tdeogr\.pdf, s\. 66\)/);
assert.ok(cell.indexOf("Kaynak:") > cell.indexOf("örtük"), "Kaynak teşhisin ARDINDA olmalı.");

// --- Ardışık sayfalar aralığa iniyor, kopuklar virgülle ayrılıyor ---
// Sekiz getirim isabetinin ham sayfa listesi aksi hâlde hücreyi doldururdu.

const cellFor = (pages) =>
  needsBlock([weak({ ragSources: [{ documentName: "tdeogr.pdf", pages }] })]).tables[0][1][4];

assert.match(cellFor([66, 67, 68]), /s\. 66-68\)/, "Ardışık sayfalar aralık olmalı.");
assert.match(cellFor([66, 71]), /s\. 66, 71\)/, "Kopuk sayfalar virgülle ayrılmalı.");
assert.match(cellFor([66, 67, 71, 72, 90]), /s\. 66-67, 71-72, 90\)/);
assert.match(cellFor([68, 66, 67]), /s\. 66-68\)/, "Sırasız gelen sayfalar sıralanmalı.");
assert.match(cellFor([66, 66, 67]), /s\. 66-67\)/, "Yinelenen sayfa tekilleşmeli.");

// --- İki belge ayrı ayrı anılmalı ---

const twoDocs = cellFor.call(null, [66]) && needsBlock([weak({
  ragSources: [
    { documentName: "tdeogr.pdf", pages: [66, 67] },
    { documentName: "ek-kilavuz.pdf", pages: [4] }
  ]
})]).tables[0][1][4];
assert.match(twoDocs, /tdeogr\.pdf, s\. 66-67; ek-kilavuz\.pdf, s\. 4/);

// --- Sayfa bilgisi yoksa yalnız belge adı; kaynak yoksa hiç ek yok ---

assert.match(cellFor([]), /\(Kaynak: tdeogr\.pdf\)/, "Sayfasız kaynak yalnız adıyla anılmalı.");
const noSource = needsBlock([weak()]).tables[0][1][4];
assert.doesNotMatch(noSource, /Kaynak/, "Kaynak yoksa parantez hiç eklenmemeli.");
assert.match(noSource, /örtük iletiyi belirleme/, "Teşhis yine de görünmeli.");

// --- Geriye dönük uyum: ragSources taşımayan eski analiz ---

const legacyOutcome = weak();
delete legacyOutcome.ragSources;
const legacy = needsBlock([legacyOutcome]).tables[0][1][4];
assert.doesNotMatch(legacy, /Kaynak/);
assert.match(legacy, /örtük iletiyi belirleme/);

// --- Teşhis hiç yoksa sütun eklenmemeli (bugünkü davranış korunuyor) ---

const noContext = needsBlock([weak({ ragContext: "", ragSources: [] })]);
assert.equal(noContext.tables[0][0].length, 4, "Kavramsal Bağlam sütunu hiç eklenmemeli.");

// --- Güçlü çıktı F bölümüne hiç girmemeli ---

const strongOnly = needsBlock([weak({ successRate: 0.9 })]);
assert.equal(strongOnly.tables[0].length, 1, "Yalnız başlık satırı kalmalı.");

console.log("report-sources.test.js: tüm kontroller geçti.");
