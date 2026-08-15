# Changelog

Bu dosya, MAHİR projesindeki önemli değişiklikleri kronolojik olarak takip etmek için hazırlanmıştır.

## Uzak Servislerde Paylaşılan Parola Yeniden Etkin - 2026-08-16

- OCR ve RAG uç noktaları 2026-08-10'dan beri herkese açıktı (geliştirme kolaylığı için bilinçli olarak kapatılmıştı). İkisi de yeni birer parolayla yeniden dağıtıldı; parolasız veya yanlış parolalı istekler artık **401** alıyor.
- Doğrulandı (canlı, her iki serviste de): parolasız istek 401, yanlış parolalı istek 401, doğru parolalı istek 200.
- Bu, 10 Ağustos kaydındaki "pilot öncesi geri açılmalıdır" maddesini kapatıyor. Ayrıca çok ajanlı hattın sonraki fazı için ön koşuldu: ajanların kendi prompt'unu gönderebildiği genel bir uç nokta, parola olmadan herkesin o GPU'da rastgele prompt çalıştırabilmesi demek olurdu.
- Parolalar `secrets.local.txt` dosyasında tutuluyor ve `.gitignore`'a eklendi. **Dikkat**: `.gitignore` daha önce blanket `*` içeriyordu, merge ile normal bir Python listesine dönüştü - yani artık dosyalar varsayılan olarak yok sayılmıyor ve parola dosyası için açık kural gerekiyordu.
- Parola değişimi yalnız ortam değişkeniyle olmuyor: değer dağıtım anında Modal uygulamasına gömülüyor, yeniden `modal deploy` gerekiyor (bkz. `README.md`).

## Çok Ajanlı Analiz Hattı - Faz 1: İskelet, Orkestratör ve CED Omurgası - 2026-08-16

- `docs/architecture/` altında şartnamesi bulunan beş uzman ajan artık **çalışıyor**: Belge Anlama → Program Eşleştirme → Ölçme-Değerlendirme → Pedagojik Analiz → Raporlama. Yeni paket: `backend/app/agents/`.
- Öncesinde bu ajanların kodu vardı ama ürüne bağlı değildi: zincir yalnız `file_receiver.py`nin `.csv` dalında koşuyordu, arayüzdeki dosya girişi `.csv` kabul etmediği için öğretmen onu hiç tetikleyemiyordu, tetiklense bile yüklenen içeriği değil sabit `shared/sample-*.json` dosyalarını okuyup sonucu konsola basıyordu. Canlı analiz yolu ise hepsini atlayıp tek bir fonksiyonda her şeyi kendisi yapıyordu.
- **CED artık gerçek veri omurgası.** `agents/ced_builder.py`, tarayıcı yükünü bellek-içi bir `CEDDocument`e çeviriyor - mevcut CED üreticileri dosya yolu güdümlü olduğu için eksik olan halka buydu ve hattın CED üzerinden çalışamamasının teknik sebebi tam olarak buydu.
- **Ölçme mantığı tekilleşti.** Aynı aritmetik hem `measurement_engine.py`de hem `approved_data_analyzer.py`de ayrı ayrı yazılıydı ve ikisi sessizce ayrışabilirdi. Artık tek ev `measurement_engine`: yeni `calculate_question_totals` / `calculate_learning_outcome_totals` ham toplamları veriyor, oran fonksiyonları da onları kullanıyor.
- **Ajan bazlı izlenebilirlik.** Her ajan bir `AgentTrace` bırakıyor: ne ürettiği, ne kadar sürdüğü, hangi bulguları kaydettiği. Bu, "Kanıtları Gör"ün ajan yarısı; veri yarısı (`evidence`) zaten vardı. İz yalnız sayım ve özet taşır, öğrenci satırı taşımaz - gizlilik kapısının arkasına yan kapı açmaz.
- **Zorunlu/isteğe bağlı ajan ayrımı.** Ölçme ya da Belge Anlama düşerse analiz durur (sayısız yarım rapor, rapor yokluğundan kötüdür); Program Eşleştirme ya da Pedagojik Analiz düşerse rapor yorumsuz ama geçerli üretilir. Bu, depodaki mevcut ilkenin aynısı (RAG arızası `ragContext`i boş bırakır, analizi kesmez).
- Öğretmenin gördüğü hiçbir sayı değişmedi: yeni hat ile eski tek parça analizin çıktısı birebir aynı; ayrıca fixture'dan elle hesaplanabilen altın değerler teste sabitlendi.
- Ölü `.csv` dalı `file_receiver.py`den kaldırıldı.
- Yeni testler: `tests/test_agent_pipeline.py` (26 test - eşdeğerlik, altın değerler, CED omurgası, iz, arıza yalıtımı).

## Öğrenme Çıktısı Yüzdelerinde "Kanıtları Gör" - 2026-08-11

- Raporun D bölümündeki her başarı oranının yanında artık hesabın dayanağı gösteriliyor: kaç sorudan hesaplandığı, kaç katılımcı öğrenciden geldiği, kaç puan hücresinin öğretmen tarafından düzeltildiği ve soru bazında yüzdeler ("Soru 2: %72, Soru 5: %61, Soru 8: %70 — Toplam 710,50 / 1.050 puan").
- Ekranda özet satırı görünür, ayrıntı tıklanınca açılır; indirilen Word/PDF belgesinde aynı metin düz olarak yer alır (kapalı bir açılır blok belgede kanıtı görünmez kılardı). D tablosu 5 sütunda kaldı - yeni "Hesaplama Dayanağı" sütunu, eski "İlişkili Sorular" sütununun yerini aldı ve aynı soruları yüzdeleriyle birlikte taşıyor.
- Kanıt, oranın hesaplandığı yerde (`backend/app/approved_data_analyzer.py`) üretilip her öğrenme çıktısına `evidence` alanı olarak ekleniyor. Ön yüz bunu yeniden türetmiyor; soru-çıktı eşleşmesini normalize edilmiş metin karşılaştırmasıyla bulan eski yol yalnızca `evidence` taşımayan eski analizler için geri düşüş olarak duruyor.
- Öğretmenin düzelttiği puan hücreleri artık sayılıyor (yeni `assets/js/mahir-score-corrections.js`). Kural: yalnız makine bir değer ürettiyse ve öğretmen onu değiştirdiyse düzeltmedir - boş bir hücrenin doldurulması "öğretmen doldurdu"dur, bu yüzden elle giriş modunda düzeltme sayısı kendiliğinden sıfır kalır.
- Sayım, grup kaydedilirken alınıyor: `startNewGroup()` hemen ardından `structuredData`'yı sıfırlayıp makinenin okuduğu özgün değerleri yok ettiği için başka bir anda hesaplanamıyor. Çok gruplu akışta grup sayımları ve son incelemedeki ek düzenlemeler toplanıyor.
- Bu alan hiçbir puanı veya oranı etkilemez; bozuk/eksik gelmesi analizi durdurmaz ve gönderilmediğinde sayı sıfır görünür (eski istemcilerle uyumlu).
- Yeni testler: `tests/test_approved_data_analyzer_evidence.py` (12 test), `tests/score-corrections.test.js`, `tests/report-evidence.test.js`.

## RAG Getiriminde Göreli Skor Tabanı ve İçerik Adresli Parça Kimliği - 2026-08-11

- `rag_service.py`, Qdrant isabetlerinin zayıf kuyruğunu artık atıyor: en iyi isabetin **%78'inin** altında kalan parçalar modele hiç gitmiyor (`_drop_weak_hits`). Sabit bir `score_threshold` yerine oran kullanılmasının gerekçesi ölçüm: aynı dizinde skorlar 0,60 ile 0,94 arasında geziyor, dolayısıyla sabit bir sayı bir sorguda hiçbir şeyi elemezken başka birinde her şeyi elerdi.
- Ölçüm (8 gerçek zayıf öğrenme çıktısı, tema filtresi açık, 64 isabet): her sorgu aynı şekli veriyor - 2 güçlü isabet (0,86-0,94), bir orta grup, sonra 0,60-0,68'de bir kuyruk. Kopuş gösteren altı sorgunun ortak oran aralığı 0,771-0,793 çıktı; 0,78 hepsinde tam kopuş noktasından kesiyor. Kuyruğu düz olan iki sorguda ise 8 isabetin 8'ini de koruyor.
- Sonuç: gönderilen bağlam 64 parçadan 42'ye indi ve **analiz süresi 28,9 sn'den 13,1 sn'ye düştü** (iki ölçümde de aynı). Teşhis kalitesi ölçütleri aynen korundu: 8/8 dolu, 0 yanlış şiddet etiketi, 0 yanlış Bloom basamağı, 0 öneri sızıntısı.
- Kırpma, Qdrant'ın `score_threshold` parametresiyle değil sorgudan sonra yapılıyor ve **her zaman en az bir isabet bırakıyor** - aksi hâlde eşiğin altında kalan bir sorgu boş dönüp öğretmenin raporunda boş bir hücre bırakırdı.
- Parça kimlikleri `uuid4()` yerine içerik adresli `uuid5` ile üretiliyor (`_deterministic_point_id`). Daha önce aynı PDF'i `clear_index` çağırmadan yeniden indekslemek tüm parçaları hatasızca ikizliyor ve getirimi sessizce bozuyordu; artık ikinci yazım aynı kimliklere denk gelip üzerine yazıyor. Mevcut dizin geçerliliğini koruyor, yeniden indeksleme gerektirmez.
- Yeni birim testleri: `tests/test_rag_service_indexing.py` (11 test).

## Uzak Servislerde Paylaşılan Parola Devre Dışı (geliştirme) - 2026-08-10

- OCR işçisi (`modal_app.py`), `MAHIR_OCR_SHARED_SECRET` tanımlı olmayan bir kabuktan yeniden dağıtıldı; işçiye boş parola gömüldüğü için `X-MAHIR-OCR-Key` doğrulaması artık hiç çalışmıyor (bkz. `backend/app/ocr_worker.py`).
- Gerekçe: dağıtılmış işçide gömülü parola ile yerel `run_file_receiver.py` süreci uyuşmuyordu; her yükleme `401 "Yetkisiz istek."` alıyor, arayüzde "Belge okuma servisine ulaşılamadı" olarak görünüyordu.
- `rag_service.py` de aynı durumda: `MAHIR_RAG_SHARED_SECRET` boş dağıtıldığı için `X-MAHIR-RAG-Key` doğrulaması devre dışı.
- Bu bir kod değişikliği değildir - parola her iki dosyada da dağıtım anında yerel ortam değişkeninden okunur, kaynak kodda saklanmaz.
- **Pilot öncesi geri açılmalıdır**: iki uç nokta da şu an herkese açık. Yeniden etkinleştirmek için parolayı önce ortam değişkeni olarak tanımlayıp dağıtımı tekrarlamak, ardından yerel sunucuyu aynı pencerede aynı parolayla başlatmak yeterli (bkz. `README.md`).

## v1.8 Yerel Çalışma Kaydı - 2026-07-27

- Açık çalışma, öğretmen isteğiyle yalnız kullanılan tarayıcının yerel kayıt alanına kaydedilir.
- Her kayıt benzersiz kimlik ve kayıt zamanı taşıyan doğrulanmış v2 çalışma paketi olarak saklanır.
- Öğrenci adı, numarası, puan satırları, ham sınav verisi ve yüklenen dosya yerel çalışma kaydına alınmaz.
- Kayıt sonucu öğretmene açık başarı veya hata iletisiyle bildirilir.
- Word ve PDF indirme akışları korunmuş, Yazdır işlemi eklenmemiştir.

## v1.7 Yedek Sürüm Uyumluluğu - 2026-07-27

- Güncel çalışma yedekleri bütünlük özeti bulunan v2 şemasıyla oluşturulur.
- Bütünlüğü doğrulanan v1 dosya ve tarayıcı kayıtları, özgün içerik değiştirilmeden v2’ye dönüştürülür.
- Önizlemede kaynak ve hedef sürüm gösterilir; dönüşüm sonrasında açık öğretmen onayı zorunludur.
- Gelecekteki, desteklenmeyen, bozuk, eksik veya paket–kayıt sürümü uyuşmayan yedekler reddedilir.
- Ham sınav verisi, yüklenen dosya ve açık öğrenci listesi çalışma yedeğine alınmaz.

## Word Şablonu Veri Okuma - 2026-07-24

- MAHİR Veri Giriş Şablonu biçimindeki `.docx` belgeleri gerçek tablo yapısından okunur.
- Sınav bilgileri, soru–öğrenme çıktısı eşleştirmeleri ve öğrenci puanları yapılandırılmış JSON olarak tarayıcıya aktarılır.
- Veri Onay ekranı okunan soru ve öğrenci verileriyle dinamik oluşturulur; hücreler öğretmen tarafından düzeltilebilir.
- Eksik alanlar ve öğrenci toplam puanı uyuşmazlıkları öğretmen kontrol uyarısı olarak gösterilir.

## Veri Evrakı Yükleme - 2026-07-24

- MAHİR Veri Giriş Şablonu – Sürüm 1 projeye eklendi.
- Word, PDF ve görüntü belgeleri için sürükle-bırak ve dosya seçme alanı oluşturuldu.
- Dosya türü, boş dosya ve 20 MB boyut kontrolleri eklendi.
- Seçilen dosyanın adı, türü, boyutu ve görüntü önizlemesi kullanıcıya gösterildi.
- Dosyayı kaldırma ve “Verileri Oku ve Kontrol Et” işlemleri öğretmen kontrollü hâle getirildi.
- Word, PDF ve görüntü belgelerinin prototip doğrulama ekranına aktarılması sağlandı.

## Sprint 1 / Task 03 - 2026-07-06

Project management belgeleri oluşturuldu.

Eklenen dosyalar:

- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/DEVELOPMENT_LOG.md`

Güncellenen dosya:

- `README.md`

Notlar:

- `index.html`, `styles.css` ve `script.js` değiştirilmedi.
- `assets` klasörüne dokunulmadı.
- Kod, HTML, CSS veya JavaScript eklenmedi.
