# MAHİR UI Contract

Feature 10 - Sprint 1

Bu belge, MAHİR kullanıcı arayüzünde kullanılacak standart bileşenlerin davranış sözleşmesini tanımlar. Bundan sonraki HTML geliştirmelerinde bileşenlerin amacı, kullanım yeri, davranışı ve durumları için referans alınmalıdır.

Bu belge tasarım sistemi değildir; renk, görsel stil, HTML, CSS veya JavaScript içermez.

## 1. Primary Button

### Bileşen Adı

Primary Button

### Amacı

Öğretmeni akıştaki ana ve güvenli sonraki adıma taşımak.

### Kullanıldığı ekranlar

- Karşılama Ekranı
- Hazırlık Ekranı
- Veri Ekleme Ekranı
- Veri Doğrulama Ekranı

### Davranışı

Öğretmen butonu seçtiğinde mevcut ekrandaki geçiş şartları kontrol edilir. Şartlar sağlanıyorsa bir sonraki ekrana geçilir. Şartlar sağlanmıyorsa hata dili yerine rehber mesaj gösterilir.

### Durumları

- Hazır
- Seçilebilir
- Geçici olarak pasif
- İşlem bekliyor
- Rehber mesaj gerektiriyor

### Tekrar kullanılabilir mi?

Evet. Akıştaki ana ilerleme eylemleri için tekrar kullanılabilir.

## 2. Secondary Button

### Bileşen Adı

Secondary Button

### Amacı

Öğretmene geri dönme, düzenleme veya alternatif işlem başlatma imkanı vermek.

### Kullanıldığı ekranlar

- Veri Ekleme Ekranı
- Veri Doğrulama Ekranı
- Rapor Ekranı

### Davranışı

Öğretmeni ana akışı bozmadan önceki adıma, düzenleme alanına veya yardımcı bir işleme yönlendirir. Ana ilerleme eyleminin yerine geçmez.

### Durumları

- Hazır
- Seçilebilir
- Geçici olarak pasif
- Düzenleme başlatıyor
- Geri dönüş başlatıyor

### Tekrar kullanılabilir mi?

Evet. Geri, düzenle ve yardımcı eylemler için tekrar kullanılabilir.

## 3. Progress Stepper

### Bileşen Adı

Progress Stepper

### Amacı

Öğretmene sürecin hangi aşamasında olduğunu ve kalan ana adımları göstermek.

### Kullanıldığı ekranlar

- Hazırlık Ekranı
- Veri Ekleme Ekranı
- Veri Doğrulama Ekranı
- Analiz Süreci Ekranı
- Rapor Ekranı

### Davranışı

Akış aşamalarını `Hazırlık`, `Veri`, `Analiz`, `Rapor` sırasıyla gösterir. Aktif aşama, tamamlanan aşamalar ve bekleyen aşamalar öğretmene anlaşılır biçimde sunulur. Öğretmeni teknik süreç ayrıntılarıyla karşı karşıya bırakmaz.

### Durumları

- Bekleyen adım
- Aktif adım
- Tamamlanan adım
- Geri dönülebilir adım
- Kilitli adım

### Tekrar kullanılabilir mi?

Evet. Çok adımlı tüm MAHİR akışlarında kullanılabilir.

## 4. Upload Box

### Bileşen Adı

Upload Box

### Amacı

Öğretmenin mevcut sınav verilerini dosya olarak paylaşmasına alan sağlamak.

### Kullanıldığı ekranlar

- Veri Ekleme Ekranı

### Davranışı

Öğretmene dosya ekleyebileceğini ve desteklenen biçimleri açıkça bildirir. Dosya eklenmediğinde süreci keskin bir hata ile durdurmaz; elle veri girişi alternatifini ve tamamlanabilir bilgi yaklaşımını görünür kılar.

### Durumları

- Boş
- Dosya seçimi bekliyor
- Dosya eklenmiş
- Desteklenmeyen biçim için rehber mesaj gösteriyor
- Elle veri girişi alternatifi seçilmiş

### Tekrar kullanılabilir mi?

Evet. Veri veya belge paylaşımı gerektiren ileriki ekranlarda aynı davranış ilkesiyle kullanılabilir.

## 5. Dropdown

### Bileşen Adı

Dropdown

### Amacı

Öğretmenin sınırlı ve önceden tanımlı seçenekler arasından seçim yapmasını sağlamak.

### Kullanıldığı ekranlar

- Hazırlık Ekranı
- Veri Doğrulama Ekranı

### Davranışı

Seçenek listesini öğretmene açık ve kontrollü biçimde sunar. Seçim yapılmadığında hata dili yerine seçim yapılmasının rapor bağlamını güçlendireceğini anlatan rehber mesaj gösterilir.

### Durumları

- Seçim bekliyor
- Seçilmiş
- Düzenleniyor
- Geçici olarak pasif
- Rehber mesaj gerektiriyor

### Tekrar kullanılabilir mi?

Evet. Ders, sınıf düzeyi, veri giriş yöntemi ve benzeri kontrollü seçimlerde tekrar kullanılabilir.

## 6. Information Card

### Bileşen Adı

Information Card

### Amacı

Öğretmene kısa, güven veren ve karar destekleyici bilgileri gruplar halinde sunmak.

### Kullanıldığı ekranlar

- Karşılama Ekranı
- Hazırlık Ekranı
- Rapor Ekranı

### Davranışı

Tek bir ana fikri kısa başlık ve açıklamayla sunar. Öğretmenin bilişsel yükünü artırmadan, akışın güven ve amaç bilgisini destekler.

### Durumları

- Bilgi veriyor
- Vurgulanmış bilgi
- Tamamlanabilir bilgi
- Pasif bilgilendirme

### Tekrar kullanılabilir mi?

Evet. Güven maddeleri, açıklamalar, rapor özetleri ve yönlendirme alanları için tekrar kullanılabilir.

## 7. Validation Card

### Bileşen Adı

Validation Card

### Amacı

Analize geçmeden önce algılanan veya girilen bilgileri öğretmenin kontrolüne sunmak.

### Kullanıldığı ekranlar

- Veri Doğrulama Ekranı

### Davranışı

Ders, sınıf düzeyi, öğrenci sayısı, soru sayısı, öğrenme çıktısı eşleştirmesi ve veri giriş yöntemi gibi bilgileri listeler. Eksik bilgi varsa hata gibi değil, tamamlanabilir bilgi olarak sunar.

### Durumları

- Tamamlanmış bilgi
- Tamamlanabilir bilgi
- Düzenlenebilir bilgi
- Öğretmen onayı bekliyor
- Analize hazır

### Tekrar kullanılabilir mi?

Evet. Öğretmen onayı gerektiren diğer kontrol adımlarında tekrar kullanılabilir.

## 8. Analysis Progress

### Bileşen Adı

Analysis Progress

### Amacı

Rapor taslağı hazırlanırken öğretmene sürecin anlamlı değerlendirme aşamalarını göstermek.

### Kullanıldığı ekranlar

- Analiz Süreci Ekranı

### Davranışı

Aşama listesini anlaşılır eğitim diliyle sunar. Teknik terimler, sistem içi işlem ifadeleri veya öğretmenin kontrolünü zayıflatan ifadeler kullanmaz. Süreç tamamlandığında rapor ekranına geçişe hazır hale gelir.

### Durumları

- Bekleyen aşama
- Devam eden aşama
- Tamamlanan aşama
- Öğretmen kontrolü gerektirebilecek aşama
- Rapor ekranına hazır

### Tekrar kullanılabilir mi?

Evet. Çok aşamalı değerlendirme veya rapor hazırlık akışlarında tekrar kullanılabilir.

## 9. Summary Card

### Bileşen Adı

Summary Card

### Amacı

Rapor veya doğrulama ekranlarında önemli bilgileri kısa ve taranabilir şekilde özetlemek.

### Kullanıldığı ekranlar

- Veri Doğrulama Ekranı
- Rapor Ekranı

### Davranışı

Bir bilgi grubunu kısa başlık ve özet içerikle sunar. Öğretmenin raporun ana noktalarını hızlıca anlamasına yardımcı olur.

### Durumları

- Boş değil
- Tamamlanabilir
- İnceleme bekliyor
- Öğretmen tarafından düzenlenebilir
- Onaya hazır

### Tekrar kullanılabilir mi?

Evet. Genel değerlendirme, güçlü alanlar, gelişim alanları ve izleme planı özetleri için tekrar kullanılabilir.

## 10. Report Section

### Bileşen Adı

Report Section

### Amacı

Rapor içeriğini resmî, ölçülü ve öğretmen kontrolüne uygun bölümler halinde sunmak.

### Kullanıldığı ekranlar

- Rapor Ekranı

### Davranışı

Raporun her bölümünü ayrı bir içerik alanı olarak sunar. Bölüm içeriği taslak niteliğindedir; öğretmenin inceleme, düzenleme ve son onay hakkı korunur.

### Durumları

- Taslak hazır
- İnceleme bekliyor
- Düzenlenebilir
- Tamamlanabilir
- Öğretmen onayına hazır

### Tekrar kullanılabilir mi?

Evet. Raporun tüm ana bölümleri için tekrar kullanılabilir.

## 11. Source Reference Panel

### Bileşen Adı

Source Reference Panel

### Amacı

Rapor taslağındaki değerlendirmelerin hangi veri veya dayanaklara bağlı olduğunu öğretmene göstermek.

### Kullanıldığı ekranlar

- Rapor Ekranı

### Davranışı

Kaynak dayanaklarını ve değerlendirme gerekçelerini öğretmen tarafından incelenebilir biçimde listeler. Kesin hüküm dili yerine kanıt ve taslak yaklaşımını destekler.

### Durumları

- Kaynak dayanağı mevcut
- Kaynak dayanağı tamamlanabilir
- İnceleme bekliyor
- Öğretmen notu eklenebilir
- Rapor bölümüne bağlı

### Tekrar kullanılabilir mi?

Evet. Kanıt, kaynak, dayanak veya açıklama gerektiren rapor alanlarında tekrar kullanılabilir.

## 12. Notification Message

### Bileşen Adı

Notification Message

### Amacı

Hata dili kullanmadan öğretmeni bilgilendirmek, yönlendirmek veya eksik bilgiyi tamamlanabilir biçimde göstermek.

### Kullanıldığı ekranlar

- Karşılama Ekranı
- Hazırlık Ekranı
- Veri Ekleme Ekranı
- Veri Doğrulama Ekranı
- Analiz Süreci Ekranı
- Rapor Ekranı

### Davranışı

Öğretmene ne olduğunu, neden önemli olduğunu ve bir sonraki mantıklı adımın ne olduğunu açıklar. Mesajlar kısa, ölçülü ve öğretmen dostu olmalıdır.

### Durumları

- Bilgilendirme
- Rehberlik
- Tamamlanabilir bilgi
- İşlem bekleniyor
- Son onay hatırlatması

### Tekrar kullanılabilir mi?

Evet. Tüm ekranlarda rehberlik ve süreç açıklaması için tekrar kullanılabilir.
