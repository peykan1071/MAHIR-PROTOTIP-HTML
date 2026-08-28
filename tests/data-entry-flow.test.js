"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "styles.css"), "utf8");

assert.match(html, /id="saved-groups-title">Sınavlar/);
assert.match(html, /data-confirm-final-analysis hidden>Sınav Analizlerine Başla/);
assert.match(html, /data-return-to-saved-reports hidden>Raporlara Geri Dön/);
assert.match(html, /data-open-general-evaluation>Üç Raporla Genel Değerlendirme Oluştur/);
assert.match(html, /data-analysis-path checked/);
assert.match(html, /Sınav Evraklarını Analiz Et/);
assert.match(html, /yeni sınav evrakı yüklemeyin/);
assert.match(html, /Genel değerlendirme için üç Word \(\.docx\) raporu gerekir/);
assert.match(html, /Sabit ağırlıklar: Yazılı %70 · Dinleme\/izleme %15 · Konuşma %15/);
assert.ok(
  html.indexOf("data-confirm-final-analysis") > html.indexOf("data-validation-errors-card"),
  "Toplu onay düğmesi sınav ve kontrol kartlarının sonunda olmalıdır."
);
assert.match(html, /Sınavlara Dön/);
assert.doesNotMatch(html, /Kaydedilen Gruplar|Sınav Gruplarına Dön|OCR tarafından oluşturulan sınav grubu/);
assert.match(script, /const approveAllSavedExams =/);
assert.match(script, /confirmFinalButton\.dataset\.examsApproved/);
assert.match(script, /confirmFinalButton\.textContent = hasAnalyzedExam \? "Sınav Analizlerine Devam Et" : "Sınav Analizlerine Başla"/);
assert.match(script, /const analyzeAllSavedExamsSequentially = async/);
assert.match(script, /for \(const groupIndex of readyIndexes\)/);
assert.match(script, /await analyzeNextReadyGroup\(groupIndex/);
assert.match(script, /showAnalysisScreen: false/);
assert.match(html, /<h3>Sınav Raporları<\/h3>/);
assert.match(script, /const showSavedExamReport =/);
assert.match(script, /renderAnalysis\(group\.analysis, group\.trace, \{ allowApprovedReportSwitch: true \}\)/);
assert.match(script, /reportLocked === "true" && !allowApprovedReportSwitch/);
assert.match(script, /returnToSavedReportsButton\.hidden = !hasAnalyzedExam/);
assert.match(script, /showSavedExamReport\(reportIndex\)/);
assert.match(script, /assessmentComponent\.value = "general"/);
assert.match(script, /generalReportMerger\?\.scrollIntoView/);
assert.match(script, /analysisPathInputs\.forEach/);
assert.match(script, /const tdeGeneralEnabled = isPrototypeScopeEnabled\(\) && profileId === "tde-70-15-15"/);
assert.match(script, /analysisPathCard\.hidden = !tdeGeneralEnabled/);
assert.match(styles, /\[data-analysis-path-card\]\[hidden\]\s*\{[^}]*display: none !important/s);
assert.match(script, /const isGeneralEvaluationReport = String\(reportRuntime\.exam\?\.componentType \|\| ""\) === "general"/);
assert.match(script, /generalEvaluationEntry\.hidden = currentProfileId\(\) !== "tde-70-15-15" \|\| !isGeneralEvaluationReport/);
assert.match(styles, /\[data-general-evaluation-entry\]\[hidden\]\s*\{[^}]*display: none !important/s);
assert.match(script, /input\.value === "general" \? "general" : "written"/);
assert.match(script, /button\.dataset\.viewSavedReport = String\(index\)/);
assert.match(script, /const isReadyForAnalysis = group\.workflowStatus === "outcomes-complete"/);
assert.match(script, /button\.dataset\.analyzeNextGroup = String\(index\)/);
assert.match(script, /isReadyForAnalysis\s*\? "Analizi Başlat"/);
assert.match(script, /Rapor görüntüleniyor/);
assert.match(script, /Raporu Görüntüle/);
assert.match(script, /group\.reportApproved = Boolean\(event\.target\.checked\)/);
assert.match(script, /mahir:report-approval-state/);
assert.match(html, /data-ebys-prepare disabled aria-disabled="true"/);
assert.doesNotMatch(script, /typeSelect\.dataset\.inlineExamField = "examType"/);
assert.doesNotMatch(script, /questionMapCard\.append\(outcomeActions\)/);
assert.match(html, /<tr><th>Sınıf\/Şube<\/th><td colspan="5">9-A<\/td><\/tr>/);
assert.doesNotMatch(html, /<tr><th>Sınav Türü<\/th><td colspan="5">Yazılı<\/td><\/tr>/);
assert.match(html, /Sınıf\/şube \(ör\. 9-A\) açıkça belirtilmelidir/);

assert.match(script, /questions\.length < 1 \|\| questions\.length > 15/);
assert.match(script, /Azami puanların toplamı tam olarak 100 olmalıdır/);
assert.match(script, /Her azami puan sıfırdan büyük tam sayı olmalıdır/);
assert.match(script, /Toplam puan 0–100 arasında tam sayı olmalıdır/);
assert.match(script, /Aynı öğrenci referansı bu sınavda birden fazla kez bulunuyor/);
assert.match(script, /Sınav türü yalnız Yazılı, Dinleme veya Konuşma olmalıdır/);
assert.match(html, /max="15"[^>]*data-recovered-question-count/);
assert.match(html, /data-question-count required/);

assert.match(script, /const studentReferenceSortKey =/);
assert.match(script, /const normalizeDetectedQuestionStructure =/);
assert.match(script, /question\.maximumScore/);
assert.match(script, /groupMaximums\[index\]/);
assert.match(script, /const componentTypeFromExam =/);
assert.match(script, /\.map\(normalizeDetectedQuestionStructure\)/);
assert.match(script, /componentType: normalizedExamType/);
assert.match(script, /const sortStudentsByReference =/);
assert.match(script, /sourceFile: usefulValue\(student\.sourceFile\)/);
assert.match(script, /sourceLink\.textContent = value/);
assert.doesNotMatch(script, /examTypeSource:\s*["']file-name["']/);
assert.doesNotMatch(script, /const examTypeFromFileName/);

assert.doesNotMatch(script, /isImageUpload && \(legacyRowExplosion \|\| !hasReadableGroupContext\)/);
assert.match(script, /student\.scores\?\.\[questionIndex\] \?\? ""/);
assert.match(script, /student\.studentNo \|\| ""/);

assert.match(html, /id="question-map-title">Ortak Öğrenme Çıktıları/);
assert.match(html, /assets\/js\/mahir-shared-outcomes\.js[\s\S]*script\.js/);
assert.match(script, /MAHIRSharedOutcomes\?\.componentKey\(exam\)/);
assert.match(script, /MAHIRSharedOutcomes\?\.applySharedOutcomes\(/);
assert.match(script, /MAHIRSharedOutcomes\?\.repairMissingSharedOutcomes\(/);
assert.match(script, /nativeSelect\.multiple = true/);
assert.match(script, /İsteğe bağlı — öğrenme çıktısı seçiniz/);
assert.match(script, /listbox\.hidden = true/);
assert.match(script, /outcome\.indicators\.forEach/);
assert.match(styles, /\.outcome-combobox-listbox\[hidden\]/);
assert.doesNotMatch(script, /saved-exam-outcome-select/);
assert.match(script, /outcomes: availableOutcomes/);
assert.match(script, /options\.slice\(0, 9\)/);
assert.match(script, /Math\.min\(visibleOptionHeight, 420, availableSpace\)/);
assert.match(script, /item\.append\(heading, privacyNotice, tableWrap/);
assert.match(script, /const placeQuestionMapAtPageEnd =/);
assert.match(script, /if \(finalReviewMode\) placeQuestionMapAtPageEnd\(\)/);
assert.match(script, /startOutcomeSelection\(0\)/);
assert.match(script, /saveCurrentOutcomeSelection\(\) \|\| !approveAllSavedExams\(\)/);
const outcomeSaveBlock = script.slice(
  script.indexOf("const saveCurrentOutcomeSelection ="),
  script.indexOf("const nextGroupForAnalysis =")
);
assert.doesNotMatch(outcomeSaveBlock, /validateStudents/);
assert.doesNotMatch(outcomeSaveBlock, /students: approvedData\.students/);
assert.match(script, /maxLabel\.textContent = "Azami Puan"/);
assert.doesNotMatch(script, /inlineQuestionGroupIndex/);
assert.match(script, /cell\.textContent = value;\s*maxScoreRow\.append\(cell\)/);
assert.match(script, /checkAndSaveButton\.textContent = "Kontrol Et ve Kaydet"/);
assert.match(script, /checkAndSaveButton\.dataset\.reviewSavedGroup = String\(index\)/);
assert.match(styles, /\.saved-group-check-button\s*\{[^}]*margin-inline-start: auto/s);

assert.match(html, /data-ocr-progress-bar/);
assert.match(html, /data-batch-upload-guidance/);
assert.match(script, /bütün şubelerine ait aynı tür sınav evraklarını tek seferde yükleyebilirsiniz/);
assert.match(script, /yalnız açıkça yazılmış sınıf\/şube bilgisine göre ayırır/);
assert.match(script, /farklı sınav türlerini aynı yüklemeye karıştırmayınız/);
assert.match(script, /examStructureCard\.hidden = sourceMode !== "manual"/);
assert.match(script, /targetRowCount = sourceMode === "manual" \? expectedStudentCount : parsedStudents\.length/);
assert.match(script, /Öğrenci referanslarını ve soru puanlarını elle giriniz/);
assert.match(script, /repairEmptyManualTable/);
assert.match(script, /looksLikeManualEntry/);
assert.match(script, /examType: componentLabels\[assessmentComponent\?\.value \|\| "written"\]/);
assert.match(script, /En az bir öğrenci kaydı bulunmalıdır/);
assert.match(script, /savedGroups\.length} sınavda toplam \$\{totalRecords} kaynak görsel korunuyor/);
assert.match(script, /examGroupLabel\(group\.exam\).*evrak/);
assert.match(html, /data-ocr-elapsed/);
assert.match(html, /data-ocr-remaining/);
assert.match(script, /const updateOcrProgress =/);
assert.match(script, /Tahmini kalan süre/);
assert.match(script, /let retryOcrFiles = \[\]/);
assert.match(script, /başarılı sonuçlar korundu\. Yalnız bu evrakları yeniden deneyebilirsiniz/);
assert.match(script, /analysis-loading/);
assert.match(styles, /\.ocr-progress-card/);
assert.match(styles, /@keyframes mahir-spin/);

assert.match(script, /mahir-ocr-draft-v1/);
assert.match(script, /const saveOcrDraft =/);
assert.match(script, /const restoreOcrDraft =/);
assert.match(script, /Otomatik kaydedilen OCR taslağı geri getirildi/);
assert.match(html, /dönem, sınav sırası, sınav tarihi ve öğretim programı bir kez okunduğunda veya tamamlandığında bu çalışmadaki bütün sınıf raporlarına uygulanır; sınıf\/şube bilgisi her sınav için ayrı korunur/);
assert.match(html, /data-exam-field="academicYear"[^>]*pattern="\[0-9\]\{4\}-\[0-9\]\{4\}"/);
assert.match(script, /const sharedReportContextFieldNames = new Set/);
assert.match(script, /"province", "district", "schoolName", "teacherName", "academicYear"/);
assert.match(script, /"term", "examSequence", "examDate", "teachingProgram"/);
assert.match(script, /if \(field === "examDate"\) return normalizeDateInputValue\(value\)/);
assert.match(script, /if \(detectedComponent\) updateExamSequenceOptions\(detectedComponent\)/);
assert.match(script, /const propagateSharedReportContext =/);
assert.match(script, /savedGroups = savedGroups\.map\(\(group\) => \(\{ \.\.\.group, exam: applyField\(group\.exam\) \}\)\)/);
assert.match(script, /sharedReportContext,/);
assert.match(script, /sharedReportContext = normalizeSharedReportContext\(draft\.sharedReportContext \|\| \{\}\)/);
assert.match(script, /const normalizeAcademicYear =/);
assert.match(script, /Number\(match\[2\]\) !== Number\(match\[1\]\) \+ 1/);
assert.match(script, /Okul adı bu alana yazılamaz/);

console.log("data-entry-flow.test.js: OCR kılavuzu kabul kontrolleri geçti.");
