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

// Teknik iz resmî rapor modeline hiçbir koşulda eklenmez. Teknik işlevler,
// ayrı demo/denetim ekranında kullanılabilmek üzere korunur.
assert.equal(traceBlock({ trace: TRACE }), undefined);
assert.equal(blocksWith({ trace: TRACE }).length, 8);
assert.match(sandbox.window.MAHIRReportExport.agentTaskText(TRACE.agents[0]), /8 soru, 35 öğrenci/);
assert.equal(sandbox.window.MAHIRReportExport.durationText(16700), "16,7 sn");

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
assert.equal(flagged.paragraphs.length, 2);
assert.match(flagged.paragraphs[0], /MAHİR değerlendirme ölçütü/);
assert.match(flagged.paragraphs[1], /Soru 4: Başarı oranı sıfır\./);
// Charter: bu bir gözlem, karar değil - kapanış cümlesi düşerse rapor, MAHİR'in
// yapmayacağını söylediği şeyi yapıyormuş gibi okunur.
assert.match(flagged.paragraphs[1], /hiçbir puanı veya oranı değiştirmez/);

// vm bağlamı kendi Array intrinsic'ini kullandığı için deepEqual gerçek-eşitlikte
// takılıyor (bkz. report-evidence.test.js'teki aynı not) - uzunluğa bakmak yeterli.
assert.equal(questionBlock("").paragraphs.length, 2);
assert.match(questionBlock("").paragraphs[1], /Ek bir ölçme bulgusu tespit edilmemiştir/);
assert.equal(questionBlock(undefined).paragraphs.length, 2);

console.log("report-trace.test.js: tüm kontroller geçti.");
