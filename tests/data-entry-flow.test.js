"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");

assert.match(html, /data-save-current-group>Verileri Kontrol Et ve Kaydet<\/button>/);
assert.match(html, /data-return-to-upload>Dosya Yükleme Aşamasına Dön<\/button>/);
assert.match(html, /data-return-to-approved-data>Onaylanan Verilere Dön<\/button>/);
assert.match(html, /data-return-to-analysis>Analiz Sonucuna Dön<\/button>/);
assert.match(html, /data-document-read-guidance/);
assert.doesNotMatch(html, /Veri Girişini Tamamla/);
assert.doesNotMatch(html, /Verilere Dön ve Düzenle/);
assert.doesNotMatch(html, /Bu Grubun Verilerini Kaydet/);
assert.match(html, /data-saved-groups-card hidden/);
assert.match(html, /data-add-image-group>Yeni Görsel Grubu Ekle<\/button>/);
assert.match(html, /data-confirm-final-analysis>Verileri Onayla ve Analize Geç<\/button>/);

assert.match(script, /if \(total === expected\) \{\s*showFinalReview\(\);\s*return;/);
assert.match(script, /addGroupButton\.hidden = sourceMode !== "images" \|\| total >= expected/);
assert.match(script, /sourceMode === "images"[\s\S]*Math\.max\(parsedStudents\.length, selectedFiles\.length \|\| 1\)[\s\S]*Math\.max\(parsedStudents\.length, expectedStudentCount\)/);
assert.match(script, /MAHİR şablonuna uygun öğrenci tablosu bulunamadı/);
assert.match(script, /aşağıda açılan \$\{expectedStudentCount\} boş satırı elle tamamlayabilirsiniz/);
assert.match(script, /screenManager\.showScreen\("data-entry-screen"\)/);
assert.match(script, /Eski analiz ve rapor geçersiz sayıldı/);
assert.match(script, /screenManager\.revokeDataApproval\(\)/);
assert.match(script, /returnToAnalysisButton\.disabled = isApproved/);
assert.doesNotMatch(script, /data-finish-data-entry/);
assert.doesNotMatch(script, /data-return-to-data/);

console.log("data-entry-flow.test.js: all assertions passed");
