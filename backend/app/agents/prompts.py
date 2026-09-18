"""Ajanların LLM'e gönderdiği prompt'lar.

Prompt'lar ajan sınıflarından ayrı tutuluyor: metinleri değiştirmek üretim
davranışını değiştirir ve bu, akış mantığından bağımsız olarak gözden
geçirilmesi gereken bir şey.
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
    "toplu istatistikleri veriliyor; öğretmenin gözden kaçırmış olabileceği "
    "teknik tutarsızlıkları işaretle.\n\n"
    "KURALLAR:\n"
    "1) Yalnızca GÖZLEM bildir; ne yapılması gerektiğini söyleme, etkinlik ya da "
    "telafi önerme. Sayıları yeniden hesaplama, yuvarlama ya da değiştirme; "
    "yalnızca aralarındaki örüntüye bak.\n"
    "2) Dikkate değer durumlar: sıfıra yakın başarı oranı (olası cevap anahtarı "
    "ya da puanlama hatası), diğerlerinden çarpıcı biçimde ayrışan soru, birebir "
    "aynı orana sahip sorular, öğretmen düzeltmesi yoğunlaşan sorular.\n"
    "3) Dikkate değer bir şey YOKSA yalnızca şunu yaz: \"Belirgin bir "
    "tutarsızlık görülmedi.\"\n"
    "4) En çok üç madde; her madde tek cümle ve ilgili soruyu numarasıyla "
    "adlandırsın (ör. \"Soru 5: ...\").\n\n"
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


# Pedagojik Analiz Ajanı'nın teşhis prompt'u - TEK kopya burada.
#
# Neden istemci tarafında: `agents` uç noktasında (`local/rag_service.py`)
# system prompt'u çağıran gönderiyor; servis kendi prompt'unu dayatmaz. Prompt'un
# ajanın yanında durması zaten doğrusu - bir ajanı tanımlayan şey büyük ölçüde
# kendi prompt'u. Teşhis kalitesini değiştirmek için yalnız bu dosya değişir,
# servisin yeniden başlatılması gerekmez.
DIAGNOSIS_SYSTEM_PROMPT = (
    "Sen kıdemli bir eğitim analistisin. BAĞLAM olarak verilen resmî öğretim programı metnine "
    "dayanarak, SORU'daki kazanıma özgü öğrenme eksikliğini kanıta dayalı biçimde teşhis eden "
    "TEK, akıcı bir paragraf yaz.\n\n"
    "KURALLAR:\n"
    "1) Yalnızca BAĞLAM'a ve SORU'daki kazanım metnine dayan; sınav sorusunun kendisini "
    "görmüyorsun, soru içeriği hakkında tahmin yürütme. BAĞLAM bu kazanıma dair hiçbir bilgi "
    "içermiyorsa YANITININ TAMAMI OLARAK yalnızca şu cümleyi yaz: \"Bu bilgi belgede bulunmuyor.\"\n"
    "2) BAĞLAM'a DEMİRLE: paragraf, BAĞLAM'dan EN AZ BİR, EN ÇOK BEŞ somut öğeyi (süreç bileşeni, "
    "beceri, kavram ya da metin türü) müfredatın kendi sözcükleriyle anmak ZORUNDA; sözcükleri "
    "değiştirme, yalnızca Türkçe çekim eki ekleyebilirsin (ör. \"...yı kavrayamamaktadır\"). Her "
    "kazanıma yazılabilecek genel bir teşhis (\"okuma becerileri eksik\") BAŞARISIZ sayılır. Kazanım "
    "kodunu yalnızca BAĞLAM'da ya da SORU'da geçiyorsa yaz; kod UYDURMA, emin değilsen bileşeni "
    "adıyla an.\n"
    "3) Tema adını, yüzdeyi (\"%\" dâhil), \"Eksikliğin şiddeti\" ifadesini ve sonraki öğrenmelere "
    "yönelik sarmal/kümülatif risk yorumunu PARAGRAFINDA HİÇ YAZMA; bunlar rapora ayrıca eklenir. "
    "Yalnızca bugün gözlenen eksikliği anlat.\n"
    "4) Eleştirel ve somut ol: teselli ifadeleri (\"geçerli bir puan\", \"gelişime açık\") ve "
    "belirsizlik dolgusu (\"belirli\", \"genellikle\", \"bazı\", \"birtakım\", \"söz konusu\") "
    "yasak; düşük oranı doğrudan öğrenme kaybı ya da kazanımın kavranamaması olarak teşhis et.\n\n"
    "BİÇİM: Türkçe, tek akıcı paragraf; madde işareti, başlık ya da markdown yok. UZUNLUK: EN ÇOK "
    "45 KELİME (katı sınır), 15 kelimenin altına da düşme. Yalnızca geçerli JSON döndür, başka "
    "metin yazma:\n"
    '{"diagnosis": "paragraf"}'
)

STRENGTH_SYSTEM_PROMPT = (
    "Sen kıdemli bir eğitim analistisin. Yalnızca verilen resmî BAĞLAM, seçilmiş sınav türü ve "
    "seçilmiş öğrenme çıktısına dayanarak güçlü performans alanını betimleyen TEK, akıcı bir "
    "paragraf yaz. BAĞLAM'dan EN AZ BİR, EN ÇOK BEŞ somut süreç bileşeni ya da kavramı müfredatın "
    "kendi sözcükleriyle an (yalnızca Türkçe çekim eki ekleyebilirsin). Başka beceri, tema ya da "
    "öğrenme çıktısı kodu yazma; neden, öğrenci sayısı ya da kalıcı öğrenme hakkında çıkarım yapma. "
    "Tema adını ve yüzdeyi (\"%\" dâhil) YAZMA; bunlar rapora ayrıca eklenir.\n\n"
    "Türkçe, en çok iki cümle ve 35 kelime. BAĞLAM seçilmiş çıktıyı desteklemiyorsa yalnızca şu "
    "cümleyi yaz: \"Bu bilgi belgede bulunmuyor.\" Yalnızca geçerli JSON döndür, başka metin yazma:\n"
    '{"diagnosis": "paragraf"}'
)
