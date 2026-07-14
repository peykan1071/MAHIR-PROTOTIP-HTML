"use strict";

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
          setDataApprovalState(true);
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
    showScreen
  };
})();

document.addEventListener("DOMContentLoaded", () => {
  preparationManager.init();
  screenManager.init();
});