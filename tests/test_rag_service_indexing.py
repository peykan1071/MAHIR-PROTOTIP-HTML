"""Tests for the two pure retrieval/indexing helpers in `rag_service.py`.

`rag_service.py` normally only runs inside a Modal container, but every heavy
import (docling, qdrant, sentence-transformers, vllm) is deferred into the
function bodies, so the module itself imports fine locally with just `modal`
installed - which is what makes these helpers testable at all. `index_pdf`
and `RAGInference` are NOT tested here; they need the container.
"""

import unittest
import uuid
from types import SimpleNamespace

import rag_service


def _hits(*scores):
    """Qdrant azalan skor sırasıyla döndürür; testler de öyle beslemeli."""

    return [SimpleNamespace(score=score) for score in scores]


class DeterministicPointIdTests(unittest.TestCase):
    def test_same_input_gives_same_id(self):
        first = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        second = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        self.assertEqual(first, second)

    def test_id_is_a_valid_uuid_string(self):
        point_id = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 0, "metin")
        self.assertEqual(str(uuid.UUID(point_id)), point_id)  # Qdrant ID olarak kabul etmeli.

    def test_scheme_is_frozen(self):
        # Altın değer: ad alanı veya anahtar biçimi değişirse aynı içerik farklı
        # ID üretir, yani mevcut dizindeki noktalar bir daha ASLA üzerine
        # yazılamaz (sessizce ikizlenir). Bu test o değişikliği gürültülü yapar.
        self.assertEqual(
            rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 0, "Sözün İnceliği"),
            "74dd1935-7f09-5563-831b-e57bfe01d01e",
        )

    def test_every_key_field_changes_the_id(self):
        base = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        variants = {
            "program_id": rag_service._deterministic_point_id("tde-10-tymm", "tdeogr.pdf", 7, "metin"),
            "document_name": rag_service._deterministic_point_id("tde-9-tymm", "baska.pdf", 7, "metin"),
            "chunk_index": rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 8, "metin"),
            "text": rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "baska metin"),
        }
        for field, point_id in variants.items():
            with self.subTest(field=field):
                self.assertNotEqual(base, point_id)
        # Ayrıca hepsi birbirinden de farklı olmalı - alanların ayracı ("|")
        # olmadan "tde-9|tdeogr" ile "tde-9t|deogr" aynı anahtara düşerdi.
        self.assertEqual(len(set(variants.values()) | {base}), 5)

    def test_identical_text_in_different_positions_stays_distinct(self):
        # repeat_table_header aynı başlık satırını tekrarlıyor: tek bir tema
        # içinde birebir aynı metinli iki parça mümkün ve çakışma sessiz veri
        # kaybı olurdu.
        first = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 3, "aynı başlık satırı")
        second = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 9, "aynı başlık satırı")
        self.assertNotEqual(first, second)


class DropWeakHitsTests(unittest.TestCase):
    def test_cuts_at_the_break_in_measured_distribution(self):
        # Gerçek ölçüm (Anlam Arayışı / TDE2.1, tema filtresi açık, top_k=8):
        # 4 isabetten sonra 0,7471 -> 0,6634 kopuşu var.
        hits = _hits(0.9424, 0.8601, 0.7609, 0.7471, 0.6634, 0.6578, 0.6266, 0.6144)
        kept = rag_service._drop_weak_hits(hits)
        self.assertEqual([hit.score for hit in kept], [0.9424, 0.8601, 0.7609, 0.7471])

    def test_keeps_everything_when_the_tail_is_flat(self):
        # Gerçek ölçüm (Sözün İnceliği / TDE2.2): kuyruk düz, kopuş yok.
        # Mutlak bir eşiğin yapamayacağı şey tam olarak bu - oran uyarlanıyor.
        hits = _hits(0.8706, 0.8692, 0.7747, 0.7460, 0.7455, 0.7377, 0.7329, 0.7256)
        self.assertEqual(len(rag_service._drop_weak_hits(hits)), 8)

    def test_never_returns_empty_when_there_were_hits(self):
        # Boş dönmek raporda boş bir hücre demek - bu fonksiyonun asla
        # üretmemesi gereken sonuç. floor_ratio=1.0 en agresif kırpma.
        hits = _hits(0.90, 0.10, 0.05)
        kept = rag_service._drop_weak_hits(hits, floor_ratio=1.0)
        self.assertEqual([hit.score for hit in kept], [0.90])

    def test_empty_input_stays_empty(self):
        self.assertEqual(rag_service._drop_weak_hits([]), [])

    def test_single_hit_is_kept(self):
        hits = _hits(0.61)
        self.assertEqual(len(rag_service._drop_weak_hits(hits)), 1)

    def test_non_positive_top_score_is_left_alone(self):
        # Kosinüs negatif olabilir; orada `top * 0.78` eşiği yükseltir, yani
        # oranla kırpmak anlamını yitirir - liste olduğu gibi geçmeli.
        hits = _hits(-0.10, -0.40, -0.90)
        self.assertEqual(len(rag_service._drop_weak_hits(hits)), 3)


if __name__ == "__main__":
    unittest.main()
