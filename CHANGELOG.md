# Changelog

Bu dosya, MAHİR projesindeki önemli değişiklikleri kronolojik olarak takip etmek için hazırlanmıştır.

## Uzak Servislerdeki Paylaşılan Parola Tamamen Kaldırıldı - 2026-08-28

- **Karar:** OCR ve RAG uzak Modal servislerini koruyan `X-MAHIR-OCR-Key` / `X-MAHIR-RAG-Key` paylaşılan parola katmanı tümüyle kaldırıldı; iki uç nokta artık kalıcı olarak herkese açık.
- Kaldırılan kod: `rag_service.py` ve `modal_app.py`'deki `modal.Secret` tanımları + `secrets=[...]` bağlamaları, `ocr_worker.py` ve `rag_service.web_query`'deki `hmac.compare_digest` doğrulama blokları (`401 "Yetkisiz istek."` yanıtı dahil), `ocr_protocol.SHARED_SECRET_HEADER`, `rag_client.py` / `remote_ocr_client.py`'deki istek başlığı enjeksiyonu ve `remote_ocr_client.py`'deki 401'e özgü hata mesajı.
- Kaldırılan yapılandırma: `MAHIR_BASLAT.ps1`'in `secrets.local.txt` yükleme bloğu, `.gitignore`'daki `secrets.local.txt` kuralı.
- Güncellenen doküman: `README.md` "OCR ve RAG demo erişimi" bölümü (artık kurulum gerektirmiyor, yalnız isteğe bağlı `MAHIR_*_REMOTE_URL`); `CHANGELOG` içindeki geçmiş kayıtlar korundu. `benchmarks/` ölçüm paketindeki `load_secrets` de aynı yönde temizlendi (ayrı, henüz takip edilmeyen dizin).
- Güncellenen test: `tests/test_remote_ocr_client.py`'deki iki 401 senaryosu 500'e çevrildi (mekanizma değil, "HTTP hatası yeniden denenmez" davranışı sınanıyor).
- **Yanlış kullanıma karşı kalan tek yapısal koruma:** `rag_service.py` içindeki `MAX_AGENT_PROMPTS` / `MAX_AGENT_PROMPT_CHARS` / `MAX_AGENT_OUTPUT_TOKENS` sınırları. Üretim ortamına geçişte kurumsal kimlik doğrulama ayrıca eklenmelidir.
- **Dağıtım gerekli:** parola gömülü olduğu için `modal deploy rag_service.py` ve `modal deploy modal_app.py` yeniden çalıştırılmalı; aksi halde canlı uçlarda eski parola hâlâ zorunlu kalır.

## Charter'ın Öneri/Nedensellik Yasağı Kaldırıldı - 2026-08-24

- **Bulgu:** `run_diagnosis_test.py` ile tekrarlı testlerde bir örüntü ortaya çıktı - model aynı iyi içeriği ("Mekânları karşılaştıran bir sunum hazırlayabilme eksikliği") defalarca üretiyor ama HER SEFERİNDE aynı tek cümle içinde yasaklı bir bağlaçla ("nedeniyle", "kaynaklanmaktadır") bitiriyordu. Cümle düzeyinde çalışan kırpma, tek cümlelik yanıtlarda iyi içerikle birlikte cümlenin TAMAMINI siliyor, öğretmen hiçbir teşhis görmüyordu.
- Kullanıcı kararı: hem oran-nedensellik hem de öneri/etkinlik dili kısıtı **tamamen kaldırıldı** (akıllı madde-düzeyi kırpma değil). Öneri yasağı `DEVELOPMENT_CHARTER.md`'nin bağlayıcı bölümünde açıkça yazıyordu ("MAHİR etkinlik, kaynak, kitap sayfası, öğretim yöntemi veya telafi programı önermez") - bu satır da kullanıcı onayıyla charter'dan kaldırıldı (charter'ın kendi maddesi: "kullanıcı onayıyla güncellenebilir"). Kanıt/grounding zorunluluğu ve gizlilik ilkeleri DOKUNULMADI.
- Kaldırılanlar: `prompts.py`/`rag_service.py`'deki iki sistem prompt'unun nedensellik-bağlacı ve "ÇÖZÜM ÖNERME" maddeleri; `pipeline.py`'deki `_UNSUPPORTED_CLAIM_PATTERNS`/`_ACTION_LANGUAGE_PATTERNS` filtreleri; proje geneli `charter_guard.py` modülü (TÜM ajanların LLM yanıtına uygulanan öneri süzgeci) ve onun hiçbir yerde okunmayan `strippedSentences`/`llmStrippedSentences` telemetri alanları. Oran-tekrarı (`%35` gibi modelin kendi yazdığı yüzdenin kırpılması) kapsam DIŞI bırakıldı, aynen çalışmaya devam ediyor.
- **Bir kod incelemesi hatası düzeltildi:** ilk taslakta `_answer_matches_outcome_scope`'un son güvenlik ağına yanlışlıkla oran-tekrarı kontrolü eklendi - ama bu fonksiyon MAHİR'in kendi şablonuyla SARILMIŞ tam cevabı görüyor (açılış cümlesi zaten oranı söylüyor), bu yüzden her geçerli cevabı reddediyordu. Test paketi bunu hemen yakaladı; kontrol kaldırıldı.
- `ANOMALY_SYSTEM_PROMPT` (ölçme/anomali ajanı) kasıtlı olarak dokunulmadı - kullanıcı isteği yalnız pedagojik teşhisle sınırlıydı. Not: `charter_guard` silinince bu ajanın öneri yasağı artık yalnız kendi prompt'una dayanıyor, kod-seviyeli yedek yok - pedagojik prompt'larla zaten aynı durum, bir gerileme değil.
- Canlı doğrulama: daha önce nedensellik yüzünden tamamen boşalan TDE3.2/3. Tema/%25 vakası tekrar denendiğinde bir koşuda düzgün, iki cümlelik, nedensellik/öneri dili içeren bir teşhis üretip başarıyla geçti.
- Yeni/güncellenen testler: `DEVELOPMENT_CHARTER.md` satır düzenlemesi, iki prompt kopyasının hâlâ birebir aynı kalması (`PromptDriftTests`), kaldırılan kısıtların artık kapsam denetiminden geçtiğinin regresyon kaydı (`test_causal_language_and_student_count_are_accepted`, `test_activity_or_remediation_language_is_accepted`, `test_causal_language_is_preserved`), oran-tekrarı tetikleyicisiyle yeniden yazılan `_drop_dangling_reference` testi. `charter_guard`a özgü 8 test silindi (mekanizmanın kendisi kalktığı için). Toplam 252 → 244 Python testi.

## Prototip Sunucusu Tarayıcı Önbelleğini Kapatıyor - 2026-08-16

- **Bulgu:** Kaynak dipnotu ekranda görünüyor ama indirilen PDF'e hiç düşmüyordu. Kod doğruydu; hata dağıtımdaydı. `SimpleHTTPRequestHandler` yalnızca `Last-Modified` gönderip `Cache-Control` göndermediği için tarayıcı **sezgisel önbelleklemeye** düşüyor ve dosyayı sunucuya hiç sormadan kendi kopyasından veriyor. Rapor katmanı böylece sessizce ikiye bölündü: model tarafı (`mahir-report-export-common.js`) tazelenmişken çıktı tarafı (`mahir-pdf-exporter.js`) eski kopyadan geldi.
- Artık her yanıt `Cache-Control: no-store` taşıyor. Prototipte önbelleğin kazandıracağı hiçbir şey, öğretmenin imzalayacağı resmî çıktının ekranda gördüğünden farklı olması riskini karşılamıyor.
- **Teşhis, kullanıcının elindeki PDF'ten yapıldı:** sayfalar gömülü JPEG olarak çıkarılıp okundu. Hücrelerdeki kısa atıflar (`(s. 66-67)`, `(s. 80-81)`) yerindeydi - yani `ragSources` doluydu ve model dipnotu üretmiş olmak zorundaydı, çünkü ikisi de aynı `documentName` alanına bağlı. Geriye tek açıklama kaldı: çizici o modeli görmedi.
- Yeni testler (4): rapor katmanının üç dosyası ve `index.html` için `no-store`, analiz yanıtları için `no-store`, ve tarayıcıya giden **baytların** depodaki dosyayla birebir aynı olduğu ("sunucu eski kopya servis ediyor" ihtimalini kapatır). Toplam 187 → 191 Python testi.
- **Sunucunun yeniden başlatılması gerekir** - koşan süreç eski kodu tutuyor. Tarayıcıda bir kez sabit yenileme (Ctrl+F5) eski kopyayı düşürür.

## Kaynak Gösterimi Dipnota Taşındı - 2026-08-16

- Belgenin resmî adı uzun ve F tablosunun her satırında tekrarlanınca "Kavramsal Bağlam" hücresini okunamaz kılıyordu. Akademik atıf düzenine geçildi: **hücrede kısa atıf** (`(s. 66-67)`), **belgenin tam adı tablonun altında dipnotta**, bir kez (`Kaynak: Ortaöğretim … Öğretim Programı … (2024)`).
- Birden çok kaynak belge olursa hücrede işaretçi beliriyor (`(K1, s. 66-67)`) ve dipnot ikisini de sayıyor. **Tek belgede işaretçi yok** - "K1" o durumda yalnız gürültü olurdu.
- Blok modeline `notes` alanı eklendi ve **dört render hedefinin dördü de** güncellendi: ekran önizlemesi, PDF gövdesi, Word dışa aktarıcısı, PDF dışa aktarıcısı. Mevcut `paragraphs` alanı bu işi göremezdi - o alan dört hedefte de tablonun ÖNÜNDE çiziliyor; dipnot tablodan sonra gelmeli.
- Doğrulama, blok modeliyle yetinmedi: DOM sırası da denetlendi (`h3 → p → table → p.report-note`), Word/PDF dışa aktarıcılarında `notes`un tablolardan sonra basıldığı kaynak üzerinden kontrol edildi.
- Yeni testler: kısa atıfın hücrede tam adın dipnotta olduğu, tek/çok belge ayrımı, sayfasız kaynak, kaynaksız satır, dipnotun `paragraphs`a sızmadığı.

## Kaynakta Dosya Adı Yerine Belgenin Resmî Adı - 2026-08-16

- Rapordaki kaynak gösterimi artık **"Ortaöğretim Türk Dili ve Edebiyatı Dersi Öğretim Programı - Türkiye Yüzyılı Maarif Modeli (2024), s. 66-67"** diyor; önce "tdeogr.pdf, s. 66-67" diyordu. Resmî bir rapor dayanağını dosya adıyla gösteremez.
- Ad, indeksleme anında Qdrant payload'ına yazılıyor (`document_name`) - gösterim katmanında çevrilmiyor. Kaynağı yeni `rag_service.DOCUMENT_TITLES` kaydı: `program_id` → resmî ad. `--document-title` ile geçersiz kılınabilir; kayıtta olmayan program için komut **hata veriyor**, sessizce dosya adına düşmüyor. Sebep: yanlış adlı parçalar dizine girdikten sonra ancak temizleyip yeniden indeksleyerek düzelir ve o ana kadar üretilmiş her rapor kaynağını yanlış göstermiş olur.
- **Kapaktan otomatik çıkarım denenmedi ve nedeni ölçüldü:** TDE9 belgesinin kapağında yıl, metin katmanında `2O24` (harf O, sıfır değil) olarak geçiyor - otomatik çıkarım yılı yanlış yazardı. Kapak düzeni her belgede farklı olduğu için temizleme kuralları da her yeni belgede yeniden yazılmak zorunda kalırdı.
- **Yeniden indeksleme yapıldı** (118 parça, `--replace` ile). Yeni `--replace` bayrağı önce `clear_index(program_id)` çağırıyor ve **belge adı değiştiğinde şart**: nokta kimliği içerik adresli ve `document_name` o kimliğin parçası, yani yeni adla yazılan parçalar yeni kimlik alır, eskiler üzerine yazılmaz ve dizinde aynı içerik iki adla kalırdı. Getirim bunu hatasızca yutar, yalnız sonuç bozulur.
- Canlı doğrulama: 8/8 teşhis kaynaklı ve sayfa aralıkları yeniden indekslemeden önceki ile aynı (66-67, 73-74, 80-81, 89-90) - getirim eşdeğer kaldı. Üç geniş sorguda 34 isabetin tamamı yeni adı taşıyor, eski dosya adı dizinde kalmamış.
- `index_pdf` artık boş `document_name` reddediyor. README'ye indeksleme yordamı ve `--replace` tuzağı eklendi.
- Yeni testler: kayıt çözümlemesi, geçersiz kılma, bilinmeyen programda hata, ad değişiminin nokta kimliğini değiştirdiğinin kanıtı. Toplam 181 → 187 Python testi. (Testlerden biri gerçek bir kusur yakaladı: yalnız boşluktan oluşan bir `--document-title` kaydı gölgeleyip "ad tanımlı değil" hatası veriyordu.)

## Müfredat Teşhisinde Kaynak Gösterimi (belge + sayfa) - 2026-08-16

- Raporun F bölümündeki her müfredat temelli teşhisin ardında artık dayandığı kaynak yazıyor: **"(Kaynak: tdeogr.pdf, s. 66-67)"**. D bölümündeki "Kanıtları Gör" bir ORANIN hangi puanlardan geldiğini söylüyordu; bu da bir TEŞHİSİN hangi belge sayfasından geldiğini söylüyor.
- **Yeni indeksleme veya yeni sorgu gerekmedi.** Sayfa numaraları Qdrant payload'ında zaten vardı (`pages`) ve uçtan `sources` içinde geri dönüyordu; `PedagogicalAnalysisAgent.apply_llm` yalnız "kaynak var mı" diye bakıp listeyi atıyordu. Artık `outcome["ragSources"]` olarak taşınıyor.
- Sayfa numaraları **orijinal PDF'e** göre: müfredat PDF'i sınıf/tema aralıklarına bölünerek indeksleniyor ve `rag_service.py::_extract_original_pages` düzeltmesi olmasa numaralar her dilimde 1'den başlardı.
- Getirim isabetleri belge başına **tek satıra indirgeniyor** ve ardışık sayfalar aralığa iniyor ("s. 66-68", "s. 66, 71"): sekiz isabetin ham sayfa listesi hücreyi doldururdu. Kaynak ayrı sütun değil, teşhisin ardına ekleniyor - A4 genişliğinde tablo zaten beş sütun.
- Canlı doğrulama (8 zayıf çıktı, 4 tema): **8/8 teşhis kaynaklı.** Sonuç getirimi de doğruluyor - her tema farklı ve ardışık bir aralık gösteriyor ve tema sırasıyla artıyorlar: s. 66-67, 73-74, 80-81, 89-90. Tema filtresinin doğru çalıştığının bağımsız kanıtı.
- Alan varlığı öngörülebilir: hangi yoldan geçilirse geçilsin (program yok, getirim boş, LLM kapalı) `ragSources` boş liste olarak var. Bozuk kaynak kaydı sessizce eleniyor, analiz kesilmiyor.
- Yeni testler: `tests/report-sources.test.js` (sayfa aralığı sıkıştırma, iki belge, kaynaksız satır, geriye dönük uyum) ve backend'de kaynak birleştirme testleri. Toplam 176 → 181 Python testi, 6 → 7 node dosyası.

## Teşhis Prompt'u: Bloom Kaldırıldı, Müfredata Demirlendi - 2026-08-16

- **Bloom taksonomisi tamamen kaldırıldı.** Gerekçe ölçüldü: sekiz yanıtın **tamamı** Bloom cümlesiyle açılıyor ("Bu kazanımın bilişsel düzeyi Uygulama ve %55..."), yanıt başına 2-8 kez basamak adı geçiyordu. Buna karşılık **temanın adı 0/8 yanıtta** geçiyor, yalnız 2/8 yanıt müfredattan somut bir öğe anıyordu. Yani getirim kusursuz çalışırken (8/8 kaynak dolu) model, ona **zaten söylediğimiz** şeyi (düzey, oran, şiddet) tekrarlıyor; yalnızca getirimin bilebileceği şeyi - o temanın müfredat metnini - kullanmıyordu.
- **Teşhisin yeni ekseni: BAĞLAM'a demirleme.** Yanıt artık tema adını tırnak içinde anarak başlamak ve BAĞLAM'dan en az iki somut öğeyi daha (süreç bileşeni, beceri, kavram, metin türü) adıyla anmak zorunda. "Her kazanım için yazılabilecek" genel teşhisler açıkça başarısız sayılıyor.
- **Sonuç (canlı, sıcak konteyner, 4 tema x 2 oran):**

  | Ölçüt | Önce | Sonra |
  |---|---|---|
  | Tema adı yanıtta geçiyor | 0/8 | **7-8/8** |
  | Somut müfredat öğesi anılıyor | 2/8 | **7-8/8** |
  | Bloom sözcüğü geçiyor | 8/8 | **0/8** |
  | Dolgu ("belirli/genellikle/bazı") | 14 kez | **0** |
  | Ortalama uzunluk | 96 kelime | **66-71 kelime** |

  Korunması şart olan ölçütler bozulmadı: 8/8 dolu, 8/8 doğru şiddet, 0 öneri sızıntısı, 0 reddetme ön eki.
- Teşhisler artık temaya özgü: "olay, kişi, mekân, zaman gibi yapı unsurlarını tahlil edebilme", "'örtük iletiyi belirme' ve 'metinleri karşılaştırma'", "hikâye ve gezi yazısı türleri", "roman ve tiyatro metinlerinde kelime zenginliği ve üslup özellikleri" gibi müfredatın kendi terimleriyle yazılıyor.
- **Ölçümde yakalanan üç hata, üçü de düzeltildi ve testle sabitlendi:**
  - **Örnek sızıntısı:** açılış kuralı önce somut bir örnekle yazılmıştı ("ör. 'Sözün İnceliği' temasında..."); model örneği kopyaladı ve **4. Tema kazanımlarına 1. Tema'nın adıyla başladı** - öğretmene başka bir temanın teşhisini doğruymuş gibi gösteren, hiç tema yazmamaktan kötü bir hata. Prompt'ta kopyalanabilir somut tema adı bırakılmadı.
  - **Uydurma kazanım kodu:** model sarmal risk cümlesinde var olmayan kodlar üretiyordu; artık yalnızca BAĞLAM'da veya SORU'da geçen kod yazılabiliyor.
  - **Etkinlik adlandırma:** model öneri kipi kullanmadan "gerekli olan ... analiz **etkinliklerine**" yazabiliyordu. `charter_guard` bunu yakalamıyor çünkü "gerekli olan"ı bilerek koruyor (teşhis dili). Regex genişletmek yerine prompt'ta yapılacak-iş adları yasaklandı.
- Bloom altyapısı (`_BLOOM_LEVELS_BY_VERB`, `_bloom_level_for`, artık kullanılmayan `_TURKISH_LOWER_MAP`) silindi; `_build_rag_question` bilişsel düzey enjeksiyonu yerine müfredata demirlemeyi istiyor. Şiddet etiketi mekanizması **aynen korundu** - ölçümde 8/8 doğruydu.
- **Bu değişiklik için `modal deploy` gerekmedi:** canlı teşhis yolu Faz 3'ten beri system prompt'u istemciden gönderiyor (`agents/prompts.py`). `rag_service.SYSTEM_PROMPT` yalnızca eski `queries` biçiminde kullanılıyor ve hizada tutulmak için birlikte güncellendi (drift testi koruyor).
- Ölçüm betiğindeki bir yanlış pozitif de düzeltildi: çıplak "gerekli" araması, `charter_guard`ın bilerek koruduğu teşhis dilini ("karşılaştırmak için gerekli kavramların yetersiz öğrenilmesi") sızıntı sanıyor ve her koşuda gerçek sızıntıyı görünmez yapıyordu.
- Yeni testler: prompt sözleşmesi (Bloom yok, demirleme zorunlu, dolgu yasak, uzunluk sınırı, örnek tema adı yok, kod uydurma yasak, etkinlik adlandırma yasak) ve `_build_rag_question` davranışı. Toplam 167 → 176 Python testi.

## OCR ve Analiz İşlemlerinde Süre Ölçümü - 2026-08-16

- İki uzun işlem (belge okuma ve "Verileri Onayla ve Analize Geç") sessizdi: öğretmen butona basıp bekliyor, ne kadar beklediği hiçbir yere yazılmıyordu. Artık ikisinin de başında ve sonunda süre alınıyor; sonuç **ekranda** (bildirim cümlesinin sonunda), **tarayıcı konsolunda** ve **yerel sunucu konsolunda** görünüyor.
- Ölçüm **kırılımlı**, çünkü tek bir toplam asıl soruyu yanıtlamıyor. Canlı doğrulama bunu birebir gösterdi - aynı görsel, arka arkaya iki koşu:

  | Koşu | `ocr-uzak` | `ocr-yerel` | İstemci toplam |
  |---|---|---|---|
  | Soğuk konteyner | **54,5 sn** | 54,5 sn | 54,6 sn |
  | Sıcak konteyner | **5,7 sn** | 5,8 sn | 5,8 sn |

  48,8 saniyelik farkın tamamı `ocr-uzak` satırında; yerel işlemede değil. "Neden 45 sn sürdü" sorusunun cevabı tam olarak budur ve tek bir toplam sayı bunu söyleyemezdi.
- Yeni `backend/app/timing.py`: tek bağlam yöneticisi (`stage`), tek çıktı biçimi (`[MAHIR][süre] <ad> sure=X.Xs alan=değer`). İki sert kuralı var - **istisnayı asla yutmaz** (ölçüm, ölçtüğü akışın davranışını değiştirmemeli) ve **hata hâlinde de basar** (`hata=evet`), çünkü "45 sn sonra patladı" bilgisi "45 sn sürdü" kadar değerli. `BaseException` yakalanıyor ki yarıda kesilen uzun bir OCR da ölçülsün.
- Ölçüm noktaları iç içe: `ocr-uzak` (yalnız uzak HTTP çağrısı) ⊂ `ocr-yerel` (yerel alıcının tamamı) ⊂ tarayıcı toplamı; analizde `llmRound` ⊂ `analiz-rota` ⊂ tarayıcı toplamı. Farklar sırasıyla yerel ayrıştırmayı ve ağ+JSON taşımasını veriyor (ölçüldü: analizde 55 ms).
- Analiz toplamı paralel bir mekanizma yerine **Faz 4'ün izine** eklendi (`trace.totalMs`), böylece tarayıcı elindeki `trace` nesnesinden hem toplamı hem `llmRound.durationMs`i okuyabiliyor. Uzak OCR süresi için dönüş tipi **değiştirilmedi** - 3'lü demet üç katman boyunca akıyor ve testler ona bağlı; her katman kendi satırını basıyor (`ocr_engine`in bugün yaptığının aynısı).
- Tarayıcı konsolunda `isitmadanBeri` alanı: ısıtma dosya seçilince ateşleniyor ve 30 sn kısılıyor. Isıtmanın üzerinden geçen süre kısaysa konteyner hâlâ soğuk demektir - yorumlamanın anahtarı bu.
- Süre metni Faz 4'te dışa açılan `MAHIRReportExport.durationText` ile biçimleniyor ("16,7 sn" / "340 ms", tr-TR); ikinci bir biçimlendirici yazılmadı.
- Rapora süre bilgisi **eklenmedi**: I. bölüm ajan izini gösteriyor, duvar saati ölçümü geliştirici enstrümantasyonu ve resmî belgeye ait değil.
- Yeni testler: `tests/test_timing.py` (9 test). Toplam 155 → 167 Python testi.

## Çok Ajanlı Analiz Hattı - Faz 4: İzlenebilirlik Yüzeyi - 2026-08-16

- **Hat üç fazdır çalışıyordu ama öğretmen göremiyordu.** `analyze_approved_data` yalnız `run_pipeline(...).analysis` döndürüyor, beş ajanın izini ve bulgularını o satırda düşürüyordu. Artık `analyze_approved_data_traced` ikisini birlikte veriyor ve iz `/mahir-analyze` yanıtında **`analysis`in KARDEŞİ** olarak taşınıyor - içinde değil, çünkü biri raporun kendisi diğeri raporun nasıl üretildiği. Rapor sözleşmesi değişmedi; kaydedilmiş eski çalışmalar ve tüm eşdeğerlik testleri geçerli kaldı.
- **Analiz ekranındaki sabit 6 maddelik liste gerçek koşuyla değişti**: her ajan kendi adı, yaptığı iş, süresi ve dil modeli çağrı sayısıyla görünüyor. İz gelmediğinde (genel dil değerlendirmesi, eski kaydedilmiş çalışma) sabit metin geri çekilme yolu olarak duruyor.
- **Rapora "I. ANALİZ SÜRECİ VE AJAN İZİ" bölümü eklendi**; Word ve PDF dışa aktarıcıları blok modelini genel olarak tükettiği için o iki dosyada tek satır değişiklik gerekmedi. İz yoksa bölüm hiç üretilmiyor - rapor bugünküyle birebir aynı kalıyor.
- **Ortak dil modeli turu KENDİ satırında**, ajanlara bölüştürülmüyor. Sebebi ölçümde göründü: tur bittiğinde Pedagojik Analiz'in kendi süresi 0,7 ms, turun kendisi 18,9 sn. Süreyi ajanlara paylaştırmak hem uydurma olurdu hem de tek istekli mimarinin kanıtını yok ederdi; ayrı satır ("9 istem tek istekte çözüldü") tam tersine onu görünür kılıyor.
- **`AgentTrace.llm_calls` nihayet doluyor.** Faz 2'de `trace_entry` yazılmış ve test edilmişti ama **hiçbir yerden çağrılmıyordu** - CHANGELOG alanın dolduğunu söylüyordu, kod söylemiyordu. Sahiplik artık prompt'un açık `agent` alanından okunuyor (addan çıkarmak kırılgandı: anomali prompt'unun adı ajan adıyla aynı, teşhis prompt'larınınki "pedagoji/..." ve sahibi "pedagojik-analiz"). Canlı: Ölçme 1, Pedagojik 8 kayıt.
- **Ölçme Ajanı'nın anomali bulgusu artık raporda görünüyor** (C bölümünün altında paragraf). Faz 3 onu üretiyordu ama hiçbir rapor bloğu okumuyordu. Kapanış cümlesi kasıtlı: "Bu gözlem hiçbir puanı veya oranı değiştirmez" - charter gereği bu bir gözlem, karar değil. Bulgu yoksa paragraf hiç eklenmiyor. Yol boyunca bir hata da çıktı: `getSummary()` özeti alan alan yeniden kurduğu için `anomalies` sessizce düşüyordu.
- **`PipelineError` artık yüzeye çıkıyor**: zorunlu bir ajan düştüğünde rota çıplak 500 yerine kısmi izi de gönderiyor - hangi ajan düştü, hangileri atlandı, öncekiler ne üretmişti.
- İz gizlilik kuralı `to_wire` biçimine de genişletildi ve canlı gövde üzerinde doğrulandı: öğrenci satırı, puanlar, prompt ve yanıt metni izde yok.
- **Temizlik**: ölü `_attach_rag_context` (~140 satır) kaldırıldı - işi Faz 3'te ajanın kendisine geçmişti. `rag_client.query_rag_context(s)` duruyor ama canlı akışta çağrılmıyor; `rag_service.py`nin eski `queries` biçiminin tek istemcisi oldukları için ikisi birlikte kaldırılmalı, koda not düşüldü.
- **Çürümüş testler onarıldı**: `test_approved_data_analyzer_rag.py`'de beş test hâlâ çağrılmayan `rag_client.query_rag_contexts`i mock'luyordu. Üçünün `assert_not_called` iddiası boşa dönmüştü; ikisi ise mock hiç devreye girmediği için çözülemeyen bir alan adına düşüp **DNS hatası sayesinde geçiyordu** - arıza yalıtımını ölçtüklerini sanıyorduk, ölçmüyorlardı.
- Canlı doğrulama (sıcak konteyner, gerçek rota): HTTP 200, gövde `{ok, message, analysis, trace}`; 5 ajan Türkçe etiketleriyle; ortak tur 9 istem / 9 sonuç; 8/8 teşhis dolu; anomali kasıtlı olarak bozulan Soru 4'ü adlandırdı. **Faz 3'ün maliyet iddiası bozulmadı: 15,7 sn** (iz toplamak ağ turu eklemiyor).
- Yeni testler: `tests/test_analysis_route_trace.py` (5), `tests/report-trace.test.js`, ayrıca iz/LLM kaydı testleri. Toplam 135 → 155 Python testi, 5 → 6 node dosyası.

## Çok Ajanlı Analiz Hattı - Faz 3: Tek İstekli LLM Turu + Anomali Ajanı - 2026-08-16

- **Bir analizde artık TEK LLM isteği atılıyor**, kaç ajan LLM kullanırsa kullansın. Ajanlar LLM'i doğrudan çağırmıyor; `context.enqueue_prompt(...)` ile prompt'larını kuyruğa yazıyor, orkestratör hepsini tek istekte gönderip sonuçları `apply_llm` ile sahiplerine dağıtıyor.
- Gerekçesi ölçüldü: her LLM'li ajan kendi HTTP turunu atsaydı analize ~3 sn eklerdi ve beş ajanda "ek GPU maliyeti yok" iddiası çökerdi. Canlı ölçüm: **9 prompt (8 teşhis + 1 anomali) tek turda 16,7 sn**; ikinci bir LLM ajanı eklemenin bedeli tam bir tur değil, ~3 sn oldu.
- `rag_service.py`'nin `agents` uç noktası birleştirildi: her öğe isteğe bağlı bir `retrieval` bloğu taşıyabiliyor. Getirimli (müfredat teşhisi) ve getirimsiz (anomali) prompt'lar **aynı istekte, aynı vLLM partisinde** çözülüyor. Hiçbir öğe getirim istemiyorsa Qdrant'a hiç dokunulmuyor. Eski `queries` biçimi geriye dönük uyum için duruyor.
- **Yeni LLM rolü - Ölçme Ajanı'nda anomali tespiti**: "Soru 4: Başarı oranı sıfır", "Soru 3 ve Soru 5: Benzer başarı oranları" gibi bulgular `summary.anomalies` alanına yazılıyor. Kasıtlı anomalili fixture ile canlı doğrulandı. **Hiçbir sayıyı değiştirmiyor** ve LLM'e yalnız SORU düzeyinde toplu istatistik gidiyor - öğrenci satırı gitmiyor, gizlilik kapısına yan kapı açılmıyor. Üçten az soruda prompt hiç kurulmuyor.
- Pedagojik Analiz Ajanı da kuyruğa taşındı; teşhis prompt'u `backend/app/agents/prompts.py`e geldi (birleşik biçimde system prompt'u çağıran gönderiyor ve bir ajanı tanımlayan şey büyük ölçüde kendi prompt'u). Sunucudaki kopya eski biçim için duruyor; ikisinin ayrışmasını `tests/test_agent_llm_round.py` engelliyor.
- Raporlama Ajanı artık LLM turundan SONRA koşuyor (`after_llm`), böylece LLM sonuçlarının rapora ulaşması akış sırasına bağlı - önceden üretilmiş sözlüklerin yerinde değiştirilmesi tesadüfüne değil.
- **Davranış değişikliği:** parti başarısız olduğunda çıktıları TEK TEK yeniden sorgulayan geri çekilme yolu kaldırıldı. N çıktı için N ağ turu, tek istekli mimarinin amacıyla çelişiyordu. Korunan güvence: teşhis bir zenginleştirme - tur başarısız olursa hücreler boş kalır, analiz eksiksiz üretilir, istisna fırlamaz. Testle sabitlendi.
- Canlı doğrulama: 8/8 teşhis dolu, 0 yanlış şiddet, 0 yanlış Bloom, 0 gerçek öneri sızıntısı.
- Yeni testler: `tests/test_agent_llm_round.py` (10 test). Ayrıca birim testlerinin canlı GPU'ya istek attığı fark edildi ve yalıtıldı (test paketi 149 sn'den 10 sn'ye indi).

## Çok Ajanlı Analiz Hattı - Faz 2: Paylaşılan LLM Altyapısı - 2026-08-16

- `rag_service.py`'nin uç noktasına dördüncü bir gövde biçimi eklendi: `{"agents": [{"name", "system", "user"}...]}`. Ajanlar artık kendi prompt'unu gönderebiliyor; önceden `SYSTEM_PROMPT` sabit gömülüydü ve tüm depoda tek bir LLM çağrı noktası vardı. Mevcut üç biçim (`warmup`, `queries`, tekil `question`) aynen korundu.
- Bu dal **getirime hiç dokunmuyor**: Qdrant açılmıyor, Volume reload edilmiyor, gömme yapılmıyor. MAHİR'in ajanlarının çoğu müfredat metnine değil, kendi hesapladığı verilere bakarak yorum üretiyor.
- **Ek GPU maliyeti yok.** Bir turdaki tüm ajan prompt'ları tek istekte, tek vLLM partisinde ve aynı sıcak konteynerde gidiyor. Canlı ölçüm (tam ısınmış konteyner): 1 prompt 2,9 sn / 215 karakter; 10 prompt 7,4 sn / 3448 karakter. Yani 10 prompt, tek prompt'un 2,6 katı sürede 16 katı metin üretiyor - verim 74 kr/sn'den 466 kr/sn'ye çıkıyor.
- Charter süzgeci ortak katmana taşındı: yeni `backend/app/charter_guard.py`. "MAHİR yöntem/telafi önermez" kısıtı artık tek bir ajanın değil, LLM üreten her ajanın sorunu ve her yanıt bu süzgeçten geçiyor. Mevcut 5 süzgeç testi hiç değiştirilmeden geçmeye devam ediyor - taşımanın sadık olduğunun kanıtı.
- Yeni istemci katmanı `backend/app/agents/llm.py`: parti toplayıcı + charter süzgeci + iz kaydı. HTTP için mevcut `rag_client._post` yeniden kullanılıyor (parola başlığını, hata gövdesinden Türkçe mesaj çıkarmayı ve zaman aşımını zaten doğru yapıyor). `rag_client` ile aynı "asla istisna fırlatmaz" sözleşmesi geçerli.
- Uç nokta artık çağıranın prompt'unu bu GPU'da çalıştırdığı için sınırlar kondu: istek başına en çok 16 prompt, prompt başına 8000 karakter, `maxTokens` tavanı 1024. Parola kapısı kötü niyetliyi, bu sınırlar hatayı durduruyor - döngüye giren bir ajan sessizce GPU dakikası yakmasın. Geçersiz istekler üretim çalıştırılmadan 400 alıyor.
- İz kaydı için `trace_entry` yazıldı: `{agent, promptChars, answerChars, strippedSentences, durationMs}`. Prompt ve yanıt **metni** kasıtlı olarak dışarıda - iz yalnız sayım ve özet taşıyor. (Düzeltme: bu kayıt Faz 2'de üretiliyor ama `AgentTrace.llm_calls`e hiç YAZILMIYORDU; alan Faz 4'te gerçekten dolduruldu.)
- Canlı doğrulandı: parolasız `{"agents": [...]}` isteği 401; sınır ihlalleri 400; mevcut RAG akışı bozulmadı (8/8 dolu, 0 yanlış şiddet, 0 yanlış Bloom, 0 gerçek öneri sızıntısı).
- Yeni testler: `tests/test_agent_llm.py` (11 test, gerçek yerel HTTP sunucusuna karşı).

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
