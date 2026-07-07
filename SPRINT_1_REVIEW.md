# Sprint 1 Closing Report

MAHİR - Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı

Sprint 1, MAHİR prototipinin ürün yönünü, çalışma disiplinini, temel kullanıcı akışını ve ilk arayüz omurgasını oluşturmak için yürütülmüştür. Bu rapor teknik uygulama detaylarından çok, Sprint 1 sonunda ortaya çıkan ürün kararlarını ve kazanımları özetler.

## 1. Sprint Amacı

Sprint 1'in ana amacı, MAHİR'i yalnızca bir fikir olmaktan çıkarıp öğretmen kontrollü, Türkçe çalışan ve sınav analizi raporu üretim sürecine hazırlanan somut bir prototip temeline dönüştürmekti.

Bu sprintte ürünün ilk ilkeleri netleştirildi: MAHİR öğretmenin yerine karar veren bir sistem olmayacak, öğretmenin sınav verilerini daha düzenli, kanıta dayalı ve raporlanabilir hale getirmesine yardımcı olan bir eğitim evrakı prototipi olacaktır.

Sprint boyunca hedef, büyük bir sistem kurmak değil; güven veren, sade, resmi dile uygun ve adım adım geliştirilebilir bir ürün zemini oluşturmaktı.

## 2. Tamamlanan Feature'lar

Sprint 1 kapsamında Feature 01-16 tamamlanmıştır.

| Feature | Kapanış Özeti |
| --- | --- |
| Feature 01 | Kurumsal giriş ekranı için ilk semantik HTML iskeleti oluşturuldu. |
| Feature 02 | Ana sayfa yerleşimi için ilk layout düzeni kuruldu. |
| Feature 03 | Sistem fontlarına dayalı temel tipografi hiyerarşisi oluşturuldu. |
| Feature 04 | Kurumsal görsel varlıklar için `assets` klasör yapısı ve adlandırma standardı belirlendi. |
| Feature 05 | Logo, hero, bayrak ve ikon varlıklarının hedef dosya yolları netleştirildi. |
| Feature 06 | MAHİR Design System belgesi oluşturularak tasarım kararları tek referansta toplandı. |
| Feature 07 | Roadmap, changelog ve development log belgeleriyle proje yönetim zemini kuruldu. |
| Feature 08 | Altı ekranlık düşük sadakatli wireframe hazırlandı. |
| Feature 09 | Wireframe genişletilerek her ekran için amaç, psikoloji, işlem ve başarı kriterleri tanımlandı. |
| Feature 10 | UI Contract oluşturularak temel bileşen davranışları standartlaştırıldı. |
| Feature 11 | Altı ekranlık semantik HTML temeli kuruldu. |
| Feature 12 | Visual Identity belgesiyle güven, resmiyet, sadelik ve erişilebilirlik ilkeleri tanımlandı. |
| Feature 13 | Görsel kimlik ilkeleri `styles.css` içine temel renk, tipografi, kart ve buton dili olarak uygulandı. |
| Feature 14 | İlk kullanıcı arayüzü için container, bölüm boşlukları, kartlar, stepper, upload, validation ve rapor yerleşim temeli oluşturuldu. |
| Feature 15 | Ekranlar tek sayfa içinde bağımsız `screen` yapısına ayrıldı; başlangıçta yalnızca karşılama ekranının görünmesi sağlandı. |
| Feature 16 | JavaScript tabanlı navigation engine kuruldu; ekran geçişleri, aktif stepper durumu ve sayfa üstüne dönüş davranışı çalışır hale getirildi. |

## 3. Temel Mimari Kararlar

MAHİR'in ilk prototipi yalın HTML, CSS ve JavaScript ile geliştirilecek şekilde konumlandırıldı. Framework, build sistemi, veritabanı, API, OCR, dosya okuma, PDF/Word üretimi ve gerçek yapay zeka entegrasyonu Sprint 1 kapsamı dışında bırakıldı.

Tek sayfalık yapı korunurken kullanıcı deneyimi uzun bir sayfa gibi değil, adım adım ilerleyen bir uygulama akışı gibi tasarlandı. Bu karar, öğretmenin aynı anda yalnızca bulunduğu ekranı görmesini ve süreçte zihinsel yükünün azalmasını destekler.

Bileşen dili UI Contract ile ayrıştırıldı. Primary Button, Secondary Button, Progress Stepper, Upload Box, Validation Card, Analysis Progress, Report Section ve Notification Message gibi temel parçalar ürün davranışı açısından standart hale getirildi.

## 4. UX Kararları

Sprint 1'de UX yaklaşımı öğretmen psikolojisi üzerinden şekillendirildi. Karşılama ekranı, öğretmene yeni bir yük değil, kontrollü bir destek aracı sunduğunu açıkça hissettirecek şekilde kurgulandı.

Akış, Karşılama, Hazırlık, Veri Ekleme, Veri Doğrulama, Analiz Süreci ve Rapor ekranları üzerinden ilerleyecek şekilde tanımlandı. Bu sıralama öğretmenin önce bağlamı belirlemesini, sonra veriyi paylaşmasını, ardından kontrol ve rapor adımlarına geçmesini sağlar.

Hata dili yerine rehber mesaj yaklaşımı benimsendi. Eksik bilgiler keskin bir engel gibi değil, tamamlanabilir bilgiler olarak sunulacaktır. Bu karar MAHİR'in öğretmen dostu ve güven veren ürün dili açısından temel bir kazanımdır.

## 5. Ürün Kazanımları

Sprint 1 sonunda MAHİR'in ürün karakteri belirginleşmiştir. Prototip artık yalnızca bir rapor fikri değil; öğretmenin sınav verisini yapılandırılmış değerlendirme ve rapor taslağına dönüştürmesini anlatan ekran akışına sahiptir.

Öğretmen kontrolü ilkesi tüm belgelerde ve arayüz kararlarında korunmuştur. Raporun sahibi öğretmendir; MAHİR yalnızca düzenleme, yapılandırma ve taslak hazırlama desteği sağlar.

Ürünün dili resmi, ölçülü, akademik ve kamu hizmeti anlayışına uygun bir hatta oturtulmuştur. Tasarım yönü de MEB, EBA, ÖBA, e-Okul ve MEBBİS gibi resmi sistemlerin güven tonunu çağdaş ve sade bir arayüz yaklaşımıyla birleştirecek şekilde tanımlanmıştır.

## 6. Tamamlanan Teknik Altyapı

Sprint 1'de ürünün çalışabilir temel dosya yapısı korunmuş ve genişletilmiştir. `index.html`, `styles.css` ve `script.js` dosyaları prototipin ana uygulama yüzeyi olarak yapılandırılmıştır.

Altı ekranın semantik HTML temeli oluşturulmuş, ekranlar `screen` mantığıyla ayrılmış ve JavaScript ile yönetilebilir hale getirilmiştir. Navigation engine sayesinde Başlayalım, Devam, Düzenle, Analizi Başlat ve Raporu Görüntüle eylemleri ekran akışını değiştirebilir duruma gelmiştir.

CSS tarafında görsel kimlik ilkeleri, temel tipografi, kart dili, buton görünümü, section boşlukları ve ekran durum sınıfları oluşturulmuştur. Bu altyapı ileride yapılacak tasarım ve işlev geliştirmeleri için kontrollü bir başlangıç sağlar.

## 7. Sprint Sonunda Ortaya Çıkan Ürün Durumu

Sprint 1 sonunda MAHİR, doğrudan tarayıcıda açılabilir bir HTML/CSS/JavaScript prototipi halindedir. Kullanıcı ilk olarak karşılama ekranını görür ve adım adım hazırlık, veri ekleme, doğrulama, analiz süreci ve rapor ekranına ilerleyebilir.

Prototip henüz gerçek veri işleme, dosya okuma, yapay zeka, OCR veya rapor üretimi yapmaz. Buna rağmen ürün deneyiminin ana omurgası kurulmuştur: öğretmen kontrollü, aşamalı, güven veren ve rapor taslağına yönelen bir akış görünür durumdadır.

Sprint 1 çıktısı, Sprint 2'de yapılacak içerik, etkileşim, doğrulama ve rapor alanı geliştirmeleri için sağlam bir ürün zemini sağlar.

## 8. Sprint 2'ye Devreden Konular

Sprint 2'ye devreden başlıklar şunlardır:

- Hazırlık ekranındaki ders ve sınıf düzeyi seçimlerinin rehber mesajlarla güçlendirilmesi.
- Veri ekleme ekranında gerçek dosya okuma yapmadan örnek/prototip veri giriş deneyiminin netleştirilmesi.
- Veri doğrulama ekranında öğretmen kontrolünü destekleyen düzenleme alanlarının olgunlaştırılması.
- Analiz süreci ekranında aşama durumlarının daha anlaşılır hale getirilmesi.
- Rapor ekranındaki bölümlerin örnek taslak içeriklerle ürün değerini daha görünür kılması.
- Görsel varlıkların uygun sprintte ve kapsam onayıyla arayüze kontrollü biçimde bağlanması.
- Erişilebilirlik, okunabilirlik ve temel kullanım testlerinin genişletilmesi.

Bu konular Sprint 2 çalışması değildir; yalnızca Sprint 1 sonunda devreden ürün gündemidir.

## 9. Sprint 1 Değerlendirmesi

Sprint 1 başarılı şekilde tamamlanmıştır. Çalışma, Development Charter ilkesine uygun biçimde küçük, kontrollü ve onaylı adımlarla ilerlemiştir.

Kapsam yönetimi korunmuştur. Gerçek yapay zeka, veri işleme, dosya okuma, PDF/Word üretimi, kullanıcı hesabı veya karmaşık sistem entegrasyonu eklenmemiştir. Bu sayede prototip, erken aşamada sade ve denetlenebilir kalmıştır.

En önemli ürün kazanımı, MAHİR'in yönünün netleşmesidir. Ürün artık öğretmenin güven duygusunu, karar yetkisini ve resmi raporlama ihtiyacını merkeze alan bir eğitim aracı olarak şekillenmektedir.

## 10. Sonuç

Sprint 1, MAHİR için güçlü bir başlangıç sprinti olmuştur. Projenin geliştirme disiplini, belge mimarisi, tasarım ilkeleri, kullanıcı akışı, bileşen sözleşmesi, semantik HTML temeli, görsel kimlik uygulaması ve ekran geçiş motoru tamamlanmıştır.

Sprint sonunda MAHİR, öğretmen kontrollü sınav analizi ve değerlendirme raporu prototipi için çalışır bir ilk ürün omurgasına sahiptir. Bundan sonraki ilerleme, aynı kontrollü geliştirme anlayışıyla ve kullanıcı onayıyla yürütülmelidir.
