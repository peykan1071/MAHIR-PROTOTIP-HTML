# MAHİR Design System v1.0

Bu belge, MAHİR Kurumsal Giriş Ekranı için logo, hero, bayrak, ikon, renk, tipografi, kart, buton ve boşluk kullanım kurallarını tek yerde toplar. Bu belge uygulama kodu değildir; tasarım kararları için referans dokümandır.

## 1. Logo Kullanımı

MAHİR logosu kurumsal kimliği temsil eder ve yalnızca açıkça belirlenen alanlarda kullanılmalıdır. Logo, sayfa içinde dikkat dağıtmayacak ölçekte konumlandırılmalı ve metin hiyerarşisinin önüne geçmemelidir.

Logo dosyası:

- `assets/logo/mahir-logo.png`

Kullanım ilkeleri:

- Logo dosya adı değiştirilmez.
- Logo sıkıştırılmaz, esnetilmez veya oranı bozulmaz.
- Logo üzerine metin, efekt veya gölge eklenmez.
- Logo alternatifleri oluşturulacaksa ayrı sprint kapsamında belgelenir.

## 2. Hero Görseli Kullanımı

Hero görseli, MAHİR'in öğretmen odaklı kullanım bağlamını anlatmak için kullanılmalıdır. Görsel, uygulamanın asıl işlevini gölgelememeli ve metin okunabilirliğini azaltmamalıdır.

Hero dosyası:

- `assets/hero/mahir-hero-teacher.png`

Kullanım ilkeleri:

- Hero görseli yalnızca giriş ekranında destekleyici görsel olarak kullanılmalıdır.
- Görsel üzerine yoğun metin bindirilmemelidir.
- Görsel kırpma veya yerleşim kararı ayrı tasarım sprintinde yapılmalıdır.
- Placeholder görsel kullanılmaz.

## 3. Bayrak Görseli Kullanımı

Bayrak görseli kurumsal ve yerel bağlamı destekleyen yardımcı bir varlık olarak değerlendirilmelidir. Ana marka öğesi logo olduğu için bayrak görseli ikincil düzeyde kullanılmalıdır.

Bayrak dosyası:

- `assets/flag/mahir-kurumsal-bayrak.png`

Kullanım ilkeleri:

- Bayrak görseli dekoratif yoğunluk oluşturacak şekilde tekrarlanmaz.
- Bayrak görseli logo yerine kullanılmaz.
- Bayrak görselinin konumu ve boyutu ayrı sprintte belirlenir.

## 4. İkon Sistemi

İkonlar, MAHİR arayüzündeki bilgi kartları, değer alanları ve süreç göstergeleri için destekleyici görsel işaretlerdir. İkonlar açıklayıcı olmalı, metnin yerine geçmemelidir.

İkon dosyaları:

- `assets/icons/document.png`
- `assets/icons/chart.png`
- `assets/icons/brain.png`
- `assets/icons/clipboard.png`
- `assets/icons/shield-check.png`
- `assets/icons/upload-file.png`
- `assets/icons/sparkles.png`
- `assets/icons/report-file.png`
- `assets/icons/trust.png`
- `assets/icons/target.png`
- `assets/icons/analytics.png`
- `assets/icons/teacher-control.png`

Kullanım ilkeleri:

- İkon dosya adları değiştirilmez.
- Aynı anlam için aynı ikon tekrar kullanılır.
- İkonlar bilgi mimarisini desteklemek için kullanılır.
- Yeni ikon ihtiyacı oluşursa dosya adı ve kullanım amacı önce belgelenir.

## 5. Renk Sistemi

Renk sistemi MAHİR'in sakin, güvenilir ve öğretmen dostu algısını desteklemelidir. Renkler arayüzü süslemek için değil, hiyerarşi ve yönlendirme amacıyla kullanılmalıdır.

İlkeler:

- Ana renk, yardımcı renk ve nötr renkler ayrı sprintte tanımlanır.
- Renkler erişilebilir kontrast hedefi gözetilerek seçilir.
- Uyarı, başarı ve bilgi durumları için anlamlı renk rolleri belirlenir.
- Tek renge aşırı bağımlı bir arayüz oluşturulmaz.

## 6. Tipografi

Tipografi, öğretmenlerin metni hızlı taramasını ve güvenle okumasını sağlayacak şekilde düzenlenmelidir. Sistem fontları temel alınır; dış font veya CDN kullanılmaz.

İlkeler:

- Ana başlık güçlü ve okunaklı olmalıdır.
- Alt başlıklar daha sakin bir hiyerarşi kurmalıdır.
- Açıklama metinlerinde rahat satır yüksekliği kullanılmalıdır.
- Kart başlıkları belirgin, kart açıklamaları sade olmalıdır.
- Buton metni kısa, eylem odaklı ve güçlü görünmelidir.

## 7. Kart Yapısı

Kartlar, giriş ekranında bilgi gruplarını ayrıştırmak için kullanılır. Kart yapısı sade, taranabilir ve öğretmen dostu olmalıdır.

İlkeler:

- Kartlar tek bir ana fikri taşımalıdır.
- Kart başlığı kısa ve açık olmalıdır.
- Kart açıklaması gereksiz teknik dil içermemelidir.
- Kart içeriği ikon kullanılsa bile metinle anlaşılabilir kalmalıdır.
- Kart görsel yoğunluğu düşük tutulmalıdır.

## 8. Buton Sistemi

Butonlar açık eylem çağrıları için kullanılır. MAHİR giriş ekranında birincil buton, kullanıcıyı sonraki adıma hazırlayan ana eylemi temsil eder.

İlkeler:

- Birincil buton metni kısa ve doğrudan olmalıdır.
- Buton metni öğretmen dostu bir tonda yazılmalıdır.
- Aynı ekranda gereksiz sayıda birincil buton kullanılmaz.
- Butonların görsel stilleri ayrı tasarım sprintinde netleştirilir.

## 9. Boşluk ve Hizalama

Boşluk sistemi, ekranın sakin ve düzenli algılanmasını sağlar. Hizalama, kullanıcının bölümler arasındaki ilişkiyi kolayca anlamasına yardım etmelidir.

İlkeler:

- Header, hero, bilgi kartları, buton alanı, değer bandı ve footer arasında net boşluk bırakılır.
- İçerik genişliği kontrollü tutulur.
- Kartlar ve değer alanları hizalı bir grid yapısıyla ilerler.
- Dikey akış kullanıcıyı yukarıdan aşağıya doğal biçimde yönlendirmelidir.

## 10. Responsive İlkeler

Responsive yapı, MAHİR ekranının farklı cihazlarda okunabilir ve kullanılabilir kalmasını sağlamalıdır. Mobil görünümde içerik sıkışmamalı, taşmamalı ve metinler birbirini örtmemelidir.

İlkeler:

- Masaüstünde çok sütunlu alanlar kullanılabilir.
- Dar ekranlarda sütunlar sade bir dikey akışa dönüşmelidir.
- Butonlar ve kartlar dokunmatik kullanım için yeterli alana sahip olmalıdır.
- Görseller mobilde metin okunabilirliğini bozmayacak şekilde konumlandırılmalıdır.
- Responsive kararlar ayrı sprint kapsamında uygulanır ve test edilir.
