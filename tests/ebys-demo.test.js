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
assert.equal(pkg.attachments[0].name, "MAHIR_Genel_Degerlendirme_Raporu.docx");
assert.equal(pkg.attachments.length, 4);
assert.equal(pkg.attachments[1].type, "Dayanak Bileşen Raporu");
assert.equal(pkg.coverLetter.signatoryRole, "Türk Dili ve Edebiyatı Öğretmeni");
assert.equal(pkg.coverLetter.signatoryName, "Örnek Öğretmen");
assert.equal(pkg.status, "draft");

console.log("ebys-demo.test.js: tüm kontroller geçti.");
