(function () {
  "use strict";

  const DEMO_NOTICE = "EBYS entegrasyonu demo ortamında simüle edilmektedir. Demo: Bu işlem gerçek EBYS sistemine belge göndermez.";
  const text = (value) => String(value ?? "").trim();
  const metadataMap = (model) => Object.fromEntries((model?.metadata || []).map((item) => [item.label, text(item.value)]));
  const slashList = (values) => [...new Set(values.map(text).filter(Boolean))].join(" / ");
  const normalizedExamComponent = (value) => {
    const normalized = text(value).toLocaleLowerCase("tr-TR");
    if (normalized.includes("dinleme")) return "dinleme";
    if (normalized.includes("konuşma")) return "konuşma";
    if (normalized.includes("yazılı")) return "yazılı";
    return "";
  };

  const buildPackage = (model, filename, approvedReports = []) => {
    const metadata = metadataMap(model);
    const coveredClassSections = slashList(approvedReports.map((report) => report.classSection));
    const missing = ["Okul/Kurum Adı", "Öğretmenin Adı Soyadı", "Ders", "Sınıf/Şube", "Dönem"]
      .filter((key) => {
        if (key === "Sınıf/Şube" && coveredClassSections) return false;
        return !metadata[key] || metadata[key] === "—";
      });
    const reportType = metadata["Sınav Türü"] || "Sınav Analizi";
    const course = metadata.Ders || "ders";
    const classSection = metadata["Sınıf/Şube"] || coveredClassSections || "sınıf/şube";
    const teacherName = metadata["Öğretmenin Adı Soyadı"] || "—";
    const schoolName = metadata["Okul/Kurum Adı"] || "—";
    const coveredComponents = [...new Set(approvedReports.map((report) => normalizedExamComponent(report.examType)).filter(Boolean))];
    const metadataComponent = normalizedExamComponent(reportType);
    const isGeneralEvaluation = (!approvedReports.length && reportType === "Genel Değerlendirme")
      || ["yazılı", "dinleme", "konuşma"].every((component) => coveredComponents.includes(component));
    const coveredExamType = coveredComponents.length === 1 ? coveredComponents[0] : metadataComponent || "sınav";
    const classScope = coveredClassSections || classSection;
    const attachments = approvedReports.length
      ? approvedReports.map((report, index) => ({ order: index + 1, name: report.filename, type: `${report.label} Analiz Raporu` }))
      : [{ order: 1, name: filename, type: "Ana Analiz Raporu" }];
    if (reportType === "Genel Değerlendirme" && !approvedReports.length) {
      [
        "MAHIR_Yazili_Sinav_Sonuclari_Analiz_Raporu.docx",
        "MAHIR_Dinleme_Izleme_Sinavi_Sonuclari_Analiz_Raporu.docx",
        "MAHIR_Konusma_Sinavi_Sonuclari_Analiz_Raporu.docx"
      ].forEach((name, index) => attachments.push({ order: index + 2, name, type: "Dayanak Bileşen Raporu" }));
    }
    const reportWord = attachments.length > 1 ? "analiz raporları" : "analiz raporu";
    return {
      schema: "mahir.ebys-demo-package",
      schemaVersion: 1,
      simulation: true,
      notice: DEMO_NOTICE,
      status: missing.length ? "missing-information" : "draft",
      missingInformation: missing,
      routing: {
        addressee: "OKUL / KURUM MÜDÜRLÜĞÜNE",
        documentType: "Üst Yazı",
        process: "Bilgi ve gereği",
        nextStatus: "Paraf bekliyor"
      },
      coverLetter: {
        subject: isGeneralEvaluation
          ? `${course} ${classScope} yazılı, dinleme ve konuşma sınavları sonuçlarının değerlendirilmesi`
          : `${course} ${classScope} ${coveredExamType} sınav sonuçlarının değerlendirilmesi`,
        body: isGeneralEvaluation
          ? `${course} dersi ${classScope} sınıf/şubesine ait yazılı, dinleme ve konuşma sınavları sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere genel değerlendirme analiz raporları ekte sunulmuştur.`
          : `${course} dersi ${classScope} sınıf/şubesine ait ${coveredExamType} sınav sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere ${reportWord} ekte sunulmuştur.`,
        institutionName: schoolName,
        signatoryName: teacherName,
        signatoryRole: `${course} Öğretmeni`
      },
      attachments,
      officialFields: {
        ebysDocumentNumber: null,
        ebysTransactionDate: null,
        signatureStatus: "Elektronik imza bekliyor"
      }
    };
  };

  const renderPreview = (container, pkg) => {
    container.replaceChildren();
    const title = document.createElement("h4");
    title.textContent = "Resmî Yazı Taslağı";
    const table = document.createElement("table");
    const rows = [
      ["Muhatap", pkg.routing.addressee],
      ["Belge Türü", pkg.routing.documentType],
      ["Konu", pkg.coverLetter.subject],
      ["Metin", pkg.coverLetter.body],
      ["Ekler", pkg.attachments.map((item) => `Ek-${item.order}: ${item.name}`).join("\n")],
      ["İmza Makamı", pkg.coverLetter.signatoryRole],
      ["Sonraki İşlem", "Okul yönetimi parafı ve yetkili elektronik imza"]
    ];
    rows.forEach(([label, value]) => {
      const row = document.createElement("tr");
      const th = document.createElement("th");
      const td = document.createElement("td");
      th.textContent = label;
      if (label === "Ekler") {
        const attachmentList = document.createElement("div");
        attachmentList.className = "ebys-attachment-list";
        pkg.attachments.forEach((item) => {
          const attachment = document.createElement("div");
          attachment.textContent = `Ek-${item.order}: ${item.name}`;
          attachmentList.append(attachment);
        });
        td.append(attachmentList);
      } else {
        td.textContent = value;
      }
      row.append(th, td);
      table.append(row);
    });
    container.append(title, table);
    container.hidden = false;
  };

  const downloadPackage = (pkg) => {
    const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: "application/json;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "MAHIR_EBYS_Demo_Aktarim_Paketi.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  };

  const initialize = () => {
    const card = document.querySelector("[data-ebys-demo]");
    if (!card) return;
    const prepare = card.querySelector("[data-ebys-prepare]");
    const transfer = card.querySelector("[data-ebys-transfer]");
    const downloadLetter = card.querySelector("[data-ebys-download-letter]");
    const preview = card.querySelector("[data-ebys-preview]");
    const approvalWrap = card.querySelector("[data-ebys-approval-wrap]");
    const approval = card.querySelector("[data-ebys-approval]");
    const status = card.querySelector("[data-ebys-status]");
    let currentPackage = null;
    let approvalState = { total: 0, approved: 0, allApproved: false, reports: [] };

    const applyApprovalState = (state = {}) => {
      approvalState = { ...approvalState, ...state };
      prepare.disabled = !approvalState.allApproved;
      prepare.setAttribute("aria-disabled", String(prepare.disabled));
      if (!approvalState.allApproved) {
        status.textContent = approvalState.total
          ? `${approvalState.approved}/${approvalState.total} sınav raporu onaylandı. Tek üst yazı için bütün raporları onaylayınız.`
          : "Tek üst yazı hazırlanabilmesi için bütün sınav raporlarını ayrı ayrı kontrol edip onaylayınız.";
      } else {
        status.textContent = `${approvalState.approved} sınav raporunun tamamı onaylandı. Bu raporlar için tek üst yazı hazırlanabilir.`;
      }
    };
    document.addEventListener("mahir:report-approval-state", (event) => applyApprovalState(event.detail));

    prepare.addEventListener("click", () => {
      if (!approvalState.allApproved) return;
      const report = document.querySelector("#report-screen");
      const api = window.MAHIRReportExport;
      const model = api?.getReportModel?.(report);
      if (!model?.validation?.valid) {
        status.textContent = model?.validation?.message || "Raporun zorunlu kurumsal bilgileri tamamlanmalıdır.";
        return;
      }
      currentPackage = buildPackage(model, api.getDownloadFilename("docx"), approvalState.reports);
      if (currentPackage.missingInformation.length) {
        status.textContent = `Eksik bilgiler: ${currentPackage.missingInformation.join(", ")}.`;
        return;
      }
      renderPreview(preview, currentPackage);
      downloadLetter.hidden = false;
      approvalWrap.hidden = false;
      approval.checked = false;
      transfer.disabled = true;
      transfer.setAttribute("aria-disabled", "true");
      status.textContent = "Taslak hazırlandı. Öğretmen kontrolünden sonra demo aktarımı etkinleşir.";
    });

    downloadLetter.addEventListener("click", async () => {
      if (!currentPackage) return;
      const exporter = window.MAHIRDocxExporter;
      if (!exporter?.downloadOfficialLetterDocx) {
        status.textContent = "Üst yazı Word bileşeni yüklenemedi.";
        return;
      }
      await exporter.downloadOfficialLetterDocx(currentPackage);
      status.textContent = "Resmî üst yazı taslağı Word olarak indirildi. EBYS sayı ve tarih alanları taslakta boş bırakıldı.";
    });

    approval.addEventListener("change", () => {
      transfer.disabled = !approval.checked || !currentPackage;
      transfer.setAttribute("aria-disabled", String(transfer.disabled));
      if (approval.checked && currentPackage) {
        currentPackage.status = "ready-for-demo-transfer";
        status.textContent = "Taslak onaylandı; demo aktarımına hazır.";
      }
    });

    transfer.addEventListener("click", () => {
      if (!currentPackage || !approval.checked) return;
      currentPackage.status = "demo-transferred";
      currentPackage.routing.nextStatus = "Paraf bekliyor";
      currentPackage.demoTransferredAt = new Date().toISOString();
      downloadPackage(currentPackage);
      status.textContent = `Demo aktarımı tamamlandı. Paraf bekliyor. ${DEMO_NOTICE}`;
    });
  };

  window.MAHIREBYSDemo = { DEMO_NOTICE, buildPackage, initialize };
  document.addEventListener("DOMContentLoaded", initialize);
})();
