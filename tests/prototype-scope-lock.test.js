"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
const script = fs.readFileSync(path.join(root, "script.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "styles.css"), "utf8");

assert.match(html, /data-prototype-scope-lock[^>]*role="alert"/);
assert.match(html, /Bu prototipte analiz yalnız <strong>Branş Öğretmeni · Lise · 9\. sınıf · Türk Dili ve Edebiyatı<\/strong> için etkindir\./);
assert.match(html, /data-target-screen="preparation-screen">Hazırlık Seçimlerine Dön<\/button>/);
assert.doesNotMatch(html, /data-role-upload-guide[^>]*data-standard-data-entry/);

assert.match(script, /currentRole\(\) === "Branş Öğretmeni"[\s\S]*currentStage\(\) === "Lise"[\s\S]*currentGrade\(\) === "9"[\s\S]*currentCourseName\(\) === "Türk Dili ve Edebiyatı"/);
assert.match(script, /const updatePrototypeScopeLock = \(\) =>/);
assert.match(script, /standardDataEntryItems\.forEach\(\(item\) => \{ item\.hidden = true; \}\)/);
assert.match(script, /option\.disabled = !enabled/);
assert.match(script, /fileInput\.disabled = !enabled/);
assert.match(script, /readButton\.disabled = true/);
assert.match(script, /const selectFiles = \(files\) => \{[\s\S]*if \(!isPrototypeScopeEnabled\(\)\)/);
assert.match(script, /const uploadSelectedFile = \(\) => \{[\s\S]*if \(!isPrototypeScopeEnabled\(\)\)/);
assert.match(script, /const teacherTitle = currentRole\(\) === "Branş Öğretmeni" && currentCourseName\(\)[\s\S]*`\$\{currentCourseName\(\)\} Öğretmeni`/);

assert.match(styles, /\.prototype-scope-lock \{/);
assert.match(styles, /\.prototype-scope-lock\[hidden\] \{[\s\S]*display: none;/);
assert.match(styles, /\.file-select-button\[aria-disabled="true"\]/);

// Kapsam dışı bırakılan hassas bölümlerin mevcut OCR ve puanlama akışında
// hâlâ yer aldığını doğrular; bu yama bu mantıkları değiştirmemelidir.
assert.match(script, /legacyRowExplosion/);
assert.match(script, /processedDocumentKeys\.size \+ newSessionDocuments\.length > 100/);
assert.match(script, /azami puanı sıfırdan büyük olmalıdır/);
assert.match(script, /uploadChunksWithConcurrency\(uploadChunks, 3\)/);

console.log("prototype-scope-lock.test.js: prototip kapsam kilidi kontrolleri geçti.");
