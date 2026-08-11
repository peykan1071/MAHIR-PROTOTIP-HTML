(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MAHIRScoreCorrections = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // Öğretmenin kaç puan hücresini düzelttiğini sayar. Ayrı bir modül olmasının
  // sebebi test edilebilirlik: script.js bir IIFE, içindeki hiçbir şey
  // node'dan çağrılamıyor - bu mantık ise kenar durumlarla dolu.
  //
  // Bu sayı, raporun "bu %68 nereden geldi?" sorusuna verdiği cevabın parçası
  // (bkz. assets/js/mahir-report-export-common.js, D bölümü). Zamanlama
  // kritik: script.js'te saveCurrentGroup() grubu DOM'dan (zaten düzeltilmiş
  // hâliyle) alıyor ve startNewGroup() hemen ardından structuredData'yı
  // sıfırlıyor - makinenin okuduğu özgün değerler o anda yok oluyor. Fark bu
  // yüzden grup kaydedilirken alınmak zorunda, sonradan hesaplanamaz.

  const toNumber = (value) => {
    if (value === null || value === undefined) return null;
    // script.js'teki numberValue() ile aynı normalizasyon: öğretmen "7,5"
    // yazdığında bu 7.5 ile aynı sayı sayılmalı, sahte bir düzeltme olmamalı.
    const text = String(value).trim().replace(",", ".");
    if (text === "") return null;
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  };

  const isCorrection = (originalValue, approvedValue) => {
    const original = toNumber(originalValue);
    // Makine bir değer üretmediyse ortada düzeltilecek bir şey yok: boş bir
    // hücrenin doldurulması "öğretmen doldurdu"dur, "makineyi düzeltti" değil.
    // Elle giriş modunda TÜM özgün değerler null olduğu için bu kural, ayrı
    // bir mod kontrolüne gerek kalmadan düzeltme sayısını 0'da tutar.
    if (original === null) return false;
    const approved = toNumber(approvedValue);
    // Dolu bir hücrenin boşaltılması düzeltmedir (makine yanlış okumuş,
    // öğretmen silmiş) - approved === null burada kasıtlı olarak sayılıyor.
    if (approved === null) return true;
    // Kayan nokta toleransı: 0.01 adımlı puan girişinde 7.10 ile 7.1 aynı.
    return Math.abs(original - approved) > 0.0001;
  };

  const scoresOf = (student) => (Array.isArray(student && student.scores) ? student.scores : []);

  // Satırlar teknik kimlikle (technicalId) eşleştirilir, dizideki sıra ile
  // değil: son incelemede gruplar birleştiğinde sıra kayabiliyor. Kimlik
  // bulunamazsa aynı indeksteki satıra düşülür (tek gruplu akışta sıra zaten
  // birebir aynı).
  const matchStudent = (originalStudents, approvedStudent, index) => {
    const technicalId = approvedStudent && approvedStudent.technicalId;
    if (technicalId) {
      const matched = originalStudents.find((student) => student && student.technicalId === technicalId);
      if (matched) return matched;
    }
    return originalStudents[index] || null;
  };

  const diffScores = (originalStudents, approvedStudents) => {
    const originals = Array.isArray(originalStudents) ? originalStudents : [];
    const approved = Array.isArray(approvedStudents) ? approvedStudents : [];
    const byQuestionIndex = {};
    let total = 0;

    approved.forEach((approvedStudent, index) => {
      const originalStudent = matchStudent(originals, approvedStudent, index);
      if (!originalStudent) return;
      const originalScores = scoresOf(originalStudent);
      scoresOf(approvedStudent).forEach((approvedScore, questionIndex) => {
        if (!isCorrection(originalScores[questionIndex], approvedScore)) return;
        byQuestionIndex[questionIndex] = (byQuestionIndex[questionIndex] || 0) + 1;
        total += 1;
      });
    });

    return { total, byQuestionIndex };
  };

  // Birden çok grubun (ve son incelemedeki ek düzenlemelerin) sayımlarını
  // toplar - her grup kendi farkını kaydettiği için tek bir toplam gerekiyor.
  const mergeCorrections = (...counts) => {
    const byQuestionIndex = {};
    let total = 0;
    counts.forEach((entry) => {
      const source = (entry && entry.byQuestionIndex) || {};
      Object.keys(source).forEach((questionIndex) => {
        const value = Number(source[questionIndex]) || 0;
        byQuestionIndex[questionIndex] = (byQuestionIndex[questionIndex] || 0) + value;
        total += value;
      });
    });
    return { total, byQuestionIndex };
  };

  return Object.freeze({ diffScores, mergeCorrections, isCorrection });
});
