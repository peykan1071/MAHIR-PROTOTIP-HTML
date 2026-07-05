# MAHIR-PROTOTIP-HTML

MAHİR, "Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı" fikrine dayanan, Türkçe çalışan ve öğretmen kontrollü bir eğitim evrakı prototipidir.

İlk geliştirme hedefi, "Sınav Analizi ve Değerlendirme Raporu" için sade, modern ve tek sayfalık bir HTML/CSS/JavaScript prototipi hazırlamaktır.

## Geliştirme Kuralları

Bu projede geliştirme adım adım, küçük ve onaylı sürümler halinde yapılır. Her sprintte yalnızca belirlenen kapsam uygulanır; yapay zekâ, veritabanı, OCR, dosya okuma, PDF/Word üretimi ve sistem entegrasyonu ilk aşamada kapsam dışıdır.

Ayrıntılı geliştirme kuralları, sürümleme sistemi, dosya düzeni ve kontrol listeleri için bkz. [DEVELOPMENT_CHARTER.md](DEVELOPMENT_CHARTER.md).

## Sprint 1 - v1.1

MAHİR Kurumsal Giriş Ekranı için yalnızca HTML iskeleti oluşturulmuştur.

Bu sürümde oluşturulan ana bölümler:

- Header
- Hero
- Information Cards
- Primary Button Area
- Values Band
- Footer

Bu sprintte tasarım, renk, responsive yapı, animasyon, logo, ikon, bayrak, hero görseli, framework veya dış kütüphane eklenmemiştir.

## Sprint 1 - v1.2

v1.1'de oluşturulan semantik HTML iskeleti korunarak yalnızca sayfa yerleşimi oluşturulmuştur.

Bu sürümde yapılan layout düzenlemeleri:

- Header, Hero, Information Cards, Primary Button Area, Values Band ve Footer akışı kuruldu.
- Hero alanı iki sütunlu yerleşime alındı; sağ sütun boş bırakıldı.
- Information Cards alanı üç eşit kart düzenine alındı.
- Primary Button Area sayfa ortasında konumlandırıldı.
- Values Band dört sütunlu yatay yapıya alındı.
- Footer sayfanın alt alanında sade biçimde konumlandırıldı.

Bu sprintte renk, gölge, border-radius, gradient, animasyon, responsive yapı, font değişikliği, logo, ikon, bayrak, görsel, framework veya dış kütüphane eklenmemiştir.
## Sprint 1 - v1.3

v1.1 HTML iskeleti ve v1.2 layout düzeni korunarak yalnızca tipografi hiyerarşisi oluşturulmuştur.

Bu sürümde yapılan tipografi düzenlemeleri:

- Sistem fontları tanımlandı.
- Ana başlık, alt başlık ve açıklama metinleri için okunabilir font ölçüleri ve satır yükseklikleri ayarlandı.
- Kart başlıkları ve küçük açıklamalar için sade bir metin hiyerarşisi kuruldu.
- Buton metni daha güçlü görünecek şekilde düzenlendi.

Bu sprintte HTML yapısı, JavaScript, renk sistemi, logo, ikon, bayrak, hero görseli, gölge, gradient, border-radius, animasyon, responsive yapı, framework veya dış kütüphane eklenmemiştir.
## Sprint 1 - v1.4

Kurumsal görsel varlık klasör yapısı hazırlanmıştır. Bu sürümde görseller HTML'ye bağlanmamış, görseller için CSS yazılmamış ve yeni görsel/ikon dosyası üretilmemiştir.

Oluşturulan varlık klasörleri:

- `assets/`
- `assets/logo/`
- `assets/hero/`
- `assets/flag/`
- `assets/icons/`

### MAHİR UI Kit Varlık Adlandırma Standardı

Genel kurallar:

- Dosya adları küçük harfle yazılır.
- Türkçe karakter kullanılmaz.
- Kelimeler tire işaretiyle ayrılır.
- MAHİR'e ait kurumsal varlıklarda `mahir-` öneki kullanılır.
- Varlıklar kullanım alanına göre ilgili alt klasöre yerleştirilir.
- Belirsiz `yeni`, `son`, `final` gibi adlar kullanılmaz.

Önerilen varlık dosya adları:

Logo:

- `assets/logo/mahir-logo.png`

Hero:

- `assets/hero/mahir-hero-teacher.png`

Bayrak:

- `assets/flag/mahir-kurumsal-bayrak.png`

İkonlar:

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

Bu sprintte `index.html`, `styles.css` ve `script.js` dosyaları değiştirilmemiştir.
