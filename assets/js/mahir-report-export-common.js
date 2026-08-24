(() => {
  const DEFAULT_REPORT_TITLE = "SINAV SONUÇLARI ANALİZ RAPORU";
  const GENERAL_REPORT_TITLE = "TÜRK DİLİ VE EDEBİYATI GENEL DEĞERLENDİRME RAPORU";
  const COMPONENT_REPORTS = {
    written: { label: "Yazılı Sınav", title: "YAZILI SINAV SONUÇLARI ANALİZ RAPORU", summaryHeading: "B. YAZILI SINAV BAŞARI ÖZETİ" },
    listening: { label: "Dinleme/İzleme Sınavı", title: "DİNLEME/İZLEME SINAVI SONUÇLARI ANALİZ RAPORU", summaryHeading: "B. DİNLEME/İZLEME SINAVI BAŞARI ÖZETİ" },
    speaking: { label: "Konuşma Sınavı", title: "KONUŞMA SINAVI SONUÇLARI ANALİZ RAPORU", summaryHeading: "B. KONUŞMA SINAVI BAŞARI ÖZETİ" }
  };
  const BRAND_NAME = "MAHİR";
  const BRAND_EXPANSION = "Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı";
  const SUCCESS_THRESHOLD = 0.5;

  const design = {
    a4WidthPt: 595.28,
    a4HeightPt: 841.89,
    renderWidth: 794,
    renderScale: 2,
    pageMargin: 38,
    contentX: 42,
    cardGap: 8,
    titleSize: 22,
    titleLine: 28,
    subtitleSize: 10.8,
    subtitleLine: 15,
    metaSize: 9.6,
    metaLine: 13,
    headingSize: 12.8,
    headingLine: 16,
    bodySize: 10.6,
    bodyLine: 15,
    tableSize: 8.8,
    tableLine: 12,
    sectionTitlePaddingX: 9,
    sectionTitlePaddingY: 5,
    sectionPaddingX: 9,
    sectionPaddingY: 7,
    tableCellPaddingX: 5,
    tableCellPaddingY: 4,
    colors: {
      ink: "#1f1f1f",
      navy: "#17365d",
      heading: "#365f91",
      blue: "#2f75b5",
      paleBlue: "#d9eaf7",
      softBlue: "#edf4fa",
      light: "#f8fbfd",
      border: "#9ebcd3",
      muted: "#59697a"
    }
  };

  const normalizeText = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const isUseful = (value) => /[\p{L}\p{N}]/u.test(normalizeText(value)) && !/^belirtilmedi$/i.test(normalizeText(value));

  const normalizeForCompare = (value) => normalizeText(value)
    .toLocaleLowerCase("tr-TR")
    .replace(/[ıİ]/g, "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  const runtime = () => window.MAHIRReportRuntime || {};

  const valueFrom = (source, keys) => {
    for (const key of keys) {
      const value = source?.[key];
      if (isUseful(value)) return normalizeText(value);
    }
    return "";
  };

  const verifiedInstitutionValue = (source, keys) => {
    const value = valueFrom(source, keys);
    return /^\d+(?:[.,]\d+)?$/.test(value) ? "" : value;
  };

  const optionText = (selector) => {
    const element = document.querySelector(selector);
    if (!element || element.disabled || !element.value) return "";
    const text = normalizeText(element.selectedOptions?.[0]?.textContent || element.value);
    return /seçiniz$/i.test(text) ? "" : text;
  };

  const inputText = (selector) => {
    const element = document.querySelector(selector);
    if (!element || element.disabled) return "";
    return normalizeText(element.value || element.textContent || "");
  };

  const getContext = () => {
    const schoolType = inputText("#other-school-type") || optionText("#school-type");
    const course = inputText("#other-course-name") || optionText("#course-select");
    const field = optionText("#mtal-field");
    const branch = optionText("#mtal-branch");
    return {
      educationStage: optionText("#education-stage"),
      schoolType,
      programType: optionText("#program-type"),
      field,
      branch,
      fieldBranch: [field, branch].filter(Boolean).join(" / "),
      gradeLevel: optionText("#grade-level"),
      courseType: optionText("#course-type"),
      course,
      sourceScope: [optionText("#education-stage"), schoolType, optionText("#program-type"), field, branch, optionText("#grade-level"), course, optionText("#course-type")].filter(Boolean)
    };
  };

  // Analiz anındaki sınav sözleşmesini, öğretmenin rapor ekranında sonradan
  // tamamladığı güncel üstbilgiyle birleştir. Sınav türünün güvenilir kaynağı
  // aşağıdaki getComponentType/getComponentReport zinciridir; bu birleşim İl,
  // okul, öğretmen vb. son onay alanlarının A/H bölümlerine ulaşması içindir.
  const getExam = () => ({
    ...(runtime().analysis?.exam || {}),
    ...(runtime().structuredData?.exam || {}),
    ...(runtime().exam || {})
  });
  const getStructuredQuestions = () => runtime().structuredData?.questions || [];
  const getStructuredStudents = () => runtime().structuredData?.students || [];
  const getAnalysis = () => runtime().analysis || {};
  const getComponentType = () => normalizeText(
    getAnalysis().component?.componentType || getAnalysis().componentType || getExam().componentType || "written"
  ).toLowerCase();
  const getComponentReport = () => COMPONENT_REPORTS[getComponentType()] || null;
  const getExamTypeLabel = () => getComponentReport()?.label
    || normalizeText(getAnalysis().component?.componentLabel || getAnalysis().componentLabel)
    || valueFrom(getExam(), ["examType"])
    || "";
  const getReportTitle = () => getAnalysis().assessmentScope === "language-composite"
    ? GENERAL_REPORT_TITLE
    : getComponentReport()?.title || DEFAULT_REPORT_TITLE;
  const getDownloadFilename = (extension = "docx") => {
    const suffix = String(extension || "docx").replace(/^\.+/, "").toLowerCase();
    const baseName = getAnalysis().assessmentScope === "language-composite"
      ? "MAHIR_Genel_Degerlendirme_Raporu"
      : ({
          written: "MAHIR_Yazili_Sinav_Sonuclari_Analiz_Raporu",
          listening: "MAHIR_Dinleme_Izleme_Sinavi_Sonuclari_Analiz_Raporu",
          speaking: "MAHIR_Konusma_Sinavi_Sonuclari_Analiz_Raporu"
        }[getComponentType()] || "MAHIR_Sinav_Sonuclari_Analiz_Raporu");
    return `${baseName}.${suffix}`;
  };
  // Analizi ÜRETEN ajanların izi (/mahir-analyze yanıtındaki `trace`). `analysis`in
  // kardeşi, içinde değil: biri raporun kendisi, diğeri raporun nasıl üretildiği.
  const getTraceAgents = () => {
    const agents = runtime().trace?.agents;
    return Array.isArray(agents) ? agents : [];
  };

  const dateText = () => new Intl.DateTimeFormat("tr-TR", { dateStyle: "long" }).format(new Date());
  const displayDate = (value) => {
    const text = normalizeText(value);
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return text;
    return `${match[3]}.${match[2]}.${match[1]}`;
  };

  const formatNumber = (value, digits = 2) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    const hasFraction = Math.abs(number - Math.round(number)) > 0.001;
    return new Intl.NumberFormat("tr-TR", {
      minimumFractionDigits: hasFraction ? Math.min(2, digits) : 0,
      maximumFractionDigits: digits
    }).format(number);
  };

  const formatPercent = (rate) => {
    const numeric = Number(rate);
    if (!Number.isFinite(numeric)) return "";
    const percent = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
    const rounded = Math.round(percent * 100) / 100;
    const hasFraction = Math.abs(rounded - Math.round(rounded)) > 0.001;
    return `%${new Intl.NumberFormat("tr-TR", {
      minimumFractionDigits: hasFraction ? 2 : 0,
      maximumFractionDigits: 2
    }).format(rounded)}`;
  };

  const EMPTY_MARK = "—";
  const displayValue = (value) => isUseful(value) ? normalizeText(value) : EMPTY_MARK;
  const successLevel = (rate) => {
    const value = Number(rate);
    if (!Number.isFinite(value)) return EMPTY_MARK;
    if (value >= 0.85) return "Beklenen düzeyin üzerinde";
    if (value >= 0.70) return "Beklenen düzeyde";
    if (value >= 0.50) return "Gelişimi sürmekte";
    return "Gelişim desteği öncelikli";
  };

  const getQuestionOutcomes = (question = {}, structuredQuestion = {}) => {
    const source = Array.isArray(question.outcomes) && question.outcomes.length
      ? question.outcomes
      : Array.isArray(structuredQuestion.outcomes) && structuredQuestion.outcomes.length
        ? structuredQuestion.outcomes
        : [question, structuredQuestion].filter((item) => valueFrom(item, ["outcomeCode", "outcomeDescription", "outcomeKey"]));
    const seen = new Set();
    return source.map((item) => ({
      outcomeCode: normalizeText(item.outcomeCode),
      outcomeTheme: normalizeText(item.outcomeTheme),
      outcomeDescription: valueFrom(item, ["outcomeDescription", "learningOutcome", "description"]),
      outcomeKey: normalizeText(item.outcomeKey)
    })).filter((item) => {
      const key = item.outcomeKey || [item.outcomeTheme, item.outcomeCode, item.outcomeDescription].join("|");
      if (!key.replace(/\|/g, "") || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  };

  const getQuestionDescription = (question, structuredQuestion = {}) => {
    const labels = getQuestionOutcomes(question, structuredQuestion).map((outcome) =>
      [outcome.outcomeCode, outcome.outcomeDescription].filter(Boolean).join(" — ")
    ).filter(Boolean);
    return labels.join("; ") || "Öğrenme çıktısı belirtilmedi";
  };

  const getParticipatingStudents = () => {
    const students = getAnalysis().students || getStructuredStudents();
    return students.filter((student) => !["g", "girmedi", "katılmadı", "katilmadi", "yok"].includes(normalizeText(student.attendance || "Girdi").toLocaleLowerCase("tr-TR")));
  };

  const getQuestionRows = () => {
    const analysisQuestions = getAnalysis().questions || [];
    const structured = getStructuredQuestions();
    const source = analysisQuestions.length ? analysisQuestions : structured;
    const participating = Number(getAnalysis().summary?.participatingStudentCount) || getParticipatingStudents().length || 0;
    return source.map((question, index) => {
      const structuredQuestion = structured.find((item) => Number(item.number) === Number(question.number)) || structured[index] || {};
      const maxScore = Number(question.maxScore ?? structuredQuestion.maxScore) || 0;
      const average = participating && Number.isFinite(Number(question.earnedScore)) ? Number(question.earnedScore) / participating : "";
      const rate = Number(question.successRate);
      const outcomes = getQuestionOutcomes(question, structuredQuestion);
      const primaryOutcome = outcomes[0] || {};
      return {
        number: question.number ?? structuredQuestion.number ?? index + 1,
        outcomes,
        outcomeCode: primaryOutcome.outcomeCode || normalizeText(question.outcomeCode || structuredQuestion.outcomeCode),
        outcomeTheme: primaryOutcome.outcomeTheme || normalizeText(question.outcomeTheme || structuredQuestion.outcomeTheme),
        outcomeDescription: getQuestionDescription(question, structuredQuestion),
        maxScore,
        average,
        successRate: Number.isFinite(rate) ? rate : "",
        level: successLevel(rate),
        evaluation: Number.isFinite(rate)
          ? `${successLevel(rate)} düzeyindedir; değerlendirme öğretmen onaylı puanlara dayanmaktadır.`
          : "Soru için başarı oranı hesaplanamamıştır."
      };
    });
  };

  const relatedQuestionsForOutcome = (outcomeCode, outcomeTheme = "") => getQuestionRows()
    .filter((question) => question.outcomes.some((outcome) =>
      normalizeText(outcome.outcomeCode) === normalizeText(outcomeCode)
      && (!outcomeTheme || normalizeText(outcome.outcomeTheme) === normalizeText(outcomeTheme))))
    .map((question) => `S${question.number}`)
    .join(", ");

  const getSummary = () => {
    const analysis = getAnalysis();
    const summary = analysis.summary || {};
    const students = getParticipatingStudents();
    const totals = students.map((student) => Number(student.calculatedTotal ?? student.totalScore)).filter(Number.isFinite);
    const examMax = Number(summary.examMaxScore) || getQuestionRows().reduce((sum, question) => sum + (Number(question.maxScore) || 0), 0);
    const threshold = examMax * SUCCESS_THRESHOLD;
    const successful = totals.filter((total) => total >= threshold).length;
    const unsuccessful = totals.length ? totals.length - successful : "";
    const average = Number(summary.classAverage);
    return {
      questionCount: Number(summary.questionCount) || getQuestionRows().length,
      studentCount: Number(summary.studentCount) || getStructuredStudents().length || students.length,
      participatingStudentCount: Number(summary.participatingStudentCount) || students.length,
      absentStudentCount: Number(summary.absentStudentCount) || Math.max(0, (getStructuredStudents().length || students.length) - students.length),
      examMaxScore: examMax,
      classAverage: Number.isFinite(average) ? average : (totals.length ? totals.reduce((sum, item) => sum + item, 0) / totals.length : ""),
      classSuccessRate: Number(summary.classSuccessRate) || (examMax && totals.length ? (totals.reduce((sum, item) => sum + item, 0) / totals.length) / examMax : ""),
      highestScore: totals.length ? Math.max(...totals) : "",
      lowestScore: totals.length ? Math.min(...totals) : "",
      successfulStudentCount: totals.length ? successful : "",
      unsuccessfulStudentCount: totals.length ? unsuccessful : "",
      // Ölçme Ajanı'nın anomali gözlemi. Bu fonksiyon özeti yeniden KURDUĞU
      // için (alanları tek tek yazıyor) buraya eklenmeyen her alan sessizce
      // düşer - backend üretse bile rapora ulaşamaz.
      anomalies: summary.anomalies || ""
    };
  };

  const getMetadata = () => {
    const exam = getExam();
    const context = getContext();
    const summary = getSummary();
    const schoolName = verifiedInstitutionValue(exam, ["schoolName", "school", "institutionName"]);
    const teacherName = verifiedInstitutionValue(exam, ["teacherName", "teacher", "teacherFullName"]);
    const wordCourse = valueFrom(exam, ["courseName", "course"]);
    const wordClass = valueFrom(exam, ["classSection", "grade", "className"]);

    return [
      { label: "İl", value: verifiedInstitutionValue(exam, ["province", "city"]) },
      { label: "İlçe", value: verifiedInstitutionValue(exam, ["district", "town"]) },
      { label: "Okul/Kurum Adı", value: schoolName, source: "word", required: true },
      { label: "Öğretmenin Adı Soyadı", value: teacherName, source: "word", required: true },
      { label: "Eğitim Öğretim Yılı", value: verifiedInstitutionValue(exam, ["academicYear", "educationYear"]) },
      { label: "Öğretim Kademesi", value: context.educationStage, source: "context" },
      { label: "Okul Türü", value: context.schoolType, source: "context" },
      { label: "Program Türü", value: context.programType, source: "context" },
      { label: "Alan/Dal", value: context.fieldBranch, source: "context" },
      { label: "Ders", value: wordCourse || context.course, source: wordCourse ? "word" : "context", required: true },
      { label: "Ders Türü", value: context.courseType, source: "context" },
      { label: "Sınıf/Şube", value: verifiedInstitutionValue({ value: wordClass || context.gradeLevel }, ["value"]), source: wordClass ? "word" : "context", required: true },
      { label: "Dönem", value: valueFrom(exam, ["term"]) },
      { label: "Sınav Sırası", value: valueFrom(exam, ["examSequence"]) },
      { label: "Sınav Türü", value: getAnalysis().assessmentScope === "language-composite" ? "Genel Değerlendirme" : getExamTypeLabel() },
      { label: "Sınav Tarihi", value: displayDate(valueFrom(exam, ["examDate"])) },
      { label: "Rapor Tarihi", value: dateText() },
      { label: "Analiz Edilen Öğrenci Sayısı", value: summary.participatingStudentCount ? String(summary.participatingStudentCount) : "", required: true }
    ].filter((item) => isUseful(item.value));
  };

  const conflictPair = (label, wordValue, contextValue, comparator = "text") => {
    if (!isUseful(wordValue) || !isUseful(contextValue)) return null;
    let conflict = false;
    if (comparator === "grade") {
      const wordGrade = normalizeText(wordValue).match(/\d+/)?.[0] || "";
      const contextGrade = normalizeText(contextValue).match(/\d+/)?.[0] || "";
      conflict = Boolean(wordGrade && contextGrade && wordGrade !== contextGrade);
    } else {
      const a = normalizeForCompare(wordValue);
      const b = normalizeForCompare(contextValue);
      conflict = Boolean(a && b && a !== b && !a.includes(b) && !b.includes(a));
    }
    return conflict ? `${label}: Word belgesi "${wordValue}", Eğitim Bağlamı "${contextValue}" gösteriyor.` : null;
  };

  const validateModel = () => {
    const exam = getExam();
    const context = getContext();
    const summary = getSummary();
    const missing = [];
    if (!isUseful(valueFrom(exam, ["schoolName", "school", "institutionName"]))) missing.push("Okul/Kurum Adı");
    if (!isUseful(valueFrom(exam, ["teacherName", "teacher", "teacherFullName"]))) missing.push("Öğretmenin Adı Soyadı");
    if (!isUseful(valueFrom(exam, ["courseName", "course"]) || context.course)) missing.push("Ders");
    if (!isUseful(valueFrom(exam, ["classSection", "grade", "className"]) || context.gradeLevel)) missing.push("Sınıf/Şube");
    if (!isUseful(valueFrom(exam, ["province", "city"]))) missing.push("İl");
    if (!isUseful(valueFrom(exam, ["district", "town"]))) missing.push("İlçe");
    if (!isUseful(valueFrom(exam, ["academicYear", "educationYear"]))) missing.push("Eğitim Öğretim Yılı");
    if (!isUseful(valueFrom(exam, ["term"]))) missing.push("Dönem");
    if (getAnalysis().assessmentScope !== "language-composite" && !isUseful(valueFrom(exam, ["examSequence"]))) missing.push("Sınav Sırası");
    if (!isUseful(valueFrom(exam, ["examDate"]))) missing.push("Sınav Tarihi");
    if (!isUseful(valueFrom(exam, ["teachingProgram", "curriculumName"]))) missing.push("Öğretim Programı");
    if (getAnalysis().assessmentScope !== "language-composite" && !summary.participatingStudentCount) missing.push("Analiz Edilen Öğrenci Sayısı");

    const conflicts = [
      conflictPair("Ders", valueFrom(exam, ["courseName", "course"]), context.course),
      conflictPair("Sınıf/Şube", valueFrom(exam, ["classSection", "grade", "className"]), context.gradeLevel, "grade")
    ].filter(Boolean);

    return {
      valid: missing.length === 0 && conflicts.length === 0,
      missing,
      conflicts,
      message: missing.length || conflicts.length
        ? [missing.length ? `Tamamlanması gereken alanlar: ${missing.join(", ")}.` : "", conflicts.length ? `Tutarlılık kontrolü: ${conflicts.join(" ")}` : ""].filter(Boolean).join(" ")
        : "Rapor çıktıları için gerekli bilgiler tamamlandı."
    };
  };

  const metadataValue = (label) => getMetadata().find((item) => item.label === label)?.value || "";

  const buildContextTable = () => [
    ["İl", metadataValue("İl"), "İlçe", metadataValue("İlçe")],
    ["Okul / Kurum Adı", metadataValue("Okul/Kurum Adı"), "Öğretmenin Adı Soyadı", metadataValue("Öğretmenin Adı Soyadı")],
    ["Eğitim Öğretim Yılı", metadataValue("Eğitim Öğretim Yılı"), "Rapor Tarihi", metadataValue("Rapor Tarihi")],
    ["Öğretim Kademesi", metadataValue("Öğretim Kademesi"), "Okul Türü", metadataValue("Okul Türü")],
    ["Program Türü", displayValue(metadataValue("Program Türü")), "Alan / Dal", displayValue(metadataValue("Alan/Dal"))],
    ["Ders", metadataValue("Ders"), "Sınıf / Şube", metadataValue("Sınıf/Şube")],
    ["Dönem", metadataValue("Dönem"), "Sınav Sırası", metadataValue("Sınav Sırası")],
    ["Sınav Türü", metadataValue("Sınav Türü"), "Sınav Tarihi", metadataValue("Sınav Tarihi")],
    ["Analiz Edilen Öğrenci Sayısı", metadataValue("Analiz Edilen Öğrenci Sayısı"), "", ""]
  ];

  const buildGeneralSummaryBlock = () => {
    const summary = getSummary();
    const component = getComponentReport();
    const examType = getExamTypeLabel() || "Sınav";
    return {
      heading: component?.summaryHeading || "B. SINAV BAŞARI ÖZETİ",
      paragraphs: [`${examType}: ${summary.participatingStudentCount || 0} öğrencinin sınav sonuçları değerlendirilmiştir.`],
      tables: [[
        ["Öğrenci Sayısı", "Sınav Ortalaması", "En Yüksek Puan", "En Düşük Puan", "Başarı Oranı"],
        [
          summary.participatingStudentCount || "",
          formatNumber(summary.classAverage),
          formatNumber(summary.highestScore),
          formatNumber(summary.lowestScore),
          formatPercent(summary.classSuccessRate)
        ]
      ]],
      tableWidths: [[18, 22, 20, 20, 20]]
    };
  };

  // Ölçme ve Değerlendirme Ajanı'nın anomali bulgusu. Kapanış cümlesi kasıtlı:
  // bu bir GÖZLEM, karar veya öneri değil - DEVELOPMENT_CHARTER.md gereği MAHİR
  // etkinlik, yöntem veya telafi programı belirlemez. Bulgu yoksa paragraf hiç
  // eklenmez; "bir şey bulunmadı" satırı gürültüden başka bir şey olmaz.
  const anomalyParagraphs = () => {
    const finding = normalizeText(getSummary().anomalies);
    const basis = "Gerçekleşme düzeyi, öğretmen tarafından onaylanan öğrenci puanlarının sorunun azami puanına oranlanmasıyla hesaplanmıştır. MAHİR değerlendirme ölçütü: %85–100 beklenen düzeyin üzerinde, %70–84,99 beklenen düzeyde, %50–69,99 gelişimi sürmekte, %0–49,99 gelişim desteği öncelikli.";
    return [basis, isUseful(finding) ? `Dikkat çeken ölçme bulguları: ${finding} Bu gözlem hiçbir puanı veya oranı değiştirmez.` : "Ek bir ölçme bulgusu tespit edilmemiştir."];
  };

  const buildQuestionBlock = () => ({
    heading: "C. SORU BAZINDA ÖĞRENME KANITLARI",
    paragraphs: anomalyParagraphs(),
    tables: [[
      ["Soru", "İlişkilendirilen Öğrenme Çıktısı", "Azami Puan", "Ortalama Puan", "Gerçekleşme Düzeyi (%)", "Düzey"],
      ...getQuestionRows().map((question) => [
        String(question.number),
        question.outcomeDescription,
        formatNumber(question.maxScore),
        formatNumber(question.average),
        formatPercent(question.successRate),
        question.level
      ])
    ]],
    tableWidths: [[6, 52, 10, 10, 10, 12]]
  });

  // "Bu %68 nereden geldi?" sorusunun cevabı. İki parça hâlinde üretilir:
  // özet (kaç soru, kaç öğrenci, kaç düzeltme) ve ayrıntı (soru bazında
  // yüzdeler). Ekranda özet <summary>, ayrıntı açılır gövde olur; indirilen
  // Word/PDF belgesinde ikisi tek bir düz metin hücresi hâlinde birleşir -
  // orada açılır etkileşim anlamsız, ama sayıların belgede olması jüri
  // karşısında savunulabilirliğin ta kendisi.
  const outcomeEvidence = (outcome) => {
    const evidence = outcome.evidence || {};
    // Kanıt backend'de, yüzdenin hesaplandığı yerde üretiliyor
    // (backend/app/approved_data_analyzer.py). Gelmediyse (eski analiz,
    // kaydedilmiş çalışma) eski davranışa düşülür: yalnız soru numaraları.
    const questions = Array.isArray(evidence.questions) ? evidence.questions : [];
    if (!questions.length) {
      return { summary: relatedQuestionsForOutcome(outcome.outcomeCode, outcome.outcomeTheme), detail: "" };
    }
    const corrected = Number(evidence.correctedCellCount) || 0;
    const summary = [
      `${evidence.questionCount} sorudan hesaplandı`,
      `${evidence.participatingStudentCount} katılımcı öğrenci`,
      corrected ? `${corrected} hücre öğretmen tarafından düzeltildi` : "öğretmen düzeltmesi yok"
    ].join(" · ");
    const detail = [
      questions.map((question) => `Soru ${question.number}: ${formatPercent(question.successRate)}`).join(", "),
      `Toplam ${formatNumber(evidence.earnedScore)} / ${formatNumber(evidence.possibleScore)} puan`
    ].filter(Boolean).join(" — ");
    return { summary, detail };
  };

  const buildOutcomeBlock = () => {
    const outcomes = getAnalysis().outcomes || [];
    const evidences = outcomes.map(outcomeEvidence);
    const rows = outcomes.map((outcome, index) => [
      [normalizeText(outcome.outcomeTheme), normalizeText(outcome.outcomeCode || outcome.learningOutcome), normalizeText(outcome.outcomeSkill)].filter(Boolean).join(" — "),
      [evidences[index].summary, evidences[index].detail].filter(Boolean).join(" — "),
      formatPercent(outcome.successRate),
      successLevel(outcome.successRate),
      normalizeText(outcome.decision)
    ]);
    return {
      heading: "D. ÖĞRENME ÇIKTILARI VE ÖĞRENME KANITLARI ANALİZİ",
      paragraphs: ["Öğrenme kanıtının dayanağı, gerçekleşme düzeyinin hangi sorulardan ve kaç öğrencinin öğretmen tarafından onaylanan puanlarından hesaplandığını gösterir."],
      // Ekranda 2. sütun açılır bir kanıta dönüşür; diğer render hedefleri
      // (PDF gövdesi, Word ve PDF dışa aktarıcıları) blok modelini genel
      // olarak tükettiği için bu alanı hiç görmez ve düz metin basmaya
      // devam eder - o dosyalarda hiçbir değişiklik gerekmiyor.
      details: { column: 1, summaries: evidences.map((evidence) => evidence.summary) },
      tables: [[["Öğrenme Çıktısı", "Öğrenme Kanıtının Dayanağı", "Gerçekleşme Düzeyi (%)", "Gelişim Düzeyi", "Kanıta Dayalı Kısa Değerlendirme"], ...rows]],
      tableWidths: [[23, 29, 9, 13, 26]]
    };
  };

  const buildPedagogyBlock = () => {
    const outcomes = getAnalysis().outcomes || [];
    const label = (item) => [normalizeText(item.outcomeCode || item.learningOutcome), normalizeText(item.outcomeDescription || item.outcomeSkill)].filter(Boolean).join(" — ") || "Öğrenme çıktısı";
    const list = (items) => items.length
      ? items.map((item) => `${label(item)} (${formatPercent(item.successRate)})`).join("; ")
      : EMPTY_MARK;
    const above = outcomes.filter((item) => Number(item.successRate) >= 0.85);
    const expected = outcomes.filter((item) => Number(item.successRate) >= 0.70 && Number(item.successRate) < 0.85);
    const developing = outcomes.filter((item) => Number(item.successRate) >= 0.50 && Number(item.successRate) < 0.70);
    const priority = outcomes.filter((item) => Number(item.successRate) < 0.50);
    const noPriority = priority.length === 0;
    return {
      heading: "E. PEDAGOJİK DEĞERLENDİRME",
      paragraphs: [noPriority
        ? "MAHİR değerlendirme ölçütlerine göre öncelikli gelişim desteği gerektiren bir alan tespit edilmedi."
        : "Öğrenme kanıtları, öncelikli gelişim desteği gerektiren alanlar bulunduğunu göstermektedir."],
      tables: [[
        ["Değerlendirme Boyutu", "Kanıta Dayalı Pedagojik Sonuç"],
        ["Beklenen düzeyin üzerinde", list(above)],
        ["Beklenen düzeyde", list(expected)],
        ["Gelişimi sürmekte", list(developing)],
        ["Öncelikli gelişim desteği", list(priority)],
        ["Bütüncül değerlendirme", "Öğrenme kanıtları her öğrenme çıktısının kendi soru ve beceri bağlamı korunarak değerlendirilmiştir."]
      ]],
      tableWidths: [[28, 72]]
    };
  };

  // "Bu teşhis nereden geldi?" sorusunun cevabı: hangi belgenin hangi sayfası.
  // D bölümündeki "Kanıtları Gör" bir ORANIN hangi puanlardan geldiğini
  // söylüyor; bu da bir TEŞHİSİN hangi müfredat sayfasından geldiğini.
  //
  // Sayfa numaraları orijinal PDF'e göre (backend `_merge_rag_sources`).
  // Ardışık sayfalar aralığa indirgeniyor: "s. 66-68", "s. 66, 71" - sekiz
  // getirim isabetinin sayfa listesi aksi hâlde hücreyi doldururdu.
  const pageRanges = (pages) => {
    const sorted = [...new Set((pages || []).filter((page) => Number.isInteger(page) && page > 0))]
      .sort((a, b) => a - b);
    const parts = [];
    let start = null;
    let previous = null;
    sorted.forEach((page) => {
      if (start === null) { start = previous = page; return; }
      if (page === previous + 1) { previous = page; return; }
      parts.push(start === previous ? `${start}` : `${start}-${previous}`);
      start = previous = page;
    });
    if (start !== null) parts.push(start === previous ? `${start}` : `${start}-${previous}`);
    return parts.join(", ");
  };

  // Belgenin RESMÎ adı uzun ("Ortaöğretim Türk Dili ve Edebiyatı Dersi Öğretim
  // Programı - Türkiye Yüzyılı Maarif Modeli (2024)") ve her satırda tekrarlanması
  // tabloyu okunamaz kılıyordu. Akademik atıf düzeni: hücrede kısa atıf, belgenin
  // tam adı tablonun ALTINDA dipnotta - bir kez.
  //
  // Tek belge (olağan durum): hücrede "(s. 66-67)", dipnotta "Kaynak: <tam ad>".
  // Birden çok belge: hücrede "(K1, s. 66-67)", dipnotta "K1: <tam ad>".
  const documentLabels = (outcomes) => {
    const names = [];
    outcomes.forEach((outcome) => {
      (Array.isArray(outcome.ragSources) ? outcome.ragSources : []).forEach((source) => {
        const name = normalizeText(source?.documentName);
        if (name && !names.includes(name)) names.push(name);
      });
    });
    // Tek kaynakta işaretçiye gerek yok - "K1" yalnız gürültü olurdu.
    return new Map(names.map((name, index) => [name, names.length > 1 ? `K${index + 1}` : ""]));
  };

  const sourceReference = (outcome, labels) => {
    const sources = Array.isArray(outcome.ragSources) ? outcome.ragSources : [];
    const cited = sources
      .map((source) => {
        const name = normalizeText(source?.documentName);
        if (!name) return "";
        const marker = labels.get(name) || "";
        const pages = pageRanges(source?.pages);
        const parts = [marker, pages ? `s. ${pages}` : ""].filter(Boolean);
        // Ne işaretçi ne sayfa varsa (tek belge, sayfasız) atıf anlamsız -
        // dipnot zaten belgeyi adıyla söylüyor.
        return parts.join(", ");
      })
      .filter(Boolean);
    return cited.length ? `(${cited.join("; ")})` : "";
  };

  const sourceNotes = (labels) => {
    if (!labels.size) return [];
    const entries = [...labels].map(([name, marker]) => (marker ? `${marker}: ${name}` : name));
    return [`Kaynak: ${entries.join(" · ")}`];
  };

  const buildDevelopmentNeedsBlock = () => {
    const outcomes = getAnalysis().outcomes || [];
    const labels = documentLabels(outcomes);
    const direction = (rate) => rate >= 0.85 ? "Zenginleştirme" : rate >= 0.70 ? "Derinleştirme ve sürdürme" : rate >= 0.50 ? "Gelişimi destekleme" : "Öncelikli destekleme";
    const rows = outcomes.map((item) => {
      const focus = [normalizeText(item.componentLabel), normalizeText(item.outcomeCode || item.learningOutcome), normalizeText(item.outcomeDescription || item.outcomeSkill)].filter(Boolean).join(" — ");
      const evidence = `Gerçekleşme düzeyi ${formatPercent(item.successRate)}; ${successLevel(item.successRate).toLocaleLowerCase("tr-TR")}.`;
      const rawRecommendation = normalizeText(item.ragContext).replace(/\bBAĞLAM(?:'daki|daki|da)?\b/gi, "doğrulanmış kaynak");
      const recommendation = isUseful(rawRecommendation) ? rawRecommendation : EMPTY_MARK;
      return [focus || "Öğrenme çıktısı", evidence, direction(Number(item.successRate)), [recommendation, sourceReference(item, labels)].filter(Boolean).join(" ")];
    });
    return {
      heading: getAnalysis().assessmentScope === "language-composite" ? "E. ÖĞRENMEYİ DESTEKLEME VE ZENGİNLEŞTİRME ÖNERİLERİ" : "F. ÖĞRENMEYİ DESTEKLEME VE ZENGİNLEŞTİRME ÖNERİLERİ",
      paragraphs: ["Öneriler, öğretmen tarafından onaylanan öğrenme kanıtları ile seçilmiş öğrenme çıktıları ve doğrulanmış eğitim kaynakları esas alınarak hazırlanmıştır. Uygulanacak öğrenme yaşantısına öğretmen karar verir."],
      tables: [[["Öğrenme Odağı", "Öğrenme Kanıtının Gösterdiği Düzey", "Pedagojik Yön", "Kaynak Temelli Öneri"], ...rows]],
      tableWidths: [[24, 20, 18, 38]],
      notes: sourceNotes(labels)
    };
  };

  const buildSourceBlock = () => {
    const analysis = getAnalysis();
    const evidence = analysis.assessmentScope === "language-composite" ? (analysis.componentEvidence || []) : (analysis.outcomes || []);
    const collected = new Map();
    evidence.forEach((item) => {
      (Array.isArray(item.ragSources) ? item.ragSources : []).forEach((source) => {
        const name = normalizeText(source.documentName);
        if (!name) return;
        const current = collected.get(name) || { name, type: normalizeText(source.documentType || source.sourceType) || "Doğrulanmış eğitim kaynağı", pages: [], focuses: [] };
        current.pages.push(...(Array.isArray(source.pages) ? source.pages : []));
        const focus = normalizeText(item.outcomeCode || item.learningOutcomeCode || item.learningOutcome);
        if (focus && !current.focuses.includes(focus)) current.focuses.push(focus);
        collected.set(name, current);
      });
    });
    const rows = [...collected.values()].map((source) => [
      source.type,
      source.name,
      source.focuses.length ? source.focuses.join(", ") : EMPTY_MARK,
      pageRanges(source.pages) ? `s. ${pageRanges(source.pages)}` : EMPTY_MARK,
      "Pedagojik değerlendirme ve kaynak temelli önerinin doğrulanması"
    ]);
    if (!rows.length) rows.push([EMPTY_MARK, EMPTY_MARK, EMPTY_MARK, EMPTY_MARK, EMPTY_MARK]);
    return {
      heading: analysis.assessmentScope === "language-composite" ? "F. ANALİZDE YARARLANILAN KAYNAKLAR VE DAYANAKLAR" : "G. ANALİZDE YARARLANILAN KAYNAKLAR VE DAYANAKLAR",
      paragraphs: ["Bu bölüm, analiz ve kaynak temelli öneriler hazırlanırken MAHİR tarafından gerçekten kullanılan doğrulanmış kaynakları gösterir."],
      tables: [[["Kaynak Türü", "Kaynağın Resmî Adı", "İlgili Öğrenme Odağı", "Kullanılan Bölüm/Sayfa", "Rapordaki Kullanım Amacı"], ...rows]],
      tableWidths: [[16, 30, 17, 15, 22]],
      notes: ["Nicel sonuçlar öğretmen tarafından onaylanan sınav verilerinden hesaplanmış; pedagojik açıklama ve öneriler yalnız tabloda belirtilen doğrulanmış kaynaklarla sınırlandırılmıştır."]
    };
  };

  const buildDocumentInfoBlock = () => {
    const exam = getExam();
    const composite = getAnalysis().assessmentScope === "language-composite";
    const reference = `MAHIR-${getComponentType().toUpperCase()}-${dateText().replace(/\D/g, "")}`;
    return {
      heading: composite ? "G. RESMÎ İŞLEM VE ONAY BİLGİLERİ" : "H. RESMÎ İŞLEM VE ONAY BİLGİLERİ",
      paragraphs: ["Bu raporun verileri öğretmen tarafından onaylanmıştır. Kurumsal paraf ve elektronik imza işlemleri, yetkili elektronik belge yönetim sistemi üzerinden ayrıca tamamlanır."],
      tables: [
        [
          ["Düzenleyen Öğretmen", displayValue(verifiedInstitutionValue(exam, ["teacherName", "teacher", "teacherFullName"])), "Kurum", displayValue(verifiedInstitutionValue(exam, ["schoolName", "school", "institutionName"]))],
          ["Rapor Tarihi", dateText(), "MAHİR Rapor Referansı", reference],
          ["Veri Onayı", "Öğretmen tarafından onaylandı", "Kurumsal İşlem Durumu", "Paraf / elektronik imza bekliyor"],
          ["EBYS Evrak Sayısı", EMPTY_MARK, "EBYS İşlem Tarihi", EMPTY_MARK]
        ],
        [
          ["Düzenleyen Öğretmen", "Okul / Kurum Yetkilisi"],
          ["Ad Soyad: ................................................\nİmza: .........................................................", "Ad Soyad / Unvan: ...................................\nParaf / İmza: .............................................."]
        ]
      ],
      tableWidths: [[18, 32, 18, 32], [50, 50]],
      keepTogether: true
    };
  };

  const buildCompositeSummaryBlock = () => {
    const analysis = getAnalysis();
    const componentResults = analysis.componentResults || {};
    const order = ["written", "listening", "speaking"];
    const rows = order.map((component) => {
      const result = componentResults[component] || {};
      return [
        normalizeText(result.componentLabel),
        formatNumber(result.classAverage),
        formatPercent(result.weight),
        `${formatNumber(result.weightedContribution)} / ${formatNumber(result.maximumContribution)}`
      ];
    });
    return {
      heading: "B. AĞIRLIKLI GENEL SONUÇ",
      paragraphs: [
        analysis.notice || "Aynı öğrenci grubuna ait yazılı, dinleme/izleme ve konuşma puanları öğrenci bazında sırasıyla %70, %15 ve %15 ağırlıklarla birleştirilmiş; sınıf ortalaması bu birleşik puanlardan hesaplanmıştır."
      ],
      tables: [
        [["Bileşen", "Sınıf Ortalaması", "Ağırlık", "Genel Sonuca Katkı"], ...rows],
        [["Ağırlıklı Genel Sınıf Ortalaması", `${formatNumber(analysis.classAverage)} / 100`]]
      ],
      tableWidths: [[34, 22, 18, 26], [70, 30]]
    };
  };

  const buildCompositeOutcomeBlock = () => {
    const evidence = getAnalysis().componentEvidence || [];
    return {
      heading: "C. BİLEŞENLERE GÖRE ÖĞRENME ÇIKTILARI",
      paragraphs: ["Gerçekleşme oranı öğrenme çıktısının kendi sınav bileşenindeki düzeyini; ağırlıklı katkı ise ilgili bileşenin genel sonuçtaki payı içindeki karşılığını gösterir."],
      tables: [[
        ["Bileşen", "Öğrenme Çıktısı", "Alan Becerisi", "Gerçekleşme", "Ağırlıklı Karşılık", "Düzey"],
        ...evidence.map((item) => [
          normalizeText(item.componentLabel),
          [normalizeText(item.learningOutcomeTheme), normalizeText(item.learningOutcomeCode), normalizeText(item.learningOutcomeDescription)].filter(Boolean).join(" — "),
          normalizeText(item.fieldSkill),
          formatPercent(item.realizationRate),
          `${formatPercent(item.weightedContribution)} / ${formatPercent(item.componentWeight)}`,
          successLevel(item.realizationRate)
        ])
      ]],
      tableWidths: [[16, 34, 14, 12, 14, 10]]
    };
  };

  const buildCompositePedagogyBlock = () => {
    const evidence = getAnalysis().componentEvidence || [];
    const grouped = ["written", "listening", "speaking"].map((component) => {
      const items = evidence.filter((item) => item.componentType === component);
      const label = items[0]?.componentLabel || component;
      const strong = items.filter((item) => Number(item.realizationRate) >= 0.70);
      const development = items.filter((item) => Number(item.realizationRate) < 0.70);
      return [
        label,
        strong.length ? strong.map((item) => `${item.learningOutcomeCode} (${formatPercent(item.realizationRate)})`).join("; ") : EMPTY_MARK,
        development.length ? development.map((item) => `${item.learningOutcomeCode} (${formatPercent(item.realizationRate)})`).join("; ") : EMPTY_MARK
      ];
    });
    return {
      heading: "D. BÜTÜNCÜL PEDAGOJİK DEĞERLENDİRME",
      paragraphs: ["Bileşenler karşılaştırılırken öğrenme çıktılarının kendi kanıt bağlamı korunmuş; farklı dil becerileri tek bir yapay gerçekleşme yüzdesine indirgenmemiştir."],
      tables: [[["Bileşen", "Görece Güçlü Alanlar", "Gelişim İhtiyacı Gösteren Alanlar"], ...grouped]],
      tableWidths: [[18, 41, 41]]
    };
  };

  // --- Ajan izi: "bu raporu kim üretti"nin cevabı ---
  //
  // Sayılar backend'den (`AgentTrace.to_wire`), cümleler burada kuruluyor -
  // kanıt özetiyle (`outcomeEvidence`) aynı desen: hat sayı üretir, sunum
  // metni tarayıcıda kurulur.

  const durationText = (ms) => {
    const value = Number(ms);
    if (!Number.isFinite(value)) return "";
    return value >= 1000 ? `${formatNumber(value / 1000, 1)} sn` : `${Math.round(value)} ms`;
  };

  // Ajan slug'ına göre "ne yaptı" cümlesi. Bilinmeyen slug `description`a
  // düşer, böylece hatta yeni bir ajan eklendiğinde tablo bozulmaz - yalnız
  // daha genel bir cümle gösterir.
  const AGENT_TASK_TEXT = {
    "belge-anlama": (out) => [
      out.questionCount ? `${out.questionCount} soru` : "",
      out.studentCount ? `${out.studentCount} öğrenci` : ""
    ].filter(Boolean).join(", ") + " belge sözleşmesine çevrildi",
    "program-eslestirme": (out) => (out.programId
      ? `${out.outcomeCount || 0} öğrenme çıktısı öğretim programına bağlandı`
      : "Kayıtlı öğretim programı bulunamadı") +
      (out.unmappedQuestionCount ? `; ${out.unmappedQuestionCount} soru eşleşmedi` : ""),
    "olcme-degerlendirme": (out) =>
      `${out.measuredQuestionCount || 0} soru, ${out.measuredOutcomeCount || 0} öğrenme çıktısı hesaplandı` +
      (out.correctedCellTotal ? `; ${out.correctedCellTotal} öğretmen düzeltmesi` : ""),
    "pedagojik-analiz": (out) =>
      `${out.outcomeCount || 0} öğrenme çıktısı yorumlandı` +
      (out.curriculumGroundedCount ? `; ${out.curriculumGroundedCount} müfredat temelli teşhis` : ""),
    "raporlama": () => "Analiz raporu sözleşmesi kuruldu"
  };

  const agentTaskText = (entry) => {
    if (entry.skipped) return "Önceki adım tamamlanamadığı için çalıştırılmadı.";
    const build = AGENT_TASK_TEXT[entry.agent];
    const text = build ? normalizeText(build(entry.outputs || {})) : "";
    return text || normalizeText(entry.description) || "";
  };

  const agentStatusText = (entry) => {
    if (entry.skipped) return "Çalıştırılmadı";
    if (entry.failed) return "Tamamlanamadı";
    return "Tamam";
  };

  // Ortak dil modeli turu KENDİ satırında gösteriliyor, ajanlara bölüştürülmüyor.
  // Sebep: dokuz prompt tek istekte çözülüyor; süreyi paylaştırmak uydurma
  // olurdu ve tek istekli mimarinin kanıtını da yok ederdi. Ajan satırlarında
  // yalnız o ajanın kendi hesap süresi görünür (milisaniyeler) - aradaki fark
  // zaten anlatılmak istenen şey.
  const llmRoundRow = () => {
    const round = runtime().trace?.llmRound;
    if (!round?.promptCount) return null;
    return [
      "Dil modeli turu (ortak)",
      `${round.promptCount} istem tek istekte çözüldü`,
      durationText(round.durationMs),
      String(round.promptCount),
      round.ok ? "Tamam" : "Tamamlanamadı"
    ];
  };

  const buildAgentTraceBlock = () => {
    const agents = getTraceAgents();
    // İz yoksa bölüm HİÇ üretilmez: kaydedilmiş eski çalışmalarda ve genel dil
    // değerlendirmesinde rapor bugünküyle birebir aynı kalmalı.
    if (!agents.length) return null;
    const rows = agents.map((entry) => [
      normalizeText(entry.label || entry.agent),
      agentTaskText(entry),
      durationText(entry.durationMs),
      entry.llmCalls?.length ? String(entry.llmCalls.length) : "—",
      agentStatusText(entry)
    ]);
    const round = llmRoundRow();
    if (round) rows.push(round);
    return {
      heading: "I. ANALİZ SÜRECİ VE AJAN İZİ",
      paragraphs: [
        "Bu rapor, birbirine sırayla devreden uzman ajanlar tarafından üretilmiştir. " +
        "Aşağıdaki tablo her adımın ne yaptığını, ne kadar sürdüğünü ve dil modelini " +
        "kaç kez kullandığını gösterir. Sayısal sonuçların tamamı ölçme adımında " +
        "hesaplanır; dil modeli hiçbir puanı veya oranı üretmez. Dil modeline " +
        "ihtiyaç duyan adımların istemleri tek bir istekte toplanır; son satır o " +
        "ortak turu gösterir."
      ],
      tables: [[["Ajan", "Yaptığı İş", "Süre", "Dil Modeli Çağrısı", "Durum"], ...rows]]
    };
  };

  const buildCompositeBlocks = () => [
      { heading: "A. DEĞERLENDİRME VE EĞİTİM BAĞLAMI", paragraphs: [], tables: [buildContextTable()], tableWidths: [[18, 32, 18, 32]] },
      buildCompositeSummaryBlock(),
      buildCompositeOutcomeBlock(),
      buildCompositePedagogyBlock(),
      buildDevelopmentNeedsBlock(),
      buildSourceBlock(),
      buildDocumentInfoBlock()
    ].filter(Boolean);

  const buildComponentBlocks = () => [
      { heading: "A. SINAV VE EĞİTİM BAĞLAMI", paragraphs: [], tables: [buildContextTable()], tableWidths: [[18, 32, 18, 32]] },
      buildGeneralSummaryBlock(),
      buildQuestionBlock(),
      buildOutcomeBlock(),
      buildPedagogyBlock(),
      buildDevelopmentNeedsBlock(),
      buildSourceBlock(),
      buildDocumentInfoBlock()
    ].filter(Boolean);

  const getBlocks = () => getAnalysis().assessmentScope === "language-composite"
    ? buildCompositeBlocks()
    : buildComponentBlocks();

  const getReportModel = (reportElement) => {
    const model = {
      title: getReportTitle(),
      metadata: getMetadata(),
      blocks: getBlocks(),
      generatedAt: new Date().toISOString(),
      reportElement
    };
    model.validation = validateModel();
    return model;
  };

  const getPortableReportPayload = () => {
    const runtime = window.MAHIRReportRuntime || {};
    const analysis = runtime.analysis || {};
    const exam = runtime.exam || runtime.structuredData?.exam || {};
    const componentType = getComponentType();
    const componentLabel = getExamTypeLabel();
    const portableAnalysis = {
      summary: analysis.summary || {},
      questions: Array.isArray(analysis.questions) ? analysis.questions : [],
      outcomes: Array.isArray(analysis.outcomes) ? analysis.outcomes : [],
      assessmentScope: analysis.assessmentScope || exam.assessmentScope || "component",
      componentType,
      componentLabel,
      componentWeight: analysis.component?.componentWeight ?? null,
      cohortEvidence: (Array.isArray(analysis.students) ? analysis.students : []).map((student) => ({
        studentRef: normalizeText(student.studentRef),
        calculatedTotal: Number(student.calculatedTotal)
      })).filter((student) => /^Ö-\d{3,}$/.test(student.studentRef) && Number.isFinite(student.calculatedTotal))
    };
    return {
      schema: "mahir.analysis-report",
      schemaVersion: 1,
      generatedAt: new Date().toISOString(),
      exam: {
        province: exam.province || exam.city || "",
        district: exam.district || exam.town || "",
        schoolName: exam.schoolName || exam.school || exam.institutionName || "",
        teacherName: exam.teacherName || exam.teacher || exam.teacherFullName || "",
        academicYear: exam.academicYear || exam.educationYear || "",
        courseName: exam.courseName || exam.course || "",
        grade: exam.grade || "",
        classSection: exam.classSection || exam.className || "",
        term: exam.term || "",
        examSequence: exam.examSequence || "",
        examDate: exam.examDate || "",
        componentType,
        examType: componentLabel,
        weightingProfileId: exam.weightingProfileId || "",
        programId: exam.programId || "",
        teachingProgram: exam.teachingProgram || exam.curriculumName || "",
        assessmentBasis: exam.assessmentBasis || exam.measurementBasis || "",
        scenarioInfo: exam.scenarioInfo || exam.scenario || exam.sampleDocument || "",
        otherSources: exam.otherSources || exam.otherReferences || "",
        documentNo: exam.documentNo || exam.reportNo || "",
        approvalInfo: exam.approvalInfo || exam.transmissionInfo || ""
      },
      analysis: portableAnalysis,
      privacy: {
        scope: "pseudonymous-cohort-evidence",
        excludedFields: ["studentNo", "fullName", "tckn", "schoolNameFromLlmContext", "teacherNameFromLlmContext"]
      }
    };
  };

  const cell = (tag, text) => {
    const element = document.createElement(tag);
    element.textContent = text || "";
    return element;
  };

  // Ekran önizlemesini "hoş" kılan görsel katman: bilinen düzey metinlerini
  // renkli rozete, saf yüzde hücrelerini mini bir çubuğa çevirir. Bu katman
  // SADECE ekranda (renderPreviewBody) çalışır - PDF/Word çıktısı hâlâ
  // getReportModel'in düz metin hücrelerinden üretiliyor, burada hiçbir
  // sayı veya oran değişmez, yalnız aynı metin görsel olarak vurgulanır.
  const LEVEL_TONE_MAP = new Map([
    ["Beklenen düzeyin üzerinde", "excellent"],
    ["Beklenen düzeyde", "good"],
    ["Gelişimi sürmekte", "developing"],
    ["Gelişim desteği öncelikli", "priority"],
    ["Zenginleştirme", "excellent"],
    ["Derinleştirme ve sürdürme", "good"],
    ["Gelişimi destekleme", "developing"],
    ["Öncelikli destekleme", "priority"]
  ].map(([text, tone]) => [normalizeForCompare(text), tone]));
  const levelTone = (text) => LEVEL_TONE_MAP.get(normalizeForCompare(text)) || "";

  const percentTone = (numeric) => {
    if (numeric >= 85) return "excellent";
    if (numeric >= 70) return "good";
    if (numeric >= 50) return "developing";
    return "priority";
  };

  // Sütun başlığı "gerçekleşme" veya "başarı" içermiyorsa (ör. "Ağırlık" gibi
  // bir dağılım yüzdesi) çubuk çizilmez - o yüzdenin renk anlamı başarı
  // düzeyi değildir, çubuk yanlış bir yorum önerirdi.
  const isPerformancePercentHeading = (heading) => {
    const normalized = normalizeForCompare(heading);
    return normalized.includes("gerceklesme") || normalized.includes("basari");
  };

  const decoratePreviewCell = (td, text, columnIsPerformancePercent) => {
    const value = String(text ?? "");
    const tone = levelTone(value);
    if (tone) {
      const badge = document.createElement("span");
      badge.className = `level-badge level-badge--${tone}`;
      badge.textContent = value;
      td.replaceChildren(badge);
      return;
    }
    const percentMatch = columnIsPerformancePercent && value.match(/^%(-?\d+(?:,\d+)?)$/);
    const numeric = percentMatch ? Number(percentMatch[1].replace(",", ".")) : NaN;
    if (percentMatch && Number.isFinite(numeric)) {
      const wrap = document.createElement("span");
      wrap.className = "percent-cell";
      const bar = document.createElement("span");
      bar.className = "percent-cell-bar";
      bar.dataset.tone = percentTone(numeric);
      bar.style.setProperty("--pct", `${Math.max(0, Math.min(100, numeric))}%`);
      const label = document.createElement("span");
      label.className = "percent-cell-label";
      label.textContent = value;
      wrap.append(bar, label);
      td.replaceChildren(wrap);
    }
  };

  // Kanıt hücresini ekranda açılır hâle getirir: özet her zaman görünür,
  // soru bazındaki ayrıntı tıklayınca açılır. Özet metni hücrenin başında
  // olduğu için geri kalanı ayrıntı sayılır; ikisi de aynı düz metinden
  // türetildiğinden ekran ile belge asla farklı şey söyleyemez.
  const evidenceCell = (text, summaryText) => {
    const td = document.createElement("td");
    const value = String(text || "");
    const summary = String(summaryText || "");
    if (!summary || !value.startsWith(summary) || value.length <= summary.length) {
      td.textContent = value;
      return td;
    }
    const details = document.createElement("details");
    details.className = "evidence-details";
    const summaryElement = document.createElement("summary");
    summaryElement.textContent = summary;
    const body = document.createElement("p");
    body.className = "evidence-detail";
    body.textContent = value.slice(summary.length).replace(/^\s*—\s*/, "");
    details.append(summaryElement, body);
    td.append(details);
    return td;
  };

  const renderTable = (rows, details = null, widths = null, visual = false) => {
    const table = document.createElement("table");
    if (Array.isArray(widths) && widths.length) {
      const colgroup = document.createElement("colgroup");
      widths.forEach((width) => {
        const col = document.createElement("col");
        col.style.width = `${width}%`;
        colgroup.append(col);
      });
      table.append(colgroup);
      table.style.tableLayout = "fixed";
    }
    const headerRow = rows[0] || [];
    const performancePercentColumns = visual
      ? headerRow.map((heading) => isPerformancePercentHeading(heading))
      : [];
    rows.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      row.forEach((item, columnIndex) => {
        const isEvidence = details && rowIndex > 0 && columnIndex === details.column;
        const td = isEvidence
          ? evidenceCell(item, details.summaries?.[rowIndex - 1])
          : cell(rowIndex === 0 ? "th" : "td", item);
        if (visual && !isEvidence && rowIndex > 0) decoratePreviewCell(td, item, performancePercentColumns[columnIndex]);
        tr.append(td);
      });
      table.append(tr);
    });
    return table;
  };

  // Dipnot: tablodan SONRA gelen küçük punto açıklama. `paragraphs` bu işi
  // göremezdi - o alan tablonun ÖNÜNDE çiziliyor (dört render hedefinde de).
  const appendNotes = (section, block) => {
    (block.notes || []).forEach((note) => {
      if (!isUseful(note)) return;
      const p = document.createElement("p");
      p.className = "report-note";
      p.textContent = note;
      section.append(p);
    });
  };

  const renderOutputBody = (reportElement, model) => {
    const body = reportElement.querySelector("[data-output-body]");
    if (!body) return;
    body.replaceChildren();
    model.blocks.forEach((block) => {
      const section = document.createElement("section");
      section.className = "report-output-section";
      const heading = document.createElement("h3");
      heading.className = "report-output-section-title";
      heading.textContent = block.heading;
      section.append(heading);
      block.paragraphs.forEach((paragraph) => {
        if (!isUseful(paragraph)) return;
        const p = document.createElement("p");
        p.textContent = paragraph;
        section.append(p);
      });
      // Kasıtlı olarak `block.details` GEÇİLMİYOR: bu gövde PDF'e olduğu gibi
      // çizildiği için kapalı bir <details> orada kanıtı görünmez kılardı.
      block.tables.forEach((tableRows, tableIndex) => section.append(renderTable(tableRows, null, block.tableWidths?.[tableIndex])));
      appendNotes(section, block);
      body.append(section);
    });
  };

  const renderPreviewBody = (reportElement, model) => {
    const body = reportElement.querySelector("[data-report-preview-sections]");
    if (!body) return;
    body.replaceChildren();
    model.blocks.forEach((block) => {
      const section = document.createElement("article");
      section.className = "report-section";
      const heading = document.createElement("h3");
      heading.textContent = block.heading;
      section.append(heading);
      block.paragraphs.forEach((paragraph) => {
        if (!isUseful(paragraph)) return;
        const p = document.createElement("p");
        p.textContent = paragraph;
        section.append(p);
      });
      block.tables.forEach((tableRows, tableIndex) => section.append(renderTable(tableRows, block.details, block.tableWidths?.[tableIndex], true)));
      appendNotes(section, block);
      body.append(section);
    });
  };

  const syncOutputHeader = (reportElement) => {
    if (!reportElement) return null;
    const model = getReportModel(reportElement);
    const titleTarget = reportElement.querySelector("[data-output-title]");
    const visibleTitleTarget = reportElement.querySelector("#report-title");
    const list = reportElement.querySelector("[data-output-header] dl");
    if (titleTarget) titleTarget.textContent = model.title;
    if (visibleTitleTarget) visibleTitleTarget.textContent = model.title;
    if (list) {
      list.replaceChildren();
      model.metadata.forEach((item) => {
        const wrapper = document.createElement("div");
        const dt = document.createElement("dt");
        const dd = document.createElement("dd");
        dt.textContent = item.label;
        dd.textContent = item.value;
        wrapper.append(dt, dd);
        list.append(wrapper);
      });
    }
    renderOutputBody(reportElement, model);
    renderPreviewBody(reportElement, model);
    return model;
  };

  const getOutputStatusMessage = (model) => model?.validation?.message || validateModel().message;

  window.MAHIRReportExport = {
    design,
    getReportModel,
    getPortableReportPayload,
    getDownloadFilename,
    syncOutputHeader,
    validateModel,
    getOutputStatusMessage,
    normalizeText,
    formatNumber,
    formatPercent,
    // Analiz ekranı da aynı cümleleri kullanıyor (bkz. script.js
    // renderAgentTrace) - ekran ile rapor asla farklı şey söylememeli.
    agentTaskText,
    agentStatusText,
    durationText
  };
})();
