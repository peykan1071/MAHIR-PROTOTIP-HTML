# MAHİR High Fidelity Wireframe

Feature 09 - Sprint 1

Bu belge, MAHİR ilk prototipi için 6 ekranlık wireframe taslağını ve her ekranın davranış tanımını içerir. Belge metin tabanlıdır; kod, görsel, renk, ikon, logo, hero ya da bayrak yerleşimi içermez.

## 1. Karşılama Ekranı

```text
+--------------------------------------------------------------------+
| MAHİR                                                              |
| Maarif Anlayışıyla Hizmet İşleme ve Raporlama Ajanı                |
+--------------------------------------------------------------------+
|                                                                    |
| Her sınav, öğretimi geliştirecek güçlü veriler içerir.             |
| MAHİR, bu verileri güvenilir eğitim kararlarına dönüştürmenize     |
| destek olur.                                                       |
|                                                                    |
| Güven maddeleri                                                    |
| - Yeni bir iş yükü oluşturmaz.                                     |
| - Son karar her zaman öğretmenindir.                               |
| - Her değerlendirme güvenilir kanıtlarla desteklenir.              |
|                                                                    |
| [ Başlayalım ]                                                     |
|                                                                    |
| İlk adımda yalnızca dersinizi ve sınıf düzeyinizi seçmeniz          |
| yeterlidir.                                                        |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Öğretmene MAHİR'in ne yaptığını sade, güven veren ve yük azaltan bir dille anlatmak; ilk adıma geçmeye hazır hale getirmek.

2. Öğretmenin psikolojisi

   Öğretmen bu ekranda kontrolün kendisinde olduğunu, sürecin ek iş yükü değil destek aracı olduğunu ve verilerinin anlamlı bir rapor taslağına dönüşebileceğini hissetmelidir.

3. Öğretmenin yaptığı işlem

   Ana mesajı ve güven maddelerini okur, sürecin kapsamını anlar ve `Başlayalım` butonuyla hazırlık ekranına geçer.

4. Sistemin yaptığı işlem

   MAHİR, öğretmene ürünün amacı, öğretmen kontrolü ilkesi ve ilk adımın düşük zahmetli olduğu bilgisini sunar.

5. Zorunlu alanlar

   Bu ekranda zorunlu bilgi girişi yoktur.

6. İsteğe bağlı alanlar

   Bu ekranda isteğe bağlı bilgi girişi yoktur.

7. Sonraki ekrana geçiş şartı

   Öğretmenin `Başlayalım` butonunu seçmesi yeterlidir.

8. Hata yerine kullanılacak rehber mesajlar

   - Başlamak için yalnızca bir sonraki adımda dersinizi ve sınıf düzeyinizi seçmeniz yeterlidir.
   - Bu süreçte son düzenleme ve karar her zaman öğretmene aittir.

9. Bu ekranın başarı kriteri

   Öğretmen, MAHİR'in amacını anlayarak tereddüt etmeden hazırlık ekranına geçebilmelidir.

## 2. Hazırlık Ekranı

```text
+--------------------------------------------------------------------+
| Hazırlık / Veri / Analiz / Rapor                                   |
| [Hazırlık] ---- [Veri] ---- [Analiz] ---- [Rapor]                  |
+--------------------------------------------------------------------+
|                                                                    |
| Hazırlık                                                           |
|                                                                    |
| Ders seçimi                                                        |
| +--------------------------------------------------------------+   |
| | Ders seçiniz                                                 |   |
| +--------------------------------------------------------------+   |
|                                                                    |
| Sınıf düzeyi seçimi                                                |
| +--------------------------------------------------------------+   |
| | Sınıf düzeyi seçiniz                                        |   |
| +--------------------------------------------------------------+   |
|                                                                    |
|                                            [ Devam ]               |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Analiz ve rapor taslağı için temel bağlamı belirlemek: ders ve sınıf düzeyi.

2. Öğretmenin psikolojisi

   Öğretmen sürecin basit başladığını, ayrıntılı veri girişi yapmadan önce yalnızca temel seçimlerle ilerlediğini hissetmelidir.

3. Öğretmenin yaptığı işlem

   Ders seçimini yapar, sınıf düzeyini seçer ve `Devam` butonuyla veri ekleme ekranına geçer.

4. Sistemin yaptığı işlem

   MAHİR, seçilen ders ve sınıf düzeyini sonraki ekranlarda kullanılacak temel bağlam olarak hazırlar.

5. Zorunlu alanlar

   - Ders seçimi
   - Sınıf düzeyi seçimi

6. İsteğe bağlı alanlar

   Bu ekranda isteğe bağlı alan yoktur.

7. Sonraki ekrana geçiş şartı

   Ders ve sınıf düzeyi seçilmiş olmalıdır.

8. Hata yerine kullanılacak rehber mesajlar

   - Devam etmek için dersinizi seçiniz.
   - Devam etmek için sınıf düzeyini seçiniz.
   - Bu bilgiler rapor taslağının doğru bağlamda hazırlanmasına yardımcı olur.

9. Bu ekranın başarı kriteri

   Öğretmen, ders ve sınıf düzeyini kolayca seçip veri ekleme adımına geçebilmelidir.

## 3. Veri Ekleme Ekranı

```text
+--------------------------------------------------------------------+
| Hazırlık / Veri / Analiz / Rapor                                   |
| [Hazırlık] ---- [Veri] ---- [Analiz] ---- [Rapor]                  |
+--------------------------------------------------------------------+
|                                                                    |
| Mevcut sınav verilerinizi paylaşmanız yeterlidir.                  |
|                                                                    |
| +--------------------------------------------------------------+   |
| |                                                              |   |
| |                 Sürükle bırak alanı                          |   |
| |                                                              |   |
| |                 [ Dosya seç ]                                |   |
| |                                                              |   |
| +--------------------------------------------------------------+   |
|                                                                    |
| Desteklenen biçimler: Görsel, PDF, Word, Excel, CSV                |
|                                                                    |
| Elle veri girişi alternatifi                                       |
|                                                                    |
| [ Geri ]                                            [ Devam ]      |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Öğretmenin mevcut sınav verilerini paylaşmasını veya gerekiyorsa elle veri girişi yolunu seçmesini sağlamak.

2. Öğretmenin psikolojisi

   Öğretmen elindeki mevcut belge ve verilerin yeterli olduğunu, tek bir doğru giriş yolu olmadığını ve alternatiflerin açık olduğunu hissetmelidir.

3. Öğretmenin yaptığı işlem

   Sınav verisini sürükle bırak alanına ekler, `Dosya seç` butonunu kullanır veya elle veri girişi alternatifini seçer. Gerekirse `Geri` butonuyla hazırlık ekranına döner.

4. Sistemin yaptığı işlem

   MAHİR, öğretmenin seçtiği veri paylaşım yolunu kabul eder ve sonraki adımda doğrulanacak bilgi başlıklarını hazırlar.

5. Zorunlu alanlar

   - Dosya ekleme veya elle veri girişi yolunun seçilmesi

6. İsteğe bağlı alanlar

   - Birden fazla destekleyici veri belgesi
   - Elle girişte ek açıklama veya not

7. Sonraki ekrana geçiş şartı

   En az bir veri paylaşım yolu seçilmiş olmalıdır.

8. Hata yerine kullanılacak rehber mesajlar

   - Devam etmek için bir dosya ekleyebilir veya elle veri girişi seçeneğini kullanabilirsiniz.
   - Elinizdeki veri tam değilse de başlayabilirsiniz; eksik bilgiler sonraki adımda tamamlanabilir.
   - Desteklenen biçimler: Görsel, PDF, Word, Excel, CSV.

9. Bu ekranın başarı kriteri

   Öğretmen, mevcut verisini zorlanmadan paylaşabilmeli veya elle veri girişi alternatifini güvenle seçebilmelidir.

## 4. Veri Doğrulama Ekranı

```text
+--------------------------------------------------------------------+
| Hazırlık / Veri / Analiz / Rapor                                   |
| [Hazırlık] ---- [Veri] ---- [Analiz] ---- [Rapor]                  |
+--------------------------------------------------------------------+
|                                                                    |
| Veri Doğrulama                                                     |
|                                                                    |
| Algılanan bilgiler                                                 |
| +--------------------------------------------------------------+   |
| | Ders:                                                        |   |
| | Sınıf düzeyi:                                                |   |
| | Öğrenci sayısı:                                              |   |
| | Soru sayısı:                                                 |   |
| | Öğrenme çıktısı eşleştirmesi:                                |   |
| | Veri giriş yöntemi:                                          |   |
| +--------------------------------------------------------------+   |
|                                                                    |
| Daha kapsamlı değerlendirme için öğrenme çıktısı eşleştirmesi      |
| tamamlanabilir.                                                    |
|                                                                    |
| [ Düzenle ]                                  [ Analizi Başlat ]    |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Analize geçmeden önce temel bilgileri öğretmene görünür kılmak ve gerektiğinde tamamlanabilir alanları nazikçe belirtmek.

2. Öğretmenin psikolojisi

   Öğretmen hatalı yakalanmış gibi hissetmemeli; bilgileri gözden geçiren, düzeltebilen ve son kararı veren kişi olduğunu hissetmelidir.

3. Öğretmenin yaptığı işlem

   Algılanan bilgileri kontrol eder, gerekirse `Düzenle` butonuyla düzeltme yapar veya bilgileri yeterli görüyorsa `Analizi Başlat` butonunu seçer.

4. Sistemin yaptığı işlem

   MAHİR, ders, sınıf düzeyi, öğrenci sayısı, soru sayısı, öğrenme çıktısı eşleştirmesi ve veri giriş yöntemi başlıklarını öğretmenin kontrolüne sunar.

5. Zorunlu alanlar

   - Ders
   - Sınıf düzeyi
   - Öğrenci sayısı
   - Soru sayısı
   - Veri giriş yöntemi

6. İsteğe bağlı alanlar

   - Öğrenme çıktısı eşleştirmesi
   - Ek öğretmen notu

7. Sonraki ekrana geçiş şartı

   Zorunlu bilgiler görünür ve öğretmen tarafından yeterli görülmüş olmalıdır.

8. Hata yerine kullanılacak rehber mesajlar

   - Daha kapsamlı değerlendirme için öğrenme çıktısı eşleştirmesi tamamlanabilir.
   - Öğrenci sayısı net değilse bu bilgiyi düzenleyerek rapor taslağını güçlendirebilirsiniz.
   - Soru sayısı bilgisi analiz çizelgesinin daha düzenli hazırlanmasına yardımcı olur.

9. Bu ekranın başarı kriteri

   Öğretmen, analize başlamadan önce temel bilgileri anlayarak ve gerekirse düzelterek güvenle ilerleyebilmelidir.

## 5. Analiz Süreci Ekranı

```text
+--------------------------------------------------------------------+
| Hazırlık / Veri / Analiz / Rapor                                   |
| [Hazırlık] ---- [Veri] ---- [Analiz] ---- [Rapor]                  |
+--------------------------------------------------------------------+
|                                                                    |
| Analiz Süreci                                                      |
|                                                                    |
| Aşama listesi                                                      |
|                                                                    |
| [ ] Veriler doğrulanıyor.                                         |
| [ ] Soru ve puan ilişkileri yapılandırılıyor.                      |
| [ ] Öğrenme çıktıları eşleştiriliyor.                              |
| [ ] Sayısal analiz hazırlanıyor.                                   |
| [ ] Kanıt kontrolü yapılıyor.                                      |
| [ ] Pedagojik değerlendirme oluşturuluyor.                         |
| [ ] Öğretim önerileri hazırlanıyor.                                |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Öğretmene rapor taslağı hazırlık sürecinin hangi anlamlı aşamalardan geçtiğini açık ve anlaşılır biçimde göstermek.

2. Öğretmenin psikolojisi

   Öğretmen bekleme sürecinde belirsizlik yaşamamalı; yapılan değerlendirme adımlarının eğitimsel, kanıta dayalı ve ölçülü olduğunu hissetmelidir.

3. Öğretmenin yaptığı işlem

   Aşama listesini izler ve sürecin tamamlanmasını bekler. Bu ekranda öğretmenden ek veri girişi beklenmez.

4. Sistemin yaptığı işlem

   MAHİR, verilerin doğrulanması, soru-puan ilişkisinin yapılandırılması, öğrenme çıktılarının eşleştirilmesi, sayısal analiz, kanıt kontrolü, pedagojik değerlendirme ve öğretim önerileri adımlarını öğretmene anlaşılır şekilde gösterir.

5. Zorunlu alanlar

   Bu ekranda öğretmenin dolduracağı zorunlu alan yoktur.

6. İsteğe bağlı alanlar

   Bu ekranda isteğe bağlı alan yoktur.

7. Sonraki ekrana geçiş şartı

   Aşama listesindeki değerlendirme adımları tamamlanmış görünmelidir.

8. Hata yerine kullanılacak rehber mesajlar

   - Değerlendirme adımları hazırlanıyor; lütfen kısa bir süre bekleyiniz.
   - Kanıt kontrolü tamamlandığında rapor taslağı görüntülenecektir.
   - Eksik görülen bilgiler olursa rapor öncesinde öğretmen kontrolüne sunulacaktır.

9. Bu ekranın başarı kriteri

   Öğretmen, bekleme sürecinde neyin hazırlandığını anlayabilmeli ve rapor ekranına geçişi güvenle bekleyebilmelidir.

## 6. Rapor Ekranı

```text
+--------------------------------------------------------------------+
| Hazırlık / Veri / Analiz / Rapor                                   |
| [Hazırlık] ---- [Veri] ---- [Analiz] ---- [Rapor]                  |
+--------------------------------------------------------------------+
|                                                                    |
| Maarif Modeli Temelli Sınav Analizi ve Değerlendirme Raporu        |
|                                                                    |
| Raporun sahibi öğretmendir.                                        |
| Dil resmî, ölçülü, akademik ve kamu hizmeti anlayışına uygun       |
| olmalıdır.                                                         |
|                                                                    |
| Bölümler                                                           |
| +--------------------------------------------------------------+   |
| | Genel Değerlendirme                                          |   |
| | Analiz Çizelgesi                                             |   |
| | Öğrenme Çıktıları Değerlendirmesi                            |   |
| | Güçlü Öğrenme Alanları                                       |   |
| | Gelişimi Desteklenecek Alanlar                               |   |
| | Öğretim Önerileri                                            |   |
| | İzleme ve Gelişim Planı                                      |   |
| | Kaynak Dayanakları                                           |   |
| +--------------------------------------------------------------+   |
|                                                                    |
+--------------------------------------------------------------------+
```

### Davranış Tanımı

1. Ekranın amacı

   Öğretmene resmî, ölçülü, akademik ve kanıta dayalı bir rapor taslağını bölüm bölüm sunmak.

2. Öğretmenin psikolojisi

   Öğretmen raporun sahibi olduğunu, metni inceleyip düzenleyebileceğini ve son onayın kendisine ait olduğunu net biçimde hissetmelidir.

3. Öğretmenin yaptığı işlem

   Rapor bölümlerini inceler, gerekli gördüğü yerlerde düzenleme ihtiyacını belirler ve rapor taslağını kendi mesleki değerlendirmesiyle son haline hazırlar.

4. Sistemin yaptığı işlem

   MAHİR, genel değerlendirme, analiz çizelgesi, öğrenme çıktıları değerlendirmesi, güçlü öğrenme alanları, gelişimi desteklenecek alanlar, öğretim önerileri, izleme ve gelişim planı ile kaynak dayanakları bölümlerini düzenli bir rapor taslağı halinde sunar.

5. Zorunlu alanlar

   - Rapor başlığı
   - Genel Değerlendirme
   - Analiz Çizelgesi
   - Öğrenme Çıktıları Değerlendirmesi
   - Güçlü Öğrenme Alanları
   - Gelişimi Desteklenecek Alanlar
   - Öğretim Önerileri
   - İzleme ve Gelişim Planı
   - Kaynak Dayanakları

6. İsteğe bağlı alanlar

   - Öğretmen notu
   - Kurum içi açıklama
   - İzleme tarihi
   - Ek kaynak dayanağı

7. Sonraki ekrana geçiş şartı

   Bu prototip akışında rapor ekranı son ekrandır. Sonraki adım, öğretmenin taslağı incelemesi ve gerekli düzenlemeleri yapmasıdır.

8. Hata yerine kullanılacak rehber mesajlar

   - Bu rapor bir taslaktır; son düzenleme ve onay öğretmene aittir.
   - Daha güçlü bir rapor için öğrenme çıktısı eşleştirmesi ve kaynak dayanakları gözden geçirilebilir.
   - Eksik görülen bölümler öğretmen değerlendirmesiyle tamamlanabilir.

9. Bu ekranın başarı kriteri

   Öğretmen, rapor taslağını güvenle inceleyebilmeli, bölümlerin amacını anlayabilmeli ve nihai kararın kendisine ait olduğunu açıkça görebilmelidir.
