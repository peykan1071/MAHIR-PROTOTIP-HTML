# Belge Anlama Ajanı

## Amaç

Belge Anlama Ajanı, dosya yükleme aşamasında okunmuş ve öğretmen tarafından onaylanmış sınav verisini ortak MAHİR veri sözleşmesine, yani Canonical Education Document (CED) yapısına dönüştüren deterministik görev bileşenidir.

Dosyanın açılması, metin çıkarılması ve OCR kalite kontrolü bu ajanın görevi değildir. Bu işlemler, analizden önce çalışan Belge Okuma ve OCR Kalite Ajanı ile dosya alım katmanında gerçekleştirilir.

## Sorumluluklar

- Onaylı sınav, soru ve anonim öğrenci puanı alanlarını alır.
- Soru numaralarını, azami puanları ve öğrenci puanlarını standartlaştırır.
- Zorunlu alanları ve temel veri biçimlerini doğrular.
- Onaylı veriden CED nesnesi oluşturur.
- Soru ve öğrenci sayılarını işlem izine kaydeder.

## Yetki sınırı

- PDF, DOCX, XLSX veya görsel dosyayı doğrudan okumaz.
- OCR çalıştırmaz ve OCR sonucunu onaylamaz.
- Öğrenme çıktısı seçmez veya program eşleştirmesi yapmaz.
- Puan istatistiği hesaplamaz.
- Pedagojik yorum veya rapor üretmez.

## Girdi ve çıktı

**Girdi:** Öğretmenin kontrol edip onayladığı sınav bağlamı, soru tanımları ve anonim öğrenci soru puanları.

**Çıktı:** Sürüm bilgisi bulunan, standartlaştırılmış CED nesnesi ve belge anlama işlem izi.

## İş akışı

1. Onaylı veri yükünü alır.
2. Soru ve anonim öğrenci puanı alanlarını standartlaştırır.
3. Eksik veya geçersiz zorunlu alanları reddeder.
4. CED nesnesini oluşturur.
5. CED nesnesini Program Eşleştirme Ajanına aktarır.
