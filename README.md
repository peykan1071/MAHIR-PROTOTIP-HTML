# MAHİR

**Maarif Anlayışıyla Hizmet İzleme ve Raporlama Ajanı**

MAHİR; sınav verilerini öğrenme kanıtına dönüştürerek öğretmenlere kaynak temelli analiz, pedagojik değerlendirme ve raporlama desteği sunmak amacıyla geliştirilen, öğretmen kontrollü çok ajanlı yapay zekâ prototipidir.

Bu depo, MAHİR Takımı tarafından TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması kapsamında geliştirilen çalışan prototipi içermektedir.

> Ayrıntılı proje yaklaşımı, mevcut sınırlar ve gelecek vizyonu için: [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)

## Problem

Okullarda sınavlar, ortak yazılılar, soru analizleri, zümre çalışmaları ve resmî raporlar için çok sayıda veri üretilmektedir. Bu veriler çoğu zaman farklı belge ve süreçlere dağılmakta; öğretmen aynı veriyi tekrar işlemek zorunda kalabilmekte ve ortaya çıkan verinin öğrenmeyi geliştirecek bilgiye dönüştürülmesi güçleşmektedir.

MAHİR bu sorunu yalnızca evrak yükü olarak değil, **eğitim verisinin anlamlandırılması** problemi olarak ele alır.

## Çözüm Yaklaşımı

MAHİR'in yaklaşımı üç temel ilkeye dayanır:

- **İnsan denetimi:** Sistem analiz eder ve önerir; öğretmen inceler, düzeltir ve nihai onayı verir.
- **Kaynak temellilik:** Öğrenme çıktıları ve pedagojik değerlendirmeler resmî programlar ve güvenilir eğitim kaynaklarıyla ilişkilendirilir.
- **Açıklanabilirlik:** Analiz sonucunun hangi veri ve öğrenme çıktısından üretildiğinin izlenebilir olması hedeflenir.

Sistem; veri doğrulama, program eşleştirme, ölçme-değerlendirme, pedagojik analiz ve raporlama görevlerini ayrıştırılmış bileşenler üzerinden yürütmek üzere geliştirilmektedir.

## Güncel Çalışan Akış

```text
Veri Girişi
    ↓
Doğrulama
    ↓
Standart Eğitim Veri Modeli (CED)
    ↓
Program / Öğrenme Çıktısı Eşleştirme
    ↓
Ölçme ve Değerlendirme
    ↓
Pedagojik Analiz
    ↓
Öğretmen Kontrolü
    ↓
Raporlama
```

Prototipte CSV ve Word tabanlı veri giriş akışları bulunmaktadır. PDF ve görüntü tabanlı belge işleme, OCR, doğal dilde veri kabulü, MAHİR Index üzerinden resmî kaynaklara erişen RAG yapısı ve ajan orkestrasyonu geliştirme ve bütünleştirme aşamasındadır.

## Pilot Kapsamı

- **Ana pilot:** 9. Sınıf Türk Dili ve Edebiyatı
- **Doğrulama pilotu:** Fen Bilimleri

İlk sürümün odağı sınav analizi ve raporlamadır. Prototip henüz tüm öğretmen evraklarını, tüm dersleri ve tüm kademeleri kapsayan tamamlanmış bir ürün değildir.

## Teknoloji Yığını

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python
- **Veri modeli:** CED (Canonical Education Document)
- **Sürüm ve ekip çalışması:** Git / GitHub

## Depo Yapısı

```text
assets/      Görsel ve arayüz varlıkları
backend/     Veri işleme, doğrulama, analiz ve raporlama bileşenleri
docs/        Mimari ve proje dokümantasyonu
shared/      Ortak veri, örnekler ve pilot veri paketleri
index.html   Ana web arayüzü
script.js    Frontend davranışları ve entegrasyon akışı
styles.css   Arayüz stilleri
```

## Yerel Çalıştırma

Proje kök dizininde:

```bash
python backend/run_file_receiver.py
```

Ardından tarayıcıda:

```text
http://127.0.0.1:8000/index.html
```

adresini açın.

## Geliştirme Disiplini

MAHİR küçük, kontrollü ve izlenebilir geliştirme adımlarıyla ilerletilmektedir. Ana dal korunur; değişiklikler görev dallarında geliştirilir, kod/doküman incelemesinden geçirilir ve Pull Request üzerinden ana dala alınır.

Ayrıntılı geliştirme kuralları için: [DEVELOPMENT_CHARTER.md](DEVELOPMENT_CHARTER.md)

Sürüm ve geliştirme geçmişi için: [CHANGELOG.md](CHANGELOG.md)

## Takım

**MAHİR Takımı**

- Zülal Ülker Daştan — Türk Dili ve Edebiyatı
- Hakan Ergül — Matematik
- Gonca Ergül — Fen Bilimleri
- Lokman Daştan — Din Kültürü ve Ahlak Bilgisi
