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
      exam: { componentType, examSequence: componentType === "written" ? "1. Yazılı Sınav" : componentType === "listening" ? "1. Dinleme/İzleme Sınavı" : "1. Konuşma Sınavı" },
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
  assert.equal(contextRows.find((row) => row[0] === "Sınav Türü")[1], label);
  assert.equal(contextRows.find((row) => row[0] === "Dönem")[2], "Sınav Sırası");
});

[
  ["written", "MAHIR_Yazili_Sinav_Sonuclari_Analiz_Raporu.docx"],
  ["listening", "MAHIR_Dinleme_Izleme_Sinavi_Sonuclari_Analiz_Raporu.docx"],
  ["speaking", "MAHIR_Konusma_Sinavi_Sonuclari_Analiz_Raporu.docx"]
].forEach(([type, filename]) => {
  modelFor(type);
  assert.equal(sandbox.window.MAHIRReportExport.getDownloadFilename("docx"), filename);
});

const general = modelFor("general", "language-composite");
assert.equal(general.title, "TÜRK DİLİ VE EDEBİYATI GENEL DEĞERLENDİRME RAPORU");
assert.equal(general.blocks[0].tables[0].find((row) => row[0] === "Sınav Türü")[1], "Genel Değerlendirme");
assert.equal(sandbox.window.MAHIRReportExport.getDownloadFilename("pdf"), "MAHIR_Genel_Degerlendirme_Raporu.pdf");

const written = modelFor("written");
assert.deepEqual(Array.from(written.blocks[0].tableWidths[0]), [18, 32, 18, 32]);
assert.deepEqual(Array.from(written.blocks[1].tableWidths[0]), [18, 22, 20, 20, 20]);
assert.deepEqual(Array.from(written.blocks[2].tableWidths[0]), [6, 52, 10, 10, 10, 12]);
assert.deepEqual(Array.from(written.blocks[3].tableWidths[0]), [23, 29, 9, 13, 26]);

// OCR/öğrenci tablosundan kalmış eski sınav türü, analizde seçilen bileşeni ezemez.
sandbox.window.MAHIRReportRuntime = {
  structuredData: { exam: { componentType: "written", examType: "Yazılı Sınav" }, questions: [], students: [] },
  analysis: {
    exam: { componentType: "listening", examType: "Dinleme/İzleme Sınavı" },
    component: { componentType: "listening" }, summary: { participatingStudentCount: 1 }, questions: [], outcomes: []
  }
};
assert.equal(sandbox.window.MAHIRReportExport.getReportModel(null).title, "DİNLEME/İZLEME SINAVI SONUÇLARI ANALİZ RAPORU");
const portableListening = sandbox.window.MAHIRReportExport.getPortableReportPayload();
assert.equal(portableListening.exam.componentType, "listening");
assert.equal(portableListening.analysis.componentType, "listening");
assert.equal(portableListening.exam.examType, "Dinleme/İzleme Sınavı");

// Analizden sonra öğretmenin tamamladığı üstbilgi A/H bölümlerine ulaşmalı;
// eski analiz kopyası bu güncel değerleri ezmemeli.
sandbox.window.MAHIRReportRuntime.structuredData.exam = {
  componentType: "written", examType: "Yazılı Sınav", province: "ERZURUM",
  district: "PALANDÖKEN", schoolName: "MEHMET AKİF ANADOLU LİSESİ",
  teacherName: "Zülal ÜLKER DAŞTAN", academicYear: "2025-2026", classSection: "9-A",
  term: "1. Dönem", examDate: "2025-10-15", assessmentBasis: "MÜFREDAT",
  examSequence: "2. Yazılı Sınav",
  documentNo: "1", approvalInfo: "OKUL MÜDÜRLÜĞÜNE SUNULACAKTIR"
};
const completedHeaderModel = sandbox.window.MAHIRReportExport.getReportModel(null);
const completedHeaderRows = completedHeaderModel.blocks[0].tables[0].flat();
["ERZURUM", "PALANDÖKEN", "MEHMET AKİF ANADOLU LİSESİ", "Zülal ÜLKER DAŞTAN", "2025-2026", "9-A"]
  .forEach((value) => assert.ok(completedHeaderRows.includes(value)));
assert.ok(!completedHeaderModel.validation.missing.includes("Okul/Kurum Adı"));
assert.ok(completedHeaderRows.includes("2. Yazılı Sınav"));
assert.equal(sandbox.window.MAHIRReportExport.getPortableReportPayload().exam.examSequence, "2. Yazılı Sınav");
assert.equal(completedHeaderModel.title, "DİNLEME/İZLEME SINAVI SONUÇLARI ANALİZ RAPORU");

// Okul numarası ve puan gibi etiketsiz sayısallar kurumsal üstbilgiye sızamaz.
sandbox.window.MAHIRReportRuntime.analysis.exam = {
  componentType: "speaking", examType: "Konuşma Sınavı", province: "1010", district: "1001",
  schoolName: "995", teacherName: "123", academicYear: "95", classSection: "79"
};
const numericLeakModel = sandbox.window.MAHIRReportExport.getReportModel(null);
const numericLeakRows = numericLeakModel.blocks[0].tables[0].flat();
["1010", "1001", "995", "123", "95", "79"].forEach((value) => assert.ok(!numericLeakRows.includes(value)));

// Yüksek başarıda E ve F içeriksiz kalmaz; seçili çıktı dışında kod üretilmez.
sandbox.window.MAHIRReportRuntime.analysis.outcomes = [{ outcomeCode: "TDE.DİN.1", successRate: 0.82, ragContext: "", ragSources: [] }];
const highSuccessModel = sandbox.window.MAHIRReportExport.getReportModel(null);
assert.match(highSuccessModel.blocks[4].paragraphs[0], /öncelikli gelişim desteği gerektiren bir alan tespit edilmedi/);
assert.match(highSuccessModel.blocks[5].paragraphs[0], /doğrulanmış eğitim kaynakları/);
assert.match(highSuccessModel.blocks[5].tables[0][1][0], /TDE\.DİN\.1/);
assert.equal(highSuccessModel.blocks.at(-1).heading, "H. RESMÎ İŞLEM VE ONAY BİLGİLERİ");
assert.ok(!highSuccessModel.blocks.some((block) => /AJAN İZİ/.test(block.heading)));

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
