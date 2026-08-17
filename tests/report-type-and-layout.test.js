"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const commonSource = fs.readFileSync(path.join(root, "assets/js/mahir-report-export-common.js"), "utf8");
const docxSource = fs.readFileSync(path.join(root, "assets/js/mahir-docx-exporter.js"), "utf8");
const pdfSource = fs.readFileSync(path.join(root, "assets/js/mahir-pdf-exporter.js"), "utf8");

const element = (tag) => ({
  tagName: tag,
  className: "",
  children: [],
  textContent: "",
  style: {},
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
vm.runInContext(commonSource, sandbox);

const modelFor = (componentType, assessmentScope = "component") => {
  sandbox.window.MAHIRReportRuntime = {
    structuredData: {
      exam: { componentType },
      questions: [],
      students: []
    },
    analysis: {
      assessmentScope,
      component: { componentType },
      summary: { participatingStudentCount: 10 },
      questions: [],
      outcomes: []
    }
  };
  return sandbox.window.MAHIRReportExport.getReportModel(null);
};

[
  ["written", "YAZILI SINAV SONUÇLARI ANALİZ RAPORU", "Yazılı Sınav", "B. YAZILI SINAV BAŞARI ÖZETİ"],
  ["listening", "DİNLEME/İZLEME SINAVI SONUÇLARI ANALİZ RAPORU", "Dinleme/İzleme Sınavı", "B. DİNLEME/İZLEME SINAVI BAŞARI ÖZETİ"],
  ["speaking", "KONUŞMA SINAVI SONUÇLARI ANALİZ RAPORU", "Konuşma Sınavı", "B. KONUŞMA SINAVI BAŞARI ÖZETİ"]
].forEach(([type, title, label, summaryHeading]) => {
  const model = modelFor(type);
  assert.equal(model.title, title);
  assert.equal(model.blocks[1].heading, summaryHeading);
  assert.match(model.blocks[1].paragraphs[0], new RegExp(`^${label}`));
  const contextRows = model.blocks[0].tables[0];
  assert.equal(contextRows.find((row) => row[2] === "Sınav Türü")[3], label);
});

const general = modelFor("general", "language-composite");
assert.equal(general.title, "TÜRK DİLİ VE EDEBİYATI GENEL DEĞERLENDİRME RAPORU");
assert.equal(general.blocks[0].tables[0].find((row) => row[2] === "Sınav Türü")[3], "Genel Değerlendirme");

const written = modelFor("written");
assert.deepEqual(Array.from(written.blocks[0].tableWidths[0]), [18, 32, 18, 32]);
assert.deepEqual(Array.from(written.blocks[1].tableWidths[0]), [18, 22, 20, 20, 20]);
assert.deepEqual(Array.from(written.blocks[2].tableWidths[0]), [6, 52, 10, 10, 10, 12]);
assert.deepEqual(Array.from(written.blocks[3].tableWidths[0]), [23, 29, 9, 13, 26]);

assert.match(docxSource, /columnWidthsDxa/);
assert.match(docxSource, /widths: block\.tableWidths\?\.\[index\]/);
assert.match(docxSource, /<w:tblHeader\/>/);
assert.match(docxSource, /<w:cantSplit\/>/);
assert.doesNotMatch(docxSource, /CONTENT_WIDTH_DXA \/ columnCount/);

assert.match(pdfSource, /normalizeColumnWidths/);
assert.match(pdfSource, /block\.tableWidths\?\.\[index\]/);
assert.match(pdfSource, /tableLayout\.columnWidths\[columnIndex\]/);
assert.doesNotMatch(pdfSource, /const columnWidth = width \/ columnCount/);

console.log("report-type-and-layout.test.js: tüm kontroller geçti.");
