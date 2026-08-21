# Ölçme ve Değerlendirme Ajanı

## Amaç

Ölçme ve Değerlendirme Ajanı, öğretmen tarafından girilmiş veya belge okuma aşamasında elde edilip öğretmen tarafından onaylanmış soru puanlarından soru ve öğrenme çıktısı düzeyinde nicel sonuçlar üreten görev bileşenidir.

MAHİR mevcut prototipte öğrencilerin açık uçlu cevap metinlerini otomatik olarak puanlamaz. Ajanın girdisi cevap metni değil, onaylanmış soru puanlarıdır.

## Sorumluluklar

- Öğrenme çıktısı ilişkileri doğrulanmış CED nesnesini alır.
- Her soru için kazanılan ve alınabilecek toplam puanı hesaplar.
- Soru bazlı başarı oranlarını hesaplar.
- Öğrenme çıktısı bazlı ağırlıklı başarı oranlarını hesaplar.
- Oranların dayandığı soru, puan ve katılımcı kanıtını kaydeder.
- Öğretmen tarafından düzeltilen hücrelerin sayısını işlem izine taşır.
- Yalnız açıklayıcı anomali kontrolü gerektiğinde ortak LLM kuyruğuna sayı üretmeyen bir istem ekler.

## Yetki sınırı

- Öğrenci cevap metnini değerlendirmez veya otomatik puanlamaz.
- LLM kullanarak puan, oran ya da istatistik üretmez.
- Öğrenme çıktısı seçmez.
- Pedagojik öneri veya resmî rapor oluşturmaz.
- Hesaplanan sayıları LLM yanıtına göre değiştirmez.

## Girdi ve çıktı

**Girdi:** CED nesnesi, onaylanmış anonim öğrenci soru puanları, azami soru puanları ve doğrulanmış öğrenme çıktısı ilişkileri.

**Çıktı:** Soru ve öğrenme çıktısı başarı sonuçları, yeniden hesaplanabilir kanıt değerleri, varsa açıklayıcı anomali bulgusu ve işlem izi.

## İş akışı

1. CED nesnesini ve onaylı puanları alır.
2. Soru toplamlarını deterministik ölçme motoruyla hesaplar.
3. Öğrenme çıktısı toplamlarını soru katkı ağırlıklarıyla hesaplar.
4. Başarı oranlarını ve kanıt değerlerini kaydeder.
5. Gerekirse sayı üretmeyen anomali açıklaması için ortak LLM kuyruğuna istem ekler.
6. Nicel sonuçları Pedagojik Analiz Ajanına aktarır.
