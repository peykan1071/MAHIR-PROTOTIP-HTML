(function () {
  "use strict";

  const DEMO_NOTICE = "EBYS entegrasyonu demo ortamında simüle edilmektedir. Demo: Bu işlem gerçek EBYS sistemine belge göndermez.";
  const text = (value) => String(value ?? "").trim();
  const metadataMap = (model) => Object.fromEntries((model?.metadata || []).map((item) => [item.label, text(item.value)]));

  const buildPackage = (model, filename) => {
    const metadata = metadataMap(model);
    const missing = ["Okul/Kurum Adı", "Öğretmenin Adı Soyadı", "Ders", "Sınıf/Şube", "Dönem"]
      .filter((key) => !metadata[key] || metadata[key] === "—");
    const reportType = metadata["Sınav Türü"] || "Sınav Analizi";
    const course = metadata.Ders || "ders";
    const classSection = metadata["Sınıf/Şube"] || "sınıf/şube";
    const teacherName = metadata["Öğretmenin Adı Soyadı"] || "—";
    const schoolName = metadata["Okul/Kurum Adı"] || "—";
    const attachments = [{ order: 1, name: filename, type: "Ana Analiz Raporu" }];
    if (reportType === "Genel Değerlendirme") {
      [
        "MAHIR_Yazili_Sinav_Sonuclari_Analiz_Raporu.docx",
        "MAHIR_Dinleme_Izleme_Sinavi_Sonuclari_Analiz_Raporu.docx",
        "MAHIR_Konusma_Sinavi_Sonuclari_Analiz_Raporu.docx"
      ].forEach((name, index) => attachments.push({ order: index + 2, name, type: "Dayanak Bileşen Raporu" }));
    }
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
        subject: `${course} ${classSection} ${reportType} sonuçlarının değerlendirilmesi`,
        body: `${course} dersi ${classSection} sınıf/şubesine ait ${reportType.toLocaleLowerCase("tr-TR")} sonuçları MAHİR tarafından öğretmen onaylı öğrenme kanıtları üzerinden analiz edilmiştir. İncelenmek ve gerekli kurumsal işlemlerde değerlendirilmek üzere analiz raporu ekte sunulmuştur.`,
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
      td.textContent = value;
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

    prepare.addEventListener("click", () => {
      const report = document.querySelector("#report-screen");
      const api = window.MAHIRReportExport;
      const model = api?.getReportModel?.(report);
      if (!model?.validation?.valid) {
        status.textContent = model?.validation?.message || "Raporun zorunlu kurumsal bilgileri tamamlanmalıdır.";
        return;
      }
      currentPackage = buildPackage(model, api.getDownloadFilename("docx"));
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
