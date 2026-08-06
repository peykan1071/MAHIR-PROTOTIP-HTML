# MAHIR-PROTOTIP-HTML

MAHİR, "Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı" fikrine dayanan, Türkçe çalışan ve öğretmen kontrollü bir eğitim evrakı prototipidir.

İlk geliştirme hedefi, "Sınav Analizi ve Değerlendirme Raporu" için sade, modern ve tek sayfalık bir HTML/CSS/JavaScript prototipi hazırlamaktır.

## Word Şablonunu Okuma

`MAHIR_Veri_Giris_Sablonu_Surum_1.docx` dosyası doldurulup Veri Ekleme ekranından
yüklendiğinde sınav, soru ve öğrenci tabloları yerel Python servisi tarafından
okunur. Sonuçlar analizden önce düzenlenebilir Veri Onay tablolarında gösterilir.

## Güncel Çalışan Akış

Hazırlık ekranından sonra öğretmen, standart MAHİR Veri Giriş Şablonu'nu indirebilir; doldurduğu Word, PDF veya görüntü belgesini yükleyebilir. Dosya türü ve boyutu denetlendikten sonra belge öğretmen kontrol ekranına aktarılır. Görsel grubu olarak yüklenen puanlama fotoğrafları (en fazla 10 adet, her biri tek öğrencilik puan tablosu), `MAHIR_OCR_REMOTE_URL` tanımlıysa uzaktaki bir OCR sunucusuna (bkz. aşağıdaki "Google Colab ile OCR") gönderilip öğrenci satırlarına dönüştürülür; tanımlı değilse görseller OCR yapılmadan öğretmen kontrolüne bırakılır.

Yerel prototipi dosya alıcısıyla çalıştırmak için:

```bash
python3 backend/run_file_receiver.py
```

Ardından `http://127.0.0.1:8000/index.html` adresi açılır. Bu yerel sunucunun PaddleOCR'a ya da başka bir üçüncü parti pakete ihtiyacı yoktur (düz `python3` yeterlidir) — OCR hiçbir zaman bu makinede çalışmaz.

### Google Colab ile OCR

Görsel puan tablolarının OCR ile okunması, ayrı bir "OCR işçisi" (`backend/run_ocr_worker.py`) üzerinden çalışır ve bu işçinin gerçek bir GPU'ya ihtiyacı vardır. Kendi bilgisayarınızda GPU yoksa (veya yeterli VRAM yoksa) bu işçiyi ücretsiz bir Google Colab GPU'sunda çalıştırabilirsiniz:

1. `colab/mahir_ocr_colab.ipynb`'yi [Google Colab](https://colab.research.google.com/)'da açın, çalışma zamanı türünü **T4 GPU** yapın, tüm hücreleri sırayla çalıştırın.
2. Not defteri repoyu Colab'a klonlar, yalnızca OCR için gereken paketleri (`paddleocr`, `paddlepaddle-gpu`, `paddlex`) kurar, `backend/run_ocr_worker.py`'yi başlatır ve `cloudflared` ile dışa açık bir tünel kurar.
3. Son hücrede basılan `https://xxxx.trycloudflare.com` adresini kopyalayın.
4. Kendi bilgisayarınızda bu adresi kullanarak yerel sunucuyu başlatın:

```bash
set MAHIR_OCR_REMOTE_URL=https://xxxx.trycloudflare.com
python3 backend/run_file_receiver.py
```

Sınırlamalar: Colab oturumu boşta kalınca veya ~12 saat sonra kapanır; kapanırsa not defterini yeniden çalıştırıp yeni adresi `MAHIR_OCR_REMOTE_URL` olarak güncellemeniz gerekir. `MAHIR_OCR_REMOTE_URL` tanımlı değilken görsel yüklemeleri OCR yapılmadan kabul edilir; sunucu çökmez.

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
## Sprint 1 - v1.5

MAHİR UI Kit görsel varlıklarının standart dosya adlarıyla `assets` klasör yapısına yerleştirilmesi hedeflenmiştir.

Bu sprint için beklenen dosya yolları:

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

Kontrol notu: Bu kontrol sırasında varlık dosyaları henüz klasörlere eklenmemiş görünmektedir. Görseller HTML'ye bağlanmamış, CSS yazılmamış, yeni görsel/ikon üretilmemiş ve `index.html`, `styles.css`, `script.js` dosyaları değiştirilmemiştir.
## Sprint 1 / Task 03

Project management documents oluşturuldu.
