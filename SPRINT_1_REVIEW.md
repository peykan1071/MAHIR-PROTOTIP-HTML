# MAHİR Sprint 1 Review

Bu belge, MAHİR projesinde Sprint 1 boyunca yürütülen ürün geliştirme sürecinin resmî kapanış raporudur. Rapor; Development Charter, wireframe kararları, UI Contract, Visual Identity ve tamamlanan Feature kayıtları doğrultusunda hazırlanmıştır.

## 1. Sprint 1 Amacı

Sprint 1'in temel amacı, MAHİR'i yalnızca bir fikir düzeyinden çıkararak öğretmen kontrollü, Türkçe çalışan, kamu hizmeti anlayışına uygun ve tek evrak MVP yaklaşımına dayanan ilk prototip zeminine taşımaktır.

Bu sprintte hedef, gerçek yapay zekâ, veri analizi, dosya okuma veya rapor üretimi yapmak değildir. Hedef; ürünün yönünü, ekran akışını, bileşen davranışlarını, görsel kimlik ilkelerini ve çalışabilir arayüz omurgasını küçük, denetlenebilir ve onaylı adımlarla oluşturmaktır.

Sprint 1 sonunda MAHİR'in, sınav verilerini öğretmen kontrolünde yapılandırılmış değerlendirme ve rapor taslağı sürecine taşıyan ilk kullanıcı deneyimi netleşmiştir.

## 2. Tamamlanan Feature'lar

| Feature | Tamamlanan Çalışma |
| --- | --- |
| Feature 01 | Kurumsal giriş ekranı için ilk semantik HTML iskeleti oluşturuldu. |
| Feature 02 | Giriş ekranı için temel sayfa yerleşimi ve bölüm akışı kuruldu. |
| Feature 03 | Sistem fontlarına dayalı sade tipografi hiyerarşisi oluşturuldu. |
| Feature 04 | Kurumsal görsel varlıklar için `assets` klasör yapısı ve adlandırma standardı belirlendi. |
| Feature 05 | Logo, hero, bayrak ve ikon varlıklarının hedef dosya yolları netleştirildi. |
| Feature 06 | `DESIGN_SYSTEM.md` ile logo, hero, bayrak, ikon, renk, tipografi, kart, buton ve boşluk ilkeleri belgelendi. |
| Feature 07 | `ROADMAP.md`, `CHANGELOG.md` ve `docs/DEVELOPMENT_LOG.md` ile proje yönetim belgeleri oluşturuldu. |
| Feature 08 | Altı ekranlık düşük sadakatli wireframe taslağı hazırlandı. |
| Feature 09 | Wireframe her ekran için amaç, öğretmen psikolojisi, işlem, zorunlu alan, geçiş şartı ve başarı kriteriyle genişletildi. |
| Feature 10 | `UI_CONTRACT.md` ile temel arayüz bileşenlerinin davranış sözleşmesi oluşturuldu. |
| Feature 11 | Altı ekranlık Semantic HTML Foundation kuruldu. |
| Feature 12 | `VISUAL_IDENTITY.md` ile MAHİR'in güven, resmiyet, sadelik ve erişilebilirlik odaklı görsel kimliği belgelendi. |
| Feature 13 | Visual Identity kararları `styles.css` içinde temel renk, tipografi, kart, buton ve odak görünümü olarak uygulandı. |
| Feature 14 | Layout Foundation ile container, header, hero alanı, güven kartları, stepper, upload, validation ve rapor kolon temeli oluşturuldu. |
| Feature 15 | Screen Flow yapısı kuruldu; ekranlar bağımsız `screen` yapısına ayrıldı ve ilk açılışta yalnızca karşılama ekranı görünür hale getirildi. |
| Feature 16 | Navigation Engine oluşturuldu; ekran geçişleri, aktif Progress Stepper durumu ve sayfa üstüne dönüş davranışı çalışır hale getirildi. |

## 3. Ürün Açısından Kazanımlar

Sprint 1 boyunca MAHİR'in ürün kimliği öğretmen merkezli yaklaşım üzerine kurulmuştur. Ürün, öğretmenin yerine karar veren bir sistem olarak değil; öğretmenin mesleki kararını güçlendiren, veriyi düzenleyen ve rapor taslağına dönüştürmeye yardımcı olan bir destek aracı olarak konumlandırılmıştır.

Minimum girdi - maksimum pedagojik değer yaklaşımı benimsenmiştir. Öğretmenin başlangıçta yalnızca temel bağlamı seçmesi, mevcut verisini paylaşması ve süreci kontrol etmesi hedeflenmiştir. Böylece ürün yeni bir iş yükü oluşturmak yerine öğretmenin zaten sahip olduğu sınav verisini daha anlamlı hale getirmeye odaklanır.

Öğretmen onayı olmadan analiz yapılmaması temel ürün ilkesi olarak korunmuştur. Eksik bilgiler hata olarak değil, tamamlanabilir bilgi olarak ele alınmıştır. Raporun sahibi öğretmendir; MAHİR yalnızca taslak üretim, yapılandırma ve karar desteği sağlar.

Kanıta dayalı değerlendirme yaklaşımı ürün diline yerleştirilmiştir. Analiz, rapor ve kaynak dayanakları kavramları; kesin hüküm yerine ölçülü, akademik ve öğretmen denetimine açık bir değerlendirme sürecini destekleyecek şekilde kurgulanmıştır.

Kamu odaklı güvenilirlik, görsel kimlik ve dil kararlarında merkezi ilke olmuştur. MAHİR'in MEB, EBA, ÖBA, e-Okul ve MEBBİS gibi resmî sistemlerin güven tonunu taşıyan; ancak daha sade, çağdaş ve kullanıcı dostu bir arayüz dili benimsemesi hedeflenmiştir.

Tek evrak MVP yaklaşımı korunmuştur. Sprint 1, çoklu evrak, kullanıcı hesabı, veri tabanı veya karmaşık sistem entegrasyonu yerine yalnızca Sınav Analizi ve Değerlendirme Raporu akışının temelini oluşturmuştur.

## 4. Mimari Kazanımlar

Semantic HTML Foundation tamamlanmıştır. Altı ekran `main`, `section`, `header`, `footer`, `form`, `fieldset`, `article`, `aside` gibi semantik yapılarla kurulmuş; form alanları label ilişkileriyle erişilebilirlik temelini koruyacak şekilde yerleştirilmiştir.

Screen Flow yaklaşımı oluşturulmuştur. MAHİR tek sayfalık bir HTML dosyası içinde kalırken, kullanıcıya uzun bir sayfa yerine adım adım ilerleyen uygulama deneyimi sunacak ekran mantığına geçmiştir.

UI Contract ile bileşen davranışları standartlaştırılmıştır. Primary Button, Secondary Button, Progress Stepper, Upload Box, Dropdown, Information Card, Validation Card, Analysis Progress, Summary Card, Report Section, Source Reference Panel ve Notification Message için ürün davranışı netleştirilmiştir.

Visual Identity iki aşamalı biçimde ele alınmıştır: önce ilke belgesi oluşturulmuş, ardından temel renk, tipografi, kart, buton ve odak görünümü CSS tarafına kontrollü olarak uygulanmıştır.

Navigation Engine ile ekran geçişleri çalışır hale gelmiştir. Başlayalım, Devam, Düzenle, Analizi Başlat ve Raporu Görüntüle eylemleri ekranları değiştirmekte; Progress Stepper aktif ekranı göstermekte ve URL değişmeden sayfa akışı yönetilmektedir.

## 5. Sprint Boyunca Değiştirilen Kararlar

- Tek sayfalık uzun HTML görünümü yerine tek dosya içinde SPA benzeri ekran yönetimi yaklaşımı benimsendi.
- Sadece rapor çıktısı fikri yerine pedagojik karar desteği yaklaşımı öne çıkarıldı.
- Visual Identity tek seferde uygulanmak yerine önce belge, sonra CSS uygulaması olarak iki aşamaya ayrıldı.
- İlk giriş ekranı odağı, kurumsal tanıtımdan öğretmenin güven duygusunu ve kontrolünü güçlendiren akış başlangıcına dönüştürüldü.
- Eksik bilgi yaklaşımı hata dili yerine tamamlanabilir bilgi ve rehber mesaj diliyle ele alındı.
- Gerçek dosya okuma ve analiz yerine önce ekran davranışı, bileşen sözleşmesi ve akış güvenilirliği tamamlandı.
- Görsel asset'lerin varlığı kabul edildi; ancak arayüze bağlanması sonraki onaylı aşamalara bırakıldı.

## 6. Sprint 1 Sonunda Ortaya Çıkan Ürün

Bugün itibarıyla MAHİR, doğrudan tarayıcıda açılabilen, altı ekranlı ve ekran geçişleri çalışan bir HTML/CSS/JavaScript prototipi seviyesine ulaşmıştır.

Kullanıcı akışı Karşılama, Hazırlık, Veri Ekleme, Veri Doğrulama, Analiz Süreci ve Rapor ekranlarından oluşmaktadır. Öğretmen ilk ekranda ürünün amacını ve güven ilkelerini görür; ardından temel bağlamı seçer, veri ekleme alanına geçer, doğrulama ekranında bilgileri kontrol eder, analiz sürecini izler ve rapor ekranına ulaşır.

Ürün henüz gerçek yapay zekâ, gerçek veri analizi, OCR, dosya okuma, veritabanı, kullanıcı hesabı veya PDF/Word üretimi içermez. Ancak MAHİR'in ürün dili, temel ekran mimarisi, bileşen davranışları, görsel kimlik yönü ve navigation altyapısı Sprint 1 sonunda oluşmuştur.

Bu durum, Sprint 1'i bir fikir doğrulama ve ürün omurgası kurma sprinti olarak başarıyla kapatmaktadır.

## 7. Sprint 2'ye Devreden Konular

- Asset Integration
- AI Decision Engine
- Gerçek veri analizi
- Knowledge Base
- Gerçek rapor üretimi
