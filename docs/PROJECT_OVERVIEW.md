# MAHİR – Proje Genel Bakışı

**Maarif Anlayışıyla Hizmet İzleme ve Raporlama Ajanı**

MAHİR; sınav verilerini öğrenme kanıtına dönüştürerek öğretmenlere kaynak temelli analiz, pedagojik değerlendirme ve raporlama desteği sunmak amacıyla geliştirilen çok ajanlı bir yapay zekâ prototipidir.

## 1. MAHİR’in Açılımı

MAHİR, **“Maarif Anlayışıyla Hizmet İzleme ve Raporlama Ajanı”** ifadesinin kısaltmasıdır. Adı; eğitimdeki öğrenme kanıtlarını Türkiye Yüzyılı Maarif Modeli ve ilgili resmî kaynaklar doğrultusunda izleme, anlamlandırma ve raporlama amacını yansıtmaktadır.

## 2. Projenin Ortaya Çıkış Gerekçesi

MAHİR, dört eğitimcinin sahada ortak biçimde gözlemlediği bir ihtiyaçtan doğdu. Okullarda sınavlar, ortak yazılılar, soru analizleri, zümre çalışmaları ve resmî raporlar için çok sayıda veri üretilmesine rağmen bu veriler çoğu zaman dağınık kalmakta; öğrenmeyi geliştirecek bilgiye dönüşememektedir.

Öğretmen aynı veriyi farklı belgeler için tekrar tekrar işlemekte, asıl mesleki gücünü kullanması gereken pedagojik değerlendirmeye daha az zaman ayırmaktadır. Takımımız bu sorunu yalnızca bir evrak yükü olarak değil, **eğitim verisinin anlamlandırılamaması problemi** olarak ele almıştır.

## 3. Çözdüğü Problem

MAHİR; öğretmenin sisteme yüklediği sınav verilerini yapılandırmayı, sınıf ve soru bazlı başarıyı analiz etmeyi, öğrenme çıktılarındaki eksiklikleri görünür kılmayı, resmî kaynaklara dayalı iyileştirme önerileri üretmeyi ve sonuçları öğretmen onayına sunulan raporlara dönüştürmeyi hedeflemektedir.

- Dağınık sınav verilerinin tek bir anlamlı akışta toplanması ve doğrulanması
- Puanların yalnızca başarı yüzdesi olarak değil, öğrenme kanıtı olarak değerlendirilmesi
- Aynı verinin farklı rapor ve resmî belge süreçlerinde yeniden kullanılabilmesi
- Kaynağı gösterilebilen, gerekçeli ve öğretmen tarafından denetlenebilir çıktılar üretilmesi

## 4. MAHİR’in Yaklaşımı

Yaklaşımımızın merkezinde **“insan denetimli, kaynak temelli ve görevleri sınırlandırılmış yapay zekâ”** ilkesi bulunmaktadır. MAHİR’i tek bir modelin her şeyi yaptığı kapalı bir yapı olarak değil; veri doğrulama, sınav analizi, öğrenme çıktılarıyla eşleştirme, kaynak tarama, pedagojik değerlendirme ve raporlama gibi görevlerde uzmanlaşan bileşenlerin birlikte çalıştığı çok ajanlı bir sistem olarak tasarlıyoruz.

- **İnsan onayı:** Sistem önerir; öğretmen inceler, düzeltir ve nihai onayı verir.
- **Kaynak temellilik:** Analiz ve öneriler resmî programlar ile güvenilir eğitim kaynaklarına dayandırılır.
- **Açıklanabilirlik:** Sonucun hangi veriden ve hangi kaynaktan üretildiği izlenebilir olmalıdır.
- **Asgari veri ve güvenlik:** Gereksiz kişisel veri alınmaz; ajanların görev ve erişim sınırları belirlenir.
- **Modülerlik:** Sistem farklı kademe, ders, sınıf ve veri giriş biçimlerine uyarlanabilir biçimde geliştirilir.

## 5. Mevcut Durum ve Bugünkü Sınırlar

Şu anda sınav ve sınıf bilgilerinin alınabildiği, öğrenci ve soru bazlı verilerin işlenebildiği, analiz raporunun oluşturulduğu, öğretmen onayı sonrasında kilitlendiği ve PDF/Word olarak dışa aktarılabildiği çalışan bir web prototipi bulunmaktadır. Kod geliştirme süreci GitHub üzerinden yürütülmektedir.

Prototipte CSV ve Word tabanlı veri giriş akışları çalışmaktadır. PDF ve görüntü tabanlı belge işleme geliştirme sürecindedir.

Bununla birlikte mevcut prototip henüz hedeflenen uçtan uca yapay zekâ sistemi değildir. OCR ile fotoğraf/PDF okuma, doğal dilde veri kabulü, MAHİR Index üzerinden resmî kaynaklara erişen RAG yapısı, ajan orkestrasyonu, otomatik kaynak gösterimi ve güvenlik katmanları geliştirme ve bütünleştirme aşamasındadır.

İlk sürümün odağı sınav analizi ve raporlamadır; sistem henüz tüm öğretmen evraklarını, tüm dersleri ve tüm kademeleri kapsayan tamamlanmış bir ürün değildir.

## 6. Gelecek Vizyonu ve Finalde Sunulması Planlanan Nokta

Uzun vadede MAHİR’i; öğretmenin farklı biçimlerde sunduğu eğitim verisini anlayan, doğru resmî kaynakla ilişkilendiren, öğrenme eksiklerini izleyen ve kurumun raporlama süreçlerini destekleyen güvenilir bir eğitim dil ajanına dönüştürmek istiyoruz.

Finalde bütün vizyonu eksiksiz tamamlanmış gibi sunmak yerine, dar kapsamlı fakat gerçek ve ölçülebilir bir uçtan uca akış göstermeyi planlıyoruz:

**veri girişi → doğrulama → soru ve öğrenme çıktısı analizi → kaynak temelli pedagojik öneri → öğretmen kontrolü → onaylı Word/PDF raporu**

Ana pilotumuz **9. sınıf Türk Dili ve Edebiyatı**, farklı kademe ve disiplinlerde doğrulama pilotumuz **Fen Bilimleri** olacaktır.

Hedefimiz; çalışan prototipi çok ajanlı mimari, MAHİR Index ve güvenlik ilkeleriyle bütünleşmiş, jüri önünde canlı olarak gösterilebilen bir MVP düzeyine taşımaktır.

## Pilot Kapsamı

- **Ana pilot:** 9. Sınıf Türk Dili ve Edebiyatı
- **Doğrulama pilotu:** Fen Bilimleri

### Gösterilecek Uçtan Uca Akış

**Veri Girişi → Doğrulama → Sınav Analizi → Öğrenme Çıktısı Analizi → Kaynak Temelli Pedagojik Öneriler → Öğretmen Onayı → Word / PDF Rapor**
