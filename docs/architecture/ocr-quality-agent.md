# Belge Okuma ve OCR Kalite Ajanı

## Amaç

Belge Okuma ve OCR Kalite Ajanı, yüklenen dosyanın metin tabanlı mı yoksa görüntü tabanlı mı olduğunu belirleyen; OCR'nin yalnız gerektiğinde kullanılmasını sağlayan ve belge okuma sonucunu öğretmen doğrulamasına hazırlayan deterministik görev bileşenidir.

## Yetki sınırı

- Dil modeli kullanmaz.
- Pedagojik yorum veya puan hesabı yapmaz.
- OCR sonucunu kendiliğinden doğru kabul etmez.
- Öğretmen onayı vermeden veriyi analiz hattına aktarmaz.
- Metin katmanı bulunan DOCX, XLSX ve PDF belgelerinde OCR çalıştırmaz.

## Kontroller

1. Dosya biçimini ve OCR gereksinimini belirler.
2. Okunabilen öğrenci satırı sayısını dosya sayısıyla karşılaştırır.
3. Boş soru puanı hücrelerini işaretler.
4. Yazılı toplam ile soru puanları toplamı arasındaki uyuşmazlığı bildirir.
5. OCR sınırında algılanıp çıkarılan kişisel veri türlerini kayda geçirir.
6. Sonucu `hazır`, `öğretmen kontrolü gerekli` veya `elle tamamlama gerekli` durumlarından biriyle etiketler.

## Prototip sınırı

Görsel dosyalar uzak OCR servisine yönlendirilir. Metin katmanı bulunmayan taranmış PDF tespit edilir; ancak PDF sayfalarını otomatik olarak görsele dönüştürüp OCR'a gönderme özelliği bu prototipte henüz bulunmadığından öğretmen kontrolü ve elle tamamlama istenir. Bu sınırlama sessizce geçilmez.
