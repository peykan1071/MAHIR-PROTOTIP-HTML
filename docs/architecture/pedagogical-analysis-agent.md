# Pedagojik Analiz Ajanı

## Amaç

Pedagojik Analiz Ajanı, Ölçme ve Değerlendirme Ajanının ürettiği nicel sonuçları gelişim düzeyi ve kanıt önceliği bakımından sınıflandıran; kayıtlı program kaynağı bulunduğunda RAG destekli, kaynak gösteren bir açıklamayla zenginleştiren görev bileşenidir.

## Sorumluluklar

- Hesaplanmış öğrenme çıktısı başarı oranlarını değiştirmeden devralır.
- Tanımlı eşiklere göre gelişim düzeyi ve karar etiketlerini oluşturur.
- Güçlü ve gelişime açık öğrenme çıktıları için kanıt özetini hazırlar.
- Yalnız kayıtlı ders, sınıf ve tema bağlamında RAG istemi oluşturur.
- Kaynaksız veya seçilen öğrenme çıktısıyla kapsamı uyuşmayan LLM yanıtını rapora taşımaz.
- Kullandığı program kaynağını işlem izine ve rapor kanıtına ekler.

## Yetki sınırı

- Puan, başarı oranı veya istatistik hesaplamaz.
- Ham öğrenci listesini ya da kimlik belirleyici alanları LLM/RAG katmanına göndermez.
- Kaynak bulunmadığında varsayımsal müfredat açıklaması üretmez.
- Öğretim yöntemi, etkinlik, kitap sayfası veya telafi programı önermez.
- Nihai eğitim kararını öğretmen adına vermez.

## Girdi ve çıktı

**Girdi:** Hesaplanmış soru ve öğrenme çıktısı sonuçları, doğrulanmış program kimliği ve anonimleştirilmiş kanıt özeti.

**Çıktı:** Gelişim düzeyi ve karar etiketleri; uygun olduğunda kaynaklı RAG açıklaması, kaynak listesi ve işlem izi.

## LLM/RAG kullanımı

Bu ajan LLM’i serbest içerik üreticisi olarak kullanmaz. İstemler seçilen sınav türü, öğrenme çıktısı, sınıf ve tema ile sınırlandırılır. Kaynak bulunmazsa ilgili açıklama alanı boş bırakılır; deterministik analiz çalışmaya devam eder.
