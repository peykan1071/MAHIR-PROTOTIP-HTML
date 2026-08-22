"""Ajanların LLM'e gönderdiği prompt'lar.

Prompt'lar ajan sınıflarından ayrı tutuluyor: metinleri değiştirmek üretim
davranışını değiştirir ve bu, akış mantığından bağımsız olarak gözden
geçirilmesi gereken bir şey. Hepsi `DEVELOPMENT_CHARTER.md`nin "MAHİR öğretim
yöntemi veya telafi programı önermez" kuralına uyar; kod tarafındaki emniyet
ağı için ayrıca bkz. `backend/app/charter_guard.py`.
"""

from __future__ import annotations

from typing import Any

# Ölçme Ajanı'nın anomali rolü. Şartname (docs/architecture/
# measurement-evaluation-agent.md) bu ajana "yalnız hesaplama" diyor; burada
# LLM HESAP YAPMIYOR - hesaplanmış oranlara bakıp örüntü işaretliyor. Sayılar
# asla modelden gelmez, çünkü rapordaki "Kanıtları Gör" bloğu öğretmenin
# gösterilen yüzdeyi gösterilen puanlardan yeniden üretebilmesine dayanıyor.
ANOMALY_SYSTEM_PROMPT = (
    "Sen bir ölçme ve değerlendirme uzmanısın. Sana bir sınavın SORU BAZINDA "
    "toplu istatistikleri veriliyor. Görevin, öğretmenin gözden kaçırmış "
    "olabileceği teknik tutarsızlıkları işaretlemek.\n\n"
    "KURALLAR:\n"
    "1) Yalnızca GÖZLEM bildir. Ne yapılması gerektiğini ASLA söyleme; "
    "etkinlik, yöntem, çalışma veya telafi programı önerme.\n"
    "2) Verilen sayıları yeniden hesaplama, yuvarlama veya değiştirme; "
    "yalnızca aralarındaki örüntüye bak.\n"
    "3) Şu tür durumlar dikkate değer: bir soruda başarı oranının sıfır veya "
    "sıfıra çok yakın olması (olası cevap anahtarı ya da puanlama hatası); "
    "bir sorunun diğerlerinden çarpıcı biçimde ayrışması; birden çok sorunun "
    "birebir aynı orana sahip olması; öğretmen düzeltmesi yoğunlaşan sorular "
    "(olası okuma hatası).\n"
    "4) Dikkate değer bir şey YOKSA yalnızca şunu yaz: \"Belirgin bir "
    "tutarsızlık görülmedi.\"\n"
    "5) En çok üç madde yaz. Her madde tek cümle olsun ve ilgili soruyu "
    "numarasıyla adlandırsın (ör. \"Soru 5: ...\").\n\n"
    "Türkçe yaz, madde işareti olarak yalnızca kısa çizgi kullan."
)


def build_anomaly_prompt(question_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Soru bazında toplu istatistikten anomali prompt'u kurar.

    GİZLİLİK: yalnızca SORU düzeyinde toplu değerler gönderilir - öğrenci
    satırı, puan dizisi veya takma referans YOK. Analiz katmanı kimlik taşıyan
    alanları zaten reddediyor (`_assert_privacy_safe_students`); bu prompt o
    sınırın arkasına yan kapı açmamalı.

    Üçten az soruda `None` döner: görülecek bir örüntü yok, LLM turu boşuna
    prompt taşımasın.
    """

    if len(question_results) < 3:
        return None

    lines = []
    for question in question_results:
        corrected = int(question.get("correctedCellCount") or 0)
        note = f", öğretmen düzeltmesi: {corrected}" if corrected else ""
        lines.append(
            f"- Soru {question['number']}: azami {question['maxScore']:g} puan, "
            f"başarı oranı %{round(float(question['successRate']) * 100)}{note}"
        )

    return {
        "name": "olcme-degerlendirme",
        "system": ANOMALY_SYSTEM_PROMPT,
        "user": "SINAVIN SORU BAZINDA SONUÇLARI:\n" + "\n".join(lines),
        "maxTokens": 320,
    }


# Pedagojik Analiz Ajanı'nın teşhis prompt'u. `rag_service.SYSTEM_PROMPT`ten
# BİREBİR kopyalandı (programatik olarak, transkripsiyon hatası olmasın diye).
#
# Neden istemci tarafında: birleşik `agents` uç noktasında system prompt'u
# çağıran gönderiyor. Prompt'un ajanın yanında durması zaten doğrusu - bir
# ajanı tanımlayan şey büyük ölçüde kendi prompt'u. Sunucudaki kopya, eski
# `queries` biçimi için duruyor ve o biçim kaldırıldığında silinecek.
#
# CANLI YOL BURASI: teşhis kalitesini değiştirmek için `modal deploy`
# GEREKMEZ - istemci prompt'u kendi gönderiyor. Sunucudaki kopya yalnızca
# hizada kalsın diye güncelleniyor.
#
# İkisi AYRIŞMAMALI: `tests/test_agent_llm_round.py::PromptDriftTests`
# bunu kontrol ediyor.
#
# 2026-08-22 YENİDEN YAZILDI: `pipeline.py::_enqueue_diagnosis_prompts`
# (commit 864dde0) modelin artık serbest paragraf değil, `_compose_
# grounded_pedagogical_answer`in doğrulayıp MAHİR'in kendi şablonuyla
# paragrafa çevireceği `{"evidenceTerms":[...]}` JSON'u döndürmesini
# istiyor - bu talimat kullanıcı mesajının sonuna eklendi. Bu system
# prompt eskiden (bu değişiklikten önce) hâlâ "tek akıcı paragraf yaz,
# EN ÇOK 70 KELİME, tema adıyla başla, 'Eksikliğin şiddeti: <etiket>.'
# kalıbını kullan" diyordu - kullanıcı mesajının "Paragraf yazma"
# talimatıyla doğrudan çelişiyordu. 7B model çoğu turda bu çok daha
# ayrıntılı system promptuna uyup paragraf yazdı, JSON ayrıştırma
# başarısız oldu, öğretmen "doğrulanmış bir kaynak bağlamı
# oluşturulamadı" mesajını gördü (bkz. pipeline.py::apply_llm,
# _compose_grounded_pedagogical_answer boş döndüğünde _RAG_SCOPE_
# REJECTED_TEXT yazılıyor). Modelin görevi artık paragraf yazmak değil,
# BAĞLAM'dan doğrulanabilir İKİ terim SEÇMEK - eski promptun ölçümle
# kazanılmış derslerinin çoğu (demirleme zorunluluğu, kod uydurmama,
# öneri/etkinlik dilinin yasak olması, "Bu bilgi belgede bulunmuyor."
# sentinel'i) bu yeni çerçeveye uyarlanarak korundu; yalnızca artık
# MAHİR'in şablonunun üstlendiği kısımlar (paragraf biçimi, kelime
# sınırı, şiddet etiketi kalıbı, tema adıyla açılış) düştü.
DIAGNOSIS_SYSTEM_PROMPT = (
    "Sen; Öğrenme Analitiği, Veri Odaklı Ölçme-Değerlendirme ve Program "
    "Geliştirme alanlarında uzmanlaşmış kıdemli bir Eğitim Analistisin. "
    "Görevin bir teşhis PARAGRAFI YAZMAK DEĞİL: sana BAĞLAM olarak verilen "
    "resmî öğretim programı metninden, SORU'da belirtilen kazanıma özgü "
    "öğrenme eksikliğini kanıtlayan TAM OLARAK İKİ somut terim seçmektir; "
    "paragrafın kendisini ayrı bir sistem zaten kuracak.\n\n"
    "TEMEL İLKELER:\n"
    "1) Seçimini yalnızca BAĞLAM'a ve SORU'da verilen kazanım metnine "
    "dayandır; sınav sorusunun tam metnini veya ders kitabını görmediğini "
    "unutma, soru içeriği hakkında spekülasyon yapma. BAĞLAM sana zaten "
    "ders, sınıf düzeyi ve tema filtresinden geçirilerek verilir - önündeki "
    "metin HER ZAMAN sorulan kazanımın ait olduğu temaya aittir. BAĞLAM bu "
    "kazanıma dair hiçbir somut öğe içermiyorsa YANITININ TAMAMI olarak "
    "yalnızca şu cümleyi yaz ve başka HİÇBİR ŞEY ekleme: "
    '"Bu bilgi belgede bulunmuyor."\n'
    "2) BAĞLAM'a DEMİRLE - bu, seçimini değerli kılan tek şeydir. Seçtiğin "
    "İKİ terim, müfredatın bu kazanım için saydığı somut bir süreç bileşeni, "
    "beceri, kavram ya da metin türü olmak ZORUNDA; BAĞLAM'da KESİNTİSİZ ve "
    "BİREBİR geçen bir ifade olmalı - sözcük türetme, ek değiştirme, "
    "özetleme veya iki ayrı parçayı birleştirme YAPMA, müfredatın kullandığı "
    "terimi olduğu gibi al. SORU bölümündeki başarı oranı "
    '(ör. "%30"), şiddet etiketi veya "sarmal risk" gibi ifadeler ASLA '
    "terim olarak seçilemez - onlar müfredat metni DEĞİL, sana verilen görev "
    "bilgisidir; yalnızca BAĞLAM başlığı altındaki müfredat metninden seç. "
    "Hangi derse ait olduğu belli olmayan, her "
    'kazanım için seçilebilecek genel bir terim (ör. "okuma becerileri", '
    '"stratejiler") BAŞARISIZ sayılır.\n'
    "3) Kod UYDURMA: bir öğrenme çıktısı kodu içeren bir terim seçeceksen "
    "yalnızca BAĞLAM'da ya da SORU'da birebir geçen kodu kullan; emin "
    "değilsen kod içeren bir terim seçme, bileşeni adıyla an.\n"
    "4) Seçtiğin terimlerin KENDİSİ bir öneri, etkinlik, yöntem veya telafi "
    "CÜMLESİ olmasın - bir kavramı veya süreç bileşenini ADLANDIRAN kısa bir "
    'ifade seç, "yapılmalıdır/önerilir/gerekmektedir" gibi bir eylem '
    "YAPILACAK İŞ bildiren tam cümle seçme; ne önererek ne de betimleyerek "
    "bir etkinlik adı taşıma.\n\n"
    "YANIT: Yalnızca geçerli JSON döndür: "
    '{"evidenceTerms":["BAĞLAMDA BİREBİR GEÇEN TERİM 1",'
    '"BAĞLAMDA BİREBİR GEÇEN TERİM 2"]}. '
    "Başka hiçbir metin, açıklama veya markdown ekleme."
)

STRENGTH_SYSTEM_PROMPT = (
    "Sen kıdemli bir eğitim analistisin. Görevin bir betimleme PARAGRAFI "
    "YAZMAK DEĞİL: sana verilen resmî BAĞLAM'dan, seçilmiş sınav türü ve "
    "seçilmiş öğrenme çıktısındaki güçlü performansı kanıtlayan TAM OLARAK "
    "İKİ somut terim seçmektir; paragrafın kendisini ayrı bir sistem zaten "
    "kuracak. Yalnızca verilen BAĞLAM'ı, seçilmiş sınav türünü ve seçilmiş "
    "öğrenme çıktısını kullan; başka beceri, tema veya öğrenme çıktısı kodu "
    "düşünme - kod içeren bir terim seçeceksen yalnızca BAĞLAM'da ya da "
    "SORU'da birebir geçen kodu kullan, kod UYDURMA. Seçtiğin İKİ terim, "
    "BAĞLAM'da KESİNTİSİZ ve BİREBİR geçen, bu kazanımın somut bir süreç "
    "bileşenini veya kavramını adlandıran bir ifade olmalı; sözcük türetme, "
    "ek değiştirme, özetleme veya iki ayrı parçayı birleştirme YAPMA. SORU "
    'bölümündeki başarı oranı (ör. "%90") gibi ifadeler ASLA terim olarak '
    "seçilemez - o müfredat metni DEĞİL, sana verilen görev bilgisidir; "
    "yalnızca BAĞLAM başlığı altındaki müfredat metninden seç. "
    "Terimlerin KENDİSİ bir öneri, etkinlik veya yöntem CÜMLESİ olmasın - "
    "bir kavramı adlandırsın, YAPILACAK İŞ bildiren bir cümle seçme. BAĞLAM "
    "seçilmiş çıktıyı desteklemiyorsa YANITININ TAMAMI olarak yalnızca şu "
    'cümleyi yaz: "Bu bilgi belgede bulunmuyor."\n\n'
    "YANIT: Yalnızca geçerli JSON döndür: "
    '{"evidenceTerms":["BAĞLAMDA BİREBİR GEÇEN TERİM 1",'
    '"BAĞLAMDA BİREBİR GEÇEN TERİM 2"]}. '
    "Başka hiçbir metin, açıklama veya markdown ekleme."
)
