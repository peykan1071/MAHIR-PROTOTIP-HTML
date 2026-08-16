"use strict";

// mahir-report-export-common.js bir IIFE (module.exports vermiyor), bu yüzden
// window/document stub'ı içeren bir vm bağlamında yükleniyor - report-evidence
// testiyle aynı desen. Denenen şey I. bölümün ürettiği METİN: "bu raporu kim
// üretti"nin öğretmene ve jüriye söylediği cümleler.

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
  Intl, Number, Math, String, Array, Object, Boolean, JSON, Date, RegExp, console
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

const ANALYSIS = {
  summary: { participatingStudentCount: 35, questionCount: 3, classAverage: 21 },
  questions: [
    { number: 1, outcomeDescription: "kazanım", maxScore: 10, successRate: 0.72, level: "İyi" }
  ],
  outcomes: []
};

const agent = (name, label, overrides = {}) => ({
  agent: name,
  label,
  description: `${label} adımı`,
  durationMs: 3,
  outputs: {},
  issues: [],
  llmCalls: [],
  failed: false,
  skipped: false,
  ...overrides
});

const TRACE = {
  agents: [
    agent("belge-anlama", "Belge Anlama", { outputs: { questionCount: 8, studentCount: 35 } }),
    agent("program-eslestirme", "Program Eşleştirme", {
      durationMs: 12,
      outputs: { programId: "tde9", outcomeCount: 8, unmappedQuestionCount: 0 }
    }),
    agent("olcme-degerlendirme", "Ölçme ve Değerlendirme", {
      durationMs: 5,
      outputs: { measuredQuestionCount: 8, measuredOutcomeCount: 8, correctedCellTotal: 2 },
      llmCalls: [{ agent: "olcme-degerlendirme", promptChars: 400 }]
    }),
    agent("pedagojik-analiz", "Pedagojik Analiz", {
      durationMs: 16700,
      outputs: { outcomeCount: 8, weakOutcomeCount: 8, curriculumGroundedCount: 8 },
      llmCalls: new Array(8).fill({ agent: "pedagojik-analiz", promptChars: 4200 })
    }),
    agent("raporlama", "Raporlama", { durationMs: 1, outputs: { sectionCount: 5 } })
  ],
  issues: []
};

const blocksWith = (runtimeExtra) => {
  sandbox.window.MAHIRReportRuntime = {
    structuredData: { exam: {}, questions: [], students: [] },
    analysis: ANALYSIS,
    ...runtimeExtra
  };
  return sandbox.window.MAHIRReportExport.getReportModel(null).blocks;
};

const traceBlock = (runtimeExtra) =>
  blocksWith(runtimeExtra).find((block) => block.heading.startsWith("I."));

// --- İz yokken rapor BUGÜNKÜYLE birebir aynı kalmalı ---
// Kaydedilmiş eski çalışmalar ve genel dil değerlendirmesi iz taşımıyor;
// oralarda boş bir "I. bölüm" göstermek raporu bozmuş olurdu.

const withoutTrace = blocksWith({});
assert.equal(withoutTrace.length, 8, "İz yokken bölüm sayısı değişmemeli.");
assert.equal(traceBlock({}), undefined, "İz yokken I. bölüm hiç üretilmemeli.");
assert.equal(
  traceBlock({ trace: { agents: [], issues: [] } }),
  undefined,
  "Boş ajan listesi de bölüm üretmemeli."
);

// --- İz varken bölüm ve sütunlar ---

const block = traceBlock({ trace: TRACE });
assert.ok(block, "İz varken I. bölüm üretilmeli.");
assert.equal(blocksWith({ trace: TRACE }).length, 9);
assert.equal(
  block.tables[0][0].join(" | "),
  "Ajan | Yaptığı İş | Süre | Dil Modeli Çağrısı | Durum"
);
assert.equal(block.tables[0].length, 6, "Başlık + beş ajan satırı.");

// --- Her ajan kendi işini kendi sayılarıyla anlatmalı ---

const rowFor = (label) => block.tables[0].find((row) => row[0] === label);

assert.match(rowFor("Belge Anlama")[1], /8 soru, 35 öğrenci/);
assert.match(rowFor("Program Eşleştirme")[1], /8 öğrenme çıktısı/);
assert.match(rowFor("Ölçme ve Değerlendirme")[1], /8 soru, 8 öğrenme çıktısı hesaplandı/);
assert.match(rowFor("Ölçme ve Değerlendirme")[1], /2 öğretmen düzeltmesi/);
assert.match(rowFor("Pedagojik Analiz")[1], /8 müfredat temelli teşhis/);

// --- Süre ve LLM sayımı ---

assert.equal(rowFor("Belge Anlama")[2], "3 ms");
assert.equal(rowFor("Pedagojik Analiz")[2], "16,7 sn", "Saniyeye geçiş tr-TR biçiminde olmalı.");
assert.equal(rowFor("Belge Anlama")[3], "—", "LLM kullanmayan ajanda tire olmalı.");
assert.equal(rowFor("Pedagojik Analiz")[3], "8");
assert.equal(rowFor("Raporlama")[4], "Tamam");

// --- Ortak dil modeli turu KENDİ satırında ---
// Süreyi ajanlara bölüştürmek uydurma olurdu: dokuz istem tek istekte
// çözülüyor. Ayrıca tek istekli mimarinin kanıtı da bu satır - bölüştürülseydi
// "9 çağrı, tek tur" görünmez olurdu.

const withRound = traceBlock({
  trace: { ...TRACE, llmRound: { promptCount: 9, resultCount: 9, durationMs: 16700, ok: true } }
});
const roundRow = withRound.tables[0][withRound.tables[0].length - 1];
assert.equal(roundRow[0], "Dil modeli turu (ortak)");
assert.match(roundRow[1], /9 istem tek istekte çözüldü/);
assert.equal(roundRow[2], "16,7 sn");
assert.equal(roundRow[4], "Tamam");
assert.equal(withRound.tables[0].length, 7, "Başlık + beş ajan + ortak tur.");

// Tur yapılmadıysa (kayıtsız ders, LLM kapalı) satır hiç eklenmemeli.
assert.equal(block.tables[0].length, 6, "Tur yoksa yalnız ajan satırları kalmalı.");

const failedRound = traceBlock({
  trace: { ...TRACE, llmRound: { promptCount: 9, resultCount: 0, durationMs: 300, ok: false } }
});
assert.equal(failedRound.tables[0][failedRound.tables[0].length - 1][4], "Tamamlanamadı");

// --- Arızalı ve atlanan ajanlar öğretmene açıkça söylenmeli ---

const brokenTrace = {
  agents: [
    agent("olcme-degerlendirme", "Ölçme ve Değerlendirme", { failed: true }),
    agent("pedagojik-analiz", "Pedagojik Analiz", { skipped: true })
  ],
  issues: []
};
const brokenBlock = traceBlock({ trace: brokenTrace });
assert.equal(brokenBlock.tables[0][1][4], "Tamamlanamadı");
assert.equal(brokenBlock.tables[0][2][4], "Çalıştırılmadı");
assert.match(brokenBlock.tables[0][2][1], /çalıştırılmadı/i);

// --- Bilinmeyen ajan tabloyu bozmamalı, açıklamasına düşmeli ---

const futureBlock = traceBlock({
  trace: { agents: [agent("evrak-dogrulama", "Evrak Doğrulama")], issues: [] }
});
assert.equal(futureBlock.tables[0][1][1], "Evrak Doğrulama adımı");

// --- Anomali bulgusu C bölümünde, kapanış cümlesiyle birlikte ---

const questionBlock = (anomalies) => {
  sandbox.window.MAHIRReportRuntime = {
    structuredData: { exam: {}, questions: [], students: [] },
    analysis: { ...ANALYSIS, summary: { ...ANALYSIS.summary, anomalies } }
  };
  return sandbox.window.MAHIRReportExport.getReportModel(null).blocks
    .find((item) => item.heading.startsWith("C."));
};

const flagged = questionBlock("Soru 4: Başarı oranı sıfır.");
assert.equal(flagged.paragraphs.length, 1);
assert.match(flagged.paragraphs[0], /Ölçme ve Değerlendirme Ajanı'nın dikkat çektiği noktalar/);
assert.match(flagged.paragraphs[0], /Soru 4: Başarı oranı sıfır\./);
// Charter: bu bir gözlem, karar değil - kapanış cümlesi düşerse rapor, MAHİR'in
// yapmayacağını söylediği şeyi yapıyormuş gibi okunur.
assert.match(flagged.paragraphs[0], /hiçbir puanı veya oranı değiştirmez/);

// vm bağlamı kendi Array intrinsic'ini kullandığı için deepEqual gerçek-eşitlikte
// takılıyor (bkz. report-evidence.test.js'teki aynı not) - uzunluğa bakmak yeterli.
assert.equal(questionBlock("").paragraphs.length, 0, "Bulgu yoksa paragraf eklenmemeli.");
assert.equal(questionBlock(undefined).paragraphs.length, 0, "Alan hiç yoksa da paragraf olmamalı.");

console.log("report-trace.test.js: tüm kontroller geçti.");
