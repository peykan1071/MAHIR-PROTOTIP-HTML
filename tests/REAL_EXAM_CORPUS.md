# MAHİR anonim gerçek evrak kabul testleri

Bu depoda, gerçek kullanım sırasında sınanan evrakların kişisel verilerden
arındırılmış kopyaları `tests/fixtures/real_exam_corpus_anonymized` altında yer
alır. Özgün ZIP ve özgün kimlik bilgileri GitHub'a eklenmez.

Veri kümesi aşağıdaki kabul senaryolarını kalıcı olarak doğrular:

1. Aynı türde 45 yazılı evrakı OCR girdisi: 9-A için 25, 9-B için 20 görsel.
2. Aynı türde beş Word puan çizelgesi: 9-A, 9-B, 9-C, 9-D ve 9-E.
3. Aynı 25 kişilik 9-A sınavının 25 OCR görseli ile Word puan çizelgesinin
   karşılaştırılması.
4. Aynı 20 kişilik 9-B sınıfının yazılı, dinleme ve konuşma sınavlarının
   20'şer OCR evrakıyla ayrı analiz edilmesi ve üç raporun Yazılı %70,
   Dinleme %15, Konuşma %15 ağırlıklarıyla genel değerlendirmeye alınması.

Word kabul ölçütleri; 7 soru, `12+12+14+12+14+12+24=100` azami puan yapısı ve
sınıflar için sırasıyla `25, 28, 22, 20, 25` öğrenci kaydıdır.

## Anonimleştirme güvenceleri

- Öğrenci adları ve okul numaraları `ÖĞRENCİ-###` / `OGR-###` biçiminde
  oturumlardan bağımsız test kodlarına dönüştürülür.
- İl, ilçe, okul, öğretmen ve belge üst verileri kurgu test değerleriyle
  değiştirilir.
- Görsel EXIF bilgileri ve Word yazar/son düzenleyen alanları temizlenir.
- Dosyalar içerik türü ve sınıf senaryosunu anlatan nötr adlarla kaydedilir.
- `manifest.json`, her dosyanın boyutunu ve SHA-256 özetini içerir.

Anonim veri kümesi özgün arşivden yeniden üretilecekse:

```powershell
python tools/anonymize_real_exam_corpus.py `
  "C:\path\to\TEST MAHİR SINAV EVRAKLARI.zip" `
  "tests\fixtures\real_exam_corpus_anonymized"
```

Kabul testleri standart test komutuyla ve CI ortamında ek dosya gerektirmeden
çalışır.
