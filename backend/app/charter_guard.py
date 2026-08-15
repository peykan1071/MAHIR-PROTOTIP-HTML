"""MAHİR'in üretilmiş metin çıktıları için charter emniyet ağı.

`DEVELOPMENT_CHARTER.md`: "MAHİR ... öğretim yöntemi veya telafi programı
önermez." Bu kısıt `rag_service.py`nin SYSTEM_PROMPT'unda (madde 5) yazılı ama
7B'lik bir modelde prompt tek başına güvence değil - canlı ölçümde 8 yanıtın
2'si "... programları önerilir" / "... eğitim verilmesi gerekmektedir" gibi
öneri cümleleriyle bitti. Bu yüzden kod tarafında da cümle düzeyinde bir
süzgeç var.

Bu modül `approved_data_analyzer`dan buraya taşındı: kısıt tek bir ajanın
değil, LLM üreten HER ajanın sorunu. `agents/` paketi yerine üst seviyede
duruyor çünkü (a) ajanlara özgü değil - her MAHİR metin çıktısı için geçerli,
(b) `agents/__init__.py` üzerinden import döngüsü riski doğurmuyor.
"""

from __future__ import annotations

import re

# Tetikleyiciler kasıtlı olarak DAR tutuldu - teşhis dilinde meşru olan
# biçimler elenmemeli: "gerektirir" ("bu kazanım analiz becerisi gerektirir")
# ve "gerekli olan" ("gerekli olan yeteneklerin kazandırılmadığı") kalmalı;
# yalnızca reçete yazan biçimler ("gerekir", "gerekmektedir", "gereklidir",
# zorunluluk kipi "-malıdır") elenmeli.
RECOMMENDATION_PATTERN = re.compile(
    r"öneri|tavsiye|telafi|gerekmekte|gerekiyor|\bgerekir\b|gereklid[ıi]r"
    r"|ihtiyaç duyul|şartt[ıi]r|mal[ıi]d[ıi]r\b|melid[ıi]r\b"
    # "eksikliği giderme ihtiyacı ortaya çıkmaktadır" gibi kapanışlar: MAHİR'in
    # kendi terimi olan "gelişim ihtiyacı" elenmemeli, bu yüzden tetikleyici
    # "ihtiyaç" değil, telafiyi anlatan "gider-" kökü.
    r"|giderme|giderilme|gidermek|giderilmesi",
    re.IGNORECASE,
)


def strip_recommendation_sentences(answer: str) -> tuple[str, int]:
    """Öneri içeren cümleleri at; (kalan metin, atılan cümle sayısı) döndür.

    Yanıt tek bir akıcı paragraf olduğundan (bkz. SYSTEM_PROMPT çıktı biçimi)
    cümleler birbirinden büyük ölçüde bağımsız - bir cümleyi düşürmek kalan
    teşhisi bozmuyor. Hepsi öneriyse boş string döner ve çağıran taraf çıktıyı
    tamamen atar; charter ihlali içeren bir metni raporlamaktansa hücreyi boş
    bırakmak doğrusu.
    """

    sentences = re.split(r"(?<=[.!?])\s+", answer)
    kept = [sentence for sentence in sentences if not RECOMMENDATION_PATTERN.search(sentence)]
    return " ".join(kept).strip(), len(sentences) - len(kept)
