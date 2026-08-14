# 9. Sınıf Türk Dili ve Edebiyatı Ortak Yazılı Pilot Veri Paketi

Bu klasör, 9. sınıf Türk Dili ve Edebiyatı ortak yazılı pilotunun ders-sınıf kapsamlı program veri paketidir.

## Pilotun Amacı

Pilot veri paketi, MAHİR backend akışının gerçek sınav verileriyle denenebilmesi için sınav soruları, öğrenme çıktıları ve öğrenci sonuçlarını aynı dosya düzeninde toplamayı amaçlar.

## Dosyaların Görevi

- `exam-template.csv`: Sınav sorularının yerleştirileceği CSV şablonudur. Başlık sırası `question_no,question_text,correct_answer,points` biçiminde korunmalıdır.
- `learning-outcomes-template.json`: Dört temadaki alan becerilerini ve öğrenme çıktılarını; resmî konu-soru dağılım tablolarında bulunan süreç bileşenleriyle birlikte saklar. Aynı kod farklı temalarda farklı bağlam taşıdığı için her kayıt tema kimliğiyle tutulur.
- `student-results-template.json`: Anonim öğrenci cevap ve sonuçlarının yerleştirileceği JSON şablonudur.

## Veri Gizliliği

Öğrenci verileri anonim olmalıdır. Bu klasöre öğrenci adı, T.C. kimlik numarası, gerçek okul numarası veya kişisel veri eklenmemelidir.

`student_no` alanında gerçek okul numarası yerine `P001`, `P002`, `P003` gibi pilot kodları kullanılmalıdır.

`full_name` alanında gerçek ad yerine `Öğrenci 01`, `Öğrenci 02`, `Öğrenci 03` biçimi kullanılmalıdır.

## Kimliklendirme Standardı

Soru kimlikleri backend akışı içinde `q1`, `q2`, `q3` biçiminde oluşturulacak yapıyla uyumlu olmalıdır. CSV içindeki `question_no` alanı bu sırayı desteklemelidir.

## Uyumluluk

Dosya biçimleri mevcut CED veri modeli ve backend akışıyla uyumlu olmalıdır. Başlık adları, JSON anahtarları ve alan yapıları değiştirilmemelidir.

## Kapsam ve Kaynak İlkesi

- Program profili yalnız `Türk Dili ve Edebiyatı + 9. sınıf` eşleşmesinde açılır.
- Dört tema belgesi ana öğrenme çıktısı havuzunu oluşturur.
- Ortak Metin, programlar arası bileşenlerin kavramsal açıklama kaynağıdır.
- 1. ve 2. dönem konu-soru dağılım tabloları, ortak yazılılarda kullanılan süreç bileşenlerini ve senaryo kapsamını doğrular.
- Resmî belgede bulunmayan ders, sınıf, sınav veya süreç bileşeni için veri üretilmez.
- Ana öğrenme çıktılarının güncel metni dört tema belgesinden doğrulanır; toplu 2024 program PDF'si yalnız destekleyici kaynaktır.
- Süreç bileşenlerinin kapsamı ve metni 1. ve 2. dönem resmî konu-soru dağılım tablolarından alınır; satır sonundan kaynaklanan kelime bölünmeleri dışında içerik kısaltılmaz.
