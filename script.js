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
    studentNo: `${100 + order}`,
    fullName: order === 1 ? "Ayşe Yılmaz" : "Mehmet Kaya",
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
    monitoringPlan: ["Bir sonraki sınavda aynı kazanım izlenir."]
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
    monitoringPlan: ["Bir sonraki sınavda aynı kazanım izlenir."],
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
      name: "MeasurementOutput", description: "Sınıf, soru, kazanım istatistikleri ve dağılımlar.",
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
      ["101", "Ayşe Yılmaz", "8", "15"],
      ["102", "Mehmet Kaya", "7", "13"]
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
      createStudent("101", "Ayşe Yılmaz", { q1: "A", q2: "B" }, 15),
      createStudent("102", "Mehmet Kaya", { q1: "A", q2: "C" }, 13)
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
        createStudent("101", "Ayşe Yılmaz", { q1: "A", q2: "B" }, 15),
        createStudent("102", "Mehmet Kaya", { q1: "A", q2: "C" }, 13)
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
        studentNo: "101",
        fullName: "Ayşe Yılmaz",
        answers: Object.fromEntries(questions.map((question, index) => [question.id, index % 2 === 0 ? "A" : "B"])),
        totalScore: 88,
        confidence: 0.9
      },
      {
        studentNo: "102",
        fullName: "Mehmet Kaya",
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
    }
  };
})();


const fileUploadBridge = (() => {
  const progressTexts = ["✓ Dosya alındı", "✓ Belge okunuyor", "✓ CED oluşturuluyor", "✓ Program eşleştiriliyor", "✓ Ölçme analizi yapılıyor", "✓ Pedagojik analiz yapılıyor", "✓ Rapor hazırlanıyor", "✓ Tamamlandı"];
  const maxFileSize = 20 * 1024 * 1024;
  const allowedExtensions = ["pdf", "doc", "docx", "jpg", "jpeg", "png", "webp"];

  const init = () => {
    const fileInput = document.querySelector("#exam-file");
    const dropzone = document.querySelector("[data-upload-dropzone]");
    const fileCard = document.querySelector("[data-uploaded-file-card]");
    const filePreview = document.querySelector("[data-file-preview]");
    const fileName = document.querySelector("[data-file-name]");
    const fileType = document.querySelector("[data-file-type]");
    const fileSize = document.querySelector("[data-file-size]");
    const fileExtension = document.querySelector("[data-file-extension]");
    const removeButton = document.querySelector("[data-remove-file]");
    const readButton = document.querySelector("[data-read-document]");
    const statusMessage = document.querySelector("[data-upload-status]");

    if (!fileInput || !readButton || typeof FormData === "undefined" || typeof fetch === "undefined") {
      return;
    }

    let selectedFile = null;
    let structuredData = null;
    let previewUrl = null;
    let progressTimer;

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
        return "Bu dosya türü desteklenmiyor. Word, PDF, JPG, PNG veya WEBP yükleyiniz.";
      }
      if (file.size > maxFileSize) {
        return "Dosya 20 MB sınırını aşıyor. Daha küçük bir dosya yükleyiniz.";
      }
      if (file.size === 0) {
        return "Dosya boş görünüyor. Lütfen başka bir dosya seçiniz.";
      }
      return "";
    };

    const clearPreviewUrl = () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
    };

    const clearFile = () => {
      selectedFile = null;
      fileInput.value = "";
      clearPreviewUrl();
      fileCard?.setAttribute("hidden", "");
      readButton.disabled = true;
      readButton.setAttribute("aria-disabled", "true");
      setStatus("Öğrenci T.C. kimlik numarası yüklemeyiniz. Belirsiz okunan alanlar analizden önce öğretmen onayına sunulacaktır.");
    };

    const renderPreview = (file) => {
      if (!filePreview) return;
      clearPreviewUrl();
      filePreview.replaceChildren();
      const extension = getExtension(file);

      if (file.type.startsWith("image/")) {
        previewUrl = URL.createObjectURL(file);
        const image = document.createElement("img");
        image.src = previewUrl;
        image.alt = "";
        filePreview.append(image);
        return;
      }

      const badge = document.createElement("span");
      badge.dataset.fileExtension = "";
      badge.textContent = extension.toUpperCase();
      filePreview.append(badge);
    };

    const selectFile = (file) => {
      const error = validateFile(file);
      if (error) {
        clearFile();
        setStatus(error, "error");
        return;
      }

      selectedFile = file;
      if (fileName) fileName.textContent = file.name;
      if (fileType) fileType.textContent = file.type || `${getExtension(file).toUpperCase()} belgesi`;
      if (fileSize) fileSize.textContent = formatBytes(file.size);
      if (fileExtension) fileExtension.textContent = getExtension(file).toUpperCase();
      renderPreview(file);
      fileCard?.removeAttribute("hidden");
      readButton.disabled = false;
      readButton.setAttribute("aria-disabled", "false");
      setStatus("Dosya hazır. “Verileri Oku ve Kontrol Et” düğmesiyle öğretmen onay ekranına geçebilirsiniz.", "success");
    };

    const showProgressStep = (activeIndex) => {
      const list = document.querySelector("#analysis-screen .analysis-progress ol");
      if (!list) return;
      while (list.children.length < progressTexts.length) list.append(document.createElement("li"));
      Array.from(list.children).forEach((item, index) => {
        item.textContent = index <= activeIndex ? progressTexts[index] : progressTexts[index].replace("✓ ", "");
      });
    };

    const showReport = (text) => {
      const reportTarget = document.querySelector("#report-screen .summary-card p");
      if (!reportTarget) return;
      reportTarget.textContent = text;
      reportTarget.style.whiteSpace = "pre-line";
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

    const renderValidationData = (data) => {
      if (!data) return;
      structuredData = data;
      const questionBody = document.querySelector("[data-validation-questions]");
      const studentHead = document.querySelector("[data-validation-student-head]");
      const studentBody = document.querySelector("[data-validation-students]");
      const examSummary = document.querySelector("[data-validation-exam-summary]");
      const warningList = document.querySelector("[data-validation-warnings]");
      const questions = data.questions || [];

      questionBody?.replaceChildren();
      questions.forEach((question) => {
        const row = document.createElement("tr");
        row.dataset.questionRow = "";
        row.append(
          editableCell(question.number, `${question.number}. soru numarası`, "number", "number"),
          editableCell(question.maxScore, `${question.number}. soru azami puanı`, "number", "maxScore"),
          editableCell(
            question.outcomeCode,
            `${question.number}. soru öğrenme çıktısı kodu`,
            "text",
            "outcomeCode"
          )
        );
        questionBody?.append(row);
      });

      if (studentHead) {
        const row = document.createElement("tr");
        ["Öğrenci No", "Ad Soyad", ...questions.map((question) => `S${question.number}`), "Toplam", "Katılım"]
          .forEach((label) => {
            const header = document.createElement("th");
            header.scope = "col";
            header.textContent = label;
            row.append(header);
          });
        studentHead.replaceChildren(row);
      }

      studentBody?.replaceChildren();
      (data.students || []).forEach((student) => {
        const row = document.createElement("tr");
        row.dataset.studentRow = "";
        row.dataset.rowNumber = student.rowNumber;
        row.append(
          editableCell(student.studentNo, `${student.fullName || student.rowNumber} okul numarası`, "text", "studentNo"),
          editableCell(student.fullName, `${student.rowNumber}. öğrenci adı soyadı`, "text", "fullName")
        );
        questions.forEach((question, index) => {
          row.append(editableCell(student.scores?.[index], `${student.fullName || student.rowNumber} S${question.number} puanı`, "number", "score"));
        });
        row.append(
          editableCell(student.totalScore, `${student.fullName || student.rowNumber} toplam puanı`, "number", "totalScore"),
          editableCell(student.attendance, `${student.fullName || student.rowNumber} katılım durumu`, "text", "attendance")
        );
        studentBody?.append(row);
      });

      if (examSummary) {
        const exam = data.exam || {};
        const identity = [exam.schoolName, exam.course, exam.classSection].filter(Boolean).join(" · ");
        examSummary.textContent = `${identity || "Sınav bilgileri eksik"} — ${data.summary?.questionCount || 0} soru, ${data.summary?.studentCount || 0} öğrenci satırı okundu.`;
      }

      if (warningList) {
        warningList.replaceChildren();
        const warnings = data.warnings?.length ? data.warnings : ["Belge yapısında otomatik kontrol uyarısı bulunmadı."];
        warnings.forEach((warning) => {
          const item = document.createElement("li");
          item.textContent = warning;
          warningList.append(item);
        });
      }
    };

    const numberValue = (input) => {
      const value = input?.value.trim().replace(",", ".");
      return value === "" ? null : Number(value);
    };

    const collectApprovedData = () => {
      const questions = Array.from(document.querySelectorAll("[data-question-row]")).map((row) => ({
        number: numberValue(row.querySelector('[data-validation-field="number"]')),
        maxScore: numberValue(row.querySelector('[data-validation-field="maxScore"]')),
        outcomeCode: row.querySelector('[data-validation-field="outcomeCode"]')?.value.trim() || ""
      }));
      const students = Array.from(document.querySelectorAll("[data-student-row]")).map((row) => ({
        rowNumber: Number(row.dataset.rowNumber),
        studentNo: row.querySelector('[data-validation-field="studentNo"]')?.value.trim() || "",
        fullName: row.querySelector('[data-validation-field="fullName"]')?.value.trim() || "",
        scores: Array.from(row.querySelectorAll('[data-validation-field="score"]')).map(numberValue),
        totalScore: numberValue(row.querySelector('[data-validation-field="totalScore"]')),
        attendance: row.querySelector('[data-validation-field="attendance"]')?.value.trim() || "Girdi"
      }));
      return { exam: structuredData?.exam || {}, questions, students };
    };

    const renderAnalysis = (analysis) => {
      const summary = analysis.summary || {};
      const reportSummary = document.querySelector("#report-screen .summary-card p");
      const general = document.querySelector("#report-screen [aria-labelledby='general-evaluation-title'] p");
      const analysisTable = document.querySelector("#report-screen [aria-labelledby='analysis-table-title'] p");
      const outcomes = document.querySelector("#report-screen [aria-labelledby='learning-outcomes-title'] p");
      const strong = document.querySelector("#report-screen [aria-labelledby='strong-areas-title'] p");
      const development = document.querySelector("#report-screen [aria-labelledby='development-areas-title'] p");
      const suggestions = document.querySelector("#report-screen [aria-labelledby='teaching-suggestions-title'] p");
      const percent = (rate) => `%${((rate || 0) * 100).toFixed(2)}`;
      const strongOutcomes = (analysis.outcomes || []).filter((item) => item.successRate >= 0.70);
      const developmentOutcomes = (analysis.outcomes || []).filter((item) => item.successRate < 0.70);

      if (reportSummary) reportSummary.textContent = `${summary.participatingStudentCount} öğrencinin ${summary.questionCount} soruya ait öğretmen onaylı puanları analiz edilmiştir.`;
      if (general) general.textContent = `Sınıf ortalaması ${summary.classAverage}; genel başarı oranı ${percent(summary.classSuccessRate)} olarak hesaplanmıştır. Sınava katılmayan öğrenci sayısı ${summary.absentStudentCount}.`;
      if (analysisTable) analysisTable.textContent = (analysis.questions || []).map((item) => `Soru ${item.number}: ${percent(item.successRate)}`).join(" · ");
      if (outcomes) outcomes.textContent = (analysis.outcomes || []).map((item) => `${item.outcomeCode}: ${percent(item.successRate)} (${item.category})`).join(" · ");
      if (strong) strong.textContent = strongOutcomes.length ? strongOutcomes.map((item) => `${item.outcomeCode} — ${percent(item.successRate)}`).join(" · ") : "Güçlü alan eşiğine ulaşan öğrenme çıktısı bulunmamaktadır.";
      if (development) development.textContent = developmentOutcomes.length ? developmentOutcomes.map((item) => `${item.outcomeCode} — ${percent(item.successRate)}`).join(" · ") : "Öncelikli gelişim alanı belirlenmemiştir.";
      if (suggestions) suggestions.textContent = (analysis.outcomes || []).map((item) => `${item.outcomeCode}: ${item.decision}`).join(" ");
    };

    const analyzeApprovedData = () => {
      const approvalButton = document.querySelector('[data-approval-action="confirm-data"]');
      if (!structuredData || !approvalButton) return;
      approvalButton.disabled = true;
      approvalButton.textContent = "Analiz Başlatılıyor…";
      showMessage("Öğretmen onaylı veriler analiz motoruna aktarılıyor.");

      fetch("/mahir-analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectApprovedData())
      })
        .then((response) => response.json().catch(() => ({})).then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
          if (!response.ok) throw new Error(payload.message || "Onaylanan veriler analiz edilemedi.");
          renderAnalysis(payload.analysis || {});
          showProgressStep(progressTexts.length - 1);
          screenManager.approveData();
          screenManager.showScreen("analysis-screen");
          showMessage(payload.message, "success");
        })
        .catch((error) => {
          const approvalMessage = document.querySelector("[data-approval-message]");
          if (approvalMessage) {
            approvalMessage.textContent = error.message;
            approvalMessage.focus({ preventScroll: true });
          }
          showMessage(error.message, "error");
        })
        .finally(() => {
          approvalButton.disabled = false;
          approvalButton.textContent = "Verileri Onayla";
        });
    };

    const uploadSelectedFile = () => {
      if (!selectedFile) return;
      const formData = new FormData();
      let progressIndex = 0;
      formData.append("exam-file", selectedFile);
      readButton.disabled = true;
      readButton.setAttribute("aria-disabled", "true");
      readButton.textContent = "Belge Okunuyor…";
      window.clearInterval(progressTimer);
      showProgressStep(progressIndex);
      progressTimer = window.setInterval(() => {
        if (progressIndex < progressTexts.length - 2) showProgressStep(++progressIndex);
      }, 500);

      fetch("/mahir-upload", {
        method: "POST",
        body: formData
      })
        .then((response) => response.json().catch(() => ({})).then((payload) => ({ response, payload })))
        .then(({ response, payload }) => {
          const logMethod = response.ok ? "info" : "warn";
          const message = payload.message || (response.ok ? "Dosya başarıyla işlendi." : "Dosya işlenemedi.");
          window.clearInterval(progressTimer);
          if (response.ok) {
            renderValidationData(payload.structuredData);
            showProgressStep(progressTexts.length - 1);
            const reportText = payload.reportText || payload.report || payload.report_text;
            const reportRequest = reportText ? Promise.resolve(reportText) : fetch(`/shared/report-example.txt?ts=${Date.now()}`).then((reportResponse) => reportResponse.ok ? reportResponse.text() : message);
            reportRequest.then(showReport).catch(() => showReport(message));
            screenManager.showScreen("validation-screen");
          } else {
            showReport(message);
          }
          console[logMethod]("[MAHIR] Dosya backend alıcısına gönderildi.", payload);
          showMessage(message, response.ok ? "success" : "error");
        })
        .catch((error) => {
          window.clearInterval(progressTimer);
          console.warn("[MAHIR] Dosya backend alıcısına gönderilemedi.", error);
          showMessage("Belge okuma servisine ulaşılamadı. Prototip sunucusunu çalıştırıp yeniden deneyiniz.", "error");
          showReport("Backend bağlantısı kurulamadı.");
        })
        .finally(() => {
          readButton.disabled = false;
          readButton.setAttribute("aria-disabled", "false");
          readButton.textContent = "Verileri Oku ve Kontrol Et";
        });
    };

    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (file) selectFile(file);
    });

    removeButton?.addEventListener("click", clearFile);
    readButton.addEventListener("click", uploadSelectedFile);
    document.addEventListener("mahir:confirm-data", analyzeApprovedData);

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
      const file = event.dataTransfer?.files?.[0];
      if (file) selectFile(file);
    });
  };

  return { init };
})();
document.addEventListener("DOMContentLoaded", () => {
  preparationManager.init();
  screenManager.init();
  fileUploadBridge.init();
});
