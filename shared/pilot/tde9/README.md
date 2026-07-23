# 9. Sınıf Türk Dili ve Edebiyatı Ortak Yazılı Pilot Veri Paketi

Bu klasör, 9. sınıf Türk Dili ve Edebiyatı ortak yazılı pilotu için gerçek verilerin sonradan yerleştirileceği standart veri paketi iskeletidir.

## Pilotun Amacı

Pilot veri paketi, MAHİR backend akışının gerçek sınav verileriyle denenebilmesi için sınav soruları, öğrenme çıktıları ve öğrenci sonuçlarını aynı dosya düzeninde toplamayı amaçlar.

## Dosyaların Görevi

- `exam-template.csv`: Sınav sorularının yerleştirileceği CSV şablonudur. Başlık sırası `question_no,question_text,correct_answer,points` biçiminde korunmalıdır.
- `learning-outcomes-template.json`: Öğretim programı öğrenme çıktılarının yerleştirileceği JSON şablonudur.
- `student-results-template.json`: Anonim öğrenci cevap ve sonuçlarının yerleştirileceği JSON şablonudur.

## Veri Gizliliği

Öğrenci verileri anonim olmalıdır. Bu klasöre öğrenci adı, T.C. kimlik numarası, gerçek okul numarası veya kişisel veri eklenmemelidir.

`student_no` alanında gerçek okul numarası yerine `P001`, `P002`, `P003` gibi pilot kodları kullanılmalıdır.

`full_name` alanında gerçek ad yerine `Öğrenci 01`, `Öğrenci 02`, `Öğrenci 03` biçimi kullanılmalıdır.

## Kimliklendirme Standardı

Soru kimlikleri backend akışı içinde `q1`, `q2`, `q3` biçiminde oluşturulacak yapıyla uyumlu olmalıdır. CSV içindeki `question_no` alanı bu sırayı desteklemelidir.

## Uyumluluk

Dosya biçimleri mevcut CED veri modeli ve backend akışıyla uyumlu olmalıdır. Başlık adları, JSON anahtarları ve alan yapıları değiştirilmemelidir.
