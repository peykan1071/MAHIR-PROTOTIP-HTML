# Program Eşleştirme Ajanı

## Amaç

Program Eşleştirme Ajanı, öğretmenin her soru için seçtiği öğrenme çıktısını ders, sınıf ve kayıtlı resmî program kataloğu bağlamında doğrulayan deterministik görev bileşenidir.

Prototip, soru metninden öğrenme çıktısını kendiliğinden tahmin edip kesinleştirmez. Pedagojik eşleştirme öğretmenin sorumluluğundadır; ajan bu seçimin kayıtlı programla tutarlı olup olmadığını denetler ve analizde kullanılacak ilişkiyi standartlaştırır.

## Sorumluluklar

- CED nesnesini ve sınav bağlamını alır.
- Ders ve sınıf için kayıtlı program profilini bulur.
- Seçilmiş öğrenme çıktısı kodlarının program bağlamıyla uyumunu doğrular.
- Birden fazla çıktı seçilmişse soru puanına katkı ağırlıklarını korur.
- Öğrenme çıktısı seçilmemiş soruları açıkça işaretler.
- Doğrulanmış eşleştirmeyi sonraki analiz adımına aktarır.

## Yetki sınırı

- Soru içeriğinden otomatik öğrenme çıktısı üretmez.
- Öğretmen adına pedagojik eşleştirme kararı vermez.
- Puan veya başarı oranı hesaplamaz.
- Pedagojik yorum ve raporlama yapmaz.
- Kayıtlı olmayan bir program için varsayımsal müfredat içeriği oluşturmaz.

## Girdi ve çıktı

**Girdi:** CED nesnesi, ders, sınıf düzeyi ve öğretmenin soru bazında seçtiği öğrenme çıktıları.

**Çıktı:** Doğrulanmış program kimliği, öğrenme çıktısı ilişkileri, eşleştirilmemiş soru bulguları ve işlem izi.

## İş akışı

1. CED nesnesini ve sınav bağlamını alır.
2. İlgili kayıtlı program profilini çözümler.
3. Öğretmenin seçtiği çıktı kodlarını bağlam içinde doğrular.
4. Eksik veya uyumsuz eşleştirmeleri bildirir.
5. Doğrulanmış ilişkileri Ölçme ve Değerlendirme Ajanına aktarır.
