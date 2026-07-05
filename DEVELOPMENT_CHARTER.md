# MAHİR Development Charter v1.0

Bu belge, MAHİR projesinin geliştirme kurallarını, sürüm yönetimini, dosya düzenini ve çalışma disiplinini tanımlar. Amaç, prototipin küçük, anlaşılır, öğretmen kontrollü ve sürdürülebilir adımlarla ilerlemesini sağlamaktır.

## 1. Proje Adı ve Amacı

Proje adı: MAHİR - Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı

MAHİR, Türkçe çalışan ve öğretmen kontrolünü merkeze alan bir eğitim evrakı prototipidir. İlk hedef, "Sınav Analizi ve Değerlendirme Raporu" için sade, modern ve tek sayfalık bir HTML/CSS/JavaScript arayüzü geliştirmektir.

Prototip, öğretmenin sınav bilgilerini, soru bazlı verileri ve öğrenme çıktılarıyla ilgili değerlendirmelerini yapılandırılmış rapor taslaklarına dönüştürme fikrini görselleştirmek için hazırlanır. Bu aşamada üretilen tüm içerikler örnek taslak kabul edilir; son düzenleme ve onay öğretmene aittir.

## 2. Teknik Kapsam

İlk geliştirme aşamasında proje yalın web teknolojileriyle yürütülür:

- HTML ile tek sayfalık yapı kurulur.
- CSS ile sade, modern ve okunaklı bir arayüz tasarlanır.
- JavaScript ile yalnızca temel sayfa içi etkileşimler sağlanır.
- Harici framework, paket yöneticisi veya build sistemi kullanılmaz.
- Proje dosyaları doğrudan tarayıcıda açılabilecek biçimde tutulur.
- GitHub Desktop, sürüm takibi ve GitHub'a gönderim için temel araç olarak kullanılır.

Bu teknik kapsam, prototipin hızlı anlaşılmasını, kolay incelenmesini ve öğretmen ihtiyaçlarına göre adım adım şekillendirilmesini amaçlar.

## 3. İlk Aşamada Yapılmayacaklar

Aşağıdaki işler ilk prototip aşamasında yapılmayacaktır:

- Gerçek yapay zekâ entegrasyonu
- Veritabanı bağlantısı
- Kullanıcı hesabı, giriş sistemi veya yetkilendirme
- OCR veya optik form okuma
- Dosya yükleme ve dosya okuma
- PDF veya Word üretimi
- Harici API entegrasyonu
- Çok sayfalı uygulama yapısı
- Karmaşık rapor motoru
- Otomatik karar verme veya öğretmen onayı olmadan çıktı üretme
- Logo, bayrak, ikon veya görsel kimlik çalışması
- Hero görseli veya büyük tanıtım görseli

Bu sınırlamalar, projenin ilk aşamada net, denetlenebilir ve küçük adımlarla gelişmesini sağlar.

## 4. Klasör ve Dosya Yapısı

Projenin ilk aşamadaki dosya yapısı yalın tutulur:

```text
MAHIR-PROTOTIP-HTML/
├─ README.md
├─ DEVELOPMENT_CHARTER.md
├─ index.html
├─ styles.css
└─ script.js
```

Dosya sorumlulukları:

- `README.md`: Projenin kısa tanımı, çalışma özeti ve ana belge bağlantıları.
- `DEVELOPMENT_CHARTER.md`: Geliştirme kuralları, sürüm sistemi ve çalışma disiplini.
- `index.html`: Tek sayfalık arayüzün HTML yapısı.
- `styles.css`: Görsel düzen, tipografi, renkler ve responsive davranış.
- `script.js`: Sayfa içi temel etkileşimler.

Yeni klasör veya dosya yalnızca sprint kapsamı açıkça gerektiriyorsa eklenir.

## 5. Sprint ve Sürümleme Sistemi

Geliştirme küçük sürümler halinde ilerler:

- v0.1 - Proje iskeleti
- v0.2 - Temel giriş ekranı
- v0.3 - Sınav bilgileri formu
- v0.4 - Soru bazlı analiz alanı
- v0.5 - Taslak üretim alanı
- v1.0 - İlk çalışan prototip

Her sürüm için kurallar:

- Sürüm başlamadan önce kapsam netleştirilir.
- Kapsam dışı özellik eklenmez.
- Sürüm sonunda değişen dosyalar raporlanır.
- Eksik, risk veya teknik not varsa ayrıca belirtilir.
- Kullanıcı onayı alınmadan bir sonraki sürüme geçilmez.
- GitHub'a gönderim, kullanıcı onayı ve kontrolüyle yapılır.

Commit mesajları kısa ve sürüm odaklı yazılır. Örnek: `v0.2 temel giriş ekranı`.

## 6. GitHub Desktop ile Çalışma Akışı

GitHub Desktop bu projede ana Git aracı olarak kullanılır.

Önerilen akış:

1. GitHub Desktop açılır.
2. `MAHIR-PROTOTIP-HTML` deposu seçilir.
3. Çalışma klasörünün `C:\Projects\MAHIR-PROTOTIP-HTML` olduğu kontrol edilir.
4. Sprint kapsamındaki dosya değişiklikleri yapılır.
5. GitHub Desktop içinde `Changes` sekmesinde değişen dosyalar incelenir.
6. Kapsam dışı dosya değişikliği varsa commit öncesi durdurulur.
7. Commit mesajı sürüme uygun yazılır.
8. `Commit to main` seçilir.
9. `Push origin` ile GitHub'a gönderilir.
10. GitHub web arayüzünde dosyalar kontrol edilir.

Commit veya push işlemi, kullanıcı açıkça onaylamadan otomatik yapılmaz.

## 7. Codex Çalışma Kuralları

Codex bu projede uygulayıcı ve denetleyici yardımcı olarak çalışır.

Kurallar:

- Kullanıcı onayı olmadan yeni sprint başlatılmaz.
- Kullanıcı onayı olmadan GitHub üzerinde işlem yapılmaz.
- Her sprintte yalnızca belirtilen dosyalar değiştirilir.
- Kapsam dışı özellik önerilse bile uygulanmaz.
- Büyük değişiklikler küçük ve anlaşılır parçalara bölünür.
- Kod değişikliği yapılmadan önce mevcut dosyalar okunur.
- İşlem sonunda değişen dosyalar açıkça raporlanır.
- Eksik doğrulama varsa saklanmaz, açıkça belirtilir.
- Kullanıcının elle yaptığı değişiklikler geri alınmaz.
- `index.html`, `styles.css` ve `script.js` gibi ana dosyalarda gereksiz refaktör yapılmaz.

Codex, proje boyunca öğretmen kontrolü ilkesini ve sade prototip yaklaşımını korumalıdır.

## 8. Tasarım Sistemi İlkeleri

MAHİR arayüzü öğretmen dostu, sakin ve iş odaklı olmalıdır.

Tasarım ilkeleri:

- Türkçe metinler açık, kısa ve resmi-samimi dengede olmalıdır.
- Arayüz sade, modern ve okunabilir kalmalıdır.
- Gereksiz görsel kalabalık oluşturulmamalıdır.
- Renkler ölçülü kullanılmalıdır.
- Metin hiyerarşisi net olmalıdır.
- Buton, açıklama ve durum mesajları öğretmeni yönlendirmelidir.
- Mobil ve masaüstü görünümde metin taşması oluşmamalıdır.
- Kartlar ve paneller sade kenarlık, düşük gölge ve dengeli boşluklarla kullanılmalıdır.
- Uygulama, bir tanıtım sitesi gibi değil, kullanılabilir bir eğitim aracı gibi hissettirmelidir.

İlk aşamada logo, ikon, bayrak, hero görseli veya marka görsel sistemi eklenmez.

## 9. Her Sprint Sonunda Kontrol Listesi

Her sprint sonunda aşağıdaki kontroller yapılır:

- Belirlenen kapsam tamamlandı mı?
- Kapsam dışı özellik eklendi mi?
- Yeni dosya eklendiyse gerekçesi var mı?
- Değişen dosyalar raporlandı mı?
- README veya ilgili belge güncellendi mi?
- Sayfa temel olarak açılabilir durumda mı?
- JavaScript hata riski var mı?
- Mobil görünümde belirgin taşma riski var mı?
- Öğretmen kontrolü ilkesi korunuyor mu?
- Bir sonraki sürüme geçmeden kullanıcı onayı alındı mı?

Kontrol sonucu kısa ve net şekilde kullanıcıya bildirilir.

## 10. Yasaklı İşlemler

Aşağıdaki işlemler kullanıcı açıkça istemedikçe yapılmaz:

- Kullanıcı onayı olmadan commit veya push yapmak
- Kullanıcı onayı olmadan sonraki sürüme geçmek
- Kapsam dışı dosya oluşturmak
- Kapsam dışı özellik eklemek
- Gerçek yapay zekâ, API veya veritabanı entegrasyonu yapmak
- Dosya yükleme, OCR, PDF veya Word üretimi eklemek
- Çok sayfalı yapı kurmak
- Harici framework veya paket sistemi eklemek
- Mevcut kullanıcı değişikliklerini geri almak
- `git reset`, `git checkout --` veya benzeri geri alma işlemleri yapmak
- Gizli anahtar, token veya kişisel veri istemek ya da depoya yazmak
- Öğretmen onayı olmadan kesin rapor üreten bir akış tasarlamak

Bu charter, proje ilerledikçe kullanıcı onayıyla güncellenebilir. v1.0'a kadar temel amaç, küçük adımlar, açık kapsam ve öğretmen kontrolünü korumaktır.
