(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MAHIRWorkspaceBackup = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const FORMAT = "mahir-workspace-backup";
  const CURRENT_SCHEMA_VERSION = 2;
  const STORAGE_PREFIX = "mahir:workspace:";
  const FORBIDDEN_KEYS = new Set([
    "students",
    "student",
    "studentRecords",
    "studentNo",
    "fullName",
    "rawExamData",
    "rawFile",
    "uploadedFiles"
  ]);

  const clone = (value) => JSON.parse(JSON.stringify(value));

  const stableStringify = (value) => {
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
    if (value && typeof value === "object") {
      return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
    }
    return JSON.stringify(value);
  };

  const digest = (value) => {
    const text = stableStringify(value);
    let hash = 0x811c9dc5;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  };

  const withoutIntegrity = (backup) => {
    const copy = clone(backup);
    delete copy.integrity;
    return copy;
  };

  const seal = (backup) => ({
    ...backup,
    integrity: {
      algorithm: "fnv1a-32",
      digest: digest(withoutIntegrity(backup))
    }
  });

  const findForbiddenPath = (value, path = "workspace") => {
    if (!value || typeof value !== "object") return null;
    for (const [key, child] of Object.entries(value)) {
      const childPath = `${path}.${key}`;
      if (FORBIDDEN_KEYS.has(key)) return childPath;
      const nested = findForbiddenPath(child, childPath);
      if (nested) return nested;
    }
    return null;
  };

  const assertObject = (value, message) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(message);
  };

  const validateIntegrity = (backup) => {
    assertObject(backup.integrity, "Yedek bütünlük bilgisi eksik.");
    if (backup.integrity.algorithm !== "fnv1a-32" || typeof backup.integrity.digest !== "string") {
      throw new Error("Yedek bütünlük yöntemi desteklenmiyor.");
    }
    if (backup.integrity.digest !== digest(withoutIntegrity(backup))) {
      throw new Error("Yedek bütünlük kontrolünü geçemedi; dosya bozulmuş veya değiştirilmiş olabilir.");
    }
  };

  const validateWorkspace = (workspace, version) => {
    assertObject(workspace, "Yedek çalışma kaydı eksik.");
    if (workspace.schemaVersion !== version) {
      throw new Error("Paket sürümü ile çalışma kaydı sürümü uyuşmuyor.");
    }
    ["teacherContext", "decisions", "justifications", "questionApprovals", "reportTexts", "approvals", "timestamps"]
      .forEach((key) => {
        if (!(key in workspace)) throw new Error(`Yedekte zorunlu “${key}” alanı eksik.`);
      });
    const forbiddenPath = findForbiddenPath(workspace);
    if (forbiddenPath) throw new Error(`Yedek gizlilik sınırını ihlal ediyor: ${forbiddenPath}.`);
  };

  const inspect = (input) => {
    const original = typeof input === "string" ? JSON.parse(input) : clone(input);
    assertObject(original, "Geçerli bir MAHİR yedeği seçilmedi.");
    if (original.format !== FORMAT) throw new Error("Dosya MAHİR çalışma yedeği biçiminde değil.");
    if (!Number.isInteger(original.schemaVersion)) throw new Error("Yedek şema sürümü eksik.");
    if (original.schemaVersion > CURRENT_SCHEMA_VERSION) {
      throw new Error(`Bu yedek daha yeni v${original.schemaVersion} şeması kullanıyor ve bu sürümde açılamaz.`);
    }
    if (![1, CURRENT_SCHEMA_VERSION].includes(original.schemaVersion)) {
      throw new Error(`v${original.schemaVersion} yedek şeması desteklenmiyor.`);
    }
    validateIntegrity(original);
    validateWorkspace(original.workspace, original.schemaVersion);
    return {
      original,
      sourceVersion: original.schemaVersion,
      targetVersion: CURRENT_SCHEMA_VERSION,
      converted: original.schemaVersion === 1
    };
  };

  const migrateV1Workspace = (workspace) => ({
    ...clone(workspace),
    schemaVersion: CURRENT_SCHEMA_VERSION,
    migration: {
      sourceVersion: 1,
      targetVersion: CURRENT_SCHEMA_VERSION,
      convertedAt: new Date().toISOString()
    }
  });

  const prepareRestore = (input) => {
    const result = inspect(input);
    const workspace = result.converted ? migrateV1Workspace(result.original.workspace) : clone(result.original.workspace);
    const normalized = result.converted
      ? seal({
        format: FORMAT,
        schemaVersion: CURRENT_SCHEMA_VERSION,
        createdAt: result.original.createdAt,
        workspace
      })
      : clone(result.original);
    return { ...result, workspace, normalized };
  };

  const createBackup = (workspace) => {
    const safeWorkspace = {
      teacherContext: {},
      decisions: [],
      justifications: [],
      questionApprovals: [],
      reportTexts: {},
      approvals: {},
      timestamps: {},
      ...clone(workspace),
      schemaVersion: CURRENT_SCHEMA_VERSION
    };
    validateWorkspace(safeWorkspace, CURRENT_SCHEMA_VERSION);
    return seal({
      format: FORMAT,
      schemaVersion: CURRENT_SCHEMA_VERSION,
      createdAt: new Date().toISOString(),
      workspace: safeWorkspace
    });
  };

  const createLegacyV1Backup = (workspace) => {
    const legacyWorkspace = { ...clone(workspace), schemaVersion: 1 };
    validateWorkspace(legacyWorkspace, 1);
    return seal({
      format: FORMAT,
      schemaVersion: 1,
      createdAt: new Date().toISOString(),
      workspace: legacyWorkspace
    });
  };

  const createRecordId = (now = new Date()) => {
    const stamp = now.toISOString().replace(/[-:.TZ]/g, "");
    const random = Math.random().toString(36).slice(2, 8);
    return `${stamp}-${random}`;
  };

  const saveLocalRecord = (storage, workspace, options = {}) => {
    if (!storage || typeof storage.setItem !== "function" || typeof storage.getItem !== "function") {
      throw new Error("Tarayıcı yerel kayıt alanına erişilemiyor.");
    }
    const savedAt = options.savedAt || new Date().toISOString();
    const recordId = options.recordId || createRecordId(new Date(savedAt));
    const backup = createBackup({
      ...clone(workspace),
      timestamps: {
        ...(workspace.timestamps || {}),
        savedAt
      }
    });
    const key = `${STORAGE_PREFIX}${recordId}`;
    storage.setItem(key, JSON.stringify(backup));
    const verified = inspect(storage.getItem(key));
    return { key, recordId, savedAt, backup: verified.original };
  };

  const migrateStoredV1Records = (storage) => {
    if (!storage) return { migrated: 0, rejected: 0 };
    let migrated = 0;
    let rejected = 0;
    const keys = Array.from({ length: storage.length }, (_, index) => storage.key(index))
      .filter((key) => key && key.startsWith(STORAGE_PREFIX));
    keys.forEach((key) => {
      try {
        const prepared = prepareRestore(storage.getItem(key));
        if (prepared.converted) {
          storage.setItem(key, JSON.stringify(prepared.normalized));
          migrated += 1;
        }
      } catch (_error) {
        rejected += 1;
      }
    });
    return { migrated, rejected };
  };

  const downloadJson = (backup, filename = "MAHIR_Calisma_Yedegi_v2.json") => {
    const blob = new Blob([`${JSON.stringify(backup, null, 2)}\n`], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const textByHeading = (headingId) => document.querySelector(`#report-screen [aria-labelledby="${headingId}"] p`)?.textContent || "";

  const collectWorkspace = () => ({
    teacherContext: Object.fromEntries(Array.from(document.querySelectorAll("[data-prep-field]"))
      .map((field) => [field.dataset.prepField, field.value || ""])),
    decisions: [],
    justifications: [],
    questionApprovals: [],
    reportTexts: {
      summary: textByHeading("report-summary-title"),
      generalEvaluation: textByHeading("general-evaluation-title"),
      analysisTable: textByHeading("analysis-table-title"),
      learningOutcomes: textByHeading("learning-outcomes-title"),
      strengths: textByHeading("strong-areas-title"),
      developmentAreas: textByHeading("development-areas-title"),
      teachingSuggestions: textByHeading("teaching-suggestions-title"),
      monitoringPlan: textByHeading("monitoring-plan-title"),
      sourceReferences: textByHeading("source-reference-title")
    },
    approvals: {
      finalReport: Boolean(document.querySelector("[data-final-report-approval]")?.checked)
    },
    timestamps: { savedAt: new Date().toISOString() }
  });

  const applyWorkspace = (workspace) => {
    Object.entries(workspace.reportTexts || {}).forEach(([key, value]) => {
      const headingMap = {
        summary: "report-summary-title",
        generalEvaluation: "general-evaluation-title",
        analysisTable: "analysis-table-title",
        learningOutcomes: "learning-outcomes-title",
        strengths: "strong-areas-title",
        developmentAreas: "development-areas-title",
        teachingSuggestions: "teaching-suggestions-title",
        monitoringPlan: "monitoring-plan-title",
        sourceReferences: "source-reference-title"
      };
      const target = document.querySelector(`#report-screen [aria-labelledby="${headingMap[key]}"] p`);
      if (target && typeof value === "string") target.textContent = value;
    });
    const finalApproval = document.querySelector("[data-final-report-approval]");
    if (finalApproval) {
      finalApproval.checked = Boolean(workspace.approvals?.finalReport);
      finalApproval.dispatchEvent(new Event("change", { bubbles: true }));
    }
    document.dispatchEvent(new CustomEvent("mahir:workspace-restored", { detail: { workspace: clone(workspace) } }));
  };

  const init = () => {
    const downloadButton = document.querySelector("[data-download-workspace-backup]");
    const saveButton = document.querySelector("[data-save-local-workspace]");
    const saveMessage = document.querySelector("[data-local-workspace-message]");
    const input = document.querySelector("[data-workspace-backup-input]");
    const preview = document.querySelector("[data-workspace-backup-preview]");
    const message = document.querySelector("[data-workspace-backup-message]");
    const confirmButton = document.querySelector("[data-confirm-workspace-restore]");
    const cancelButton = document.querySelector("[data-cancel-workspace-restore]");
    let pending = null;

    if (!downloadButton || !saveButton || !saveMessage || !input || !preview || !message || !confirmButton || !cancelButton) return;
    migrateStoredV1Records(window.localStorage);

    const resetPreview = () => {
      pending = null;
      input.value = "";
      preview.hidden = true;
      confirmButton.disabled = true;
      message.textContent = "";
      message.className = "workspace-backup-message";
    };

    downloadButton.addEventListener("click", () => downloadJson(createBackup(collectWorkspace())));
    saveButton.addEventListener("click", () => {
      saveMessage.hidden = false;
      try {
        const result = saveLocalRecord(window.localStorage, collectWorkspace());
        const savedTime = new Date(result.savedAt).toLocaleString("tr-TR");
        saveMessage.className = "workspace-backup-message is-success";
        saveMessage.textContent = `Çalışma bu tarayıcıya anonim olarak kaydedildi (${savedTime}). Öğrenci verileri ve yüklenen sınav dosyası kayda alınmadı.`;
      } catch (error) {
        saveMessage.className = "workspace-backup-message is-error";
        saveMessage.textContent = `Çalışma kaydedilemedi: ${error.message}`;
      }
    });
    input.addEventListener("change", async () => {
      resetPreview();
      const file = input.files?.[0];
      if (!file) return;
      try {
        pending = prepareRestore(await file.text());
        preview.hidden = false;
        confirmButton.disabled = false;
        message.className = "workspace-backup-message is-success";
        message.textContent = pending.converted
          ? `Yedek doğrulandı: v${pending.sourceVersion} → v${pending.targetVersion}. Eski yedek yalnız bellekte dönüştürüldü; geri yükleme için onayınız gerekir.`
          : `Yedek doğrulandı: v${pending.sourceVersion}. Geri yükleme için onayınız gerekir.`;
      } catch (error) {
        preview.hidden = false;
        message.className = "workspace-backup-message is-error";
        message.textContent = error.message;
      }
    });
    confirmButton.addEventListener("click", () => {
      if (!pending) return;
      applyWorkspace(pending.workspace);
      message.className = "workspace-backup-message is-success";
      message.textContent = pending.converted
        ? "v1’den v2’ye dönüştürülen çalışma öğretmen onayıyla geri yüklendi."
        : "Çalışma öğretmen onayıyla geri yüklendi.";
      confirmButton.disabled = true;
      pending = null;
    });
    cancelButton.addEventListener("click", resetPreview);
  };

  if (typeof document !== "undefined") document.addEventListener("DOMContentLoaded", init);

  return {
    FORMAT,
    CURRENT_SCHEMA_VERSION,
    STORAGE_PREFIX,
    stableStringify,
    digest,
    createBackup,
    createLegacyV1Backup,
    saveLocalRecord,
    inspect,
    prepareRestore,
    migrateStoredV1Records
  };
});
