(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MAHIRProgramCatalog = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const normalize = (value) => String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("tr-TR")
    .trim()
    .replace(/\s+/g, " ");

  const programs = Object.freeze([
    Object.freeze({
      id: "tde-9-tymm",
      courseNames: Object.freeze(["Türk Dili ve Edebiyatı", "Seçmeli Türk Dili ve Edebiyatı"]),
      grade: "9",
      dataUrl: "shared/pilot/tde9/learning-outcomes-template.json"
    })
  ]);

  const resolve = (courseName, grade) => {
    const course = normalize(courseName);
    const gradeValue = String(grade || "").trim().replace(/\.\s*sınıf$/i, "");
    return programs.find((program) => (
      program.grade === gradeValue
      && program.courseNames.some((name) => normalize(name) === course)
    )) || null;
  };

  const skillsForComponent = (component) => ({
    written: ["Okuma", "Yazma"],
    listening: ["Dinleme/İzleme"],
    speaking: ["Konuşma"],
    general: []
  }[component] || []);

  const filterOutcomes = (outcomes, component) => {
    const allowed = new Set(skillsForComponent(component).map(normalize));
    return (Array.isArray(outcomes) ? outcomes : [])
      .filter((outcome) => allowed.has(normalize(outcome?.skill)))
      .flatMap((outcome) => {
        const components = Array.isArray(outcome.processComponents) ? outcome.processComponents : [];
        if (!components.length) return [outcome];
        return components.map((component) => ({
          ...outcome,
          id: `${outcome.id}-${String(component.code || "").toLocaleLowerCase("tr-TR").replace(/[^a-z0-9]+/g, "-")}`,
          code: component.code,
          title: component.title,
          parentCode: outcome.code,
          parentTitle: outcome.title,
          indicators: Array.isArray(component.indicators) ? component.indicators : [],
          processComponent: true
        }));
      });
  };

  return Object.freeze({ normalize, programs, resolve, skillsForComponent, filterOutcomes });
});
