"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "styles.css"), "utf8");

assert.match(html, /MAHİR Veri Giriş Şablonu<\/h3>/);
assert.match(html, /shared\/templates\/MAHIR_Veri_Giris_Sablonu\.docx/);
assert.match(html, /Puan Çizelgesi Görseli \(OCR\)/);
assert.match(html, /Öğrenci bazlı puan çizelgesi görsellerini yükleyin\./);
assert.match(html, /Ornek_Sinav_Kagidi_Soru_Bazli_Puan_Cizelgesi\.docx/);
assert.match(html, /Örnek Sınav Kâğıdını İndir/);
assert.match(html, /data-ocr-guidance/);
assert.match(html, /Soru Bazlı Puan Çizelgesi/);
assert.match(html, /Çizelge yapısı/);
assert.match(html, /renk, ölçü ve tasarımının örnekle aynı olması gerekmez/);
assert.match(html, /Uygun olmayan belgeler/);
assert.match(html, /bu alanda işleme alınmaz/);
assert.match(html, /Kişisel verilerin korunması/);
assert.match(html, /data-personal-data-warning/);
assert.match(html, /Öğrenci adı, soyadı, T\.C\. kimlik numarası ve gereksiz diğer kişisel verileri yüklemeyiniz veya girmeyiniz/);
assert.match(html, /yalnızca okul numarasını kullanınız/);
assert.ok(html.indexOf("data-personal-data-warning") < html.indexOf("data-ocr-guidance"));
assert.match(html, /Belirsiz okunan alanlar analizden önce öğretmen onayına sunulacaktır\./);
assert.doesNotMatch(html, /Öğrenci T\.C\. kimlik numarası yüklemeyiniz/);
assert.match(html, /Öğrencinin Aldığı Puan/);
assert.doesNotMatch(html, /MAHİR Veri Giriş Şablonu\s*[–-]\s*Sürüm/);
assert.match(html, /data-save-current-group>Verileri Kontrol Et ve Kaydet<\/button>/);
assert.match(html, /data-return-to-upload>Dosya Yükleme Aşamasına Dön<\/button>/);
assert.match(html, /data-return-to-approved-data>Onaylanan Verilere Dön<\/button>/);
assert.match(html, /data-return-to-analysis>Analiz Sonucuna Dön<\/button>/);
assert.match(html, /data-document-read-guidance/);
assert.match(html, /KVKK veri minimizasyonu:/);
assert.match(html, /analiz ve LLM katmanına oturumluk takma öğrenci referansı aktarılır/);
assert.doesNotMatch(html, /Veri Girişini Tamamla/);
assert.doesNotMatch(html, /Verilere Dön ve Düzenle/);
assert.doesNotMatch(html, /Bu Grubun Verilerini Kaydet/);
assert.match(html, /data-saved-groups-card hidden/);
assert.match(html, /data-add-image-group>Yeni Görsel Grubu Ekle<\/button>/);
assert.match(html, /data-confirm-final-analysis>Verileri Onayla ve Analize Geç<\/button>/);

assert.match(script, /if \(total === expected\) \{\s*showFinalReview\(\);\s*return;/);
assert.match(script, /ocrGuidance\?\.toggleAttribute\("hidden", mode !== "images"\)/);
assert.match(script, /Çizelge Fotoğraflarını Seç/);
assert.match(script, /Belirsiz okunan alanlar analizden önce öğretmen onayına sunulacaktır\./);
assert.doesNotMatch(script, /Öğrenci T\.C\. kimlik numarası yüklemeyiniz/);
assert.match(script, /addGroupButton\.hidden = sourceMode !== "images" \|\| total >= expected/);
assert.match(script, /const startNewGroup = \(\) => \{[\s\S]*clearAllFiles\(\);[\s\S]*clearValidationErrors\(\);/);
assert.doesNotMatch(script, /clearFile\(\)/);
assert.match(script, /if \(returnToUploadButton\) returnToUploadButton\.hidden = true/);
assert.match(script, /sourceMode === "images"[\s\S]*Math\.max\(parsedStudents\.length, selectedFiles\.length \|\| 1\)[\s\S]*Math\.max\(parsedStudents\.length, expectedStudentCount\)/);
assert.match(script, /Veriler öğretmen kontrolüne sunulmuştur\. Kaydetmeden önce otomatik kontroller çalıştırılacaktır\./);
assert.doesNotMatch(script, /kontrol edilmesi gereken bir sorun tespit etmedi/);
assert.match(script, /Bu gruptaki \$\{students\.length\} öğrenci kaydı henüz kaydedilmedi/);
assert.match(script, /Toplam \$\{total\}\/\$\{expected\} öğrenci kaydı korunuyor/);
assert.doesNotMatch(script, /öğrenci kaydı daha eklenmeden analiz onayı/);
assert.match(script, /const sourceFile = payload\.fileName \|\| selectedFiles\[payloadIndex\]\?\.name \|\| ""/);
assert.match(script, /sourceFile: student\.sourceFile \|\| sourceFile/);
assert.match(script, /showSourceFile \? \["Kaynak Görsel"\] : \[\]/);
assert.match(script, /row\.dataset\.sourceFile = student\.sourceFile \|\| ""/);
assert.match(script, /sourceFile: row\.dataset\.sourceFile \|\| ""/);
assert.match(script, /OCR okuyamadı; veri öğretmen tarafından tamamlandı/);
assert.match(script, /studentRef: student\.technicalId \|\| `Ö-/);
assert.match(script, /studentIdentityMode: "session-pseudonymized"/);
assert.doesNotMatch(script, /students: \(approvedData\.students \|\| \[\]\)\.map\(\(student, index\) => \(\{\s*\.\.\.student/);
assert.match(script, /MAHİR şablonuna uygun öğrenci tablosu bulunamadı/);
assert.match(script, /aşağıda açılan \$\{expectedStudentCount\} boş satırı elle tamamlayabilirsiniz/);
assert.match(script, /screenManager\.showScreen\("data-entry-screen"\)/);
assert.match(script, /Eski analiz ve rapor geçersiz sayıldı/);
assert.match(script, /screenManager\.revokeDataApproval\(\)/);
assert.match(script, /returnToAnalysisButton\.disabled = isApproved/);
assert.doesNotMatch(script, /data-finish-data-entry/);
assert.doesNotMatch(script, /data-return-to-data/);
assert.match(styles, /\.post-save-card\[hidden\][\s\S]*\.final-data-review-card\[hidden\][\s\S]*display: none !important/);

// Düzeltme sayımının zamanlaması: fark, savedGroups.push İÇİNDE alınmak
// zorunda. students orada DOM'dan (düzeltilmiş) gelirken structuredData hâlâ
// makinenin okuduğu özgün değerleri tutuyor; startNewGroup() hemen ardından
// structuredData'yı null yapıp o değerleri yok ediyor. Çağrı buradan çıkarsa
// sayım sessizce sıfırlanır - bu yüzden kaynakta sabitleniyor.
assert.match(
  script,
  /savedGroups\.push\(\{[\s\S]*?corrections: window\.MAHIRScoreCorrections\?\.diffScores\(structuredData\?\.students, students\)[\s\S]*?\}\);/,
  "Düzeltme farkı savedGroups.push içinde, grup kaydedilirken alınmalı."
);
assert.match(script, /startNewGroup = \(\) => \{[\s\S]*?structuredData = null/);
// Sayım analiz yüküne girmeli, yoksa rapordaki kanıt hep "düzeltme yok" der.
assert.match(script, /correctedCells: \(window\.MAHIRScoreCorrections\?\.mergeCorrections\(/);
assert.match(html, /assets\/js\/mahir-score-corrections\.js/);

console.log("data-entry-flow.test.js: all assertions passed");
