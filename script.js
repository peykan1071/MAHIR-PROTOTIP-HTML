"use strict";

/* =========================================================
   MAHIR AI ENGINE CORE - FEATURE 23
   ========================================================= */
(() => {
  const version = "0.23.0";

  const createId = (prefix) => {
    const randomId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    return `${prefix}-${randomId}`;
  };

  const createSession = () => ({
    id: createId("mahir-session"),
    createdAt: new Date().toISOString(),
    teacherSelections: {},
    uploadedFiles: [],
    analysisStatus: "idle",
    reportStatus: "idle"
  });

  const createInitialState = () => ({
    context: {},
    documents: {},
    structuredData: {},
    curriculum: {},
    statistics: {},
    pedagogy: {},
    evidence: {},
    report: {},
    validation: {},
    teacherApproval: {},
    logs: []
  });

  const createEventBus = () => {
    const listeners = new Map();

    return {
      on(eventName, handler) {
        if (typeof handler !== "function") {
          return () => {};
        }

        const handlers = listeners.get(eventName) || new Set();
        handlers.add(handler);
        listeners.set(eventName, handlers);

        return () => this.off(eventName, handler);
      },

      off(eventName, handler) {
        const handlers = listeners.get(eventName);

        if (!handlers) {
          return;
        }

        handlers.delete(handler);

        if (handlers.size === 0) {
          listeners.delete(eventName);
        }
      },

      emit(eventName, payload = {}) {
        const handlers = listeners.get(eventName);

        if (!handlers) {
          return;
        }

        handlers.forEach((handler) => {
          handler(payload);
        });
      }
    };
  };

  const createLogger = (state) => ({
    start(agentName) {
      const entry = {
        id: createId("mahir-log"),
        agent: agentName,
        startedAt: new Date().toISOString(),
        finishedAt: null,
        durationMs: null,
        status: "started",
        success: false
      };

      state.logs.push(entry);
      return entry;
    },

    finish(entry, success = true) {
      const finishedAt = new Date();
      const startedAt = new Date(entry.startedAt);

      entry.finishedAt = finishedAt.toISOString();
      entry.durationMs = Math.max(0, finishedAt.getTime() - startedAt.getTime());
      entry.status = success ? "completed" : "failed";
      entry.success = Boolean(success);

      return entry;
    },

    info(message, details = {}) {
      const entry = {
        id: createId("mahir-log"),
        message,
        details,
        createdAt: new Date().toISOString(),
        status: "info",
        success: true
      };

      state.logs.push(entry);
      return entry;
    }
  });

  class BaseAgent {
    constructor({ name, state, logger, events }) {
      this.name = name;
      this.state = state;
      this.logger = logger;
      this.events = events;
      this.status = "idle";
    }

    initialize() {
      this.status = "initialized";
      return Promise.resolve({ agent: this.name, status: this.status });
    }

    execute() {
      this.status = "executed";
      return Promise.resolve({ agent: this.name, status: this.status });
    }

    validate() {
      this.status = "validated";
      return Promise.resolve({ agent: this.name, status: this.status });
    }

    export() {
      this.status = "exported";
      return Promise.resolve({ agent: this.name, status: this.status });
    }

    reset() {
      this.status = "idle";
      return Promise.resolve({ agent: this.name, status: this.status });
    }
  }

  class DocumentAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "DocumentAgent" });
    }
  }

  class StructuringAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "StructuringAgent" });
    }
  }

  class CurriculumAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "CurriculumAgent" });
    }
  }

  class MeasurementAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "MeasurementAgent" });
    }
  }

  class PedagogyAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "PedagogyAgent" });
    }
  }

  class EvidenceAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "EvidenceAgent" });
    }
  }

  class ValidationAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "ValidationAgent" });
    }
  }

  class ReportAgent extends BaseAgent {
    constructor(config) {
      super({ ...config, name: "ReportAgent" });
    }
  }

  class OCRService {}
  class LLMService {}
  class CurriculumService {}
  class StatisticsService {}
  class ReportService {}

  class AIOrchestrator {
    constructor({ agents, logger, events }) {
      this.agents = agents;
      this.logger = logger;
      this.events = events;
      this.flow = [
        "DocumentAgent",
        "StructuringAgent",
        "CurriculumAgent",
        "MeasurementAgent",
        "PedagogyAgent",
        "EvidenceAgent",
        "ValidationAgent",
        "ReportAgent"
      ];
      this.status = "idle";
    }

    async run() {
      this.status = "running";
      this.events.emit("orchestrator:started", { flow: [...this.flow] });

      for (const agentName of this.flow) {
        const agent = this.agents[agentName];

        if (!agent) {
          continue;
        }

        console.info(`[MAHIR] ${agentName} başladı`);
        const logEntry = this.logger.start(agentName);
        this.events.emit("agent:started", { agent: agentName });

        try {
          await agent.initialize();
          await agent.execute();
          await agent.validate();
          await agent.export();
          this.logger.finish(logEntry, true);
          this.events.emit("agent:completed", { agent: agentName, log: logEntry });
          console.info(`[MAHIR] ${agentName} bitti`);
        } catch (error) {
          this.logger.finish(logEntry, false);
          this.events.emit("agent:failed", { agent: agentName, error, log: logEntry });
          console.error(`[MAHIR] ${agentName} tamamlanamadı`, error);
          throw error;
        }
      }

      this.status = "completed";
      this.events.emit("orchestrator:completed", { flow: [...this.flow] });
      return { status: this.status, flow: [...this.flow] };
    }

    reset() {
      this.status = "idle";
      return Promise.all(this.flow.map((agentName) => this.agents[agentName]?.reset()));
    }
  }

  const state = createInitialState();
  const session = createSession();
  const events = createEventBus();
  const logger = createLogger(state);
  const agentConfig = { state, logger, events };
  const agents = {
    DocumentAgent: new DocumentAgent(agentConfig),
    StructuringAgent: new StructuringAgent(agentConfig),
    CurriculumAgent: new CurriculumAgent(agentConfig),
    MeasurementAgent: new MeasurementAgent(agentConfig),
    PedagogyAgent: new PedagogyAgent(agentConfig),
    EvidenceAgent: new EvidenceAgent(agentConfig),
    ValidationAgent: new ValidationAgent(agentConfig),
    ReportAgent: new ReportAgent(agentConfig)
  };
  const services = {
    OCRService: new OCRService(),
    LLMService: new LLMService(),
    CurriculumService: new CurriculumService(),
    StatisticsService: new StatisticsService(),
    ReportService: new ReportService()
  };
  const orchestrator = new AIOrchestrator({ agents, logger, events });

  window.MAHIR = {
    version,
    session,
    state,
    agents,
    orchestrator,
    services,
    logger,
    events
  };

  logger.info("MAHIR initialized", { version, sessionId: session.id });
  console.info("MAHIR initialized");
})();

/* =========================================================
   MAHIR AGENT CONTRACTS AND DATA SCHEMAS - FEATURE 24
   ========================================================= */
(() => {
  const MAHIR = window.MAHIR;

  if (!MAHIR) {
    return;
  }

  const contractVersion = "1.0.0";
  const utils = {
    isPlainObject(value) {
      return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    },
    isNonEmptyString(value) {
      return typeof value === "string" && value.trim().length > 0;
    },
    isFiniteNumber(value) {
      return typeof value === "number" && Number.isFinite(value);
    },
    isArray(value) {
      return Array.isArray(value);
    },
    createId(prefix = "mahir") {
      const randomId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      return `${prefix}-${randomId}`;
    },
    nowIso() {
      return new Date().toISOString();
    },
    deepClone(value) {
      if (typeof structuredClone === "function") {
        return structuredClone(value);
      }
      return JSON.parse(JSON.stringify(value));
    },
    getByPath(source, path) {
      if (!path) {
        return source;
      }
      return path.split(".").reduce((current, key) => current == null ? undefined : current[key], source);
    },
    validateRequiredPaths(payload, requiredPaths = []) {
      return requiredPaths.reduce((errors, path) => {
        const value = utils.getByPath(payload, path);
        if (value === undefined || value === null || value === "") {
          errors.push({ fieldPath: path, message: `${path} zorunlu alanı eksik.` });
        }
        return errors;
      }, []);
    },
    summarizePayload(payload) {
      if (Array.isArray(payload)) {
        return { type: "array", length: payload.length };
      }
      if (utils.isPlainObject(payload)) {
        return { type: "object", keys: Object.keys(payload) };
      }
      return { type: typeof payload, value: payload };
    }
  };

  const result = (errors = [], warnings = []) => ({ valid: errors.length === 0, errors, warnings });
  const assertArray = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (value !== undefined && !Array.isArray(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı dizi olmalıdır.` });
    }
  };
  const assertObject = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (value !== undefined && !utils.isPlainObject(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı nesne olmalıdır.` });
    }
  };
  const teacherContextDefault = () => ({
    educationLevel: "Lise",
    schoolType: "Anadolu Lisesi",
    programType: null,
    field: null,
    branch: null,
    grade: "10",
    courseType: "Ortak Ders",
    course: "Türk Dili ve Edebiyatı",
    customSchoolType: null,
    customCourse: null
  });
  const uploadedDocumentDefault = () => ({
    id: utils.createId("document"),
    name: "ornek-sinav-verisi.csv",
    type: "spreadsheet",
    mimeType: "text/csv",
    size: 2048,
    source: "mock",
    uploadedAt: utils.nowIso(),
    checksum: "mock-checksum",
    metadata: {}
  });
  const examQuestionDefault = (order = 1) => ({
    id: `q${order}`,
    order,
    text: `${order}. soru örnek metni`,
    maxScore: 10,
    questionType: "open-ended",
    answerKey: "Örnek cevap anahtarı",
    learningOutcomeIds: [`TDE.${order}`],
    confidence: 0.9
  });
  const studentRecordDefault = (order = 1) => ({
    id: `student-${order}`,
    studentNo: `DEMO-${String(order).padStart(3, "0")}`,
    fullName: order === 1 ? "Örnek Kayıt A" : "Örnek Kayıt B",
    answers: { q1: order === 1 ? 8 : 7, q2: order === 1 ? 7 : 6 },
    totalScore: order === 1 ? 15 : 13,
    metadata: {}
  });
  const evidenceItemDefault = () => ({
    id: "evidence-1",
    claim: "Öğrenciler temel çıkarım becerisinde güçlü görünmektedir.",
    sourceType: "measurement",
    sourceId: "q1",
    metric: "averageScoreRate",
    value: 0.75,
    confidence: 0.85,
    explanation: "Örnek ölçme verisi üzerinden oluşturulan kanıt maddesi."
  });
  const validationIssueDefault = () => ({
    id: utils.createId("validation-issue"),
    severity: "warning",
    code: "MOCK_WARNING",
    message: "Örnek uyarı kaydı.",
    sourceAgent: "ValidationAgent",
    fieldPath: "mock.path",
    suggestion: "Öğretmen kontrolü ile tamamlanabilir."
  });
  const auditEntryDefault = () => ({
    id: utils.createId("audit"),
    timestamp: utils.nowIso(),
    agent: "System",
    action: "initialize",
    status: "completed",
    durationMs: 0,
    inputSummary: {},
    outputSummary: {},
    errors: []
  });

  const dataTypes = {
    TeacherContext: { name: "TeacherContext", version: contractVersion, createDefault: teacherContextDefault },
    UploadedDocument: { name: "UploadedDocument", version: contractVersion, createDefault: uploadedDocumentDefault },
    ExamQuestion: { name: "ExamQuestion", version: contractVersion, createDefault: examQuestionDefault },
    StudentRecord: { name: "StudentRecord", version: contractVersion, createDefault: studentRecordDefault },
    EvidenceItem: { name: "EvidenceItem", version: contractVersion, createDefault: evidenceItemDefault },
    ValidationIssue: { name: "ValidationIssue", version: contractVersion, createDefault: validationIssueDefault },
    AuditEntry: { name: "AuditEntry", version: contractVersion, createDefault: auditEntryDefault }
  };

  const makeDocumentOutput = () => ({
    documents: [uploadedDocumentDefault()],
    extractedText: ["Örnek sınav metni"],
    detectedTables: [],
    detectedQuestions: [examQuestionDefault(1), examQuestionDefault(2)],
    detectedStudents: [studentRecordDefault(1), studentRecordDefault(2)],
    ambiguities: []
  });
  const makeStructuringOutput = () => ({
    exam: { id: "exam-1", title: "Türk Dili ve Edebiyatı Örnek Sınavı", maxScore: 20, metadata: {} },
    questions: [examQuestionDefault(1), examQuestionDefault(2)],
    students: [studentRecordDefault(1), studentRecordDefault(2)],
    scoringModel: { maxScore: 20, method: "sum" },
    ambiguities: []
  });
  const makeCurriculumOutput = () => ({
    curriculumMatches: [
      { questionId: "q1", learningOutcomeId: "TDE.1", confidence: 0.86 },
      { questionId: "q2", learningOutcomeId: "TDE.2", confidence: 0.82 }
    ],
    unmatchedQuestions: [],
    sourceReferences: [{ id: "src-1", title: "Örnek öğretim programı", type: "curriculum" }],
    confidenceSummary: { average: 0.84 }
  });
  const makeMeasurementOutput = () => ({
    classStatistics: { studentCount: 2, averageScore: 14, maxScore: 20 },
    questionStatistics: [{ questionId: "q1", averageScore: 7.5, maxScore: 10 }, { questionId: "q2", averageScore: 6.5, maxScore: 10 }],
    learningOutcomeStatistics: [{ learningOutcomeId: "TDE.1", successRate: 0.75 }],
    distribution: { high: 1, medium: 1, low: 0 },
    anomalies: []
  });
  const makePedagogyOutput = () => ({
    strengths: ["Metin çıkarımı güçlüdür."],
    developmentAreas: ["Kanıt kullanımı geliştirilebilir."],
    misconceptions: [],
    teachingSuggestions: ["Kısa kanıt temelli yazma etkinliği uygulanabilir."],
    monitoringPlan: ["Bir sonraki değerlendirmede aynı öğrenme çıktısı izlenir."]
  });
  const makeEvidenceOutput = () => ({ evidenceItems: [evidenceItemDefault()], unsupportedClaims: [], confidenceSummary: { average: 0.85 } });
  const makeValidationOutput = () => ({ valid: true, issues: [], blockingIssues: [], warnings: [], approvalRequired: true });
  const makeReportOutput = () => ({
    title: "Maarif Modeli Temelli Sınav Analizi ve Değerlendirme Raporu",
    executiveSummary: "Örnek yürütücü özet.",
    generalEvaluation: "Örnek genel değerlendirme.",
    questionAnalysis: [],
    learningOutcomeEvaluation: [],
    strengths: ["Metin çıkarımı güçlüdür."],
    developmentAreas: ["Kanıt kullanımı geliştirilebilir."],
    teachingSuggestions: ["Kısa kanıt temelli yazma etkinliği uygulanabilir."],
    monitoringPlan: ["Bir sonraki değerlendirmede aynı öğrenme çıktısı izlenir."],
    sourceReferences: [{ id: "src-1", title: "Örnek öğretim programı" }],
    teacherReviewStatus: "pending"
  });
  const createContract = ({ name, description, required, optional = [], defaultFactory, customValidate }) => ({
    name,
    version: contractVersion,
    description,
    required,
    optional,
    validate(payload) {
      const errors = [];
      const warnings = [];
      if (!utils.isPlainObject(payload)) {
        errors.push({ fieldPath: "payload", message: `${name} plain object bekler.` });
        return result(errors, warnings);
      }
      errors.push(...utils.validateRequiredPaths(payload, required));
      if (typeof customValidate === "function") {
        const customResult = customValidate(payload);
        errors.push(...(customResult?.errors || []));
        warnings.push(...(customResult?.warnings || []));
      }
      return result(errors, warnings);
    },
    createDefault() {
      return utils.deepClone(defaultFactory());
    }
  });

  const contracts = {
    DocumentInput: createContract({
      name: "DocumentInput", description: "DocumentAgent için öğretmen bağlamı ve yüklenen dosya girdisi.",
      required: ["teacherContext", "uploadedFiles"], defaultFactory: () => ({ teacherContext: teacherContextDefault(), uploadedFiles: [uploadedDocumentDefault()] }),
      customValidate(payload) { const errors = []; assertObject(payload, "teacherContext", errors); assertArray(payload, "uploadedFiles", errors); return { errors, warnings: [] }; }
    }),
    DocumentOutput: createContract({
      name: "DocumentOutput", description: "DocumentAgent tarafından çıkarılan ham belge ve algılama çıktısı.",
      required: ["documents", "extractedText", "detectedTables", "detectedQuestions", "detectedStudents", "ambiguities"], defaultFactory: makeDocumentOutput,
      customValidate(payload) { const errors = []; ["documents", "extractedText", "detectedTables", "detectedQuestions", "detectedStudents", "ambiguities"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    StructuringInput: createContract({
      name: "StructuringInput", description: "StructuringAgent için DocumentOutput girdisi.",
      required: ["documents", "extractedText", "detectedQuestions", "detectedStudents"], optional: ["detectedTables", "ambiguities"], defaultFactory: makeDocumentOutput,
      customValidate(payload) { const errors = []; ["documents", "extractedText", "detectedQuestions", "detectedStudents"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    StructuringOutput: createContract({
      name: "StructuringOutput", description: "Yapılandırılmış sınav, soru, öğrenci ve puanlama modeli.",
      required: ["exam", "questions", "students", "scoringModel", "ambiguities"], defaultFactory: makeStructuringOutput,
      customValidate(payload) { const errors = []; assertObject(payload, "exam", errors); assertObject(payload, "scoringModel", errors); ["questions", "students", "ambiguities"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    CurriculumInput: createContract({
      name: "CurriculumInput", description: "CurriculumAgent için öğretmen bağlamı ve soru listesi.",
      required: ["teacherContext", "questions"], defaultFactory: () => ({ teacherContext: teacherContextDefault(), questions: [examQuestionDefault(1), examQuestionDefault(2)] }),
      customValidate(payload) { const errors = []; assertObject(payload, "teacherContext", errors); assertArray(payload, "questions", errors); return { errors, warnings: [] }; }
    }),
    CurriculumOutput: createContract({
      name: "CurriculumOutput", description: "Öğrenme çıktısı eşleştirme ve kaynak referansları.",
      required: ["curriculumMatches", "unmatchedQuestions", "sourceReferences", "confidenceSummary"], defaultFactory: makeCurriculumOutput,
      customValidate(payload) { const errors = []; ["curriculumMatches", "unmatchedQuestions", "sourceReferences"].forEach((path) => assertArray(payload, path, errors)); assertObject(payload, "confidenceSummary", errors); return { errors, warnings: [] }; }
    }),
    MeasurementInput: createContract({
      name: "MeasurementInput", description: "MeasurementAgent için soru, öğrenci, puanlama ve müfredat eşleşmeleri.",
      required: ["questions", "students", "scoringModel", "curriculumMatches"], defaultFactory: () => ({ questions: [examQuestionDefault(1), examQuestionDefault(2)], students: [studentRecordDefault(1), studentRecordDefault(2)], scoringModel: { maxScore: 20, method: "sum" }, curriculumMatches: makeCurriculumOutput().curriculumMatches }),
      customValidate(payload) { const errors = []; ["questions", "students", "curriculumMatches"].forEach((path) => assertArray(payload, path, errors)); assertObject(payload, "scoringModel", errors); return { errors, warnings: [] }; }
    }),
    MeasurementOutput: createContract({
      name: "MeasurementOutput", description: "Sınıf, soru ve öğrenme çıktısı istatistikleri ile dağılımlar.",
      required: ["classStatistics", "questionStatistics", "learningOutcomeStatistics", "distribution", "anomalies"], defaultFactory: makeMeasurementOutput,
      customValidate(payload) { const errors = []; assertObject(payload, "classStatistics", errors); assertObject(payload, "distribution", errors); ["questionStatistics", "learningOutcomeStatistics", "anomalies"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    PedagogyInput: createContract({
      name: "PedagogyInput", description: "PedagogyAgent için öğretmen bağlamı, ölçme ve müfredat çıktısı.",
      required: ["teacherContext", "measurementOutput", "curriculumOutput"], defaultFactory: () => ({ teacherContext: teacherContextDefault(), measurementOutput: makeMeasurementOutput(), curriculumOutput: makeCurriculumOutput() }),
      customValidate(payload) { const errors = []; ["teacherContext", "measurementOutput", "curriculumOutput"].forEach((path) => assertObject(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    PedagogyOutput: createContract({
      name: "PedagogyOutput", description: "Güçlü alanlar, gelişim alanları ve öğretim önerileri.",
      required: ["strengths", "developmentAreas", "misconceptions", "teachingSuggestions", "monitoringPlan"], defaultFactory: makePedagogyOutput,
      customValidate(payload) { const errors = []; ["strengths", "developmentAreas", "misconceptions", "teachingSuggestions", "monitoringPlan"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    EvidenceInput: createContract({
      name: "EvidenceInput", description: "EvidenceAgent için ölçme, pedagoji ve müfredat çıktıları.",
      required: ["measurementOutput", "pedagogyOutput", "curriculumOutput"], defaultFactory: () => ({ measurementOutput: makeMeasurementOutput(), pedagogyOutput: makePedagogyOutput(), curriculumOutput: makeCurriculumOutput() }),
      customValidate(payload) { const errors = []; ["measurementOutput", "pedagogyOutput", "curriculumOutput"].forEach((path) => assertObject(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    EvidenceOutput: createContract({
      name: "EvidenceOutput", description: "Kanıt maddeleri, desteklenmeyen iddialar ve güven özeti.",
      required: ["evidenceItems", "unsupportedClaims", "confidenceSummary"], defaultFactory: makeEvidenceOutput,
      customValidate(payload) { const errors = []; ["evidenceItems", "unsupportedClaims"].forEach((path) => assertArray(payload, path, errors)); assertObject(payload, "confidenceSummary", errors); return { errors, warnings: [] }; }
    }),
    ValidationInput: createContract({
      name: "ValidationInput", description: "ValidationAgent için önceki tüm ajan çıktıları.",
      required: ["documentOutput", "structuringOutput", "curriculumOutput", "measurementOutput", "pedagogyOutput", "evidenceOutput"], defaultFactory: () => ({ documentOutput: makeDocumentOutput(), structuringOutput: makeStructuringOutput(), curriculumOutput: makeCurriculumOutput(), measurementOutput: makeMeasurementOutput(), pedagogyOutput: makePedagogyOutput(), evidenceOutput: makeEvidenceOutput() }),
      customValidate(payload) { const errors = []; ["documentOutput", "structuringOutput", "curriculumOutput", "measurementOutput", "pedagogyOutput", "evidenceOutput"].forEach((path) => assertObject(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    ValidationOutput: createContract({
      name: "ValidationOutput", description: "Bloklayıcı konular, uyarılar ve öğretmen onayı gereksinimi.",
      required: ["valid", "issues", "blockingIssues", "warnings", "approvalRequired"], defaultFactory: makeValidationOutput,
      customValidate(payload) { const errors = []; ["issues", "blockingIssues", "warnings"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    ReportInput: createContract({
      name: "ReportInput", description: "ReportAgent için rapor üretim bağlamı ve doğrulanmış ajan çıktıları.",
      required: ["teacherContext", "structuredData", "curriculumOutput", "measurementOutput", "pedagogyOutput", "evidenceOutput", "validationOutput"], defaultFactory: () => ({ teacherContext: teacherContextDefault(), structuredData: makeStructuringOutput(), curriculumOutput: makeCurriculumOutput(), measurementOutput: makeMeasurementOutput(), pedagogyOutput: makePedagogyOutput(), evidenceOutput: makeEvidenceOutput(), validationOutput: makeValidationOutput() }),
      customValidate(payload) { const errors = []; ["teacherContext", "structuredData", "curriculumOutput", "measurementOutput", "pedagogyOutput", "evidenceOutput", "validationOutput"].forEach((path) => assertObject(payload, path, errors)); return { errors, warnings: [] }; }
    }),
    ReportOutput: createContract({
      name: "ReportOutput", description: "Öğretmen incelemesine hazır rapor taslağı bölümleri.",
      required: ["title", "executiveSummary", "generalEvaluation", "questionAnalysis", "learningOutcomeEvaluation", "strengths", "developmentAreas", "teachingSuggestions", "monitoringPlan", "sourceReferences", "teacherReviewStatus"], defaultFactory: makeReportOutput,
      customValidate(payload) { const errors = []; ["questionAnalysis", "learningOutcomeEvaluation", "strengths", "developmentAreas", "teachingSuggestions", "monitoringPlan", "sourceReferences"].forEach((path) => assertArray(payload, path, errors)); return { errors, warnings: [] }; }
    })
  };

  const createSchemaRegistry = () => {
    const registry = new Map();
    return {
      register(name, contract) { registry.set(name, contract); return contract; },
      get(name) { return registry.get(name); },
      has(name) { return registry.has(name); },
      list() { return Array.from(registry.keys()); },
      validate(name, payload) {
        const contract = registry.get(name);
        return contract ? contract.validate(payload) : result([{ fieldPath: name, message: `${name} sözleşmesi bulunamadı.` }], []);
      }
    };
  };
  const createAgentOutputs = () => ({
    document: null,
    structuring: null,
    curriculum: null,
    measurement: null,
    pedagogy: null,
    evidence: null,
    validation: null,
    report: null
  });
  const agentContracts = {
    DocumentAgent: { input: "DocumentInput", output: "DocumentOutput", stateKey: "document" },
    StructuringAgent: { input: "StructuringInput", output: "StructuringOutput", stateKey: "structuring" },
    CurriculumAgent: { input: "CurriculumInput", output: "CurriculumOutput", stateKey: "curriculum" },
    MeasurementAgent: { input: "MeasurementInput", output: "MeasurementOutput", stateKey: "measurement" },
    PedagogyAgent: { input: "PedagogyInput", output: "PedagogyOutput", stateKey: "pedagogy" },
    EvidenceAgent: { input: "EvidenceInput", output: "EvidenceOutput", stateKey: "evidence" },
    ValidationAgent: { input: "ValidationInput", output: "ValidationOutput", stateKey: "validation" },
    ReportAgent: { input: "ReportInput", output: "ReportOutput", stateKey: "report" }
  };

  const schemaRegistry = createSchemaRegistry();
  Object.values(contracts).forEach((contract) => schemaRegistry.register(contract.name, contract));

  MAHIR.version = "0.24.0";
  MAHIR.utils = utils;
  MAHIR.contracts = contracts;
  MAHIR.dataTypes = dataTypes;
  MAHIR.schemaRegistry = schemaRegistry;
  MAHIR.state.contracts = contracts;
  MAHIR.state.pipeline = MAHIR.state.pipeline || {};
  MAHIR.state.pipeline.flow = Object.keys(agentContracts);
  MAHIR.state.agentOutputs = MAHIR.state.agentOutputs || createAgentOutputs();
  MAHIR.state.validationIssues = MAHIR.state.validationIssues || [];
  MAHIR.state.auditLog = MAHIR.state.auditLog || [];

  if (typeof MAHIR.logger.error !== "function") {
    MAHIR.logger.error = (message, details = {}) => {
      const entry = { id: utils.createId("mahir-log"), message, details, createdAt: utils.nowIso(), status: "error", success: false };
      MAHIR.state.logs.push(entry);
      return entry;
    };
  }

  Object.entries(agentContracts).forEach(([agentName, config]) => {
    const agent = MAHIR.agents[agentName];
    if (!agent) {
      return;
    }
    agent.contract = config;
    agent.execute = () => {
      agent.status = "executed";
      return Promise.resolve(contracts[config.output].createDefault());
    };
  });

  const composeInput = (agentName, initialInput) => {
    const outputs = MAHIR.state.agentOutputs;
    const factories = {
      DocumentAgent: () => initialInput,
      StructuringAgent: () => outputs.document,
      CurriculumAgent: () => ({ teacherContext: initialInput.teacherContext, questions: outputs.structuring?.questions || [] }),
      MeasurementAgent: () => ({ questions: outputs.structuring?.questions || [], students: outputs.structuring?.students || [], scoringModel: outputs.structuring?.scoringModel || {}, curriculumMatches: outputs.curriculum?.curriculumMatches || [] }),
      PedagogyAgent: () => ({ teacherContext: initialInput.teacherContext, measurementOutput: outputs.measurement, curriculumOutput: outputs.curriculum }),
      EvidenceAgent: () => ({ measurementOutput: outputs.measurement, pedagogyOutput: outputs.pedagogy, curriculumOutput: outputs.curriculum }),
      ValidationAgent: () => ({ documentOutput: outputs.document, structuringOutput: outputs.structuring, curriculumOutput: outputs.curriculum, measurementOutput: outputs.measurement, pedagogyOutput: outputs.pedagogy, evidenceOutput: outputs.evidence }),
      ReportAgent: () => ({ teacherContext: initialInput.teacherContext, structuredData: outputs.structuring, curriculumOutput: outputs.curriculum, measurementOutput: outputs.measurement, pedagogyOutput: outputs.pedagogy, evidenceOutput: outputs.evidence, validationOutput: outputs.validation })
    };
    return factories[agentName]();
  };

  const createIssue = (agentName, validationResult, phase) => ({
    id: utils.createId("validation-issue"),
    severity: "blocking",
    code: `CONTRACT_${phase.toUpperCase()}_INVALID`,
    message: `${agentName} ${phase} sözleşme doğrulaması başarısız oldu.`,
    sourceAgent: agentName,
    fieldPath: validationResult.errors[0]?.fieldPath || "payload",
    suggestion: "Sözleşme zorunlu alanları tamamlanmalıdır.",
    errors: validationResult.errors,
    warnings: validationResult.warnings
  });
  const writeAudit = ({ agentName, status, durationMs, input, output, errors = [] }) => {
    MAHIR.state.auditLog.push({
      id: utils.createId("audit"),
      timestamp: utils.nowIso(),
      agent: agentName,
      action: "execute",
      status,
      durationMs,
      inputSummary: utils.summarizePayload(input),
      outputSummary: utils.summarizePayload(output),
      errors
    });
  };
  const stopWithIssue = (agentName, validationResult, phase) => {
    const issue = createIssue(agentName, validationResult, phase);
    MAHIR.state.validationIssues.push(issue);
    MAHIR.state.pipeline.status = "failed";
    MAHIR.state.pipeline.currentAgent = agentName;
    MAHIR.state.pipeline.completedAt = utils.nowIso();
    MAHIR.orchestrator.status = "failed";
    MAHIR.logger.error(issue.message, { issue });
    MAHIR.events.emit("mahir:pipeline:error", { agent: agentName, phase, issue });
    return { status: "failed", agent: agentName, phase, issue };
  };

  MAHIR.orchestrator.createMockInput = () => contracts.DocumentInput.createDefault();
  MAHIR.orchestrator.run = async (initialInput = MAHIR.orchestrator.createMockInput()) => {
    MAHIR.state.agentOutputs = createAgentOutputs();
    MAHIR.state.validationIssues = [];
    MAHIR.state.auditLog = [];
    MAHIR.state.pipeline = { status: "running", currentAgent: null, flow: [...MAHIR.orchestrator.flow], startedAt: utils.nowIso(), completedAt: null };
    MAHIR.orchestrator.status = "running";
    MAHIR.events.emit("orchestrator:started", { flow: [...MAHIR.orchestrator.flow] });

    for (const agentName of MAHIR.orchestrator.flow) {
      const agent = MAHIR.agents[agentName];
      const config = agentContracts[agentName];
      const input = composeInput(agentName, initialInput);
      MAHIR.state.pipeline.currentAgent = agentName;
      const inputValidation = schemaRegistry.validate(config.input, input);
      if (!inputValidation.valid) {
        writeAudit({ agentName, status: "failed", durationMs: 0, input, output: null, errors: inputValidation.errors });
        return stopWithIssue(agentName, inputValidation, "input");
      }

      console.info(`[MAHIR] ${agentName} başladı`);
      const logEntry = MAHIR.logger.start(agentName);
      MAHIR.events.emit("agent:started", { agent: agentName });
      try {
        await agent.initialize(input);
        const output = await agent.execute(input);
        await agent.validate(output);
        await agent.export(output);
        const outputValidation = schemaRegistry.validate(config.output, output);
        if (!outputValidation.valid) {
          MAHIR.logger.finish(logEntry, false);
          writeAudit({ agentName, status: "failed", durationMs: logEntry.durationMs || 0, input, output, errors: outputValidation.errors });
          return stopWithIssue(agentName, outputValidation, "output");
        }
        MAHIR.state.agentOutputs[config.stateKey] = output;
        MAHIR.logger.finish(logEntry, true);
        writeAudit({ agentName, status: "completed", durationMs: logEntry.durationMs || 0, input, output });
        MAHIR.events.emit("agent:completed", { agent: agentName, log: logEntry });
        MAHIR.events.emit("mahir:agent:completed", { agent: agentName, output });
        console.info(`[MAHIR] ${agentName} bitti`);
      } catch (error) {
        MAHIR.logger.finish(logEntry, false);
        const runtimeResult = result([{ fieldPath: agentName, message: error.message }], []);
        writeAudit({ agentName, status: "failed", durationMs: logEntry.durationMs || 0, input, output: null, errors: runtimeResult.errors });
        return stopWithIssue(agentName, runtimeResult, "runtime");
      }
    }

    MAHIR.orchestrator.status = "completed";
    MAHIR.state.pipeline.status = "completed";
    MAHIR.state.pipeline.currentAgent = null;
    MAHIR.state.pipeline.completedAt = utils.nowIso();
    const completed = { status: "completed", flow: [...MAHIR.orchestrator.flow] };
    MAHIR.events.emit("orchestrator:completed", completed);
    return completed;
  };
  MAHIR.orchestrator.reset = () => {
    MAHIR.orchestrator.status = "idle";
    MAHIR.state.agentOutputs = createAgentOutputs();
    MAHIR.state.validationIssues = [];
    MAHIR.state.auditLog = [];
    return Promise.all(MAHIR.orchestrator.flow.map((agentName) => MAHIR.agents[agentName]?.reset()));
  };

  MAHIR.logger.info("MAHIR contracts initialized", { contractCount: schemaRegistry.list().length });
  console.info("MAHIR contracts initialized");
})();
/* =========================================================
   DOCUMENT AGENT CORE - FEATURE 25
   ========================================================= */
(() => {
  const MAHIR = window.MAHIR;

  if (!MAHIR) {
    return;
  }

  const documentTypes = [
    "exam_pdf",
    "exam_image",
    "answer_key",
    "excel_scores",
    "word_exam",
    "csv_scores",
    "unknown"
  ];

  const utils = MAHIR.utils;
  const createValidationResult = (errors = [], warnings = []) => ({ valid: errors.length === 0, errors, warnings });
  const getPrimaryFile = (input = {}) => input.uploadedFiles?.[0] || {};
  const now = () => utils.nowIso();

  const createDocumentWarning = ({ code, message, severity = "info", page = null }) => ({
    code,
    message,
    severity,
    page
  });

  const createQuestion = (number) => ({
    id: `q${number}`,
    number,
    text: `${number}. örnek soru metni`,
    maxScore: 10,
    page: 1,
    bbox: { x: 80, y: 120 + number * 90, width: 720, height: 72 },
    confidence: 0.92,
    status: "mock"
  });

  const createAnswerKey = (questionId, correctAnswer) => ({
    questionId,
    correctAnswer,
    confidence: 0.9
  });

  const createStudent = (studentNo, fullName, answers, totalScore) => ({
    studentNo,
    fullName,
    answers,
    totalScore,
    confidence: 0.88
  });

  const createTable = () => ({
    id: "table-1",
    page: 1,
    rows: 3,
    columns: 4,
    cells: [
      ["Öğrenci No", "Ad Soyad", "Soru 1", "Toplam"],
      ["DEMO-001", "Örnek Kayıt A", "8", "15"],
      ["DEMO-002", "Örnek Kayıt B", "7", "13"]
    ]
  });

  const createImage = () => ({
    id: "image-1",
    page: 1,
    purpose: "exam-header",
    width: 1024,
    height: 240
  });

  const createDocumentOutputDefault = () => ({
    documentId: utils.createId("document"),
    documentType: "unknown",
    metadata: {
      title: "Örnek Sınav Belgesi",
      pageCount: 1,
      language: "tr",
      source: "mock",
      createdAt: now(),
      checksum: "mock-checksum"
    },
    questions: [createQuestion(1), createQuestion(2)],
    answerKey: [createAnswerKey("q1", "A"), createAnswerKey("q2", "B")],
    students: [
      createStudent("DEMO-001", "Örnek Kayıt A", { q1: "A", q2: "B" }, 15),
      createStudent("DEMO-002", "Örnek Kayıt B", { q1: "A", q2: "C" }, 13)
    ],
    tables: [createTable()],
    images: [createImage()],
    warnings: [createDocumentWarning({ code: "MOCK_PROVIDER", message: "Bu çıktı mock provider tarafından üretilmiştir." })],
    confidence: 0.89,
    processingTime: 0
  });

  const validateArray = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (!Array.isArray(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı dizi olmalıdır.` });
    }
  };

  const validateObject = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (!utils.isPlainObject(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı nesne olmalıdır.` });
    }
  };

  const validateNumber = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (!utils.isFiniteNumber(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı sayı olmalıdır.` });
    }
  };

  const createContract = ({ name, description, required, optional = [], createDefault, validate }) => ({
    name,
    version: "1.0.0",
    description,
    required,
    optional,
    validate(payload) {
      const errors = [];
      const warnings = [];

      if (!utils.isPlainObject(payload)) {
        errors.push({ fieldPath: "payload", message: `${name} plain object bekler.` });
        return createValidationResult(errors, warnings);
      }

      errors.push(...utils.validateRequiredPaths(payload, required));

      if (typeof validate === "function") {
        const customResult = validate(payload);
        errors.push(...(customResult.errors || []));
        warnings.push(...(customResult.warnings || []));
      }

      return createValidationResult(errors, warnings);
    },
    createDefault() {
      return utils.deepClone(createDefault());
    }
  });
  const documentOutputContract = createContract({
    name: "DocumentOutput",
    description: "DocumentAgent tarafından sınıflandırılmış ve standartlaştırılmış belge çıktısı.",
    required: [
      "documentId",
      "documentType",
      "metadata",
      "metadata.title",
      "metadata.pageCount",
      "metadata.language",
      "metadata.source",
      "metadata.createdAt",
      "metadata.checksum",
      "questions",
      "answerKey",
      "students",
      "tables",
      "images",
      "warnings",
      "confidence",
      "processingTime"
    ],
    optional: [],
    createDefault: createDocumentOutputDefault,
    validate(payload) {
      const errors = [];
      const warnings = [];
      validateObject(payload, "metadata", errors);
      ["questions", "answerKey", "students", "tables", "images", "warnings"].forEach((path) => validateArray(payload, path, errors));
      validateNumber(payload, "confidence", errors);
      validateNumber(payload, "processingTime", errors);

      if (!documentTypes.includes(payload.documentType)) {
        errors.push({ fieldPath: "documentType", message: "documentType tanımlı belge türlerinden biri olmalıdır." });
      }

      if (payload.questions?.some((question) => !utils.isNonEmptyString(question.id) || !utils.isFiniteNumber(question.number))) {
        errors.push({ fieldPath: "questions", message: "Her soru id ve number alanı taşımalıdır." });
      }

      if (payload.answerKey?.some((answer) => !utils.isNonEmptyString(answer.questionId))) {
        errors.push({ fieldPath: "answerKey", message: "Her cevap anahtarı maddesi questionId taşımalıdır." });
      }

      if (payload.confidence < 0.5) {
        warnings.push({ fieldPath: "confidence", message: "Belge güven değeri düşük görünüyor." });
      }

      return { errors, warnings };
    }
  });

  const structuringInputContract = createContract({
    name: "StructuringInput",
    description: "StructuringAgent için Feature 25 DocumentOutput girdisi.",
    required: ["documentId", "documentType", "metadata", "questions", "students", "tables"],
    optional: ["answerKey", "images", "warnings", "confidence", "processingTime"],
    createDefault: createDocumentOutputDefault,
    validate(payload) {
      const errors = [];
      validateObject(payload, "metadata", errors);
      ["questions", "students", "tables"].forEach((path) => validateArray(payload, path, errors));
      return { errors, warnings: [] };
    }
  });

  MAHIR.contracts.DocumentOutput = documentOutputContract;
  MAHIR.contracts.StructuringInput = structuringInputContract;
  MAHIR.state.contracts = MAHIR.contracts;
  MAHIR.schemaRegistry.register("DocumentOutput", documentOutputContract);
  MAHIR.schemaRegistry.register("StructuringInput", structuringInputContract);
  const createMockProvider = () => ({
    name: "mock",
    detectDocumentType(file = {}) {
      const name = String(file.name || "").toLowerCase();
      const mimeType = String(file.mimeType || file.type || "").toLowerCase();

      if (name.includes("answer") || name.includes("cevap")) {
        return "answer_key";
      }
      if (mimeType.includes("pdf") || name.endsWith(".pdf")) {
        return "exam_pdf";
      }
      if (mimeType.includes("image") || /\.(png|jpg|jpeg|webp)$/.test(name)) {
        return "exam_image";
      }
      if (/\.(xlsx|xls)$/.test(name)) {
        return "excel_scores";
      }
      if (/\.(docx|doc)$/.test(name)) {
        return "word_exam";
      }
      if (mimeType.includes("csv") || name.endsWith(".csv")) {
        return "csv_scores";
      }
      return "unknown";
    },
    extractMetadata(input, documentType) {
      const file = getPrimaryFile(input);
      return {
        title: file.name || "Örnek Sınav Belgesi",
        pageCount: documentType === "excel_scores" || documentType === "csv_scores" ? 1 : 2,
        language: "tr",
        source: "mock",
        createdAt: file.uploadedAt || now(),
        checksum: file.checksum || "mock-checksum"
      };
    },
    extractQuestions() {
      return [createQuestion(1), createQuestion(2)];
    },
    extractAnswerKey() {
      return [createAnswerKey("q1", "A"), createAnswerKey("q2", "B")];
    },
    extractStudents() {
      return [
        createStudent("DEMO-001", "Örnek Kayıt A", { q1: "A", q2: "B" }, 15),
        createStudent("DEMO-002", "Örnek Kayıt B", { q1: "A", q2: "C" }, 13)
      ];
    },
    extractTables() {
      return [createTable()];
    },
    extractImages() {
      return [createImage()];
    }
  });

  class DocumentService {
    constructor() {
      this.activeProvider = "mock";
      this.providers = {
        openaiVision: { name: "openaiVision", available: false },
        azureDocument: { name: "azureDocument", available: false },
        googleDocumentAI: { name: "googleDocumentAI", available: false },
        tesseract: { name: "tesseract", available: false },
        paddleOCR: { name: "paddleOCR", available: false },
        mistralOCR: { name: "mistralOCR", available: false },
        mock: createMockProvider()
      };
    }

    get provider() {
      return this.providers[this.activeProvider];
    }

    initialize(input = {}) {
      return Promise.resolve({ provider: this.activeProvider, inputSummary: utils.summarizePayload(input) });
    }

    detectDocumentType(input = {}) {
      return Promise.resolve(this.provider.detectDocumentType(getPrimaryFile(input)));
    }

    extract(input = {}) {
      return Promise.resolve({ rawText: "Mock OCR çıktısı", inputSummary: utils.summarizePayload(input) });
    }

    extractMetadata(input = {}, context = {}) {
      return Promise.resolve(this.provider.extractMetadata(input, context.documentType));
    }

    extractQuestions() {
      return Promise.resolve(this.provider.extractQuestions());
    }

    extractStudents() {
      return Promise.resolve(this.provider.extractStudents());
    }

    extractTables() {
      return Promise.resolve(this.provider.extractTables());
    }

    extractAnswerKey() {
      return Promise.resolve(this.provider.extractAnswerKey());
    }

    extractImages() {
      return Promise.resolve(this.provider.extractImages());
    }

    finalize(input = {}, context = {}) {
      const startedAt = context.startedAt || performance.now();
      const documentType = context.documentType || "unknown";
      const metadata = context.metadata || this.provider.extractMetadata(input, documentType);
      const output = {
        documentId: utils.createId("document"),
        documentType,
        metadata,
        questions: context.questions || [],
        answerKey: context.answerKey || [],
        students: context.students || [],
        tables: context.tables || [],
        images: context.images || [],
        warnings: context.warnings?.length ? context.warnings : [createDocumentWarning({ code: "MOCK_PROVIDER", message: "Bu çıktı mock provider tarafından üretilmiştir." })],
        confidence: 0.89,
        processingTime: Math.max(0, Math.round(performance.now() - startedAt))
      };
      return Promise.resolve(output);
    }
  }

  const documentService = new DocumentService();
  MAHIR.services.document = documentService;
  const runDocumentStep = async (label, methodName, input, context) => {
    console.info(`[MAHIR] ${label} başladı`);
    const stepLog = MAHIR.logger.start(`DocumentAgent.${methodName}`);

    try {
      const value = await documentService[methodName](input, context);
      MAHIR.logger.finish(stepLog, true);
      console.info(`[MAHIR] ${label} bitti`);
      return value;
    } catch (error) {
      MAHIR.logger.finish(stepLog, false);
      MAHIR.logger.error(`${label} tamamlanamadı`, { error: error.message });
      throw error;
    }
  };

  MAHIR.agents.DocumentAgent.execute = async (input = MAHIR.contracts.DocumentInput.createDefault()) => {
    const startedAt = performance.now();
    const context = { startedAt, warnings: [] };
    MAHIR.events.emit("mahir:document:started", { inputSummary: utils.summarizePayload(input) });

    try {
      await runDocumentStep("Document Service Initialize", "initialize", input, context);
      context.documentType = await runDocumentStep("Document Type Detection", "detectDocumentType", input, context);
      context.metadata = await runDocumentStep("Metadata Extraction", "extractMetadata", input, context);
      context.questions = await runDocumentStep("Question Extraction", "extractQuestions", input, context);
      context.answerKey = await runDocumentStep("Answer Key Extraction", "extractAnswerKey", input, context);
      context.students = await runDocumentStep("Student Extraction", "extractStudents", input, context);
      context.tables = await runDocumentStep("Table Extraction", "extractTables", input, context);
      context.images = await runDocumentStep("Image Extraction", "extractImages", input, context);
      const output = await runDocumentStep("Document Finalize", "finalize", input, context);
      const validationResult = MAHIR.schemaRegistry.validate("DocumentOutput", output);

      if (!validationResult.valid) {
        const issue = {
          id: utils.createId("validation-issue"),
          severity: "blocking",
          code: "DOCUMENT_OUTPUT_INVALID",
          message: "DocumentOutput sözleşme doğrulaması başarısız oldu.",
          sourceAgent: "DocumentAgent",
          fieldPath: validationResult.errors[0]?.fieldPath || "DocumentOutput",
          suggestion: "DocumentService çıktısı DocumentOutput sözleşmesine uygun hale getirilmelidir.",
          errors: validationResult.errors,
          warnings: validationResult.warnings
        };
        MAHIR.state.validationIssues.push(issue);
        MAHIR.events.emit("mahir:document:error", { issue });
        throw new Error(issue.message);
      }

      MAHIR.state.agentOutputs.document = output;
      MAHIR.events.emit("mahir:document:completed", { output });
      console.info("Document Agent Completed");
      return output;
    } catch (error) {
      MAHIR.events.emit("mahir:document:error", { error });
      throw error;
    }
  };

  MAHIR.document = {
    agent: MAHIR.agents.DocumentAgent,
    service: documentService,
    documentTypes,
    models: {
      question: createQuestion,
      answerKey: createAnswerKey,
      student: createStudent,
      table: createTable,
      image: createImage,
      warning: createDocumentWarning
    },
    run(input) {
      return MAHIR.agents.DocumentAgent.execute(input);
    }
  };

  MAHIR.logger.info("MAHIR Document Agent Core initialized", { activeProvider: documentService.activeProvider });
  console.info("MAHIR Document Agent Core initialized");
})();
/* =========================================================
   STRUCTURING AGENT CORE - FEATURE 26
   ========================================================= */
(() => {
  const MAHIR = window.MAHIR;

  if (!MAHIR) {
    return;
  }

  const utils = MAHIR.utils;
  const createValidationResult = (errors = [], warnings = []) => ({ valid: errors.length === 0, errors, warnings });

  const normalizeValue = (value) => {
    if (value === undefined || value === "") {
      return null;
    }
    if (Array.isArray(value)) {
      return value.map(normalizeValue);
    }
    if (utils.isPlainObject(value)) {
      return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [key, normalizeValue(entryValue)]));
    }
    return value;
  };

  const toNumber = (value, fallback = 0) => {
    if (utils.isFiniteNumber(value)) {
      return value;
    }
    const parsed = Number(String(value ?? "").replace(",", "."));
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const toStringValue = (value) => value === undefined || value === null ? "" : String(value);

  const createStructuringIssue = ({ code, message, severity = "warning", source = "StructuringAgent" }) => ({
    id: utils.createId("missing-info"),
    code,
    message,
    severity,
    source
  });

  const validateArray = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (!Array.isArray(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı dizi olmalıdır.` });
    }
  };

  const validateObject = (payload, path, errors) => {
    const value = utils.getByPath(payload, path);
    if (!utils.isPlainObject(value)) {
      errors.push({ fieldPath: path, message: `${path} alanı nesne olmalıdır.` });
    }
  };

  const createContract = ({ name, description, required, optional = [], createDefault, validate }) => ({
    name,
    version: "1.0.0",
    description,
    required,
    optional,
    validate(payload) {
      const errors = [];
      const warnings = [];

      if (!utils.isPlainObject(payload)) {
        errors.push({ fieldPath: "payload", message: `${name} plain object bekler.` });
        return createValidationResult(errors, warnings);
      }

      errors.push(...utils.validateRequiredPaths(payload, required));

      if (typeof validate === "function") {
        const customResult = validate(payload);
        errors.push(...(customResult.errors || []));
        warnings.push(...(customResult.warnings || []));
      }

      return createValidationResult(errors, warnings);
    },
    createDefault() {
      return utils.deepClone(createDefault());
    }
  });
  const createMockDocumentOutput = () => {
    const questionScores = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 10, 10];
    const questions = questionScores.map((score, index) => ({
      id: `q${index + 1}`,
      number: index + 1,
      text: `${index + 1}. örnek yapılandırma sorusu`,
      maxScore: score,
      page: index < 9 ? 1 : 2,
      bbox: { x: 80, y: 90 + (index % 9) * 72, width: 720, height: 58 },
      confidence: 0.9,
      status: "mock"
    }));
    const answerKey = questions.map((question, index) => ({ questionId: question.id, correctAnswer: index % 2 === 0 ? "A" : "B", confidence: 0.9 }));
    const students = [
      {
        studentNo: "DEMO-001",
        fullName: "Örnek Kayıt A",
        answers: Object.fromEntries(questions.map((question, index) => [question.id, index % 2 === 0 ? "A" : "B"])),
        totalScore: 88,
        confidence: 0.9
      },
      {
        studentNo: "DEMO-002",
        fullName: "Örnek Kayıt B",
        answers: Object.fromEntries(questions.map((question, index) => [question.id, index % 3 === 0 ? "A" : "C"])),
        totalScore: 72,
        confidence: 0.87
      }
    ];

    return {
      documentId: "document-structuring-mock",
      documentType: "exam_pdf",
      metadata: {
        title: "Türk Dili ve Edebiyatı 10. Sınıf Yazılı Sınavı",
        pageCount: 2,
        language: "tr",
        source: "mock",
        createdAt: utils.nowIso(),
        checksum: "structuring-mock-checksum",
        course: "Türk Dili ve Edebiyatı",
        educationLevel: "Lise",
        schoolType: "Anadolu Lisesi",
        grade: "10",
        examType: "Yazılı Sınav",
        examDate: null,
        teacher: null
      },
      questions,
      answerKey,
      students,
      tables: [{ id: "table-structuring-1", page: 1, rows: 3, columns: 4, cells: [] }],
      images: [],
      warnings: [],
      confidence: 0.9,
      processingTime: 12
    };
  };

  const buildQuestion = (question, answerKeyItem) => ({
    id: toStringValue(question.id || `q${question.number}`),
    number: toNumber(question.number, 0),
    text: normalizeValue(question.text),
    maxScore: toNumber(question.maxScore, 0),
    learningOutcomeIds: Array.isArray(question.learningOutcomeIds) ? question.learningOutcomeIds : [],
    answerKey: answerKeyItem?.correctAnswer ?? null,
    page: toNumber(question.page, 0),
    confidence: toNumber(question.confidence, 0),
    status: question.status || "normalized"
  });

  const buildStudent = (student, questions) => {
    const answersObject = utils.isPlainObject(student.answers) ? student.answers : {};
    const answers = questions.map((question) => ({ questionId: question.id, answer: normalizeValue(answersObject[question.id]) }));
    const questionScores = questions.map((question) => ({
      questionId: question.id,
      score: answersObject[question.id] && question.answerKey && answersObject[question.id] === question.answerKey ? question.maxScore : 0
    }));

    return {
      studentNo: toStringValue(student.studentNo),
      fullName: normalizeValue(student.fullName),
      answers,
      questionScores,
      totalScore: toNumber(student.totalScore, questionScores.reduce((sum, item) => sum + item.score, 0))
    };
  };

  const createStructuringOutputDefault = () => {
    const documentOutput = createMockDocumentOutput();
    const questions = documentOutput.questions.map((question) => buildQuestion(question, documentOutput.answerKey.find((item) => item.questionId === question.id)));
    const students = documentOutput.students.map((student) => buildStudent(student, questions));
    const totalScore = questions.reduce((sum, question) => sum + question.maxScore, 0);

    return {
      exam: {
        id: utils.createId("exam"),
        title: documentOutput.metadata.title,
        course: documentOutput.metadata.course,
        educationLevel: documentOutput.metadata.educationLevel,
        schoolType: documentOutput.metadata.schoolType,
        grade: documentOutput.metadata.grade,
        examType: documentOutput.metadata.examType,
        examDate: documentOutput.metadata.examDate,
        teacher: documentOutput.metadata.teacher,
        questionCount: questions.length,
        totalScore
      },
      questions,
      students,
      scoringModel: {
        totalScore,
        questionWeights: Object.fromEntries(questions.map((question) => [question.id, question.maxScore])),
        gradingScale: { type: "100-point", max: 100, pass: 50 },
        answerKeyPresent: questions.every((question) => Boolean(question.answerKey)),
        scoreDistribution: students.map((student) => ({ studentNo: student.studentNo, totalScore: student.totalScore }))
      },
      missingInformation: [],
      quality: {
        ocrConfidence: documentOutput.confidence,
        missingQuestionCount: 0,
        missingAnswerKey: false,
        missingScores: false,
        duplicateStudents: [],
        warnings: []
      },
      confidence: documentOutput.confidence
    };
  };

  const structuringOutputContract = createContract({
    name: "StructuringOutput",
    description: "DocumentOutput üzerinden normalize edilmiş ortak MAHİR sınav veri modeli.",
    required: ["exam", "questions", "students", "scoringModel", "missingInformation", "quality", "confidence"],
    optional: [],
    createDefault: createStructuringOutputDefault,
    validate(payload) {
      const errors = [];
      validateObject(payload, "exam", errors);
      validateObject(payload, "scoringModel", errors);
      validateObject(payload, "quality", errors);
      ["questions", "students", "missingInformation"].forEach((path) => validateArray(payload, path, errors));
      if (payload.exam && !utils.isFiniteNumber(payload.exam.questionCount)) {
        errors.push({ fieldPath: "exam.questionCount", message: "Soru sayısı sayı olmalıdır." });
      }
      if (payload.exam && !utils.isFiniteNumber(payload.exam.totalScore)) {
        errors.push({ fieldPath: "exam.totalScore", message: "Toplam puan sayı olmalıdır." });
      }
      if (!utils.isFiniteNumber(payload.confidence)) {
        errors.push({ fieldPath: "confidence", message: "confidence sayı olmalıdır." });
      }
      return { errors, warnings: [] };
    }
  });

  MAHIR.contracts.StructuringOutput = structuringOutputContract;
  MAHIR.state.contracts = MAHIR.contracts;
  MAHIR.schemaRegistry.register("StructuringOutput", structuringOutputContract);
  const structuringCore = {
    readDocument(input) {
      return normalizeValue(input || createMockDocumentOutput());
    },
    normalize(documentOutput) {
      return normalizeValue({
        ...documentOutput,
        questions: (documentOutput.questions || []).map((question) => ({ ...question, maxScore: toNumber(question.maxScore, 0), number: toNumber(question.number, 0) })),
        students: (documentOutput.students || []).map((student) => ({ ...student, studentNo: toStringValue(student.studentNo), totalScore: toNumber(student.totalScore, 0) }))
      });
    },
    buildExam(normalizedDocument, questions) {
      const metadata = normalizedDocument.metadata || {};
      return {
        id: utils.createId("exam"),
        title: metadata.title || "Sınav Analizi",
        course: metadata.course || "Türk Dili ve Edebiyatı",
        educationLevel: metadata.educationLevel || "Lise",
        schoolType: metadata.schoolType || "Anadolu Lisesi",
        grade: metadata.grade || "10",
        examType: metadata.examType || "Yazılı Sınav",
        examDate: metadata.examDate || null,
        teacher: metadata.teacher || null,
        questionCount: questions.length,
        totalScore: questions.reduce((sum, question) => sum + question.maxScore, 0)
      };
    },
    buildQuestions(normalizedDocument) {
      return (normalizedDocument.questions || []).map((question) => buildQuestion(question, (normalizedDocument.answerKey || []).find((item) => item.questionId === question.id)));
    },
    buildStudents(normalizedDocument, questions) {
      return (normalizedDocument.students || []).map((student) => buildStudent(student, questions));
    },
    buildScoringModel(questions, students) {
      const totalScore = questions.reduce((sum, question) => sum + question.maxScore, 0);
      return {
        totalScore,
        questionWeights: Object.fromEntries(questions.map((question) => [question.id, question.maxScore])),
        gradingScale: { type: "100-point", max: 100, pass: 50 },
        answerKeyPresent: questions.every((question) => Boolean(question.answerKey)),
        scoreDistribution: students.map((student) => ({ studentNo: student.studentNo, totalScore: student.totalScore }))
      };
    },
    detectMissingInformation(normalizedDocument, questions, students, scoringModel) {
      const missing = [];
      if (questions.length === 0) {
        missing.push(createStructuringIssue({ code: "MISSING_QUESTION", message: "Soru bilgisi bulunamadı." }));
      }
      if (questions.some((question) => !question.maxScore)) {
        missing.push(createStructuringIssue({ code: "MISSING_SCORE", message: "Bazı sorularda puan bilgisi eksik." }));
      }
      if (!scoringModel.answerKeyPresent) {
        missing.push(createStructuringIssue({ code: "MISSING_ANSWER_KEY", message: "Cevap anahtarı tüm sorular için tamamlanmamış." }));
      }
      if (students.length === 0) {
        missing.push(createStructuringIssue({ code: "MISSING_STUDENT", message: "Öğrenci bilgisi bulunamadı." }));
      }
      if ((normalizedDocument.tables || []).some((table) => !Array.isArray(table.cells))) {
        missing.push(createStructuringIssue({ code: "BROKEN_TABLE", message: "Tablo hücreleri okunabilir formatta değil." }));
      }
      if (toNumber(normalizedDocument.confidence, 0) < 0.6) {
        missing.push(createStructuringIssue({ code: "LOW_OCR_CONFIDENCE", message: "Belge okuma güven değeri düşük." }));
      }
      return missing;
    },
    buildQuality(normalizedDocument, questions, students, missingInformation, scoringModel) {
      const studentNos = students.map((student) => student.studentNo).filter(Boolean);
      const duplicateStudents = studentNos.filter((studentNo, index) => studentNos.indexOf(studentNo) !== index);
      return {
        ocrConfidence: toNumber(normalizedDocument.confidence, 0),
        missingQuestionCount: questions.filter((question) => !question.text).length,
        missingAnswerKey: !scoringModel.answerKeyPresent,
        missingScores: questions.some((question) => !question.maxScore),
        duplicateStudents: Array.from(new Set(duplicateStudents)),
        warnings: [...(normalizedDocument.warnings || []), ...missingInformation]
      };
    },
    finalize({ exam, questions, students, scoringModel, missingInformation, quality, normalizedDocument }) {
      return {
        exam,
        questions,
        students,
        scoringModel,
        missingInformation,
        quality,
        confidence: toNumber(normalizedDocument.confidence, 0)
      };
    }
  };

  const runStructuringStep = async (label, callback) => {
    console.info(`[MAHIR] ${label} başladı`);
    const stepLog = MAHIR.logger.start(`StructuringAgent.${label}`);
    try {
      const value = await Promise.resolve(callback());
      MAHIR.logger.finish(stepLog, true);
      console.info(`[MAHIR] ${label} bitti`);
      return value;
    } catch (error) {
      MAHIR.logger.finish(stepLog, false);
      MAHIR.logger.error(`${label} tamamlanamadı`, { error: error.message });
      throw error;
    }
  };

  MAHIR.agents.StructuringAgent.execute = async (input = createMockDocumentOutput()) => {
    MAHIR.events.emit("mahir:structuring:started", { inputSummary: utils.summarizePayload(input) });
    try {
      const documentOutput = await runStructuringStep("readDocument", () => structuringCore.readDocument(input));
      const normalizedDocument = await runStructuringStep("normalize", () => structuringCore.normalize(documentOutput));
      const questions = await runStructuringStep("buildQuestions", () => structuringCore.buildQuestions(normalizedDocument));
      const exam = await runStructuringStep("buildExam", () => structuringCore.buildExam(normalizedDocument, questions));
      const students = await runStructuringStep("buildStudents", () => structuringCore.buildStudents(normalizedDocument, questions));
      const scoringModel = await runStructuringStep("buildScoringModel", () => structuringCore.buildScoringModel(questions, students));
      const missingInformation = await runStructuringStep("detectMissingInformation", () => structuringCore.detectMissingInformation(normalizedDocument, questions, students, scoringModel));
      const quality = await runStructuringStep("buildQuality", () => structuringCore.buildQuality(normalizedDocument, questions, students, missingInformation, scoringModel));
      const output = await runStructuringStep("finalize", () => structuringCore.finalize({ exam, questions, students, scoringModel, missingInformation, quality, normalizedDocument }));
      const validationResult = MAHIR.schemaRegistry.validate("StructuringOutput", output);

      if (!validationResult.valid) {
        const issue = {
          id: utils.createId("validation-issue"),
          severity: "blocking",
          code: "STRUCTURING_OUTPUT_INVALID",
          message: "StructuringOutput sözleşme doğrulaması başarısız oldu.",
          sourceAgent: "StructuringAgent",
          fieldPath: validationResult.errors[0]?.fieldPath || "StructuringOutput",
          suggestion: "StructuringAgent çıktısı StructuringOutput sözleşmesine uygun hale getirilmelidir.",
          errors: validationResult.errors,
          warnings: validationResult.warnings
        };
        MAHIR.state.validationIssues.push(issue);
        MAHIR.events.emit("mahir:structuring:error", { issue });
        throw new Error(issue.message);
      }

      MAHIR.state.agentOutputs.structuring = output;
      MAHIR.events.emit("mahir:structuring:completed", { output });
      console.info("Structuring Agent Completed");
      return output;
    } catch (error) {
      MAHIR.events.emit("mahir:structuring:error", { error });
      throw error;
    }
  };

  MAHIR.structuring = {
    agent: MAHIR.agents.StructuringAgent,
    core: structuringCore,
    createMockDocumentOutput,
    normalize: structuringCore.normalize,
    run(input) {
      return MAHIR.agents.StructuringAgent.execute(input);
    }
  };

  MAHIR.logger.info("MAHIR Structuring Agent Core initialized", { version: "1.0.0" });
  console.info("MAHIR Structuring Agent Core initialized");
})();
const preparationManager = (() => {
  const emptyText = "Henüz seçilmedi";
  const mtalSchoolType = "Mesleki ve Teknik Anadolu Lisesi";
  const otherOption = "Diğer";

  const data = {
    stages: ["Ortaokul", "Lise"],
    schoolTypes: {
      Ortaokul: ["Ortaokul", "İmam Hatip Ortaokulu"],
      Lise: [
        "Anadolu Lisesi",
        "Hazırlık Sınıfı Bulunan Anadolu Lisesi",
        "Fen Lisesi",
        "Sosyal Bilimler Lisesi",
        "Anadolu İmam Hatip Lisesi",
        "Mesleki ve Teknik Anadolu Lisesi",
        "Güzel Sanatlar Lisesi",
        "Spor Lisesi",
        "Çok Programlı Anadolu Lisesi",
        "Diğer"
      ]
    },
    grades: {
      Ortaokul: ["5", "6", "7", "8"],
      Lise: ["9", "10", "11", "12"]
    },
    courseTypes: ["Ortak Ders", "Seçmeli Ders"],
    courses: {
      Ortaokul: {
        "Ortak Ders": [
          "Türkçe",
          "Matematik",
          "Fen Bilimleri",
          "Sosyal Bilgiler",
          "T.C. İnkılap Tarihi ve Atatürkçülük",
          "Yabancı Dil",
          "Din Kültürü ve Ahlak Bilgisi",
          "Görsel Sanatlar",
          "Müzik",
          "Beden Eğitimi ve Spor",
          "Bilişim Teknolojileri ve Yazılım",
          "Teknoloji ve Tasarım",
          "Rehberlik ve Kariyer Planlama"
        ],
        "Seçmeli Ders": [
          "Kur'an-ı Kerim",
          "Peygamberimizin Hayatı",
          "Temel Dinî Bilgiler",
          "Okuma Becerileri",
          "Yazarlık ve Yazma Becerileri",
          "Yaşayan Diller ve Lehçeler",
          "İletişim ve Sunum Becerileri",
          "Bilim Uygulamaları",
          "Matematik Uygulamaları",
          "Çevre Eğitimi",
          "Drama",
          "Zekâ Oyunları",
          "Halk Kültürü",
          "Medya Okuryazarlığı",
          "Hukuk ve Adalet",
          "Düşünme Eğitimi",
          "Diğer"
        ]
      },
      Lise: {
        "Ortak Ders": [
          "Türk Dili ve Edebiyatı",
          "Matematik",
          "Fizik",
          "Kimya",
          "Biyoloji",
          "Tarih",
          "Coğrafya",
          "Din Kültürü ve Ahlak Bilgisi",
          "Felsefe",
          "Birinci Yabancı Dil",
          "İkinci Yabancı Dil",
          "Görsel Sanatlar",
          "Müzik",
          "Beden Eğitimi ve Spor",
          "Bilgisayar Bilimi",
          "Sağlık Bilgisi ve Trafik Kültürü"
        ],
        "Seçmeli Ders": [
          "Seçmeli Türk Dili ve Edebiyatı",
          "Diksiyon ve Hitabet",
          "Osmanlı Türkçesi",
          "Seçmeli Matematik",
          "Seçmeli Fizik",
          "Seçmeli Kimya",
          "Seçmeli Biyoloji",
          "Psikoloji",
          "Sosyoloji",
          "Mantık",
          "Çağdaş Türk ve Dünya Tarihi",
          "Astronomi ve Uzay Bilimleri",
          "Proje Tasarımı ve Uygulamaları",
          "Bilgi Kuramı",
          "Demokrasi ve İnsan Hakları",
          "Diğer"
        ]
      }
    },
    schoolCourseAdditions: {
      "Anadolu İmam Hatip Lisesi": [
        "Kur'an-ı Kerim",
        "Arapça",
        "Mesleki Arapça",
        "Siyer",
        "Tefsir",
        "Hadis",
        "Fıkıh",
        "Kelam",
        "Hitabet ve Mesleki Uygulama",
        "Temel Dinî Bilgiler"
      ],
      "Fen Lisesi": [
        "Fen Lisesi Matematik",
        "Fen Lisesi Fizik",
        "Fen Lisesi Kimya",
        "Fen Lisesi Biyoloji"
      ],
      "Sosyal Bilimler Lisesi": [
        "Sosyal Bilim Çalışmaları",
        "Türk Kültür ve Medeniyet Tarihi",
        "Sosyal Bilimlerde Araştırma Yöntemleri",
        "Osmanlı Türkçesi",
        "Psikoloji",
        "Sosyoloji",
        "Mantık"
      ],
      "Güzel Sanatlar Lisesi": [
        "Temel Sanat Eğitimi",
        "Desen",
        "Görsel Sanatlar",
        "Müziksel İşitme Okuma ve Yazma",
        "Çalgı Eğitimi",
        "Piyano",
        "Türk Müziği Koro Eğitimi",
        "Batı Müziği Koro Eğitimi"
      ],
      "Spor Lisesi": [
        "Spor Eğitimi",
        "Temel Spor Eğitimi",
        "Bireysel Sporlar",
        "Takım Sporları",
        "Spor Yönetimi",
        "Spor Psikolojisi",
        "Antrenman Bilgisi",
        "Sporcu Sağlığı"
      ]
    },
    mtal: {
      programTypes: ["Anadolu Teknik Programı (ATP)", "Anadolu Meslek Programı (AMP)"],
      fields: [
        "Bilişim Teknolojileri",
        "Elektrik-Elektronik Teknolojisi",
        "Makine ve Tasarım Teknolojisi",
        "Motorlu Araçlar Teknolojisi",
        "Muhasebe ve Finansman",
        "Çocuk Gelişimi ve Eğitimi",
        "Sağlık Hizmetleri",
        "Yiyecek İçecek Hizmetleri",
        "Konaklama ve Seyahat Hizmetleri",
        "Giyim Üretim Teknolojisi",
        "Metal Teknolojisi",
        "Mobilya ve İç Mekân Tasarımı",
        "Diğer"
      ],
      branches: {
        "Bilişim Teknolojileri": ["Yazılım Geliştirme", "Web Programcılığı", "Ağ İşletmenliği ve Siber Güvenlik"],
        "Elektrik-Elektronik Teknolojisi": ["Elektrik Tesisatları ve Dağıtımı", "Endüstriyel Bakım Onarım", "Elektronik Sistemler"],
        "Muhasebe ve Finansman": ["Bilgisayarlı Muhasebe", "Dış Ticaret Ofis Hizmetleri"],
        "Çocuk Gelişimi ve Eğitimi": ["Erken Çocukluk Eğitimi", "Özel Eğitim"],
        "Yiyecek İçecek Hizmetleri": ["Mutfak", "Servis", "Pastacılık"]
      },
      defaultBranches: ["Genel Alan Dersleri"],
      courses: [
        "Mesleki Gelişim Atölyesi",
        "Alan Temel Dersleri",
        "Atölye ve Laboratuvar Uygulamaları",
        "İşletmelerde Mesleki Eğitim",
        "Meslek Etiği",
        "İş Sağlığı ve Güvenliği",
        "Proje Geliştirme",
        "Diğer"
      ]
    }
  };

  const placeholders = {
    stage: "Öğretim kademesi seçiniz",
    schoolType: "Okul türü seçiniz",
    programType: "Program türü seçiniz",
    mtalField: "Alan seçiniz",
    mtalBranch: "Dal seçiniz",
    grade: "Sınıf düzeyi seçiniz",
    courseType: "Ders türü seçiniz",
    course: "Ders seçiniz"
  };

  let form;
  let nextButton;
  let statusMessage;
  const fields = {};
  const cards = {};
  const summaryFields = {};

  const unique = (items) => Array.from(new Set(items.filter(Boolean)));

  const getValue = (fieldName) => (fields[fieldName]?.value || "").trim();

  const visibleCourseName = () => getValue("course") === otherOption
    ? getValue("otherCourse")
    : getValue("course");

  const publishContext = () => {
    window.MAHIRPreparationContext = {
      courseName: visibleCourseName(),
      grade: getValue("grade")
    };
    document.dispatchEvent(new CustomEvent("mahir:preparation-context-changed", {
      detail: window.MAHIRPreparationContext
    }));
  };

  const isMtalSelected = () => getValue("schoolType") === mtalSchoolType;

  const populateSelect = (fieldName, options, disabled = false) => {
    const select = fields[fieldName];

    if (!select) {
      return;
    }

    select.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = placeholders[fieldName] || "Seçiniz";
    select.append(placeholder);

    options.forEach((optionText) => {
      const option = document.createElement("option");
      option.value = optionText;
      option.textContent = optionText;
      select.append(option);
    });

    select.value = "";
    select.disabled = disabled || options.length === 0;
    updateCardState(fieldName);
  };

  const resetSelect = (fieldName) => {
    populateSelect(fieldName, [], true);
  };

  const updateCardState = (fieldName) => {
    const card = cards[fieldName];
    const field = fields[fieldName];

    if (!card || !field) {
      return;
    }

    card.classList.toggle("is-disabled", Boolean(field.disabled));
  };

  const setCardVisibility = (fieldName, shouldShow) => {
    const card = cards[fieldName];
    const field = fields[fieldName];

    if (!card || !field) {
      return;
    }

    card.hidden = !shouldShow;

    if (!shouldShow) {
      field.value = "";
      field.disabled = true;
    }

    updateCardState(fieldName);
  };

  const enableInputCard = (fieldName, shouldEnable) => {
    const field = fields[fieldName];
    const card = cards[fieldName];

    if (!field || !card) {
      return;
    }

    card.hidden = !shouldEnable;
    field.disabled = !shouldEnable;

    if (!shouldEnable) {
      field.value = "";
    }

    updateCardState(fieldName);
  };

  const setSelectOptions = (fieldName, options) => {
    populateSelect(fieldName, options, false);
  };

  const resetFromSchoolType = () => {
    enableInputCard("otherSchool", false);
    ["programType", "mtalField", "mtalBranch"].forEach((fieldName) => {
      setCardVisibility(fieldName, false);
      resetSelect(fieldName);
    });
    ["grade", "courseType", "course"].forEach(resetSelect);
    enableInputCard("otherCourse", false);
  };

  const resetFromGrade = () => {
    ["courseType", "course"].forEach(resetSelect);
    enableInputCard("otherCourse", false);
  };

  const resetFromCourseType = () => {
    resetSelect("course");
    enableInputCard("otherCourse", false);
  };

  const getCourseOptions = () => {
    const stage = getValue("stage");
    const schoolType = getValue("schoolType");
    const courseType = getValue("courseType");

    if (!stage || !courseType) {
      return [];
    }

    if (isMtalSelected()) {
      return unique(data.mtal.courses);
    }

    const baseCourses = data.courses[stage]?.[courseType] || [];
    const schoolCourses = data.schoolCourseAdditions[schoolType] || [];
    return unique([...baseCourses, ...schoolCourses, otherOption]);
  };

  const updateSummary = () => {
    const visibleSchoolType = getValue("schoolType") === otherOption && getValue("otherSchool") ? getValue("otherSchool") : getValue("schoolType");
    const visibleCourse = getValue("course") === otherOption && getValue("otherCourse") ? getValue("otherCourse") : getValue("course");
    const values = {
      stage: getValue("stage"),
      schoolType: visibleSchoolType,
      programType: getValue("programType"),
      mtalField: getValue("mtalField"),
      mtalBranch: getValue("mtalBranch"),
      grade: getValue("grade") ? `${getValue("grade")}. sınıf` : "",
      courseType: getValue("courseType"),
      course: visibleCourse
    };

    Object.entries(summaryFields).forEach(([fieldName, element]) => {
      element.textContent = values[fieldName] || emptyText;
    });
  };

  const isPreparationComplete = () => {
    const hasOtherSchool = getValue("schoolType") !== otherOption || Boolean(getValue("otherSchool"));
    const hasOtherCourse = getValue("course") !== otherOption || Boolean(getValue("otherCourse"));
    const hasMtalDetails = !isMtalSelected() || (getValue("programType") && getValue("mtalField") && getValue("mtalBranch"));

    return Boolean(
      getValue("stage") &&
      getValue("schoolType") &&
      hasOtherSchool &&
      hasMtalDetails &&
      getValue("grade") &&
      getValue("courseType") &&
      getValue("course") &&
      hasOtherCourse
    );
  };

  const updateNextButton = () => {
    const isComplete = isPreparationComplete();

    if (nextButton) {
      nextButton.disabled = !isComplete;
      nextButton.setAttribute("aria-disabled", String(!isComplete));
    }

    if (statusMessage) {
      statusMessage.textContent = isComplete
        ? "Hazırlık bilgileri tamamlandı. Veri ekleme adımına geçebilirsiniz."
        : "Seçimleri tamamladığınızda Devam Et düğmesi aktif olacaktır.";
    }
  };

  const refresh = () => {
    updateSummary();
    updateNextButton();
    publishContext();
  };

  const handleStageChange = () => {
    resetFromSchoolType();

    if (getValue("stage")) {
      setSelectOptions("schoolType", data.schoolTypes[getValue("stage")] || []);
    } else {
      resetSelect("schoolType");
    }

    refresh();
  };

  const handleSchoolTypeChange = () => {
    resetFromSchoolType();
    enableInputCard("otherSchool", getValue("schoolType") === otherOption);

    if (isMtalSelected()) {
      ["programType", "mtalField", "mtalBranch"].forEach((fieldName) => setCardVisibility(fieldName, true));
      setSelectOptions("programType", data.mtal.programTypes);
    } else if (getValue("schoolType")) {
      setSelectOptions("grade", data.grades[getValue("stage")] || []);
    }

    refresh();
  };

  const handleProgramTypeChange = () => {
    ["mtalField", "mtalBranch", "grade", "courseType", "course"].forEach(resetSelect);
    enableInputCard("otherCourse", false);

    if (getValue("programType")) {
      setSelectOptions("mtalField", data.mtal.fields);
    }

    refresh();
  };

  const handleMtalFieldChange = () => {
    ["mtalBranch", "grade", "courseType", "course"].forEach(resetSelect);
    enableInputCard("otherCourse", false);

    if (getValue("mtalField")) {
      setSelectOptions("mtalBranch", data.mtal.branches[getValue("mtalField")] || data.mtal.defaultBranches);
    }

    refresh();
  };

  const handleMtalBranchChange = () => {
    ["grade", "courseType", "course"].forEach(resetSelect);
    enableInputCard("otherCourse", false);

    if (getValue("mtalBranch")) {
      setSelectOptions("grade", data.grades[getValue("stage")] || []);
    }

    refresh();
  };

  const handleGradeChange = () => {
    resetFromGrade();

    if (getValue("grade")) {
      setSelectOptions("courseType", data.courseTypes);
    }

    refresh();
  };

  const handleCourseTypeChange = () => {
    resetFromCourseType();

    if (getValue("courseType")) {
      setSelectOptions("course", getCourseOptions());
    }

    refresh();
  };

  const handleCourseChange = () => {
    enableInputCard("otherCourse", getValue("course") === otherOption);
    refresh();
  };

  const bindEvents = () => {
    fields.stage?.addEventListener("change", handleStageChange);
    fields.schoolType?.addEventListener("change", handleSchoolTypeChange);
    fields.programType?.addEventListener("change", handleProgramTypeChange);
    fields.mtalField?.addEventListener("change", handleMtalFieldChange);
    fields.mtalBranch?.addEventListener("change", handleMtalBranchChange);
    fields.grade?.addEventListener("change", handleGradeChange);
    fields.courseType?.addEventListener("change", handleCourseTypeChange);
    fields.course?.addEventListener("change", handleCourseChange);
    fields.otherSchool?.addEventListener("input", refresh);
    fields.otherCourse?.addEventListener("input", refresh);
  };

  const collectElements = () => {
    form = document.querySelector("[data-preparation-form]");
    nextButton = document.querySelector("[data-preparation-next]");
    statusMessage = document.querySelector("[data-preparation-status]");

    document.querySelectorAll("[data-prep-field]").forEach((field) => {
      fields[field.dataset.prepField] = field;
    });

    document.querySelectorAll("[data-field-card]").forEach((card) => {
      cards[card.dataset.fieldCard] = card;
    });

    document.querySelectorAll("[data-summary-field]").forEach((field) => {
      summaryFields[field.dataset.summaryField] = field;
    });
  };

  const init = () => {
    collectElements();

    if (!form || !fields.stage) {
      return;
    }

    populateSelect("stage", data.stages, false);
    resetSelect("schoolType");
    ["programType", "mtalField", "mtalBranch"].forEach((fieldName) => {
      setCardVisibility(fieldName, false);
      resetSelect(fieldName);
    });
    ["grade", "courseType", "course"].forEach(resetSelect);
    enableInputCard("otherSchool", false);
    enableInputCard("otherCourse", false);
    bindEvents();
    refresh();
  };

  return { init };
})();

const screenManager = (() => {
  const activeScreenClass = "active-screen";
  const hiddenScreenClass = "hidden-screen";
  const initialScreenId = "welcome-screen";
  const analysisScreenId = "analysis-screen";
  const validationScreenId = "validation-screen";
  const screenStepLabels = {
    "welcome-screen": "Karşılama",
    "preparation-screen": "Hazırlık",
    "data-entry-screen": "Veri",
    "validation-screen": "Veri",
    "analysis-screen": "Analiz",
    "report-screen": "Rapor"
  };
  const approvalMessages = {
    waiting: "Analize geçmek için paylaşılan veri kapsamını gözden geçirip öğretmen onayıyla işaretleyiniz.",
    guide: "Daha kapsamlı değerlendirme için ek bilgiler paylaşabilirsiniz. Mevcut verilerle de analiz oluşturulabilir.",
    approved: "Veriler öğretmen onayıyla işaretlendi. Analiz süreci başlatılıyor."
  };
  const screens = new Map();
  let currentScreenId = initialScreenId;
  let dataApprovalGranted = false;

  const registerScreens = () => {
    document.querySelectorAll("[data-screen]").forEach((screen) => {
      if (screen.id) {
        screens.set(screen.id, screen);
      }
    });
  };

  const getApprovalMessage = () => document.querySelector("[data-approval-message]");

  const updateApprovalMessage = (message) => {
    const approvalMessage = getApprovalMessage();

    if (approvalMessage) {
      approvalMessage.textContent = message;
    }
  };

  const setDataApprovalState = (isApproved) => {
    const validationScreen = screens.get(validationScreenId);
    dataApprovalGranted = isApproved;

    if (validationScreen) {
      validationScreen.dataset.dataApprovalState = isApproved ? "approved" : "pending";
    }

    updateApprovalMessage(isApproved ? approvalMessages.approved : approvalMessages.waiting);
  };

  const setScreenState = (screen, isActive) => {
    screen.classList.toggle(activeScreenClass, isActive);
    screen.classList.toggle(hiddenScreenClass, !isActive);
    screen.dataset.screenState = isActive ? "active" : "hidden";
    screen.hidden = !isActive;
    screen.setAttribute("aria-hidden", String(!isActive));
  };

  const updateProgressStepper = (screen) => {
    const stepper = screen.querySelector('[data-component="Progress Stepper"]');
    const activeStepLabel = screenStepLabels[screen.id];

    if (!stepper || !activeStepLabel) {
      return;
    }

    stepper.querySelectorAll("[aria-current]").forEach((step) => {
      step.removeAttribute("aria-current");
    });

    Array.from(stepper.querySelectorAll("li")).forEach((step) => {
      if (step.textContent.trim() === activeStepLabel) {
        step.setAttribute("aria-current", "step");
      }
    });
  };

  const updateGlobalProcessNav = (screenId) => {
    const activeStepLabel = screenStepLabels[screenId];
    const globalNav = document.querySelector(".welcome-process-nav");

    if (!globalNav || !activeStepLabel) {
      return;
    }

    globalNav.querySelectorAll("[aria-current]").forEach((step) => {
      step.removeAttribute("aria-current");
    });

    Array.from(globalNav.querySelectorAll("li")).forEach((step) => {
      if (step.textContent.trim() === activeStepLabel) {
        step.setAttribute("aria-current", "step");
      }
    });
  };

  const showApprovalGuide = () => {
    updateApprovalMessage(approvalMessages.guide);
    const approvalMessage = getApprovalMessage();

    if (approvalMessage) {
      approvalMessage.focus({ preventScroll: true });
    }
  };

  const canOpenScreen = (targetScreenId) => {
    if (targetScreenId === analysisScreenId && !dataApprovalGranted) {
      showApprovalGuide();
      return false;
    }

    return true;
  };

  const showScreen = (targetScreenId) => {
    const targetScreen = screens.get(targetScreenId);

    if (!targetScreen || !canOpenScreen(targetScreenId)) {
      return false;
    }

    screens.forEach((screen, screenId) => {
      setScreenState(screen, screenId === targetScreenId);
    });

    currentScreenId = targetScreenId;
    updateProgressStepper(targetScreen);
    updateGlobalProcessNav(targetScreenId);
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    return true;
  };

  const bindNavigationControls = () => {
    document.querySelectorAll("[data-target-screen]").forEach((control) => {
      control.addEventListener("click", () => {
        if (control.disabled || control.getAttribute("aria-disabled") === "true") {
          return;
        }

        if (control.dataset.resetDataApproval === "true") {
          setDataApprovalState(false);
        }

        if (control.dataset.approvalAction === "confirm-data") {
          document.dispatchEvent(new CustomEvent("mahir:confirm-data"));
          return;
        }

        showScreen(control.dataset.targetScreen);
      });
    });
  };

  const init = () => {
    registerScreens();
    setDataApprovalState(false);
    showScreen(currentScreenId);
    bindNavigationControls();
  };

  return {
    init,
    showScreen,
    approveData() {
      setDataApprovalState(true);
    },
    revokeDataApproval() {
      setDataApprovalState(false);
    }
  };
})();


const fileUploadBridge = (() => {
  const maxFileSize = 20 * 1024 * 1024;
  const allowedExtensions = ["pdf", "doc", "docx", "xlsx", "jpg", "jpeg", "png", "webp"];

  const init = () => {
    const fileInput = document.querySelector("#exam-file");
    const dropzone = document.querySelector("[data-upload-dropzone]");
    const filesList = document.querySelector("[data-uploaded-files-list]");
    const readButton = document.querySelector("[data-read-document]");
    const statusMessage = document.querySelector("[data-upload-status]");
    const studentCountInput = document.querySelector("[data-student-count]");
    const questionCountInput = document.querySelector("[data-question-count]");
    const questionConfiguration = document.querySelector("[data-question-configuration]");
    const scoreTotal = document.querySelector("[data-score-total]");
    const structureStatus = document.querySelector("[data-exam-structure-status]");
    const assessmentComponent = document.querySelector("[data-assessment-component]");
    const languageAssessmentField = document.querySelector("[data-language-assessment-field]");
    const componentWeightNote = document.querySelector("[data-component-weight-note]");
    const programDataStatus = document.querySelector("[data-program-data-status]");
    const generalReportMerger = document.querySelector("[data-general-report-merger]");
    const generalReportStatus = document.querySelector("[data-general-report-status]");
    const mergeGeneralReportsButton = document.querySelector("[data-merge-general-reports]");
    const generalReportInputs = Array.from(document.querySelectorAll("[data-general-report-file]"));
    const standardDataEntryItems = Array.from(document.querySelectorAll("[data-standard-data-entry]"));
    const contextStatus = document.querySelector("[data-context-status]");
    const examSequenceField = document.querySelector("[data-exam-sequence-field]");
    const examSequenceSelect = document.querySelector('[data-exam-field="examSequence"]');
    const saveGroupButton = document.querySelector("[data-save-current-group]");
    const addGroupButton = document.querySelector("[data-add-image-group]");
    const confirmFinalButton = document.querySelector("[data-confirm-final-analysis]");
    const returnToUploadButton = document.querySelector("[data-return-to-upload]");
    const validationStudentCountControl = document.querySelector("[data-validation-student-count-control]");
    const validationExpectedCount = document.querySelector("[data-validation-expected-count]");
    const validationStudentCountEditor = document.querySelector("[data-validation-student-count-editor]");
    const validationStudentCountEditorInput = document.querySelector("[data-validation-student-count-input]");
    const validationStudentCountStatus = document.querySelector("[data-validation-student-count-status]");
    const studentRecordUndo = document.querySelector("[data-student-record-undo]");
    const studentRecordUndoMessage = document.querySelector("[data-student-record-undo-message]");

    if (!fileInput || !readButton || typeof FormData === "undefined" || typeof fetch === "undefined") {
      return;
    }

    let selectedFiles = [];
    let sourceMode = "images";
    let structuredData = null;
    let previewUrls = [];
    let progressTimer;
    let learningOutcomes = [];
    let programLearningOutcomes = [];
    let activeProgramId = "";
    let programRequestSequence = 0;
    let savedGroups = [];
    let currentGroupNumber = 1;
    let finalReviewMode = false;
    let lastRemovedStudentRecord = null;
    const generalReportFiles = { written: null, listening: null, speaking: null };
    const reportRuntime = window.MAHIRReportRuntime = window.MAHIRReportRuntime || {};
    const componentLabels = {
      written: "Yazılı Sınav",
      listening: "Dinleme/İzleme Sınavı",
      speaking: "Konuşma Sınavı",
      general: "Genel Değerlendirme"
    };
    const examSequenceOptions = {
      written: ["1. Yazılı Sınav", "2. Yazılı Sınav"],
      listening: ["1. Dinleme/İzleme Sınavı", "2. Dinleme/İzleme Sınavı"],
      speaking: ["1. Konuşma Sınavı", "2. Konuşma Sınavı"]
    };
    const profiles = {
      "tde-70-15-15": {
        title: "Türk Dili ve Edebiyatı",
        weights: { written: 0.70, listening: 0.15, speaking: 0.15 }
      },
      "language-50-25-25": {
        title: "Türkçe ve yabancı dil",
        weights: { written: 0.50, listening: 0.25, speaking: 0.25 }
      }
    };
    const normalizeCourseName = (value) => String(value || "").normalize("NFKC").toLocaleLowerCase("tr-TR").trim().replace(/\s+/g, " ");
    const tdeCourses = new Set(["Türk Dili ve Edebiyatı", "Seçmeli Türk Dili ve Edebiyatı"].map(normalizeCourseName));
    const languageCourses = new Set([
      "Türkçe", "Yabancı Dil", "Birinci Yabancı Dil", "İkinci Yabancı Dil",
      "İngilizce", "Almanca", "Fransızca", "Arapça", "Mesleki Arapça", "Rusça",
      "İspanyolca", "İtalyanca", "Çince", "Japonca", "Farsça"
    ].map(normalizeCourseName));
    const profileIdForCourse = (courseName) => {
      const normalized = normalizeCourseName(courseName);
      if (tdeCourses.has(normalized)) return "tde-70-15-15";
      if (languageCourses.has(normalized)) return "language-50-25-25";
      return null;
    };

    const currentCourseName = () => window.MAHIRPreparationContext?.courseName || "";
    const currentGrade = () => window.MAHIRPreparationContext?.grade || "";
    const currentProfileId = () => profileIdForCourse(currentCourseName());
    const currentProgram = () => window.MAHIRProgramCatalog?.resolve(currentCourseName(), currentGrade()) || null;
    const examFieldAliases = {
      province: ["province", "city"],
      district: ["district", "town"],
      schoolName: ["schoolName", "school", "institutionName"],
      teacherName: ["teacherName", "teacher", "teacherFullName"],
      academicYear: ["academicYear", "educationYear"],
      classSection: ["classSection", "grade", "className"],
      term: ["term"],
      examSequence: ["examSequence"],
      examDate: ["examDate"],
      teachingProgram: ["teachingProgram", "curriculumName"],
      assessmentBasis: ["assessmentBasis", "measurementBasis"],
      scenarioInfo: ["scenarioInfo", "scenario", "sampleDocument"],
      otherSources: ["otherSources", "otherReferences"],
      documentNo: ["documentNo", "reportNo"],
      approvalInfo: ["approvalInfo", "transmissionInfo"]
    };

    const usefulValue = (value) => {
      const text = String(value ?? "").trim();
      return text && /[\p{L}\p{N}]/u.test(text) && !/^(okunamadı|belirtilmedi|null|undefined)$/i.test(text) ? text : "";
    };

    const looksLikeTckn = (value) => {
      const digits = String(value || "").replace(/\D/g, "");
      if (digits.length !== 11 || digits.startsWith("0")) return false;
      const numbers = [...digits].map(Number);
      const tenth = ((numbers[0] + numbers[2] + numbers[4] + numbers[6] + numbers[8]) * 7
        - (numbers[1] + numbers[3] + numbers[5] + numbers[7])) % 10;
      const eleventh = numbers.slice(0, 10).reduce((sum, number) => sum + number, 0) % 10;
      return numbers[9] === (tenth + 10) % 10 && numbers[10] === eleventh;
    };

    const contextInputs = () => Array.from(document.querySelectorAll("[data-exam-field]"));

    const readAliasedValue = (source, keys) => {
      for (const key of keys) {
        const value = usefulValue(source?.[key]);
        if (value) return value;
      }
      return "";
    };

    const institutionFieldNames = new Set([
      "province", "district", "schoolName", "teacherName", "academicYear",
      "classSection", "teachingProgram"
    ]);
    const isVerifiedInstitutionValue = (field, value, exam) => {
      if (!institutionFieldNames.has(field)) return true;
      const text = usefulValue(value);
      if (!text) return false;
      if (/^\d+(?:[.,]\d+)?$/.test(text) && field !== "classSection") return false;
      if (field === "classSection" && /^\d+(?:[.,]\d+)?$/.test(text)) return false;
      const verified = exam?.verifiedMetadataFields;
      return exam?.metadataSource === "labeled-template"
        || (Array.isArray(verified) && verified.includes(field));
    };

    const collectContextData = () => Object.fromEntries(contextInputs().map((input) => [input.dataset.examField, input.value.trim()]));

    const updateExamSequenceOptions = (component) => {
      if (!examSequenceSelect || !examSequenceField) return;
      const options = examSequenceOptions[component] || [];
      const previousValue = examSequenceSelect.value;
      examSequenceSelect.replaceChildren(new Option("Seçiniz", ""));
      options.forEach((value) => examSequenceSelect.add(new Option(value, value)));
      examSequenceSelect.value = options.includes(previousValue) ? previousValue : "";
      const enabled = options.length > 0;
      examSequenceField.hidden = !enabled;
      examSequenceSelect.disabled = !enabled;
      examSequenceSelect.toggleAttribute("data-required-context", enabled);
      if (!enabled) examSequenceSelect.value = "";
    };

    const normalizeDateInputValue = (value) => {
      const text = usefulValue(value);
      if (!text) return "";
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
      const match = text.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
      return match ? `${match[3]}-${match[2].padStart(2, "0")}-${match[1].padStart(2, "0")}` : "";
    };

    const refreshContextStatus = () => {
      if (!contextStatus) return;
      const missing = contextInputs().filter((input) => input.hasAttribute("data-required-context") && !usefulValue(input.value));
      contextStatus.textContent = missing.length
        ? `Rapor için ${missing.length} zorunlu alan henüz eksik. Belgeden okunabilen bilgiler otomatik yerleştirilecek; kalan alanları öğretmen tamamlayacaktır.`
        : "Raporun kurumsal üstbilgileri için gerekli bilgiler tamamlandı.";
      contextStatus.classList.toggle("is-error", missing.length > 0);
      contextStatus.classList.toggle("is-success", missing.length === 0);
    };

    const populateContextFields = (exam = {}) => {
      const automaticDefaults = {
        classSection: currentGrade(),
        teachingProgram: currentProgram()?.title || (activeProgramId ? `${currentCourseName()} ${currentGrade()} Öğretim Programı` : "")
      };
      contextInputs().forEach((input) => {
        const field = input.dataset.examField;
        const candidate = readAliasedValue(exam, examFieldAliases[field] || [field]);
        const detected = isVerifiedInstitutionValue(field, candidate, exam) ? candidate : "";
        const rawValue = detected || automaticDefaults[field] || "";
        const value = input.type === "date" ? normalizeDateInputValue(rawValue) : rawValue;
        const teacherEdited = input.dataset.valueSource === "teacher";
        const shouldUseDetectedValue = Boolean(detected && !teacherEdited);
        const shouldUseDefaultValue = Boolean(!detected && !usefulValue(input.value) && value);
        if (shouldUseDetectedValue || shouldUseDefaultValue) {
          input.value = value;
          input.dataset.valueSource = detected ? "document" : "context";
          input.classList.add("is-auto-filled");
        }
      });
      refreshContextStatus();
    };

    const hasDetectedMahirTemplate = (data = {}) => {
      const exam = data.exam || {};
      const populatedMetadata = Object.values(examFieldAliases).filter((aliases) => readAliasedValue(exam, aliases)).length;
      return populatedMetadata >= 5 && (data.students || []).length > 0;
    };

    const inferDocumentType = (data = {}) => {
      const exam = data.exam || {};
      const populatedMetadata = Object.values(examFieldAliases).filter((aliases) => readAliasedValue(exam, aliases)).length;
      if (hasDetectedMahirTemplate(data) || populatedMetadata >= 5) return "mahir-template";
      if (sourceMode === "template") return "unrecognized-template";
      if (sourceMode === "manual") return "handwritten-table";
      return "score-table";
    };

    const documentTypeLabel = (type) => ({
      "mahir-template": "Doldurulmuş MAHİR şablonu",
      "unrecognized-template": "Şablon yapısı doğrulanamayan belge",
      "score-table": "Öğrenci soru puan çizelgesi",
      "handwritten-table": "Elle hazırlanmış tablo"
    }[type] || "Tanımlanamayan belge");

    const setProgramStatus = (message, state = "") => {
      if (!programDataStatus) return;
      programDataStatus.hidden = !message;
      programDataStatus.textContent = message;
      programDataStatus.classList.toggle("is-error", state === "error");
      programDataStatus.classList.toggle("is-success", state === "success");
    };

    const applyComponentOutcomeFilter = () => {
      learningOutcomes = window.MAHIRProgramCatalog?.filterOutcomes(
        programLearningOutcomes,
        assessmentComponent?.value || "written"
      ) || [];
      renderQuestionConfiguration();
    };

    const setGeneralReportStatus = (message, state = "") => {
      if (!generalReportStatus) return;
      generalReportStatus.textContent = message;
      generalReportStatus.classList.toggle("is-error", state === "error");
      generalReportStatus.classList.toggle("is-success", state === "success");
    };

    const refreshGeneralReportFiles = () => {
      const selectedCount = Object.values(generalReportFiles).filter(Boolean).length;
      const complete = selectedCount === 3;
      if (mergeGeneralReportsButton) {
        mergeGeneralReportsButton.disabled = !complete;
        mergeGeneralReportsButton.setAttribute("aria-disabled", String(!complete));
      }
      if (!complete) {
        setGeneralReportStatus(`Genel değerlendirme için MAHİR'den indirilen üç Word (.docx) analiz raporu gereklidir. Seçilen rapor: ${selectedCount}/3.`);
      }
    };

    const updateGeneralReportMode = (enabled, profile) => {
      if (generalReportMerger) generalReportMerger.hidden = !enabled;
      standardDataEntryItems.forEach((item) => { item.hidden = enabled; });
      const studentCountField = studentCountInput?.closest("label");
      const questionCountField = questionCountInput?.closest("label");
      if (studentCountField) studentCountField.hidden = enabled;
      if (questionCountField) questionCountField.hidden = enabled;
      if (scoreTotal) scoreTotal.hidden = enabled;
      if (questionConfiguration) questionConfiguration.hidden = enabled;
      if (structureStatus) structureStatus.hidden = enabled;
      if (programDataStatus) programDataStatus.hidden = enabled || !programDataStatus.textContent;
      const scenarioGuidance = document.querySelector("[data-scenario-guidance]");
      if (scenarioGuidance) scenarioGuidance.hidden = enabled;

      const structureTitle = document.querySelector("#exam-structure-title");
      const structureDescription = structureTitle?.nextElementSibling;
      if (structureTitle) structureTitle.textContent = enabled ? "Genel Değerlendirme Türü" : "Soru, Puan ve Öğrenme Çıktısı Eşleştirmesi";
      if (structureDescription) structureDescription.textContent = enabled
        ? "Genel değerlendirme, aynı gruba ait üç MAHİR analiz raporunun doğrulanıp birleştirilmesiyle oluşturulur."
        : "Azami puan zorunludur. Öğrenme çıktısı biliniyorsa seçilir; bilinmiyorsa soru bazlı analiz yapılır.";

      if (enabled && profile) {
        document.querySelector("[data-general-weight-badge]").textContent = Object.values(profile.weights).map((weight) => `%${weight * 100}`).join(" · ");
        Object.entries(profile.weights).forEach(([component, weight]) => {
          const target = document.querySelector(`[data-general-report-weight="${component}"]`);
          if (target) target.textContent = `Genel sonuca etkisi: %${weight * 100}`;
        });
        refreshGeneralReportFiles();
      } else if (!enabled) {
        configureSourceMode(sourceMode);
      }
    };

    const updateComponentNote = () => {
      let component = assessmentComponent?.value || "written";
      const profileId = currentProfileId();
      const profile = profiles[profileId];
      const enabled = Boolean(profile);
      const generalMode = enabled && component === "general";
      if (languageAssessmentField) languageAssessmentField.hidden = !enabled;
      if (assessmentComponent && !enabled) {
        assessmentComponent.value = "written";
        component = "written";
      }
      updateExamSequenceOptions(component);
      updateGeneralReportMode(generalMode, profile);
      if (!componentWeightNote) return;
      componentWeightNote.hidden = !enabled;
      if (!enabled) {
        componentWeightNote.textContent = "";
      } else {
        componentWeightNote.textContent = component === "general"
          ? "Genel değerlendirme; aynı değerlendirme grubundaki yazılı, dinleme/izleme ve konuşma bileşenlerinden elde edilen öğrenme kanıtlarını, öğrenme çıktılarını ve alan becerilerini birlikte yorumlar. Üç bileşen tamamlanmadan kesinleştirilmez."
          : `${profile.title} değerlendirme sonucunda ${componentLabels[component]} %${profile.weights[component] * 100} ağırlığındadır. Her bileşen 100 puan üzerinden değerlendirilir.`;
      }
      applyComponentOutcomeFilter();
    };

    const outcomeOptionText = (outcome = {}) => [
      outcome.theme,
      outcome.parentCode,
      outcome.code,
      outcome.title
    ].filter(Boolean).join(" — ");

    const closeOutcomeCombobox = (combobox, { restoreFocus = false } = {}) => {
      if (!combobox) return;
      const trigger = combobox.querySelector("[data-outcome-trigger]");
      const listbox = combobox.querySelector("[data-outcome-listbox]");
      if (!trigger || !listbox || listbox.hidden) return;
      listbox.hidden = true;
      combobox.classList.remove("is-open", "opens-up");
      trigger.setAttribute("aria-expanded", "false");
      trigger.removeAttribute("aria-activedescendant");
      if (restoreFocus) trigger.focus();
    };

    const closeOtherOutcomeComboboxes = (current) => {
      document.querySelectorAll("[data-outcome-combobox].is-open").forEach((combobox) => {
        if (combobox !== current) closeOutcomeCombobox(combobox);
      });
    };

    const createOutcomeCombobox = (savedValues, rowIndex) => {
      const placeholderText = learningOutcomes.length
        ? "İsteğe bağlı — öğrenme çıktısı seçiniz"
        : "İsteğe bağlı — çıktı verisi bulunmuyor";
      const combobox = document.createElement("div");
      combobox.className = "outcome-combobox";
      combobox.dataset.outcomeCombobox = "";

      const nativeSelect = document.createElement("select");
      nativeSelect.className = "outcome-native-select";
      nativeSelect.dataset.questionOutcome = "";
      nativeSelect.multiple = true;
      nativeSelect.tabIndex = -1;
      nativeSelect.setAttribute("aria-hidden", "true");
      const savedIds = new Set((Array.isArray(savedValues) ? savedValues : [savedValues]).filter(Boolean));
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = placeholderText;
      placeholder.selected = savedIds.size === 0;
      nativeSelect.append(placeholder);

      const listboxId = `outcome-listbox-${rowIndex + 1}`;
      const trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "outcome-combobox-trigger";
      trigger.dataset.outcomeTrigger = "";
      trigger.setAttribute("role", "combobox");
      trigger.setAttribute("aria-haspopup", "listbox");
      trigger.setAttribute("aria-expanded", "false");
      trigger.setAttribute("aria-controls", listboxId);
      trigger.setAttribute("aria-label", `Soru ${rowIndex + 1} öğrenme çıktıları`);
      trigger.disabled = !learningOutcomes.length;

      const valueText = document.createElement("span");
      valueText.className = "outcome-combobox-value";
      valueText.dataset.outcomeValue = "";
      const arrow = document.createElement("span");
      arrow.className = "outcome-combobox-arrow";
      arrow.setAttribute("aria-hidden", "true");
      trigger.append(valueText, arrow);

      const listbox = document.createElement("div");
      listbox.id = listboxId;
      listbox.className = "outcome-combobox-listbox";
      listbox.dataset.outcomeListbox = "";
      listbox.setAttribute("role", "listbox");
      listbox.setAttribute("aria-multiselectable", "true");
      listbox.hidden = true;

      let activeIndex = -1;
      const options = [];

      const emptyOption = document.createElement("div");
      emptyOption.id = `${listboxId}-option-0`;
      emptyOption.className = "outcome-combobox-option";
      emptyOption.dataset.optionIndex = "0";
      emptyOption.setAttribute("role", "option");
      emptyOption.setAttribute("aria-selected", savedIds.size ? "false" : "true");
      emptyOption.textContent = learningOutcomes.length ? "Seçimleri temizle" : placeholderText;
      listbox.append(emptyOption);
      options.push(emptyOption);

      learningOutcomes.forEach((outcome, optionIndex) => {
        const optionText = outcomeOptionText(outcome);
        const nativeOption = document.createElement("option");
        nativeOption.value = outcome.id;
        nativeOption.textContent = optionText;
        nativeOption.selected = savedIds.has(outcome.id);
        nativeSelect.append(nativeOption);

        const option = document.createElement("div");
        option.id = `${listboxId}-option-${optionIndex + 1}`;
        option.className = "outcome-combobox-option";
        option.dataset.outcomeOption = outcome.id;
        option.dataset.optionIndex = String(optionIndex + 1);
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", savedIds.has(outcome.id) ? "true" : "false");
        option.textContent = optionText;
        listbox.append(option);
        options.push(option);
      });

      const selectedOutcomes = () => learningOutcomes.filter((outcome) => Array.from(nativeSelect.selectedOptions).some((option) => option.value === outcome.id));
      const refreshSelection = () => {
        const selected = selectedOutcomes();
        valueText.textContent = selected.length === 1
          ? outcomeOptionText(selected[0])
          : selected.length > 1
            ? `${selected.length} öğrenme çıktısı seçildi`
            : placeholderText;
        emptyOption.setAttribute("aria-selected", selected.length ? "false" : "true");
        options.slice(1).forEach((option, index) => {
          option.setAttribute("aria-selected", selected.some((outcome) => outcome.id === learningOutcomes[index]?.id) ? "true" : "false");
        });
      };
      refreshSelection();

      const setActiveOption = (nextIndex, { scroll = true } = {}) => {
        if (!options.length) return;
        activeIndex = Math.min(options.length - 1, Math.max(0, nextIndex));
        options.forEach((option, index) => option.classList.toggle("is-active", index === activeIndex));
        trigger.setAttribute("aria-activedescendant", options[activeIndex].id);
        if (scroll) options[activeIndex].scrollIntoView({ block: "nearest" });
      };

      const selectOption = (optionIndex) => {
        if (!options[optionIndex]) return;
        if (optionIndex === 0) {
          Array.from(nativeSelect.options).forEach((option) => { option.selected = false; });
        } else {
          const nativeOption = nativeSelect.options[optionIndex];
          if (nativeOption) nativeOption.selected = !nativeOption.selected;
        }
        refreshSelection();
        activeIndex = optionIndex;
        nativeSelect.dispatchEvent(new Event("input", { bubbles: true }));
        nativeSelect.dispatchEvent(new Event("change", { bubbles: true }));
      };

      const openCombobox = () => {
        if (!options.length || !listbox.hidden) return;
        closeOtherOutcomeComboboxes(combobox);
        listbox.hidden = false;
        combobox.classList.add("is-open");
        trigger.setAttribute("aria-expanded", "true");

        const firstEight = options.slice(0, 8);
        const eightOptionHeight = Math.ceil(firstEight.reduce((height, option) => height + option.getBoundingClientRect().height, 0) + 2);
        const triggerRect = trigger.getBoundingClientRect();
        const spaceBelow = window.innerHeight - triggerRect.bottom - 12;
        const spaceAbove = triggerRect.top - 12;
        const opensUp = spaceBelow < Math.min(eightOptionHeight, 280) && spaceAbove > spaceBelow;
        const availableSpace = Math.max(160, opensUp ? spaceAbove : spaceBelow);
        combobox.classList.toggle("opens-up", opensUp);
        listbox.style.maxHeight = `${Math.max(160, Math.min(eightOptionHeight, availableSpace))}px`;
        const currentSelectedIndex = learningOutcomes.findIndex((outcome) => Array.from(nativeSelect.selectedOptions).some((option) => option.value === outcome.id));
        setActiveOption(currentSelectedIndex >= 0 ? currentSelectedIndex + 1 : 0, { scroll: false });
        options[activeIndex]?.scrollIntoView({ block: "nearest" });
      };

      trigger.addEventListener("click", () => {
        if (listbox.hidden) openCombobox();
        else closeOutcomeCombobox(combobox);
      });

      trigger.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          const direction = event.key === "ArrowDown" ? 1 : -1;
          if (listbox.hidden) {
            openCombobox();
            if (!nativeSelect.selectedOptions.length && direction < 0) setActiveOption(options.length - 1);
          } else {
            setActiveOption(activeIndex < 0 ? (direction > 0 ? 0 : options.length - 1) : activeIndex + direction);
          }
        } else if (event.key === "Home" && !listbox.hidden) {
          event.preventDefault();
          setActiveOption(0);
        } else if (event.key === "End" && !listbox.hidden) {
          event.preventDefault();
          setActiveOption(options.length - 1);
        } else if ((event.key === "Enter" || event.key === " ") && !listbox.hidden) {
          event.preventDefault();
          selectOption(activeIndex);
        } else if ((event.key === "Enter" || event.key === " ") && listbox.hidden) {
          event.preventDefault();
          openCombobox();
        } else if (event.key === "Escape" && !listbox.hidden) {
          event.preventDefault();
          closeOutcomeCombobox(combobox, { restoreFocus: true });
        } else if (event.key === "Tab") {
          closeOutcomeCombobox(combobox);
        }
      });

      listbox.addEventListener("pointerdown", (event) => event.preventDefault());
      listbox.addEventListener("click", (event) => {
        const option = event.target.closest("[data-option-index]");
        if (option) selectOption(Number(option.dataset.optionIndex));
      });
      listbox.addEventListener("pointermove", (event) => {
        const option = event.target.closest("[data-option-index]");
        if (option) setActiveOption(Number(option.dataset.optionIndex), { scroll: false });
      });

      combobox.append(nativeSelect, trigger, listbox);
      return combobox;
    };

    const currentQuestionConfiguration = () => Array.from(questionConfiguration?.querySelectorAll("[data-question-config-row]") || []).map((row, index) => {
      const outcomeSelect = row.querySelector("[data-question-outcome]");
      const selected = Array.from(outcomeSelect?.selectedOptions || [])
        .map((option) => learningOutcomes.find((outcome) => outcome.id === option.value))
        .filter(Boolean);
      const weight = selected.length ? 1 / selected.length : 0;
      const outcomes = selected.map((outcome) => ({
        outcomeCode: outcome.code || "",
        outcomeDescription: outcome.title || "",
        outcomeTheme: outcome.theme || "",
        outcomeSkill: outcome.skill || "",
        parentOutcomeCode: outcome.parentCode || outcome.code || "",
        parentOutcomeDescription: outcome.parentTitle || outcome.title || "",
        outcomeKey: outcome.id || "",
        weight
      }));
      const primary = outcomes[0] || {};
      return {
        number: index + 1,
        maxScore: Number(row.querySelector("[data-question-score]")?.value || 0),
        outcomes,
        outcomeCode: primary.outcomeCode || "",
        outcomeDescription: primary.outcomeDescription || "",
        outcomeTheme: primary.outcomeTheme || "",
        outcomeSkill: primary.outcomeSkill || "",
        parentOutcomeCode: primary.parentOutcomeCode || "",
        parentOutcomeDescription: primary.parentOutcomeDescription || "",
        outcomeKey: primary.outcomeKey || ""
      };
    });

    const updateStructureStatus = () => {
      if ((assessmentComponent?.value || "written") === "general") return true;
      const questions = currentQuestionConfiguration();
      const total = questions.reduce((sum, question) => sum + question.maxScore, 0);
      if (scoreTotal) scoreTotal.textContent = `Toplam puan: ${total.toLocaleString("tr-TR")}`;
      const incomplete = questions.some((question) => question.maxScore <= 0);
      if (structureStatus) {
        structureStatus.textContent = incomplete
          ? "Her soru için sıfırdan büyük bir azami puan giriniz."
          : `${questions.length} soru ve ${total.toLocaleString("tr-TR")} toplam puan hazır. Öğrenme çıktısı seçilmeyen sorular soru bazında analiz edilir.`;
        structureStatus.classList.toggle("is-success", !incomplete);
        structureStatus.classList.toggle("is-error", incomplete);
      }
      return !incomplete;
    };

    const renderQuestionConfiguration = () => {
      if (!questionConfiguration || !questionCountInput) return;
      const count = Math.min(20, Math.max(1, Number(questionCountInput.value) || 1));
      const previous = currentQuestionConfiguration();
      questionCountInput.value = String(count);
      questionConfiguration.replaceChildren();
      for (let index = 0; index < count; index += 1) {
        const saved = previous[index] || {};
        const row = document.createElement("div");
        row.className = "question-configuration-row";
        row.dataset.questionConfigRow = "";
        const badge = document.createElement("span");
        badge.className = "question-number-badge";
        badge.textContent = `Soru ${index + 1}`;
        const scoreLabel = document.createElement("label");
        scoreLabel.textContent = "Azami Puan";
        const scoreInput = document.createElement("input");
        scoreInput.type = "number";
        scoreInput.min = "0.01";
        scoreInput.step = "0.01";
        scoreInput.required = true;
        scoreInput.value = saved.maxScore || "";
        scoreInput.dataset.questionScore = "";
        scoreLabel.append(scoreInput);
        const outcomeField = document.createElement("div");
        outcomeField.className = "outcome-combobox-field";
        outcomeField.hidden = !activeProgramId || (assessmentComponent?.value || "written") === "general";
        const outcomeCaption = document.createElement("span");
        outcomeCaption.className = "outcome-combobox-label";
        outcomeCaption.textContent = "Öğrenme Çıktıları";
        const savedOutcomeKeys = Array.isArray(saved.outcomes) && saved.outcomes.length
          ? saved.outcomes.map((outcome) => outcome.outcomeKey).filter(Boolean)
          : [saved.outcomeKey].filter(Boolean);
        const outcomeHelp = document.createElement("small");
        outcomeHelp.className = "outcome-combobox-help";
        outcomeHelp.textContent = "Birden fazla çıktı seçilebilir; soru puanı seçilen çıktılar arasında eşit paylaşılır.";
        outcomeField.append(outcomeCaption, createOutcomeCombobox(savedOutcomeKeys, index), outcomeHelp);
        row.append(badge, scoreLabel, outcomeField);
        questionConfiguration.append(row);
      }
      updateStructureStatus();
    };

    const loadLearningOutcomes = () => {
      const requestId = ++programRequestSequence;
      const program = currentProgram();
      activeProgramId = program?.id || "";
      programLearningOutcomes = [];
      learningOutcomes = [];
      if (!program) {
        setProgramStatus(
          currentCourseName() && currentGrade()
            ? "Bu derse ait öğretim programı ve öğrenme çıktıları henüz MAHİR’e tanımlanmamıştır. Soru ve puan bilgileriyle soru bazlı değerlendirmeye devam edebilirsiniz."
            : ""
        );
        renderQuestionConfiguration();
        return Promise.resolve();
      }
      setProgramStatus("Öğretim programı verileri yükleniyor.");
      return fetch(program.dataUrl)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Program verisi okunamadı.")))
      .then((payload) => {
        if (requestId !== programRequestSequence) return;
        programLearningOutcomes = Array.isArray(payload.learning_outcomes) ? payload.learning_outcomes : [];
        setProgramStatus("9. sınıf Türk Dili ve Edebiyatı öğretim programı verileri hazır.", "success");
        applyComponentOutcomeFilter();
        populateContextFields(structuredData?.exam || {});
      })
      .catch(() => {
        if (requestId !== programRequestSequence) return;
        activeProgramId = "";
        setProgramStatus("Öğretim programı verileri yüklenemedi. Öğrenme çıktısı seçmeden soru bazlı değerlendirmeye devam edebilirsiniz.", "error");
        renderQuestionConfiguration();
      });
    };

    const setStatus = (message, state = "") => {
      if (!statusMessage) return;
      statusMessage.textContent = message;
      statusMessage.classList.toggle("is-error", state === "error");
      statusMessage.classList.toggle("is-success", state === "success");
    };

    const showMessage = (message, state = "") => {
      const analysisMessage = document.querySelector("#analysis-screen .notification-message");
      setStatus(message, state);
      if (analysisMessage) analysisMessage.textContent = message;
    };

    const formatBytes = (bytes) => {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const getExtension = (file) => file.name.split(".").pop()?.toLowerCase() || "";

    const validateFile = (file) => {
      if (!allowedExtensions.includes(getExtension(file))) {
        return "Bu dosya türü desteklenmiyor. Word, PDF, Excel (.xlsx), JPG, PNG veya WEBP yükleyiniz.";
      }
      if (file.size > maxFileSize) {
        return "Dosya 20 MB sınırını aşıyor. Daha küçük bir dosya yükleyiniz.";
      }
      if (file.size === 0) {
        return "Dosya boş görünüyor. Lütfen başka bir dosya seçiniz.";
      }
      return "";
    };

    const clearPreviewUrls = () => {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      previewUrls = [];
    };

    const isSameFile = (a, b) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;

    const removeFileAt = (index) => {
      selectedFiles.splice(index, 1);
      renderFilesList();
    };

    const buildFileRow = (file, index) => {
      const item = document.createElement("article");
      item.className = "uploaded-file-card";

      const preview = document.createElement("div");
      preview.className = "file-preview";
      preview.setAttribute("aria-hidden", "true");
      const extension = getExtension(file);
      if (file.type.startsWith("image/")) {
        const url = URL.createObjectURL(file);
        previewUrls.push(url);
        const image = document.createElement("img");
        image.src = url;
        image.alt = "";
        preview.append(image);
      } else {
        const badge = document.createElement("span");
        badge.dataset.fileExtension = "";
        badge.textContent = extension.toUpperCase();
        preview.append(badge);
      }

      const details = document.createElement("div");
      details.className = "uploaded-file-details";
      const name = document.createElement("h3");
      name.textContent = file.name;
      const meta = document.createElement("p");
      const typeSpan = document.createElement("span");
      typeSpan.textContent = file.type || `${extension.toUpperCase()} belgesi`;
      meta.append(typeSpan, document.createTextNode(` · ${formatBytes(file.size)}`));
      details.append(name, meta);

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.className = "secondary-button remove-file-button";
      removeButton.textContent = "Dosyayı Kaldır";
      removeButton.addEventListener("click", () => removeFileAt(index));

      item.append(preview, details, removeButton);
      return item;
    };

    const renderFilesList = () => {
      clearPreviewUrls();
      if (filesList) {
        filesList.replaceChildren();
        selectedFiles.forEach((file, index) => filesList.append(buildFileRow(file, index)));
        filesList.toggleAttribute("hidden", selectedFiles.length === 0);
      }
      const hasFiles = selectedFiles.length > 0;
      readButton.disabled = !hasFiles;
      readButton.setAttribute("aria-disabled", String(!hasFiles));
      setStatus(
        hasFiles
          ? `${selectedFiles.length} dosya hazır. Okunan alanlar öğretmen onayına sunulacaktır.`
          : "Belirsiz okunan alanlar analizden önce öğretmen onayına sunulacaktır.",
        hasFiles ? "success" : ""
      );
    };

    const clearAllFiles = () => {
      selectedFiles = [];
      fileInput.value = "";
      renderFilesList();
    };

    // Uzak OCR işçisinin soğuk başlangıcı ölçülen sürenin %75-85'i (konteyner
    // açılışı + modelleri GPU'ya yükleme ~30-50 sn; asıl OCR yalnızca 7-12 sn).
    // Öğretmen dosyalarını seçer seçmez bu hazırlığı başlatıyoruz ki "Verileri
    // Oku"ya bastığında büyük ölçüde bitmiş olsun. Ateşle-unut: yanıtı
    // beklenmez, hatası yutulur - ısıtma başarısız olsa da yükleme eskisi gibi
    // (yalnızca daha yavaş) çalışır.
    // Tek seferlik değil, kısılmış: öğretmen aynı oturumda ikinci bir grup
    // yüklediğinde konteyner çoktan kapanmış olabilir, o yüzden yeniden
    // ısıtılabilmeli - ama her dosya seçiminde tekrar tekrar değil.
    const WARM_UP_THROTTLE_MS = 30000;
    const warmUpAt = {};
    const warmUp = (path) => {
      const now = Date.now();
      if (now - (warmUpAt[path] || 0) < WARM_UP_THROTTLE_MS) return;
      warmUpAt[path] = now;
      fetch(path).catch(() => {});
    };
    const warmUpOcr = () => warmUp("/mahir-ocr-warmup");
    // RAG'in soğuk başlangıcı daha da uzun (ölçülen ~110 sn: konteyner +
    // bge-m3 + vLLM/Qwen2.5-7B) ve bugün tam "Onayla ve Analiz Et"e basıldığı
    // anda ödeniyor. Doğrulama ekranı açılırken ısıtıyoruz: öğretmen puanları
    // incelerken hazırlık biter, rag_service.py'deki scaledown_window=300 de
    // konteyneri o inceleme boyunca ayakta tutar.
    const warmUpRag = () => warmUp("/mahir-rag-warmup");

    // --- Süre ölçümü ---
    //
    // İki uzun işlem (belge okuma ve analiz) sessizdi: öğretmen butona basıp
    // bekliyor, ne kadar beklediği hiçbir yere yazılmıyordu. Ölçüm kırılımlı,
    // çünkü tek bir toplam asıl soruyu yanıtlamıyor - aynı iş soğuk
    // konteynerde 160 sn, sıcakta 15,7 sn sürebiliyor (ölçüldü).
    //
    // Biçimlendirme MAHIRReportExport.durationText'ten geliyor ("16,7 sn" /
    // "340 ms", tr-TR); ikinci bir biçimlendirici yazmaya gerek yok.
    const durationText = (ms) => window.MAHIRReportExport?.durationText?.(ms) ?? `${Math.round(ms)} ms`;

    // Isıtmanın üzerinden geçen süre: "neden 45 sn sürdü"nün cevabı çoğu zaman
    // burada. Kısaysa uzak konteyner hâlâ soğuk demektir.
    const sinceWarmUp = (path) => (warmUpAt[path] ? durationText(Date.now() - warmUpAt[path]) : "ısıtılmadı");

    const startTimer = (label) => {
      const began = performance.now();
      return (fields = {}) => {
        const elapsed = performance.now() - began;
        console.info(`[MAHIR][süre] ${label} toplam ${durationText(elapsed)}`, fields);
        return durationText(elapsed);
      };
    };

    const selectFiles = (files) => {
      const incoming = Array.from(files || []);
      if (!incoming.length) return;

      const accumulate = fileInput.multiple;
      const existing = accumulate ? selectedFiles : [];
      const newFiles = incoming.filter((file) => !existing.some((current) => isSameFile(current, file)));
      const merged = [...existing, ...newFiles];

      const error = merged.length > 10 ? "Bir görsel grubunda en fazla 10 dosya seçebilirsiniz." : newFiles.map(validateFile).find(Boolean);
      if (error) {
        fileInput.value = "";
        setStatus(error, "error");
        return;
      }

      selectedFiles = merged;
      fileInput.value = "";
      renderFilesList();
      warmUpOcr();
    };

    const configureSourceMode = (mode) => {
      sourceMode = mode;
      clearAllFiles();
      const title = document.querySelector("[data-upload-title]");
      const description = document.querySelector("[data-upload-description]");
      const rules = document.querySelector("[data-upload-rules]");
      const label = document.querySelector("[data-file-select-label]");
      const templateCard = document.querySelector("[data-template-card]");
      const ocrGuidance = document.querySelector("[data-ocr-guidance]");
      const dropzone = document.querySelector("[data-upload-dropzone]");
      if ((assessmentComponent?.value || "written") === "general") {
        standardDataEntryItems.forEach((item) => { item.hidden = true; });
        return;
      }
      templateCard?.toggleAttribute("hidden", mode !== "template");
      ocrGuidance?.toggleAttribute("hidden", mode !== "images");
      dropzone?.toggleAttribute("hidden", mode === "manual");
      if (mode === "manual") {
        readButton.disabled = false;
        readButton.setAttribute("aria-disabled", "false");
        readButton.textContent = "Elle Giriş Tablosunu Aç";
        setStatus("Soru sayınıza göre boş öğrenci tablosu hazırlanacak; verileri öğretmen olarak doğrudan girebilirsiniz.", "success");
        return;
      }
      const images = mode === "images";
      fileInput.multiple = images;
      fileInput.accept = images ? ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" : ".pdf,.doc,.docx,.xlsx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
      if (title) title.textContent = images ? "Soru bazlı puan çizelgelerini yükleyin" : "Veri evrakını yükleyin";
      if (description) description.textContent = images ? "Her öğrenci için üç satırlı Soru Bazlı Puan Çizelgesinin fotoğrafını seçin. Bir grupta en fazla 10 görsel yükleyebilirsiniz." : "MAHİR şablonunu veya öğretmen tarafından hazırlanmış Word, PDF ya da Excel tablosunu seçiniz.";
      if (rules) rules.textContent = images ? "JPG, PNG veya WEBP · En fazla 10 görsel · Dosya başına 20 MB" : "Word, PDF veya Excel (.xlsx) · En fazla 20 MB";
      if (label) label.textContent = images ? "Çizelge Fotoğraflarını Seç" : "Dosya Seç";
      readButton.textContent = images ? "Çizelgeleri Oku ve Kontrol Et" : "Verileri Oku ve Kontrol Et";
    };

    const SAFE_REPORT_INTRO = "Bu rapor; öğretmen tarafından onaylanan sınav verileri, seçilen sınav türü ve ilişkilendirilen öğrenme çıktıları temel alınarak hazırlanmıştır.";
    const REPORT_UNAVAILABLE_MESSAGE = "Analiz özeti oluşturulamadı. Verileri ve servis bağlantısını kontrol ederek yeniden deneyiniz.";

    const showReportIntro = (text = SAFE_REPORT_INTRO) => {
      const reportTarget = document.querySelector("[data-report-intro]");
      if (!reportTarget) return;
      reportTarget.textContent = text;
    };

    const editableCell = (value, label, type = "text", field = "") => {
      const cell = document.createElement("td");
      const input = document.createElement("input");
      input.className = "validation-input";
      input.type = type;
      input.value = value ?? "";
      input.setAttribute("aria-label", label);
      if (field) input.dataset.validationField = field;
      if (type === "number") input.step = "0.01";
      cell.append(input);
      return cell;
    };

    const refreshResolvedOcrWarnings = () => {
      document.querySelectorAll("[data-ocr-failure-source]").forEach((item) => {
        const source = item.dataset.ocrFailureSource;
        const matchingRows = Array.from(document.querySelectorAll("[data-student-row]"))
          .filter((row) => row.dataset.sourceFile === source);
        const completed = matchingRows.length > 0 && matchingRows.every((row) =>
          Array.from(row.querySelectorAll("input")).every((input) => usefulValue(input.value))
        );
        item.textContent = completed
          ? `${source}: OCR okuyamadı; veri öğretmen tarafından tamamlandı.`
          : item.dataset.originalWarning;
        item.classList.toggle("is-resolved", completed);
      });
    };

    const setValidationStudentCountEditorOpen = (open) => {
      if (!validationStudentCountEditor) return;
      validationStudentCountEditor.hidden = !open;
      document.querySelector("[data-edit-validation-student-count]")?.toggleAttribute("hidden", open);
      if (open && validationStudentCountEditorInput) {
        validationStudentCountEditorInput.value = studentCountInput?.value || "";
        validationStudentCountEditorInput.focus();
        validationStudentCountEditorInput.select();
      }
    };

    const refreshValidationStudentCountStatus = () => {
      if (finalReviewMode || validationStudentCountControl?.hidden) return;
      const expected = Math.max(1, Number(studentCountInput?.value) || 1);
      const saved = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      const current = document.querySelectorAll("[data-student-row]").length;
      const projected = saved + current;
      if (validationExpectedCount) validationExpectedCount.textContent = String(expected);
      if (validationStudentCountEditorInput) validationStudentCountEditorInput.value = String(expected);
      if (validationStudentCountStatus) {
        validationStudentCountStatus.textContent = projected === expected
          ? `Mevcut kayıtlarla ${projected}/${expected} öğrenciye ulaşılıyor.`
          : projected > expected
            ? `Mevcut kayıtlar beklenen sayıyı ${projected - expected} öğrenci aşıyor. Fazla kaydı çıkarabilir veya beklenen sayıyı düzenleyebilirsiniz.`
            : `Mevcut kayıtlarla ${projected}/${expected} öğrenciye ulaşılıyor; ${expected - projected} kayıt daha eklenebilir.`;
        validationStudentCountStatus.classList.toggle("is-error", projected > expected);
        validationStudentCountStatus.classList.toggle("is-success", projected === expected);
      }
      const approvalMessage = document.querySelector("[data-approval-message]");
      if (approvalMessage) approvalMessage.textContent = `Bu gruptaki ${current} öğrenci kaydı henüz kaydedilmedi. Grup kaydedildiğinde toplam ${projected}/${expected} öğrenciye ulaşılacaktır.`;
    };

    const renderValidationData = (data, options = {}) => {
      if (!data) return;
      finalReviewMode = Boolean(options.finalReview);
      structuredData = data;
      populateContextFields(data.exam || {});
      const contextData = collectContextData();
      const detectedDocumentType = inferDocumentType(data);
      structuredData.exam = { ...(data.exam || {}), ...contextData, documentType: detectedDocumentType };
      reportRuntime.structuredData = structuredData;
      reportRuntime.exam = structuredData.exam;
      reportRuntime.analysis = null;
      reportRuntime.trace = null;
      const questionBody = document.querySelector("[data-validation-questions]");
      const studentHead = document.querySelector("[data-validation-student-head]");
      const studentBody = document.querySelector("[data-validation-students]");
      const examSummary = document.querySelector("[data-validation-exam-summary]");
      const warningList = document.querySelector("[data-validation-warnings]");
      const documentReadGuidance = document.querySelector("[data-document-read-guidance]");
      const questions = currentQuestionConfiguration();
      const expectedStudentCount = Math.max(1, Number(studentCountInput?.value) || 1);
      if (validationStudentCountControl) validationStudentCountControl.hidden = Boolean(options.finalReview);
      if (validationExpectedCount) validationExpectedCount.textContent = String(expectedStudentCount);
      setValidationStudentCountEditorOpen(false);
      studentRecordUndo?.setAttribute("hidden", "");
      lastRemovedStudentRecord = null;
      const privacyWarnings = [];
      const parsedStudents = (data.students || []).map((student, index) => {
        const detectedTckn = looksLikeTckn(student.studentNo);
        if (detectedTckn) {
          privacyWarnings.push(`${usefulValue(student.sourceFile) || `${index + 1}. satır`}: KVKK uyarısı — T.C. kimlik numarası algılandı ve öğrenci analiz verisinden çıkarıldı.`);
        }
        return ({
        rowNumber: student.rowNumber || index + 1,
        studentNo: detectedTckn ? "" : usefulValue(student.studentNo),
        technicalId: student.technicalId || `Ö-${String(savedGroups.reduce((sum, group) => sum + group.students.length, 0) + index + 1).padStart(3, "0")}`,
        sourceFile: usefulValue(student.sourceFile),
        scores: Array.from({ length: questions.length }, (_, scoreIndex) => student.scores?.[scoreIndex] ?? null),
        totalScore: student.totalScore ?? null
        });
      });
      const templateCouldNotBeRead = sourceMode === "template" && !hasDetectedMahirTemplate(data);
      const targetRowCount = options.finalReview
        ? parsedStudents.length
        : sourceMode === "images"
          ? Math.max(parsedStudents.length, selectedFiles.length || 1)
          : Math.max(parsedStudents.length, expectedStudentCount);
      const students = [...parsedStudents];
      const savedStudentCount = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      while (students.length < targetRowCount) {
        const index = students.length;
        students.push({
          rowNumber: index + 1,
          studentNo: "",
          technicalId: `Ö-${String(savedStudentCount + index + 1).padStart(3, "0")}`,
          sourceFile: sourceMode === "images" ? selectedFiles[index]?.name || "" : "",
          scores: Array(questions.length).fill(null),
          totalScore: null
        });
      }

      if (documentReadGuidance) {
        documentReadGuidance.hidden = !templateCouldNotBeRead;
        documentReadGuidance.classList.toggle("is-error", templateCouldNotBeRead);
        documentReadGuidance.textContent = templateCouldNotBeRead
          ? `Yüklenen belgede MAHİR şablonuna uygun öğrenci tablosu bulunamadı. Öğrenci numaraları ve soru puanları otomatik okunamadı. Dosya yükleme aşamasına dönerek doğru belgeyi seçebilir veya aşağıda açılan ${expectedStudentCount} boş satırı elle tamamlayabilirsiniz.`
          : "";
      }
      structuredData = {
        ...data,
        exam: { ...(data.exam || {}), ...contextData, documentType: detectedDocumentType },
        questions,
        students,
        summary: { ...(data.summary || {}), questionCount: questions.length, studentCount: students.length }
      };
      reportRuntime.structuredData = structuredData;
      reportRuntime.exam = structuredData.exam;

      questionBody?.replaceChildren();
      questions.forEach((question) => {
        const row = document.createElement("tr");
        const outcomeSummary = (question.outcomes || []).length
          ? question.outcomes.map((outcome) => `${outcome.outcomeCode}${outcome.outcomeDescription ? ` — ${outcome.outcomeDescription}` : ""}`).join("; ")
          : `${question.outcomeCode}${question.outcomeDescription ? ` — ${question.outcomeDescription}` : ""}`;
        [question.number, question.maxScore, outcomeSummary].forEach((value) => {
          const cell = document.createElement("td");
          cell.className = "readonly-summary";
          cell.textContent = value;
          row.append(cell);
        });
        questionBody?.append(row);
      });

      if (studentHead) {
        const row = document.createElement("tr");
        const showSourceFile = sourceMode === "images" && students.some((student) => usefulValue(student.sourceFile));
        [
          ...(showSourceFile ? ["Kaynak Görsel"] : []),
          "Okul Numarası",
          ...questions.map((question) => `S${question.number}`),
          "Toplam",
          ...(!options.finalReview ? ["İşlem"] : [])
        ]
          .forEach((label) => {
            const header = document.createElement("th");
            header.scope = "col";
            header.textContent = label;
            row.append(header);
          });
        studentHead.replaceChildren(row);
      }

      studentBody?.replaceChildren();
      students.forEach((student, studentIndex) => {
        const row = document.createElement("tr");
        row.dataset.studentRow = "";
        row.dataset.rowNumber = student.rowNumber || studentIndex + 1;
        row.dataset.technicalId = student.technicalId || `Ö-${String(studentIndex + 1).padStart(3, "0")}`;
        row.dataset.sourceFile = student.sourceFile || "";
        if (sourceMode === "images" && students.some((item) => usefulValue(item.sourceFile))) {
          const sourceCell = document.createElement("td");
          sourceCell.className = "readonly-summary";
          sourceCell.textContent = student.sourceFile || "Kaynak görsel belirlenemedi";
          row.append(sourceCell);
        }
        row.append(editableCell(student.studentNo, `${student.rowNumber || studentIndex + 1}. satır okul numarası`, "text", "studentNo"));
        questions.forEach((question, index) => {
          row.append(editableCell(student.scores?.[index], `${student.rowNumber || studentIndex + 1}. satır S${question.number} puanı`, "number", "score"));
        });
        row.append(editableCell(student.totalScore, `${student.rowNumber || studentIndex + 1}. satır toplam puanı`, "number", "totalScore"));
        if (!options.finalReview) {
          const actionCell = document.createElement("td");
          actionCell.className = "student-record-action-cell";
          const removeButton = document.createElement("button");
          removeButton.type = "button";
          removeButton.className = "student-record-remove-button";
          removeButton.dataset.removeStudentRecord = "";
          const recordLabel = student.studentNo || student.sourceFile || `${studentIndex + 1}. satır`;
          removeButton.textContent = "× Kaydı çıkar";
          removeButton.setAttribute("aria-label", `${recordLabel} öğrenci kaydını bu gruptan çıkar`);
          removeButton.title = "Bu öğrenci kaydını gruptan çıkar";
          actionCell.append(removeButton);
          row.append(actionCell);
        }
        studentBody?.append(row);
      });

      if (examSummary) {
        const exam = data.exam || {};
        const identity = [exam.schoolName, exam.course, exam.classSection].filter(Boolean).join(" · ");
        examSummary.textContent = `${documentTypeLabel(detectedDocumentType)} · ${identity || "Bağlam bilgileri öğretmen tarafından tamamlanacak"} — ${questions.length} soru, bu grupta ${students.length} öğrenci kaydı.`;
      }

      if (warningList) {
        warningList.replaceChildren();
        const relevantWarnings = [...(data.warnings || []), ...privacyWarnings].filter((warning) => !/soru|öğrenme çıktısı|azami puan/i.test(warning));
        const configuredTotal = questions.reduce((sum, question) => sum + Number(question.maxScore || 0), 0);
        const documentTotal = Number(data.exam?.totalMaxScore);
        if (Number.isFinite(documentTotal) && documentTotal > 0 && Math.abs(documentTotal - configuredTotal) > 0.01) {
          relevantWarnings.push(`Belgedeki toplam puan (${documentTotal}) ile tanımlanan soru puanları toplamı (${configuredTotal}) eşleşmiyor.`);
        }
        const warnings = relevantWarnings.length
          ? relevantWarnings
          : ["Veriler öğretmen kontrolüne sunulmuştur. Kaydetmeden önce otomatik kontroller çalıştırılacaktır."];
        warnings.forEach((warning) => {
          const item = document.createElement("li");
          item.textContent = warning;
          const ocrFailure = String(warning).match(/^(.+?):\s*(?:Görselde tablo tespit edilemedi|Görseldeki tablo satırından öğrenci bilgisi okunamadı)\.?$/i);
          if (ocrFailure) {
            item.dataset.ocrFailureSource = ocrFailure[1];
            item.dataset.originalWarning = warning;
          }
          warningList.append(item);
        });
        refreshResolvedOcrWarnings();
      }
      document.querySelector("[data-post-save-actions]")?.setAttribute("hidden", "");
      document.querySelector("[data-final-data-review]")?.toggleAttribute("hidden", !options.finalReview);
      if (saveGroupButton) saveGroupButton.hidden = Boolean(options.finalReview);
      if (returnToUploadButton) returnToUploadButton.hidden = Boolean(options.finalReview);
      renderSavedGroups();
      if (!options.finalReview) refreshValidationStudentCountStatus();
    };

    const numberValue = (input) => {
      const value = input?.value.trim().replace(",", ".");
      return value === "" ? null : Number(value);
    };

    const collectApprovedData = () => {
      const questions = structuredData?.questions || [];
      const students = Array.from(document.querySelectorAll("[data-student-row]")).map((row) => ({
        rowNumber: Number(row.dataset.rowNumber),
        studentNo: row.querySelector('[data-validation-field="studentNo"]')?.value.trim() || "",
        technicalId: row.dataset.technicalId,
        sourceFile: row.dataset.sourceFile || "",
        scores: Array.from(row.querySelectorAll('[data-validation-field="score"]')).map(numberValue),
        totalScore: numberValue(row.querySelector('[data-validation-field="totalScore"]'))
      }));
      const componentType = assessmentComponent?.value || "written";
      const profileId = currentProfileId();
      if (componentType === "general") {
        return {
          exam: {
            ...(structuredData?.exam || {}),
            ...collectContextData(),
            courseName: currentCourseName(),
            course: currentCourseName(),
            grade: currentGrade(),
            programId: currentProgram()?.id || null,
            componentType,
            examType: componentLabels[componentType] || "Genel Değerlendirme",
            weightingProfileId: profileId,
            assessmentScope: "language-composite"
          },
          questions,
          students,
          componentAnalyses: reportRuntime.languageComponentAnalyses || {}
        };
      }
      return {
        exam: {
          ...(structuredData?.exam || {}),
          ...collectContextData(),
          courseName: currentCourseName(),
          course: currentCourseName(),
          grade: currentGrade(),
          programId: currentProgram()?.id || null,
          componentType: profileId ? componentType : "written",
          examType: componentLabels[profileId ? componentType : "written"],
          weightingProfileId: profileId,
          assessmentScope: componentType === "general" ? "language-composite" : "component"
        },
        questions,
        students
      };
    };

    const renderCurrentStudents = (students, warnings = structuredData?.warnings || []) => {
      renderValidationData({
        ...(structuredData || {}),
        exam: { ...(structuredData?.exam || {}), ...collectContextData() },
        questions: structuredData?.questions || currentQuestionConfiguration(),
        students,
        warnings,
        summary: { ...(structuredData?.summary || {}), studentCount: students.length }
      });
    };

    const removeStudentRecord = (row) => {
      if (!row || finalReviewMode || saveGroupButton?.hidden) return;
      const rows = Array.from(document.querySelectorAll("[data-student-row]"));
      const index = rows.indexOf(row);
      if (index < 0) return;
      const students = collectApprovedData().students || [];
      const [student] = students.splice(index, 1);
      if (!student) return;
      const sourceFile = row.dataset.sourceFile || student.sourceFile || "";
      const originalWarnings = [...(structuredData?.warnings || [])];
      let removedFile = null;
      let removedFileIndex = -1;
      if (sourceFile && !students.some((item) => item.sourceFile === sourceFile)) {
        removedFileIndex = selectedFiles.findIndex((file) => file.name === sourceFile);
        if (removedFileIndex >= 0) [removedFile] = selectedFiles.splice(removedFileIndex, 1);
      }
      const remainingWarnings = sourceFile
        ? originalWarnings.filter((warning) => !String(warning).startsWith(`${sourceFile}:`))
        : originalWarnings;
      lastRemovedStudentRecord = { student, index, sourceFile, removedFile, removedFileIndex, originalWarnings };
      renderFilesList();
      renderCurrentStudents(students, remainingWarnings);
      if (studentRecordUndoMessage) {
        studentRecordUndoMessage.textContent = `${sourceFile || student.studentNo || `${index + 1}. satır`} kaynaklı öğrenci kaydı bu gruptan çıkarıldı.`;
      }
      studentRecordUndo?.removeAttribute("hidden");
      lastRemovedStudentRecord = { student, index, sourceFile, removedFile, removedFileIndex, originalWarnings };
      clearValidationErrors();
      refreshValidationStudentCountStatus();
      invalidateAnalysisAfterApprovedDataEdit();
    };

    const undoStudentRecordRemoval = () => {
      if (!lastRemovedStudentRecord || finalReviewMode) return;
      const removed = lastRemovedStudentRecord;
      const students = collectApprovedData().students || [];
      students.splice(Math.min(removed.index, students.length), 0, removed.student);
      if (removed.removedFile) {
        const fileIndex = removed.removedFileIndex < 0 ? selectedFiles.length : Math.min(removed.removedFileIndex, selectedFiles.length);
        selectedFiles.splice(fileIndex, 0, removed.removedFile);
      }
      renderFilesList();
      renderCurrentStudents(students, removed.originalWarnings);
      lastRemovedStudentRecord = null;
      studentRecordUndo?.setAttribute("hidden", "");
      clearValidationErrors();
      refreshValidationStudentCountStatus();
    };

    const applyValidationStudentCount = () => {
      const value = Number(validationStudentCountEditorInput?.value);
      if (!Number.isInteger(value) || value < 1 || value > 100) {
        validationStudentCountEditorInput?.classList.add("is-invalid");
        validationStudentCountStatus.textContent = "Öğrenci sayısı 1 ile 100 arasında bir tam sayı olmalıdır.";
        validationStudentCountStatus.classList.add("is-error");
        return;
      }
      validationStudentCountEditorInput?.classList.remove("is-invalid");
      if (studentCountInput) studentCountInput.value = String(value);
      setValidationStudentCountEditorOpen(false);
      renderSavedGroups();
      const students = collectApprovedData().students || [];
      const errors = validateStudents(students, true);
      const saved = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      if (saved + students.length > value) {
        errors.push({ message: `Bu grup kaydedilirse öğrenci sayısı ${saved + students.length} olacak; güncellenen toplam ${value}.`, input: null });
      }
      if (errors.length) showValidationErrors(errors);
      else clearValidationErrors();
      refreshValidationStudentCountStatus();
      invalidateAnalysisAfterApprovedDataEdit();
    };

    const renderSavedGroups = () => {
      const list = document.querySelector("[data-saved-groups-list]");
      const summary = document.querySelector("[data-saved-groups-summary]");
      const total = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      const expected = Math.max(1, Number(studentCountInput?.value) || 1);
      if (summary) summary.textContent = savedGroups.length
        ? `${savedGroups.length} grup içinde ${total}/${expected} öğrenci kaydı korunuyor.`
        : "Henüz kaydedilmiş öğrenci grubu bulunmuyor.";
      document.querySelector("[data-saved-groups-card]")?.toggleAttribute("hidden", savedGroups.length === 0);
      list?.replaceChildren();
      savedGroups.forEach((group, index) => {
        const item = document.createElement("li");
        item.textContent = `${index + 1}. Grup — ${group.students.length} öğrenci`;
        list?.append(item);
      });
    };

    const clearValidationErrors = () => {
      document.querySelectorAll(".validation-input.is-invalid").forEach((input) => input.classList.remove("is-invalid"));
      const card = document.querySelector("[data-validation-errors-card]");
      card?.setAttribute("hidden", "");
      document.querySelector("[data-validation-errors]")?.replaceChildren();
    };

    const showValidationErrors = (errors) => {
      const card = document.querySelector("[data-validation-errors-card]");
      const summary = document.querySelector("[data-validation-errors-summary]");
      const list = document.querySelector("[data-validation-errors]");
      if (!card || !summary || !list) return;
      list.replaceChildren();
      errors.forEach((error) => {
        error.input?.classList.add("is-invalid");
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "validation-error-link";
        button.textContent = error.message;
        button.addEventListener("click", () => {
          error.input?.focus({ preventScroll: false });
          error.input?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
        item.append(button);
        list.append(item);
      });
      summary.textContent = `${errors.length} sorun bulundu. Bütün sorunları düzeltip tek seferde yeniden kontrol ediniz.`;
      card.removeAttribute("hidden");
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      const approvalMessage = document.querySelector("[data-approval-message]");
      if (approvalMessage) approvalMessage.textContent = `Bu grupta düzeltilmesi gereken ${errors.length} sorun bulundu.`;
    };

    const validateStudents = (students, includeSavedDuplicates = true) => {
      clearValidationErrors();
      const errors = [];
      const questions = structuredData?.questions || [];
      const savedNumbers = new Set(includeSavedDuplicates
        ? savedGroups.flatMap((group) => group.students.map((student) => student.studentNo))
        : []);
      const currentNumbers = new Map();
      const rows = Array.from(document.querySelectorAll("[data-student-row]"));
      students.forEach((student, index) => {
        const row = rows[index];
        const noInput = row?.querySelector('[data-validation-field="studentNo"]');
        const scoreInputs = Array.from(row?.querySelectorAll('[data-validation-field="score"]') || []);
        const totalInput = row?.querySelector('[data-validation-field="totalScore"]');
        const rowLabel = `${index + 1}. satır`;
        if (!usefulValue(student.studentNo)) {
          errors.push({ message: `${rowLabel} — Okul numarası boş veya okunamadı.`, input: noInput });
        } else {
          if (savedNumbers.has(student.studentNo)) errors.push({ message: `${rowLabel} — ${student.studentNo} okul numarası daha önce kaydedilmiş bir grupta bulunuyor.`, input: noInput });
          if (currentNumbers.has(student.studentNo)) errors.push({ message: `${rowLabel} — ${student.studentNo} okul numarası bu grupta yineleniyor.`, input: noInput });
          currentNumbers.set(student.studentNo, index);
        }
        student.scores.forEach((score, scoreIndex) => {
          const maxScore = Number(questions[scoreIndex]?.maxScore || 0);
          const input = scoreInputs[scoreIndex];
          if (!Number.isFinite(score)) errors.push({ message: `${rowLabel} — S${scoreIndex + 1} puanı boş veya okunamadı.`, input });
          else if (score < 0 || score > maxScore) errors.push({ message: `${rowLabel} — S${scoreIndex + 1} puanı 0 ile ${maxScore} arasında olmalıdır; girilen değer ${score}.`, input });
        });
        const calculated = student.scores.every(Number.isFinite) ? student.scores.reduce((sum, score) => sum + score, 0) : null;
        if (!Number.isFinite(student.totalScore)) errors.push({ message: `${rowLabel} — Toplam puan boş veya okunamadı.`, input: totalInput });
        else if (calculated !== null && Math.abs(student.totalScore - calculated) > 0.01) {
          errors.push({ message: `${rowLabel} — Toplam puan ${calculated} olmalıdır; girilen değer ${student.totalScore}.`, input: totalInput });
        }
      });
      return errors;
    };

    const currentStudents = () => collectApprovedData().students || [];

    const saveCurrentGroup = () => {
      if (finalReviewMode) return;
      const students = currentStudents();
      const errors = validateStudents(students, true);
      const expected = Math.max(1, Number(studentCountInput?.value) || 1);
      const alreadySaved = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      if (alreadySaved + students.length > expected) {
        errors.push({ message: `Bu grup kaydedilirse öğrenci sayısı ${alreadySaved + students.length} olacak; başlangıçta belirtilen toplam ${expected}.`, input: null });
      }
      if (errors.length) {
        document.querySelector("[data-post-save-actions]")?.setAttribute("hidden", "");
        document.querySelector("[data-final-data-review]")?.setAttribute("hidden", "");
        showValidationErrors(errors);
        return;
      }
      savedGroups.push({
        number: currentGroupNumber,
        students: students.map((student) => ({ ...student })),
        sourceMode,
        documentType: structuredData?.exam?.documentType || inferDocumentType(structuredData),
        // Düzeltme sayısı YALNIZ burada yakalanabilir: students yukarıda
        // DOM'dan (öğretmenin düzelttiği hâliyle) geldi, structuredData ise
        // hâlâ makinenin okuduğu özgün değerleri tutuyor - ve startNewGroup()
        // birazdan structuredData'yı null yapıp o özgün değerleri yok edecek.
        corrections: window.MAHIRScoreCorrections?.diffScores(structuredData?.students, students)
      });
      currentGroupNumber += 1;
      const total = savedGroups.reduce((sum, group) => sum + group.students.length, 0);
      renderSavedGroups();
      clearValidationErrors();
      if (saveGroupButton) saveGroupButton.hidden = true;
      if (returnToUploadButton) returnToUploadButton.hidden = true;
      if (validationStudentCountControl) validationStudentCountControl.hidden = true;
      document.querySelectorAll("[data-remove-student-record]").forEach((button) => { button.hidden = true; });
      studentRecordUndo?.setAttribute("hidden", "");
      if (total === expected) {
        showFinalReview();
        return;
      }
      const postSave = document.querySelector("[data-post-save-actions]");
      const postSummary = document.querySelector("[data-post-save-summary]");
      postSave?.removeAttribute("hidden");
      if (postSummary) postSummary.textContent = `${total}/${expected} öğrenci verisi başarıyla kaydedildi. Önceki kayıtlar korunarak yeni görsel grubunu ekleyebilirsiniz.`;
      if (addGroupButton) addGroupButton.hidden = sourceMode !== "images" || total >= expected;
      const approvalMessage = document.querySelector("[data-approval-message]");
      if (approvalMessage) approvalMessage.textContent = `Toplam ${total}/${expected} öğrenci kaydı korunuyor. Kalan ${expected - total} öğrenci yeni bir grup olarak kaydedildiğinde analiz onayı gösterilecektir.`;
    };

    const startNewGroup = () => {
      finalReviewMode = false;
      structuredData = null;
      clearAllFiles();
      clearValidationErrors();
      document.querySelector("[data-post-save-actions]")?.setAttribute("hidden", "");
      document.querySelector("[data-final-data-review]")?.setAttribute("hidden", "");
      if (saveGroupButton) saveGroupButton.hidden = false;
      if (returnToUploadButton) returnToUploadButton.hidden = false;
      screenManager.showScreen("data-entry-screen");
      setStatus(`Kaydedilen ${savedGroups.length} grup korunuyor. Önceki grubun görselleri temizlendi; ${currentGroupNumber}. grup için yeni görselleri seçiniz.`, "success");
    };

    const returnToUpload = () => {
      finalReviewMode = false;
      structuredData = null;
      clearValidationErrors();
      document.querySelector("[data-post-save-actions]")?.setAttribute("hidden", "");
      document.querySelector("[data-final-data-review]")?.setAttribute("hidden", "");
      screenManager.showScreen("data-entry-screen");
      setStatus("Yüklediğiniz dosya korunuyor. Dosyayı kaldırıp başka bir belge seçebilir veya aynı belgeyi yeniden okutabilirsiniz.");
    };

    const invalidateAnalysisAfterApprovedDataEdit = () => {
      if (!finalReviewMode || !reportRuntime.analysis) return;
      reportRuntime.analysis = null;
      // İz, analizle birlikte geçersizleşir: eski koşunun ajan kaydını yeni
      // (henüz üretilmemiş) bir analizin yanında göstermek öğretmeni yanıltır.
      reportRuntime.trace = null;
      reportRuntime.report = null;
      screenManager.revokeDataApproval();
      document.dispatchEvent(new CustomEvent("mahir:report-reset"));
      const approvalMessage = document.querySelector("[data-approval-message]");
      if (approvalMessage) {
        approvalMessage.textContent = "Onaylanan öğrenci verileri değiştirildi. Eski analiz ve rapor geçersiz sayıldı; verileri yeniden onaylayıp analize geçiniz.";
      }
    };

    const showFinalReview = () => {
      const expected = Math.max(1, Number(studentCountInput?.value) || 1);
      const allStudents = savedGroups.flatMap((group) => group.students);
      if (allStudents.length !== expected) {
        showValidationErrors([{ message: `Veri girişi tamamlanamaz: ${allStudents.length}/${expected} öğrenci kaydı bulunuyor.`, input: null }]);
        return;
      }
      const merged = {
        ...(structuredData || {}),
        exam: { ...(structuredData?.exam || {}), ...collectContextData() },
        questions: currentQuestionConfiguration(),
        students: allStudents,
        warnings: [],
        summary: { ...(structuredData?.summary || {}), questionCount: currentQuestionConfiguration().length, studentCount: allStudents.length }
      };
      renderValidationData(merged, { finalReview: true });
      const summary = document.querySelector("[data-final-data-summary]");
      if (summary) summary.textContent = `${savedGroups.length} kaydedilmiş grup birleştirildi: ${allStudents.length} öğrenci, ${merged.questions.length} soru. Sınav ve belge bilgileri rapor aşamasında kontrol edilecektir.`;
      const approvalMessage = document.querySelector("[data-approval-message]");
      if (approvalMessage) approvalMessage.textContent = "Tüm verileri gözden geçiriniz. Açık onay verilmeden analiz başlamaz.";
    };

    // Analiz ekranındaki "Analiz Özeti" listesini beş ajanın GERÇEK koşusuyla
    // değiştirir. İz gelmediğinde (kaydedilmiş eski çalışma, genel dil
    // değerlendirmesi) listeye hiç dokunulmaz - index.html'deki sabit metin
    // geçerli bir geri çekilme yolu olarak kalır.
    const renderAgentTrace = (trace) => {
      const list = document.querySelector("[data-agent-trace]");
      const agents = Array.isArray(trace?.agents) ? trace.agents : [];
      if (!list || !agents.length) return;
      const format = window.MAHIRReportExport;
      list.replaceChildren();
      agents.forEach((entry) => {
        const item = document.createElement("li");
        // Süre ve LLM sayısı ayrı bir <span>'de: öğretmenin okuduğu cümle ile
        // teknik ölçüm birbirine karışmasın.
        const label = document.createElement("strong");
        label.textContent = entry.label || entry.agent;
        const task = document.createTextNode(` — ${format?.agentTaskText?.(entry) || ""}`);
        const meta = document.createElement("span");
        meta.className = "agent-trace-meta";
        meta.textContent = [
          format?.durationText?.(entry.durationMs),
          entry.llmCalls?.length ? `${entry.llmCalls.length} dil modeli çağrısı` : "",
          entry.failed || entry.skipped ? format?.agentStatusText?.(entry) : ""
        ].filter(Boolean).join(" · ");
        item.dataset.agent = entry.agent;
        if (entry.failed) item.dataset.agentFailed = "true";
        if (entry.skipped) item.dataset.agentSkipped = "true";
        item.append(label, task, meta);
        list.append(item);
      });

      // Ortak dil modeli turu ayrı satırda: süre ajanlara bölüştürülmüyor
      // (dokuz istem tek istekte çözülüyor, paylaştırmak uydurma olurdu).
      const round = trace.llmRound;
      if (round?.promptCount) {
        const item = document.createElement("li");
        item.dataset.agent = "llm-turu";
        const label = document.createElement("strong");
        label.textContent = "Dil modeli turu (ortak)";
        const meta = document.createElement("span");
        meta.className = "agent-trace-meta";
        meta.textContent = [
          format?.durationText?.(round.durationMs),
          round.ok ? "" : "Tamamlanamadı"
        ].filter(Boolean).join(" · ");
        item.append(label, document.createTextNode(` — ${round.promptCount} istem tek istekte çözüldü`), meta);
        list.append(item);
      }
    };

    const renderAnalysis = (analysis, trace) => {
      const reportScreen = document.querySelector("#report-screen");
      if (reportScreen?.dataset.reportLocked === "true") return;
      reportRuntime.analysis = analysis;
      // İz raporun İÇİNDE değil yanında taşınıyor; rapor sözleşmesi teknik
      // alanlarla kirlenmesin diye (bkz. backend `analyze_approved_data_traced`).
      reportRuntime.trace = trace || null;
      renderAgentTrace(trace);
      window.MAHIRReportExport?.syncOutputHeader(reportScreen);
    };

    const mergeGeneralReports = () => {
      if (!mergeGeneralReportsButton || Object.values(generalReportFiles).some((file) => !file)) return;
      const formData = new FormData();
      Object.entries(generalReportFiles).forEach(([component, file]) => {
        formData.append("analysis-report", file, `${component}-${file.name}`);
      });
      mergeGeneralReportsButton.disabled = true;
      mergeGeneralReportsButton.setAttribute("aria-disabled", "true");
      mergeGeneralReportsButton.textContent = "Raporlar Doğrulanıyor…";
      setGeneralReportStatus("Raporların ders, sınıf/şube, dönem ve bileşen bilgileri doğrulanıyor.");

      const mergeQuery = new URLSearchParams({ course: currentCourseName(), grade: currentGrade() });
      fetch(`/mahir-merge-reports?${mergeQuery}`, { method: "POST", body: formData })
        .then((response) => response.json().catch(() => ({})).then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
          if (!response.ok) throw new Error(payload.message || "Analiz raporları birleştirilemedi.");
          const exam = payload.exam || {};
          const analysis = payload.analysis || {};
          structuredData = {
            exam,
            questions: [],
            students: [],
            warnings: [],
            summary: analysis.summary || {}
          };
          reportRuntime.structuredData = structuredData;
          reportRuntime.exam = exam;
          reportRuntime.analysis = analysis;
          populateContextFields(exam);
          renderAnalysis(analysis);
          screenManager.approveData();

          const analysisProgress = document.querySelector("#analysis-screen .analysis-progress");
          const analysisTitle = analysisProgress?.querySelector("h3");
          const analysisSteps = analysisProgress?.querySelector("ol");
          if (analysisTitle) analysisTitle.textContent = "Genel Değerlendirme Özeti";
          if (analysisSteps) {
            analysisSteps.replaceChildren();
            [
              "Yazılı sınav analiz raporu doğrulandı.",
              "Dinleme/izleme sınavı analiz raporu doğrulandı.",
              "Konuşma sınavı analiz raporu doğrulandı.",
              "Ders, sınıf/şube, dönem ve okul bilgileri eşleştirildi.",
              "Bileşenler dersin resmî ağırlıklarına göre birleştirildi.",
              "Öğrenme çıktıları kendi bileşenlerindeki gerçekleşme düzeyleri korunarak raporlandı."
            ].forEach((text) => {
              const item = document.createElement("li");
              item.textContent = text;
              analysisSteps.append(item);
            });
          }
          const returnToApproved = document.querySelector("[data-return-to-approved-data]");
          if (returnToApproved) returnToApproved.hidden = true;
          setGeneralReportStatus(payload.message, "success");
          screenManager.showScreen("analysis-screen");
        })
        .catch((error) => setGeneralReportStatus(error.message, "error"))
        .finally(() => {
          mergeGeneralReportsButton.disabled = false;
          mergeGeneralReportsButton.setAttribute("aria-disabled", "false");
          mergeGeneralReportsButton.textContent = "Raporları Doğrula ve Birleştir";
        });
    };

    const analyzeApprovedData = () => {
      const approvalButton = confirmFinalButton;
      if (!structuredData || !approvalButton) return;
      const approvedData = collectApprovedData();
      const studentErrors = validateStudents(approvedData.students || [], false);
      const errors = [...studentErrors];
      if (errors.length) {
        showValidationErrors(errors);
        return;
      }
      const analysisPayload = {
        ...approvedData,
        // "Bu %68 nereden geldi?" cevabının parçası: kaç puan hücresinin
        // öğretmen tarafından düzeltildiği. Grup bazında kaydedilen sayımlara,
        // son inceleme ekranında yapılan EK düzenlemeler eklenir - bu aşamada
        // structuredData zaten birleştirilmiş (düzeltilmiş) değerleri tuttuğu
        // için buradaki fark yalnızca sonradan yapılanları verir, mükerrer
        // sayım olmaz.
        correctedCells: (window.MAHIRScoreCorrections?.mergeCorrections(
          ...savedGroups.map((group) => group.corrections),
          window.MAHIRScoreCorrections.diffScores(structuredData?.students, approvedData.students)
        ) || {}).byQuestionIndex || {},
        exam: approvedData.exam,
        questions: approvedData.questions,
        students: (approvedData.students || []).map((student, index) => ({
          rowNumber: student.rowNumber,
          studentRef: student.technicalId || `Ö-${String(index + 1).padStart(3, "0")}`,
          scores: student.scores,
          totalScore: student.totalScore
        })),
        ...(approvedData.componentAnalyses ? { componentAnalyses: approvedData.componentAnalyses } : {}),
        privacyContext: {
          studentIdentityMode: "session-pseudonymized",
          excludedFields: ["fullName", "tckn", "studentNo", "sourceFile"]
        }
      };
      approvalButton.disabled = true;
      approvalButton.textContent = "Analiz Başlatılıyor…";
      showMessage("Öğretmen onaylı veriler analiz motoruna aktarılıyor.");

      // Ölçüm doğrulamalardan sonra, istek gitmeden hemen önce başlıyor.
      const stopTimer = startTimer("Analiz");

      fetch("/mahir-analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(analysisPayload)
      })
        .then((response) => response.json().catch(() => ({})).then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
          if (!response.ok) throw new Error(payload.message || "Onaylanan veriler analiz edilemedi.");
          const analysis = payload.analysis || {};
          const selectedComponent = assessmentComponent?.value || "written";
          if (selectedComponent !== "general" && currentProfileId()) {
            reportRuntime.languageComponentAnalyses = reportRuntime.languageComponentAnalyses || {};
            reportRuntime.languageComponentAnalyses[selectedComponent] = analysis;
          }
          renderAnalysis(analysis, payload.trace);
          screenManager.approveData();
          screenManager.showScreen("analysis-screen");
          // Kırılım izden geliyor (Faz 4): `totalMs` sunucudaki toplam,
          // `llmRound` ortak dil modeli turu. Tarayıcı toplamı ≥ rota ≥ tur
          // olmalı; aradaki farklar ağ ve JSON taşıması.
          const round = payload.trace?.llmRound || {};
          const elapsed = stopTimer({
            rota: durationText(payload.trace?.totalMs ?? 0),
            llmTuru: round.promptCount ? durationText(round.durationMs) : "yok",
            istem: round.promptCount || 0,
            ajan: payload.trace?.agents?.length || 0,
            isitmadanBeri: sinceWarmUp("/mahir-rag-warmup")
          });
          showMessage(`Analiz tamamlandı. Öğrenme kanıtlarına dayalı değerlendirme raporu görüntülenmeye hazırdır. (${elapsed})`, "success");
        })
        .catch((error) => {
          const approvalMessage = document.querySelector("[data-approval-message]");
          if (approvalMessage) {
            approvalMessage.textContent = error.message;
            approvalMessage.focus({ preventScroll: true });
          }
          const elapsed = stopTimer({ hata: error.message, isitmadanBeri: sinceWarmUp("/mahir-rag-warmup") });
          showMessage(`${error.message} (${elapsed})`, "error");
        })
        .finally(() => {
          approvalButton.disabled = false;
          approvalButton.textContent = "Verileri Onayla ve Analize Geç";
        });
    };

    const uploadSelectedFile = () => {
      const selectedSource = document.querySelector('[data-source-option]:checked')?.value;
      if (selectedSource && selectedSource !== sourceMode) sourceMode = selectedSource;
      if (!updateStructureStatus()) {
        setStatus("Sınav yapısındaki eksik alanları tamamlayınız.", "error");
        return;
      }
      if (sourceMode === "manual") {
        renderValidationData({ exam: {}, students: [], warnings: ["Veriler elle girilecektir."], summary: {} });
        screenManager.showScreen("validation-screen");
        warmUpRag();
        return;
      }
      if (!selectedFiles.length) return;
      document.dispatchEvent(new CustomEvent("mahir:report-reset"));
      readButton.disabled = true;
      readButton.setAttribute("aria-disabled", "true");
      readButton.textContent = selectedFiles.length > 1 ? `${selectedFiles.length} Belge Okunuyor…` : "Belge Okunuyor…";

      // Dosya başına ayrı istek DEĞİL, hepsi tek istekte: her istek uzak OCR
      // işçisinde ayrı bir konteyner açtırıyordu, yani N fotoğraf = N kez
      // (ölçülen) 30-50 sn'lik model yükleme. Hem yerel alıcı hem uzak işçi bir
      // istekteki görsel grubunu tek çağrıda işliyor (file_receiver.py
      // run_image_group_ocr / ocr_worker.py _run_image_group_ocr) ve ikisinin de
      // sınırı 10 dosya - arayüzün kendi sınırıyla aynı.
      const uploadFileGroup = (files) => {
        const formData = new FormData();
        files.forEach((file) => formData.append("exam-file", file));
        return fetch("/mahir-upload", { method: "POST", body: formData })
          .then((response) => response.json().catch(() => ({})).then((payload) => {
            if (!response.ok) throw new Error(payload.message || `${files.length} belge işlenemedi.`);
            return payload;
          }));
      };

      // Ölçüm burada başlıyor - doğrulamalardan SONRA, istek gitmeden hemen
      // önce: eksik alan uyarısıyla dönülen yol bir "OCR işlemi" değil.
      const stopTimer = startTimer("OCR");
      const uploadedBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);

      // Tek elemanlı liste: aşağıdaki birleştirme mantığı olduğu gibi kalıyor,
      // böylece yanıt sözleşmesi ve renderValidationData girdisi değişmiyor.
      uploadFileGroup(selectedFiles).then((payload) => [payload])
        .then((payloads) => {
          const mergedData = payloads.reduce((merged, payload, payloadIndex) => {
            const data = payload.structuredData || {};
            const sourceFile = payload.fileName || selectedFiles[payloadIndex]?.name || "";
            return {
              ...merged,
              exam: { ...(merged.exam || {}), ...(data.exam || {}) },
              students: [
                ...(merged.students || []),
                ...(data.students || []).map((student) => ({ ...student, sourceFile: student.sourceFile || sourceFile }))
              ],
              warnings: [...(merged.warnings || []), ...(data.warnings || [])],
              summary: { ...(merged.summary || {}), ...(data.summary || {}) }
            };
          }, { exam: {}, students: [], warnings: [], summary: {} });
          const message = payloads.map((payload) => payload.message).filter(Boolean).join(" ") || `${selectedFiles.length} belge başarıyla işlendi.`;
          window.clearInterval(progressTimer);
          renderValidationData(mergedData.students.length || Object.keys(mergedData.exam).length ? mergedData : {
            exam: {},
            students: [],
            warnings: ["MAHİR belge alanlarını otomatik olarak okuyamadı. Okul numaralarını ve puanları kontrol ekranında tamamlayınız."],
            summary: {}
          });
          showReportIntro();
          screenManager.showScreen("validation-screen");
          warmUpRag();
          console.info("[MAHIR] Belge grubu backend alıcısına gönderildi.", { fileCount: selectedFiles.length, studentCount: mergedData.students.length });
          const elapsed = stopTimer({
            dosya: selectedFiles.length,
            boyut: formatBytes(uploadedBytes),
            ogrenci: mergedData.students.length,
            isitmadanBeri: sinceWarmUp("/mahir-ocr-warmup")
          });
          showMessage(`${message} (${elapsed})`, "success");
        })
        .catch((error) => {
          window.clearInterval(progressTimer);
          console.warn("[MAHIR] Dosya backend alıcısına gönderilemedi.", error);
          // Hata yolu da ölçülüyor: "45 sn sonra patladı" bilgisi, "45 sn
          // sürdü" kadar değerli - zaman aşımını yavaşlıktan ayıran şey bu.
          const elapsed = stopTimer({
            dosya: selectedFiles.length,
            boyut: formatBytes(uploadedBytes),
            hata: error.message,
            isitmadanBeri: sinceWarmUp("/mahir-ocr-warmup")
          });
          showMessage(`Belge okuma servisine ulaşılamadı. Prototip sunucusunu çalıştırıp yeniden deneyiniz. (${elapsed})`, "error");
          showReportIntro(REPORT_UNAVAILABLE_MESSAGE);
        })
        .finally(() => {
          readButton.disabled = false;
          readButton.setAttribute("aria-disabled", "false");
          readButton.textContent = "Verileri Oku ve Kontrol Et";
        });
    };

    fileInput.addEventListener("change", () => {
      if (fileInput.files?.length) selectFiles(fileInput.files);
    });

    readButton.addEventListener("click", uploadSelectedFile);
    document.querySelectorAll("[data-source-option]").forEach((option) => option.addEventListener("change", () => configureSourceMode(option.value)));
    questionCountInput?.addEventListener("input", renderQuestionConfiguration);
    questionConfiguration?.addEventListener("input", updateStructureStatus);
    questionConfiguration?.addEventListener("change", updateStructureStatus);
    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest("[data-outcome-combobox]")) closeOtherOutcomeComboboxes(null);
    });
    assessmentComponent?.addEventListener("change", updateComponentNote);
    generalReportInputs.forEach((input) => input.addEventListener("change", () => {
      const component = input.dataset.generalReportFile;
      const file = input.files?.[0] || null;
      generalReportFiles[component] = file;
      const status = document.querySelector(`[data-general-report-file-status="${component}"]`);
      if (status) status.textContent = file ? file.name : "Rapor seçilmedi.";
      refreshGeneralReportFiles();
    }));
    mergeGeneralReportsButton?.addEventListener("click", mergeGeneralReports);
    document.addEventListener("mahir:preparation-context-changed", () => {
      updateComponentNote();
      loadLearningOutcomes();
      populateContextFields(structuredData?.exam || {});
    });
    contextInputs().forEach((input) => input.addEventListener("input", () => {
      input.classList.remove("is-auto-filled", "is-invalid");
      input.dataset.valueSource = "teacher";
      refreshContextStatus();
      if (structuredData) {
        structuredData.exam = { ...(structuredData.exam || {}), ...collectContextData() };
        reportRuntime.structuredData = structuredData;
        reportRuntime.exam = structuredData.exam;
        if (reportRuntime.analysis) {
          window.MAHIRReportExport?.syncOutputHeader(document.querySelector("#report-screen"));
          document.dispatchEvent(new CustomEvent("mahir:report-reset"));
        }
      }
    }));
    saveGroupButton?.addEventListener("click", saveCurrentGroup);
    addGroupButton?.addEventListener("click", startNewGroup);
    returnToUploadButton?.addEventListener("click", returnToUpload);
    confirmFinalButton?.addEventListener("click", analyzeApprovedData);
    document.querySelector("[data-edit-validation-student-count]")?.addEventListener("click", () => setValidationStudentCountEditorOpen(true));
    document.querySelector("[data-cancel-validation-student-count]")?.addEventListener("click", () => setValidationStudentCountEditorOpen(false));
    document.querySelector("[data-apply-validation-student-count]")?.addEventListener("click", applyValidationStudentCount);
    validationStudentCountEditorInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applyValidationStudentCount();
      } else if (event.key === "Escape") {
        event.preventDefault();
        setValidationStudentCountEditorOpen(false);
      }
    });
    document.querySelector("[data-validation-students]")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-remove-student-record]");
      if (button) removeStudentRecord(button.closest("[data-student-row]"));
    });
    document.querySelector("[data-undo-student-record]")?.addEventListener("click", undoStudentRecordRemoval);
    document.querySelector("[data-validation-students]")?.addEventListener("input", () => {
      invalidateAnalysisAfterApprovedDataEdit();
      refreshResolvedOcrWarnings();
    });
    document.querySelector('[data-target-screen="report-screen"]')?.addEventListener("click", () => {
      populateContextFields(structuredData?.exam || {});
      refreshContextStatus();
      window.MAHIRReportExport?.syncOutputHeader(document.querySelector("#report-screen"));
    });
    configureSourceMode(document.querySelector('[data-source-option]:checked')?.value || "images");
    updateComponentNote();
    loadLearningOutcomes();
    populateContextFields();

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone?.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      dropzone?.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    });

    dropzone?.addEventListener("drop", (event) => {
      if (event.dataTransfer?.files?.length) selectFiles(event.dataTransfer.files);
    });
  };

  return { init };
})();

const reportApprovalManager = (() => {
  let approvalInput;
  let wordButton;
  let downloadButton;
  let reportScreen;
  let outputMessage;
  let returnToAnalysisButton;

  const actionButtons = () => [wordButton, downloadButton].filter(Boolean);

  const setOutputMessage = (message = "", state = "") => {
    if (!outputMessage) return;
    outputMessage.textContent = message;
    outputMessage.hidden = !message;
    outputMessage.classList.toggle("is-error", state === "error");
    outputMessage.classList.toggle("is-success", state === "success");
  };

  const setButtonsEnabled = (enabled) => {
    actionButtons().forEach((button) => {
      button.disabled = !enabled;
      button.setAttribute("aria-disabled", String(!enabled));
    });
  };

  const syncAndValidateOutput = () => {
    if (!window.MAHIRReportExport?.syncOutputHeader) {
      setOutputMessage("Rapor çıktı modeli yüklenemedi.", "error");
      return false;
    }
    const model = window.MAHIRReportExport.syncOutputHeader(reportScreen);
    if (!model?.validation?.valid) {
      setOutputMessage(model?.validation?.message || "Rapor çıktısı için gerekli bilgiler tamamlanmalıdır.", "error");
      return false;
    }
    setOutputMessage("Rapor çıktıları etkinleştirildi. Word veya PDF seçeneklerini kullanabilirsiniz.", "success");
    return true;
  };

  const setApproved = (isApproved) => {
    if (!reportScreen) return;
    reportScreen.dataset.reportLocked = String(isApproved);
    reportScreen.querySelectorAll("article, aside").forEach((section) => {
      section.dataset.reportLocked = String(isApproved);
    });
    if (returnToAnalysisButton) {
      returnToAnalysisButton.disabled = isApproved;
      returnToAnalysisButton.setAttribute("aria-disabled", String(isApproved));
    }

    if (!isApproved) {
      setButtonsEnabled(false);
      setOutputMessage();
      return;
    }

    setButtonsEnabled(syncAndValidateOutput());
  };

  const resetApproval = () => {
    if (approvalInput) approvalInput.checked = false;
    setApproved(false);
  };

  const downloadApprovedWord = async () => {
    if (!approvalInput?.checked || wordButton?.disabled || !syncAndValidateOutput()) return;
    if (!window.MAHIRDocxExporter?.downloadReportDocx) {
      console.error("[MAHIR] Word üretici yüklenemedi.");
      return;
    }

    const originalText = wordButton.textContent;
    wordButton.disabled = true;
    wordButton.setAttribute("aria-disabled", "true");
    wordButton.textContent = "Word Hazırlanıyor…";

    try {
      await window.MAHIRDocxExporter.downloadReportDocx(reportScreen, {
        filename: window.MAHIRReportExport.getDownloadFilename("docx")
      });
    } catch (error) {
      console.error("[MAHIR] Word dosyası oluşturulamadı.", error);
      window.alert?.(error.message || "Word dosyası oluşturulamadı. Lütfen raporu kontrol edip yeniden deneyiniz.");
    } finally {
      wordButton.textContent = originalText;
      setApproved(approvalInput.checked);
    }
  };

  const downloadApprovedReport = async () => {
    if (!approvalInput?.checked || downloadButton?.disabled || !syncAndValidateOutput()) return;
    if (!window.MAHIRPdfExporter?.downloadReportPdf) {
      console.error("[MAHIR] PDF üretici yüklenemedi.");
      return;
    }

    const originalText = downloadButton.textContent;
    downloadButton.disabled = true;
    downloadButton.setAttribute("aria-disabled", "true");
    downloadButton.textContent = "PDF Hazırlanıyor…";

    try {
      await window.MAHIRPdfExporter.downloadReportPdf(reportScreen, {
        filename: window.MAHIRReportExport.getDownloadFilename("pdf")
      });
    } catch (error) {
      console.error("[MAHIR] PDF oluşturulamadı.", error);
      window.alert?.(error.message || "PDF oluşturulamadı. Lütfen raporu kontrol edip yeniden deneyiniz.");
    } finally {
      downloadButton.textContent = originalText;
      setApproved(approvalInput.checked);
    }
  };

  const init = () => {
    reportScreen = document.querySelector("#report-screen");
    approvalInput = document.querySelector("[data-final-report-approval]");
    wordButton = document.querySelector("[data-download-approved-word]");
    downloadButton = document.querySelector("[data-download-approved-pdf]");
    outputMessage = document.querySelector("[data-output-validation-message]");
    returnToAnalysisButton = document.querySelector("[data-return-to-analysis]");
    if (!reportScreen || !approvalInput || !wordButton || !downloadButton) return;

    resetApproval();
    approvalInput.addEventListener("change", () => setApproved(approvalInput.checked));
    wordButton.addEventListener("click", downloadApprovedWord);
    downloadButton.addEventListener("click", downloadApprovedReport);
    document.addEventListener("mahir:report-reset", resetApproval);
  };

  return { init };
})();
document.addEventListener("DOMContentLoaded", () => {
  preparationManager.init();
  screenManager.init();
  fileUploadBridge.init();
  reportApprovalManager.init();
});
