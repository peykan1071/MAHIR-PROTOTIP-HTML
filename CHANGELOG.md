# Changelog

Bu dosya, MAHİR projesindeki önemli değişiklikleri kronolojik olarak takip etmek için hazırlanmıştır.

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
