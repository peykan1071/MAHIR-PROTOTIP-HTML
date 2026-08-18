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

const TITLE = "Ortaöğretim Türk Dili ve Edebiyatı Dersi Öğretim Programı - Türkiye Yüzyılı Maarif Modeli (2024)";

// --- Hücrede KISA atıf, belgenin tam adı tablonun ALTINDA dipnotta ---
// Resmî ad uzun; her satırda tekrarlanması tabloyu okunamaz kılıyordu.

const cited = needsBlock([weak({ ragSources: [{ documentName: TITLE, pages: [66, 67] }] })]);
assert.equal(
  cited.tables[0][0].join(" | "),
  "Öğrenme Odağı | Öğrenme Kanıtının Gösterdiği Düzey | Pedagojik Yön | Kaynak Temelli Öneri"
);
const cell = cited.tables[0][1][3];
assert.match(cell, /örtük iletiyi belirleme/, "Teşhis metni korunmalı.");
assert.match(cell, /\(s\. 66-67\)$/, "Hücrede yalnız kısa atıf olmalı.");
assert.doesNotMatch(cell, /Ortaöğretim/, "Belgenin tam adı hücrede TEKRARLANMAMALI.");

assert.equal(cited.notes.length, 1, "Dipnot tek satır olmalı.");
assert.equal(cited.notes[0], `Kaynak: ${TITLE}`);

// --- Ardışık sayfalar aralığa iniyor, kopuklar virgülle ayrılıyor ---
// Sekiz getirim isabetinin ham sayfa listesi aksi hâlde hücreyi doldururdu.

const cellFor = (pages) =>
  needsBlock([weak({ ragSources: [{ documentName: TITLE, pages }] })]).tables[0][1][3];

assert.match(cellFor([66, 67, 68]), /\(s\. 66-68\)$/, "Ardışık sayfalar aralık olmalı.");
assert.match(cellFor([66, 71]), /\(s\. 66, 71\)$/, "Kopuk sayfalar virgülle ayrılmalı.");
assert.match(cellFor([66, 67, 71, 72, 90]), /\(s\. 66-67, 71-72, 90\)$/);
assert.match(cellFor([68, 66, 67]), /\(s\. 66-68\)$/, "Sırasız gelen sayfalar sıralanmalı.");
assert.match(cellFor([66, 66, 67]), /\(s\. 66-67\)$/, "Yinelenen sayfa tekilleşmeli.");

// --- İki belge: hücrede işaretçi, dipnotta ikisi de ---
// Tek belgede işaretçi yok (gürültü olurdu); ikiye çıkınca K1/K2 beliriyor.

const multi = needsBlock([
  weak({ ragSources: [{ documentName: TITLE, pages: [66, 67] }] }),
  weak({ outcomeCode: "TDE4.1", ragSources: [{ documentName: "Ek Kılavuz (2025)", pages: [4] }] })
]);
assert.match(multi.tables[0][1][3], /\(K1, s\. 66-67\)$/);
assert.match(multi.tables[0][2][3], /\(K2, s\. 4\)$/);
assert.equal(multi.notes[0], `Kaynak: K1: ${TITLE} · K2: Ek Kılavuz (2025)`);

// --- Sayfa bilgisi yoksa hücrede atıf yok; belge yine dipnotta anılır ---

const pageless = needsBlock([weak({ ragSources: [{ documentName: TITLE, pages: [] }] })]);
assert.doesNotMatch(pageless.tables[0][1][3], /\(s\./, "Sayfasız tek kaynakta sayfa atfı olmamalı.");
assert.equal(pageless.notes[0], `Kaynak: ${TITLE}`, "Belge yine de dipnotta anılmalı.");

// --- Kaynak yoksa ne atıf ne dipnot ---

const noSourceBlock = needsBlock([weak()]);
assert.doesNotMatch(noSourceBlock.tables[0][1][3], /\(s\./);
assert.equal(noSourceBlock.notes.length, 0, "Kaynak yoksa dipnot da olmamalı.");
assert.match(noSourceBlock.tables[0][1][3], /örtük iletiyi belirleme/, "Kaynak metni yine görünmeli.");

// --- Geriye dönük uyum: ragSources taşımayan eski analiz ---

const legacyOutcome = weak();
delete legacyOutcome.ragSources;
const legacyBlock = needsBlock([legacyOutcome]);
assert.equal(legacyBlock.notes.length, 0);
assert.match(legacyBlock.tables[0][1][3], /örtük iletiyi belirleme/);

// --- Teşhis hiç yoksa sütun eklenmemeli (bugünkü davranış korunuyor) ---

const noContext = needsBlock([weak({ ragContext: "", ragSources: [] })]);
assert.equal(noContext.tables[0][0].length, 4);
assert.equal(noContext.tables[0][1][3], "—");
assert.equal(noContext.notes.length, 0);

// --- Güçlü çıktı varsa F bölümü boş kalmamalı ---

const strongOnly = needsBlock([weak({ successRate: 0.9 })]);
assert.equal(strongOnly.tables[0].length, 2, "Güçlü çıktı satırı F bölümünde görünmeli.");
assert.match(strongOnly.paragraphs[0], /doğrulanmış eğitim kaynakları/);
assert.equal(strongOnly.tables[0][1][2], "Zenginleştirme");

// --- Dipnot, tablodan SONRA çiziliyor (paragraphs tablonun ÖNÜNDE) ---
// Dört render hedefi de once paragraphs, sonra tables, en son notes basıyor;
// dipnot `paragraphs`a konsaydı tablonun üstünde görünürdü.

const other = sandbox.window.MAHIRReportExport.getReportModel(null).blocks
  .filter((block) => !block.heading.startsWith("F.") && !block.heading.startsWith("G."));
assert.ok(other.every((block) => !(block.notes || []).length), "Kaynak notları yalnız öneri ve kaynak bölümlerinde olmalı.");
assert.ok(Array.isArray(cited.paragraphs), "paragraphs alanı korunmalı.");
assert.ok(
  cited.paragraphs.every((text) => !text.includes(TITLE)),
  "Belgenin tam adı paragraphs'a sızmamalı - orası tablonun ÖNÜ."
);

console.log("report-sources.test.js: tüm kontroller geçti.");
