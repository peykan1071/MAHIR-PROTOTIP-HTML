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
assert.match(html, /data-general-report-merger/);
assert.match(html, /Yazılı Sınav Analiz Raporu/);
assert.match(html, /Dinleme\/İzleme Sınavı Analiz Raporu/);
assert.match(html, /Konuşma Sınavı Analiz Raporu/);
assert.match(html, /data-merge-general-reports/);
assert.match(html, /öğrenci bazlı e-Okul puanı hesaplanmaz/);
assert.match(html, /data-scenario-guidance/);
assert.match(html, /Yazılı sınavın dayandığı senaryo/);
assert.match(html, /data-validation-student-count-control/);
assert.match(html, /Beklenen öğrenci sayısı/);
assert.match(html, /data-edit-validation-student-count>Düzenle<\/button>/);
assert.match(html, /data-undo-student-record>Geri Al<\/button>/);

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
assert.match(script, /Bu gruptaki \$\{current\} öğrenci kaydı henüz kaydedilmedi/);
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
assert.match(script, /createOutcomeCombobox/);
assert.match(script, /nativeSelect\.multiple = true/);
assert.match(script, /aria-multiselectable/);
assert.match(script, /const weight = selected\.length \? 1 \/ selected\.length : 0/);
assert.match(script, /Birden fazla çıktı seçilebilir; soru puanı seçilen çıktılar arasında eşit paylaşılır/);
assert.match(script, /options\.slice\(0, 8\)/);
assert.match(script, /role", "combobox/);
assert.match(script, /role", "listbox/);
assert.match(script, /ArrowDown/);
assert.match(script, /ArrowUp/);
assert.match(script, /Home/);
assert.match(script, /End/);
assert.match(script, /Enter/);
assert.match(script, /Escape/);
assert.match(script, /nativeSelect\.dispatchEvent\(new Event\("change"/);
assert.match(script, /fetch\(`\/mahir-merge-reports\?\$\{mergeQuery\}`/);
assert.match(script, /Raporları Doğrula ve Birleştir/);
assert.match(script, /updateGeneralReportMode/);
assert.match(script, /const removeStudentRecord = \(row\) =>/);
assert.match(script, /selectedFiles\.splice\(removedFileIndex, 1\)/);
assert.match(script, /renderCurrentStudents\(students, remainingWarnings\)/);
assert.match(script, /const undoStudentRecordRemoval = \(\) =>/);
assert.match(script, /const applyValidationStudentCount = \(\) =>/);
assert.match(script, /studentCountInput\.value = String\(value\)/);
assert.match(script, /Fazla kaydı çıkarabilir veya beklenen sayıyı düzenleyebilirsiniz/);
assert.match(script, /× Kaydı çıkar/);
assert.doesNotMatch(script, /shared\/report-example\.txt/);
assert.doesNotMatch(script, /payload\.reportText|payload\.report_text/);
assert.match(script, /Analiz özeti oluşturulamadı\. Verileri ve servis bağlantısını kontrol ederek yeniden deneyiniz\./);
assert.doesNotMatch(script, /Sample Exam CSV|MAT\.5\.1|SOS\.5\.1/);
assert.doesNotMatch(script, /data-finish-data-entry/);
assert.doesNotMatch(script, /data-return-to-data/);
assert.match(styles, /\.post-save-card\[hidden\][\s\S]*\.final-data-review-card\[hidden\][\s\S]*display: none !important/);
assert.match(styles, /\.outcome-combobox-listbox[\s\S]*overflow-x: hidden;[\s\S]*overflow-y: auto;/);
assert.match(styles, /\.outcome-combobox-option[\s\S]*white-space: normal;[\s\S]*overflow-wrap: anywhere;/);
assert.match(styles, /\.outcome-combobox-value[\s\S]*white-space: nowrap;[\s\S]*text-overflow: ellipsis;/);
assert.match(styles, /\.general-report-slots[\s\S]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/);
assert.match(styles, /\.question-configuration-list\[hidden\][\s\S]*display: none !important/);
assert.match(html, /MAHİR'den indirilen üç Word \(\.docx\) analiz raporu gereklidir/);
assert.match(html, /Word \(\.docx\):[\s\S]*Genel Değerlendirme ekranına yüklenebilir/);
assert.match(html, /PDF:[\s\S]*Genel Değerlendirme ekranına yüklenemez/);
assert.match(styles, /\.report-download-guidance[\s\S]*grid-column: 1 \/ -1/);
assert.match(styles, /\.validation-student-count-control[\s\S]*grid-template-columns/);
assert.match(styles, /\.student-record-remove-button[\s\S]*cursor: pointer/);
assert.match(styles, /\.student-record-undo\[hidden\][\s\S]*display: none !important/);

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
