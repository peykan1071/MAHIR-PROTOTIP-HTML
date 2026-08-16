"""İşlem sürelerini tek biçimde konsola yazan küçük yardımcı.

Neden var: iki uzun işlem (OCR ve analiz) sessizdi - öğretmen butona basıyor,
bir süre bekliyor, sonucu görüyordu; ne kadar beklediği hiçbir yere
yazılmıyordu. Ölçüm KIRILIMLI olmalı, çünkü tek bir toplam sayı asıl soruyu
yanıtlamıyor: canlı ölçümde aynı iş soğuk konteynerde 160 sn, sıcakta 15,7 sn
sürdü. "Neden 45 sn sürdü"nün cevabı neredeyse her zaman hangi katmanda
geçtiğidir.

Depodaki mevcut `print(f"[MAHIR] ...", flush=True)` desenini sürdürüyor
(bkz. `file_receiver.py`, `ocr_engine.py`) - ayrı bir günlükleme altyapısı
kurmak, tek satırlık çıktı için orantısız olurdu.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

_PREFIX = "[MAHIR][süre]"


def format_fields(fields: dict[str, Any]) -> str:
    """`{"dosya": 3}` -> `"dosya=3"`; boş/None değerler atlanır."""

    return " ".join(
        f"{key}={value}" for key, value in fields.items() if value not in (None, "")
    )


@contextmanager
def stage(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Bir aşamanın süresini ölçer ve bitişte tek satır basar.

    İki kural, ikisi de kasıtlı:

    1. **İstisnayı asla yutmaz.** Ölçüm, ölçtüğü akışın davranışını
       değiştirmemeli - `finally` ile basar, hata olduğu gibi yukarı gider.
    2. **Hata hâlinde de basar** (`hata=evet` ekleyerek). "45 sn sonra
       patladı" bilgisi, "45 sn sürdü" kadar değerli; yalnız başarı yolunda
       ölçmek en çok merak edilen durumu karanlıkta bırakırdı.

    Verilen sözlük çağıran tarafından doldurulabilir - bazı alanlar (kaç
    öğrenci okundu gibi) ancak iş bittikten sonra biliniyor:

        with stage("ocr-yerel", dosya=3) as olcum:
            ok, message, data = run(...)
            olcum["ogrenci"] = len(data["students"])
    """

    extra: dict[str, Any] = dict(fields)
    started = time.monotonic()
    failed = False
    try:
        yield extra
    except BaseException:
        failed = True
        raise
    finally:
        elapsed = time.monotonic() - started
        if failed:
            extra["hata"] = "evet"
        detail = format_fields(extra)
        print(
            f"{_PREFIX} {name} sure={elapsed:.1f}s" + (f" {detail}" if detail else ""),
            flush=True,
        )
