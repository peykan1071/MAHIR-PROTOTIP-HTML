\# Canonical Education Document (CED)



> MAHİR'in standart veri modeli.

## Değerlendirme bileşenleri

Her sınav kaydı `component_type` alanıyla `written`, `listening`, `speaking`
veya `performance` olarak saklanır. Aynı ders, dönem ve sınav sırasına ait
kayıtlar `assessment_group_id` ile gruplanır.

Bu yapı yalnız dil dersi profiline kayıtlı derslerde etkinleşir. Türk Dili ve
Edebiyatı için `tde-70-15-15`; Türkçe ve yabancı diller için
`language-50-25-25` profili kullanılır. Diğer derslerde değerlendirme bileşeni
alanı gösterilmez ve normal yazılı sınav analizi sürer.

Her bileşen önce kendi içinde 100 puan üzerinden soru/ölçüt ve öğrenme çıktısı
düzeyinde analiz edilir. Ağırlıklı genel sonuç ancak üç zorunlu bileşen de
mevcutsa kesinleşir. Performans çalışması bu üçlü sınav puanı hesabına katılmaz;
ayrı bir değerlendirme kaydıdır.
