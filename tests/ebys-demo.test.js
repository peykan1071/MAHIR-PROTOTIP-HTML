"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "../assets/js/mahir-ebys-demo.js"), "utf8");
const sandbox = {
  window: {},
  document: { addEventListener() {}, querySelector() { return null; } },
  String, Object, Array, JSON, Date, Blob, URL, setTimeout, console
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const model = { metadata: [
  { label: "Okul/Kurum Adı", value: "Örnek Anadolu Lisesi" },
  { label: "Öğretmenin Adı Soyadı", value: "Örnek Öğretmen" },
  { label: "Ders", value: "Türk Dili ve Edebiyatı" },
  { label: "Sınıf/Şube", value: "9/A" },
  { label: "Dönem", value: "1. Dönem" },
  { label: "Sınav Türü", value: "Genel Değerlendirme" }
] };
const pkg = sandbox.window.MAHIREBYSDemo.buildPackage(model, "MAHIR_Genel_Degerlendirme_Raporu.docx");
assert.equal(pkg.simulation, true);
assert.match(pkg.notice, /gerçek EBYS sistemine belge göndermez/);
assert.equal(pkg.routing.addressee, "OKUL / KURUM MÜDÜRLÜĞÜNE");
assert.equal(pkg.officialFields.ebysDocumentNumber, null);
assert.equal(pkg.officialFields.ebysTransactionDate, null);
const multiple = sandbox.window.MAHIREBYSDemo.buildPackage(model, "current.docx", [
  { label: "9-A — Yazılı", classSection: "9-A", examType: "Yazılı", filename: "9-A.docx" },
  { label: "9-B — Yazılı", classSection: "9-B", examType: "Yazılı", filename: "9-B.docx" }
]);
assert.equal(multiple.attachments.length, 2);
assert.match(multiple.coverLetter.subject, /9-A \/ 9-B yazılı/);
assert.equal(multiple.coverLetter.body, "Türk Dili ve Edebiyatı dersi 9-A / 9-B sınıf/şubesine ait yazılı sınav sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere analiz raporları ekte sunulmuştur.");
const listening = sandbox.window.MAHIREBYSDemo.buildPackage(model, "current.docx", [
  { label: "9-A — Dinleme", classSection: "9-A", examType: "Dinleme", filename: "9-A-dinleme.docx" },
  { label: "9-B — Dinleme", classSection: "9-B", examType: "Dinleme", filename: "9-B-dinleme.docx" }
]);
assert.equal(listening.coverLetter.body, "Türk Dili ve Edebiyatı dersi 9-A / 9-B sınıf/şubesine ait dinleme sınav sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere analiz raporları ekte sunulmuştur.");
const speaking = sandbox.window.MAHIREBYSDemo.buildPackage(model, "current.docx", [
  { label: "9-A — Konuşma", classSection: "9-A", examType: "Konuşma", filename: "9-A-konusma.docx" },
  { label: "9-B — Konuşma", classSection: "9-B", examType: "Konuşma", filename: "9-B-konusma.docx" }
]);
assert.equal(speaking.coverLetter.body, "Türk Dili ve Edebiyatı dersi 9-A / 9-B sınıf/şubesine ait konuşma sınav sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere analiz raporları ekte sunulmuştur.");
const general = sandbox.window.MAHIREBYSDemo.buildPackage(model, "current.docx", [
  { label: "9-A — Yazılı", classSection: "9-A", examType: "Yazılı", filename: "yazili.docx" },
  { label: "9-A — Dinleme", classSection: "9-A", examType: "Dinleme", filename: "dinleme.docx" },
  { label: "9-A — Konuşma", classSection: "9-A", examType: "Konuşma", filename: "konusma.docx" }
]);
assert.equal(general.coverLetter.body, "Türk Dili ve Edebiyatı dersi 9-A sınıf/şubesine ait yazılı, dinleme ve konuşma sınavları sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere genel değerlendirme analiz raporları ekte sunulmuştur.");
const modelWithoutClass = { metadata: model.metadata.map((item) => item.label === "Sınıf/Şube" ? { ...item, value: "" } : item) };
const reportSuppliesClass = sandbox.window.MAHIREBYSDemo.buildPackage(modelWithoutClass, "current.docx", [
  { label: "9-A — Konuşma", classSection: "9-A", examType: "Konuşma", filename: "9-A-konusma.docx" }
]);
assert.equal(reportSuppliesClass.status, "draft");
assert.doesNotMatch(reportSuppliesClass.missingInformation.join(","), /Sınıf\/Şube/);
assert.match(reportSuppliesClass.coverLetter.body, /9-A sınıf\/şubesine ait konuşma sınav sonuçları/);
assert.equal(pkg.attachments[0].name, "MAHIR_Genel_Degerlendirme_Raporu.docx");
assert.equal(pkg.attachments.length, 4);
assert.equal(pkg.attachments[1].type, "Dayanak Bileşen Raporu");
assert.equal(pkg.coverLetter.signatoryRole, "Türk Dili ve Edebiyatı Öğretmeni");
assert.equal(pkg.coverLetter.signatoryName, "Örnek Öğretmen");
assert.equal(pkg.status, "draft");

console.log("ebys-demo.test.js: tüm kontroller geçti.");
