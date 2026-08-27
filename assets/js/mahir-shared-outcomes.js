(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MAHIRSharedOutcomes = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const normalize = (value) => String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("tr-TR")
    .replace(/\s+/g, " ")
    .trim();

  const examTypeKey = (value) => {
    const normalized = normalize(value);
    if (normalized === "written" || normalized.includes("yazılı") || normalized.includes("yazili")) return "written";
    if (normalized === "listening" || normalized.includes("dinleme")) return "listening";
    if (normalized === "speaking" || normalized.includes("konuşma") || normalized.includes("konusma")) return "speaking";
    return "";
  };

  const componentKey = (exam = {}) => examTypeKey(exam.componentType) || examTypeKey(exam.examType);

  const gradeKey = (exam = {}, fallback = "") => (
    String(exam.grade || exam.classSection || fallback || "").match(/\d{1,2}/)?.[0] || ""
  );

  const questionShapeKey = (questions = []) => (Array.isArray(questions) ? questions : [])
    .map((question, index) => {
      const number = Number(question?.number || index + 1);
      const maxScore = Number(question?.maxScore);
      return `${number}:${Number.isFinite(maxScore) ? maxScore : ""}`;
    })
    .join("|");

  const structureKey = (group = {}, fallback = {}) => {
    const exam = group.exam || {};
    const course = normalize(exam.course || exam.courseName || fallback.course);
    const grade = gradeKey(exam, fallback.grade);
    const component = componentKey(exam);
    return [course, grade, component, questionShapeKey(group.questions)].join("::");
  };

  const outcomeFields = Object.freeze([
    "outcomeCode",
    "outcomeDescription",
    "outcomeIndicators",
    "outcomeTheme",
    "outcomeSkill",
    "parentOutcomeCode",
    "parentOutcomeDescription",
    "outcomeKey",
    "weight"
  ]);

  const cloneOutcome = (outcome = {}) => ({
    ...outcome,
    ...(Array.isArray(outcome.outcomeIndicators)
      ? { outcomeIndicators: [...outcome.outcomeIndicators] }
      : {})
  });

  const copyQuestionOutcomes = (sourceQuestion = {}, targetQuestion = {}) => {
    const copied = { ...targetQuestion };
    copied.outcomes = (Array.isArray(sourceQuestion.outcomes) ? sourceQuestion.outcomes : [])
      .map(cloneOutcome);
    outcomeFields.forEach((field) => {
      const value = sourceQuestion[field];
      copied[field] = Array.isArray(value) ? [...value] : (value ?? "");
    });
    return copied;
  };

  const hasOutcomeMappings = (group = {}) => (group.questions || []).some((question) => (
    (Array.isArray(question?.outcomes) && question.outcomes.length > 0)
    || Boolean(question?.outcomeKey || question?.outcomeCode || question?.outcomeDescription)
  ));

  const applySharedOutcomes = (groups, sourceIndex, fallback = {}) => {
    if (!Array.isArray(groups) || !groups[sourceIndex]) return [];
    const source = groups[sourceIndex];
    const sourceKey = structureKey(source, fallback);
    if (!sourceKey || !componentKey(source.exam || {}) || !questionShapeKey(source.questions)) return [];
    const appliedIndexes = [];
    groups.forEach((candidate, candidateIndex) => {
      if (candidateIndex === sourceIndex || candidate?.workflowStatus === "analyzed") return;
      if (!["checked", "outcomes-complete"].includes(candidate?.workflowStatus)) return;
      if (structureKey(candidate, fallback) !== sourceKey) return;
      candidate.questions = (candidate.questions || []).map((question, questionIndex) => (
        copyQuestionOutcomes(source.questions?.[questionIndex], question)
      ));
      candidate.workflowStatus = "outcomes-complete";
      appliedIndexes.push(candidateIndex);
    });
    return appliedIndexes;
  };

  const repairMissingSharedOutcomes = (groups, fallback = {}) => {
    if (!Array.isArray(groups)) return [];
    const sourceByStructure = new Map();
    groups.forEach((group, index) => {
      const key = structureKey(group, fallback);
      if (key && componentKey(group?.exam || {}) && hasOutcomeMappings(group) && !sourceByStructure.has(key)) {
        sourceByStructure.set(key, index);
      }
    });
    const repairs = [];
    groups.forEach((candidate, candidateIndex) => {
      if (hasOutcomeMappings(candidate)) return;
      const sourceIndex = sourceByStructure.get(structureKey(candidate, fallback));
      if (!Number.isInteger(sourceIndex) || sourceIndex === candidateIndex) return;
      const source = groups[sourceIndex];
      candidate.questions = (candidate.questions || []).map((question, questionIndex) => (
        copyQuestionOutcomes(source.questions?.[questionIndex], question)
      ));
      candidate.workflowStatus = "outcomes-complete";
      candidate.analysis = null;
      candidate.trace = null;
      candidate.reportApproved = false;
      repairs.push({ sourceIndex, candidateIndex });
    });
    return repairs;
  };

  return Object.freeze({
    normalize,
    examTypeKey,
    componentKey,
    questionShapeKey,
    structureKey,
    copyQuestionOutcomes,
    hasOutcomeMappings,
    applySharedOutcomes,
    repairMissingSharedOutcomes
  });
});
