(() => {
  const REPORT_TITLE = "SINAV SONUÇLARI ANALİZ RAPORU";
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

  const getExam = () => runtime().structuredData?.exam || runtime().analysis?.exam || {};
  const getStructuredQuestions = () => runtime().structuredData?.questions || [];
  const getStructuredStudents = () => runtime().structuredData?.students || [];
  const getAnalysis = () => runtime().analysis || {};
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

  const successLevel = (rate, fallback = "") => {
    if (isUseful(fallback)) return normalizeText(fallback);
    const value = Number(rate);
    if (!Number.isFinite(value)) return "Belirlenmedi";
    if (value >= 0.85) return "Çok güçlü";
    if (value >= 0.70) return "Güçlü";
    if (value >= 0.50) return "Gelişmekte";
    return "Destek gerekli";
  };

  const getQuestionDescription = (question) => {
    const structured = getStructuredQuestions().find((item) => Number(item.number) === Number(question.number)) || {};
    return valueFrom(question, ["outcomeDescription", "learningOutcome", "description"]) || valueFrom(structured, ["outcomeDescription", "learningOutcome", "description"]) || valueFrom(question, ["outcomeCode"]) || "Öğrenme çıktısı belirtilmedi";
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
      return {
        number: question.number ?? structuredQuestion.number ?? index + 1,
        outcomeCode: normalizeText(question.outcomeCode || structuredQuestion.outcomeCode),
        outcomeTheme: normalizeText(question.outcomeTheme || structuredQuestion.outcomeTheme),
        outcomeDescription: getQuestionDescription({ ...structuredQuestion, ...question }),
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
    .filter((question) => normalizeText(question.outcomeCode) === normalizeText(outcomeCode)
      && (!outcomeTheme || normalizeText(question.outcomeTheme) === normalizeText(outcomeTheme)))
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
    const schoolName = valueFrom(exam, ["schoolName", "school", "institutionName"]);
    const teacherName = valueFrom(exam, ["teacherName", "teacher", "teacherFullName"]);
    const wordCourse = valueFrom(exam, ["course"]);
    const wordClass = valueFrom(exam, ["classSection", "grade", "className"]);

    return [
      { label: "İl", value: valueFrom(exam, ["province", "city"]) },
      { label: "İlçe", value: valueFrom(exam, ["district", "town"]) },
      { label: "Okul/Kurum Adı", value: schoolName, source: "word", required: true },
      { label: "Öğretmenin Adı Soyadı", value: teacherName, source: "word", required: true },
      { label: "Eğitim Öğretim Yılı", value: valueFrom(exam, ["academicYear", "educationYear"]) },
      { label: "Öğretim Kademesi", value: context.educationStage, source: "context" },
      { label: "Okul Türü", value: context.schoolType, source: "context" },
      { label: "Program Türü", value: context.programType, source: "context" },
      { label: "Alan/Dal", value: context.fieldBranch, source: "context" },
      { label: "Ders", value: wordCourse || context.course, source: wordCourse ? "word" : "context", required: true },
      { label: "Ders Türü", value: context.courseType, source: "context" },
      { label: "Sınıf/Şube", value: wordClass || context.gradeLevel, source: wordClass ? "word" : "context", required: true },
      { label: "Dönem", value: valueFrom(exam, ["term"]) },
      { label: "Sınav Türü", value: valueFrom(exam, ["examType"]) },
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
    if (!isUseful(valueFrom(exam, ["course"]) || context.course)) missing.push("Ders");
    if (!isUseful(valueFrom(exam, ["classSection", "grade", "className"]) || context.gradeLevel)) missing.push("Sınıf/Şube");
    if (!isUseful(valueFrom(exam, ["province", "city"]))) missing.push("İl");
    if (!isUseful(valueFrom(exam, ["district", "town"]))) missing.push("İlçe");
    if (!isUseful(valueFrom(exam, ["academicYear", "educationYear"]))) missing.push("Eğitim Öğretim Yılı");
    if (!isUseful(valueFrom(exam, ["term"]))) missing.push("Dönem");
    if (!isUseful(valueFrom(exam, ["examDate"]))) missing.push("Sınav Tarihi");
    if (!isUseful(valueFrom(exam, ["teachingProgram", "curriculumName"]))) missing.push("Öğretim Programı");
    if (!isUseful(valueFrom(exam, ["assessmentBasis", "measurementBasis"]))) missing.push("Ölçme ve Değerlendirme Dayanağı");
    if (!isUseful(valueFrom(exam, ["documentNo", "reportNo"]))) missing.push("Belge / Rapor No");
    if (!isUseful(valueFrom(exam, ["approvalInfo", "transmissionInfo"]))) missing.push("İletim / Onay Bilgisi");
    if (!summary.participatingStudentCount) missing.push("Analiz Edilen Öğrenci Sayısı");

    const conflicts = [
      conflictPair("Ders", valueFrom(exam, ["course"]), context.course),
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
    ["Program Türü", metadataValue("Program Türü"), "Alan / Dal", metadataValue("Alan/Dal")],
    ["Ders", metadataValue("Ders"), "Sınıf / Şube", metadataValue("Sınıf/Şube")],
    ["Dönem", metadataValue("Dönem"), "Sınav Türü", metadataValue("Sınav Türü")],
    ["Sınav Tarihi", metadataValue("Sınav Tarihi"), "Analiz Edilen Öğrenci Sayısı", metadataValue("Analiz Edilen Öğrenci Sayısı")]
  ];

  const buildGeneralSummaryBlock = () => {
    const summary = getSummary();
    return {
      heading: "B. GENEL BAŞARI ÖZETİ",
      paragraphs: [`Genel değerlendirme: ${summary.participatingStudentCount || 0} öğrencinin sınav sonuçları değerlendirilmiştir.`],
      tables: [[
        ["Öğrenci Sayısı", "Sınav Ortalaması", "En Yüksek Puan", "En Düşük Puan", "Başarı Oranı"],
        [
          summary.participatingStudentCount || "",
          formatNumber(summary.classAverage),
          formatNumber(summary.highestScore),
          formatNumber(summary.lowestScore),
          formatPercent(summary.classSuccessRate)
        ]
      ]]
    };
  };

  // Ölçme ve Değerlendirme Ajanı'nın anomali bulgusu. Kapanış cümlesi kasıtlı:
  // bu bir GÖZLEM, karar veya öneri değil - DEVELOPMENT_CHARTER.md gereği MAHİR
  // etkinlik, yöntem veya telafi programı belirlemez. Bulgu yoksa paragraf hiç
  // eklenmez; "bir şey bulunmadı" satırı gürültüden başka bir şey olmaz.
  const anomalyParagraphs = () => {
    const finding = normalizeText(getSummary().anomalies);
    if (!isUseful(finding)) return [];
    return [
      `Ölçme ve Değerlendirme Ajanı'nın dikkat çektiği noktalar: ${finding} ` +
      "Bu gözlem hiçbir puanı veya oranı değiştirmez."
    ];
  };

  const buildQuestionBlock = () => ({
    heading: "C. SORU BAZLI BAŞARI ANALİZİ",
    paragraphs: anomalyParagraphs(),
    tables: [[
      ["Soru", "Öğrenme Çıktısı / Kazanım", "Azami Puan", "Ortalama", "Başarı %", "Durum"],
      ...getQuestionRows().map((question) => [
        String(question.number),
        question.outcomeDescription,
        formatNumber(question.maxScore),
        formatNumber(question.average),
        formatPercent(question.successRate),
        question.level
      ])
    ]]
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
      successLevel(outcome.successRate, outcome.category),
      normalizeText(outcome.decision)
    ]);
    return {
      heading: "D. ÖĞRENME ÇIKTILARI ANALİZİ",
      paragraphs: ["Başarı düzeyleri, rapor hazırlanırken kullanılan ölçütlere göre sınıflandırılır; gerekli görüldüğünde değerlendirme eşikleri açıklama bölümünde belirtilir. \"Hesaplama Dayanağı\" sütunu, her oranın hangi sorulardan ve kaç öğrenciden hesaplandığını gösterir."],
      // Ekranda 2. sütun açılır bir kanıta dönüşür; diğer render hedefleri
      // (PDF gövdesi, Word ve PDF dışa aktarıcıları) blok modelini genel
      // olarak tükettiği için bu alanı hiç görmez ve düz metin basmaya
      // devam eder - o dosyalarda hiçbir değişiklik gerekmiyor.
      details: { column: 1, summaries: evidences.map((evidence) => evidence.summary) },
      tables: [[["Öğrenme Çıktısı", "Hesaplama Dayanağı", "Başarı %", "Düzey", "Kanıt / Kısa Yorum"], ...rows]]
    };
  };

  const buildPedagogyBlock = () => {
    const outcomes = getAnalysis().outcomes || [];
    const strong = outcomes.filter((item) => Number(item.successRate) >= 0.70);
    const development = outcomes.filter((item) => Number(item.successRate) < 0.70);
    return {
      heading: "E. PEDAGOJİK DEĞERLENDİRME",
      paragraphs: [],
      tables: [[
        [`Güçlü öğrenme alanları: ${strong.map((item) => `${item.outcomeCode} (${formatPercent(item.successRate)})`).join("; ")}`],
        [`Geliştirilmesi gereken öğrenme alanları: ${development.map((item) => `${item.outcomeCode} (${formatPercent(item.successRate)})`).join("; ")}`],
        ["Değerlendirme, öğretmen tarafından onaylanan soru puanları ile resmî öğrenme çıktısı ve beceri eşleştirmeleri esas alınarak yapılmıştır."]
      ]]
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

  const sourceReference = (outcome) => {
    const sources = Array.isArray(outcome.ragSources) ? outcome.ragSources : [];
    const cited = sources
      .map((source) => {
        const name = normalizeText(source?.documentName);
        if (!name) return "";
        const pages = pageRanges(source?.pages);
        return pages ? `${name}, s. ${pages}` : name;
      })
      .filter(Boolean);
    return cited.length ? `(Kaynak: ${cited.join("; ")})` : "";
  };

  const buildDevelopmentNeedsBlock = () => {
    const outcomes = getAnalysis().outcomes || [];
    const targets = outcomes.filter((item) => Number(item.successRate) < 0.70);
    // ragContext yalnızca kayıtlı bir programda (bkz. backend/app/program_catalog.py)
    // ve RAG servisi yapılandırılmışsa dolu gelir - kapsam dışı derslerde sütun
    // hiç eklenmez, tablo bugünküyle birebir aynı kalır.
    const hasRagContext = targets.some((item) => isUseful(item.ragContext));
    const rows = targets.map((item, index) => {
      const row = [
        String(index + 1),
        `${item.outcomeCode || "Öğrenme Çıktısı"} (${formatPercent(item.successRate)})`,
        normalizeText(item.decision),
        Number(item.successRate) < 0.50 ? "Öncelikli" : "Gelişim ihtiyacı"
      ];
      // Kaynak, teşhisin ARDINA ekleniyor - ayrı sütun değil: A4 genişliğinde
      // tablo zaten beş sütun ve altıncısı okunabilirliği bozardı. Kaynağı
      // olmayan (eski analiz, kaydedilmiş çalışma) satır bugünkü gibi görünür.
      if (hasRagContext) {
        row.push([normalizeText(item.ragContext), sourceReference(item)].filter(Boolean).join(" "));
      }
      return row;
    });
    const header = ["Sıra", "Tespit Edilen İhtiyaç", "Değerlendirme Sonucu", "Öncelik Düzeyi"];
    if (hasRagContext) header.push("Kavramsal Bağlam");
    return {
      heading: "F. GELİŞİM İHTİYAÇLARI VE DEĞERLENDİRME SONUÇLARI",
      paragraphs: ["Bu bölüm uygulanacak etkinlik, kaynak, yöntem veya telafi programını belirlemez; yalnızca öğretmen onaylı sınav verilerinden hareketle gelişim ihtiyacını gösterir."],
      tables: [[header, ...rows]]
    };
  };

  const buildSourceBlock = () => {
    const context = getContext();
    const exam = getExam();
    const sourceScope = context.sourceScope || [];
    return {
      heading: "G. ANALİZDE ESAS ALINAN EĞİTİM BAĞLAMI VE KAYNAKLAR",
      paragraphs: ["Bu rapor; seçilen eğitim bağlamı, ilgili öğretim programı, ölçme ve değerlendirme esasları ile doğrulanmış sınav verileri esas alınarak hazırlanmıştır."],
      tables: [[
        ["Eğitim Bağlamı", sourceScope.join(" / "), "İnceleme Kapsamı", "Öğretmen tarafından onaylanan sınav verileri"],
        ["Öğretim Programı", valueFrom(exam, ["teachingProgram", "curriculumName"]), "Ölçme ve Değerlendirme Dayanağı", valueFrom(exam, ["assessmentBasis", "measurementBasis"])],
        ["Senaryo / Örnek Evrak", valueFrom(exam, ["scenarioInfo", "scenario", "sampleDocument"]) || "Bulunmuyor", "Diğer Dayanaklar", valueFrom(exam, ["otherSources", "otherReferences"]) || "Bulunmuyor"]
      ]]
    };
  };

  const buildDocumentInfoBlock = () => {
    const exam = getExam();
    return {
      heading: "H. BELGE BİLGİLERİ",
      paragraphs: [],
      tables: [[
        ["Düzenleyen Öğretmen", valueFrom(exam, ["teacherName", "teacher", "teacherFullName"]), "Kurum", valueFrom(exam, ["schoolName", "school", "institutionName"])],
        ["Rapor Tarihi", dateText(), "Belge / Rapor No", valueFrom(exam, ["documentNo", "reportNo"])],
        ["İletim / Onay Bilgisi", valueFrom(exam, ["approvalInfo", "transmissionInfo"]), "Belge Durumu", "Öğretmen tarafından onaylandı"]
      ]]
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

  const getBlocks = () => [
    { heading: "A. SINAV VE EĞİTİM BAĞLAMI", paragraphs: [], tables: [buildContextTable()] },
    buildGeneralSummaryBlock(),
    buildQuestionBlock(),
    buildOutcomeBlock(),
    buildPedagogyBlock(),
    buildDevelopmentNeedsBlock(),
    buildSourceBlock(),
    buildDocumentInfoBlock(),
    buildAgentTraceBlock()
  ].filter(Boolean);

  const getReportModel = (reportElement) => {
    const model = {
      title: REPORT_TITLE,
      metadata: getMetadata(),
      blocks: getBlocks(),
      generatedAt: new Date().toISOString(),
      reportElement
    };
    model.validation = validateModel();
    return model;
  };

  const cell = (tag, text) => {
    const element = document.createElement(tag);
    element.textContent = text || "";
    return element;
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

  const renderTable = (rows, details = null) => {
    const table = document.createElement("table");
    rows.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      row.forEach((item, columnIndex) => {
        const isEvidence = details && rowIndex > 0 && columnIndex === details.column;
        tr.append(isEvidence
          ? evidenceCell(item, details.summaries?.[rowIndex - 1])
          : cell(rowIndex === 0 ? "th" : "td", item));
      });
      table.append(tr);
    });
    return table;
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
      block.tables.forEach((tableRows) => section.append(renderTable(tableRows)));
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
      block.tables.forEach((tableRows) => section.append(renderTable(tableRows, block.details)));
      body.append(section);
    });
  };

  const syncOutputHeader = (reportElement) => {
    if (!reportElement) return null;
    const model = getReportModel(reportElement);
    const titleTarget = reportElement.querySelector("[data-output-title]");
    const list = reportElement.querySelector("[data-output-header] dl");
    if (titleTarget) titleTarget.textContent = model.title;
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
