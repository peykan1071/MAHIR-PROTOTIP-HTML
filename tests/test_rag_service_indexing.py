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


class DocumentTitleTests(unittest.TestCase):
    """Belgenin resmî adı - öğretmenin raporunda kaynak olarak görünen değer."""

    def test_registered_program_resolves_to_its_official_title(self):
        title = rag_service.resolve_document_title("tde-9-tymm")
        self.assertIn("Türk Dili ve Edebiyatı Dersi Öğretim Programı", title)
        self.assertIn("2024", title)

    def test_title_is_not_a_file_name(self):
        # Resmî bir rapor dayanağını "tdeogr.pdf" diye gösteremez.
        for program_id, title in rag_service.DOCUMENT_TITLES.items():
            with self.subTest(program=program_id):
                self.assertNotIn(".pdf", title.lower())

    def test_override_wins_over_the_registry(self):
        self.assertEqual(
            rag_service.resolve_document_title("tde-9-tymm", "Başka Belge (2025)"),
            "Başka Belge (2025)",
        )

    def test_unknown_program_raises_instead_of_falling_back(self):
        # Sessiz geri düşüş olsaydı yanlış adlı parçalar dizine girer ve o ana
        # kadarki her rapor kaynağını yanlış göstermiş olurdu. Hata,
        # indekslemeden ÖNCE verilmeli.
        with self.assertRaises(ValueError) as caught:
            rag_service.resolve_document_title("bilinmeyen-program")
        self.assertIn("DOCUMENT_TITLES", str(caught.exception))

    def test_blank_override_falls_back_to_the_registry(self):
        self.assertEqual(
            rag_service.resolve_document_title("tde-9-tymm", "   "),
            rag_service.DOCUMENT_TITLES["tde-9-tymm"],
        )

    def test_renaming_a_document_changes_its_point_ids(self):
        # Bu, `--replace` bayrağının VAROLUŞ SEBEBİ: ad değişince parçalar yeni
        # kimlik alır, eskiler üzerine YAZILMAZ ve dizinde aynı içerik iki adla
        # kalır. Getirim bunu hatasızca yutar, yalnız sonuç bozulur.
        old = rag_service._deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 3, "metin")
        new = rag_service._deterministic_point_id(
            "tde-9-tymm", rag_service.DOCUMENT_TITLES["tde-9-tymm"], 3, "metin"
        )
        self.assertNotEqual(old, new)


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
    def test_default_floor_keeps_the_topically_relevant_tail(self):
        # 2026-08-22: 0,78 -> 0,60 -> 0,68 -> 0,60 (bkz. _RELATIVE_SCORE_
        # FLOOR'un 2026-08-22 notları). Ne 0,78 (fazla agresif) ne 0,68
        # (hâlâ bazı senaryolarda yetersiz) doğru dengeydi - kök sorun bir
        # SAYI ayarıyla çözülemeyen yapısal bir tekrar sorunuydu, gerçek
        # çözüm `_mmr_select`. Bu eşiğin işi artık yalnız gerçekten alakasız
        # kuyruğu elemek; asıl çeşitlilik/tekrar dengesini `_mmr_select`
        # kuruyor. 0,60 bu gerçek ölçüm verisinde (Anlam Arayışı/TDE2.1)
        # kuyruğun tamamını tutuyor - MMR aşaması bunlardan hangisinin
        # nihai listeye gireceğine ayrıca karar verir.
        hits = _hits(0.9424, 0.8601, 0.7609, 0.7471, 0.6634, 0.6578, 0.6266, 0.6144)
        kept = rag_service._drop_weak_hits(hits)
        self.assertEqual(len(kept), 8)

    def test_old_0_78_ratio_still_cuts_at_the_measured_break(self):
        # Tarihi ölçüm (bkz. eski yorum) hâlâ geçerli bir davranış - yalnız
        # artık modül varsayılanı değil, `floor_ratio` ile açıkça istenmesi
        # gerekiyor.
        hits = _hits(0.9424, 0.8601, 0.7609, 0.7471, 0.6634, 0.6578, 0.6266, 0.6144)
        kept = rag_service._drop_weak_hits(hits, floor_ratio=0.78)
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
        # Kosinüs negatif olabilir; orada `top * floor_ratio` eşiği YÜKSELTİR
        # (negatifin negatifle çarpımı pozitife döner), yani oranla kırpmak
        # anlamını yitirir - liste olduğu gibi geçmeli.
        hits = _hits(-0.10, -0.40, -0.90)
        self.assertEqual(len(rag_service._drop_weak_hits(hits)), 3)


def _mmr_hits(*score_vector_pairs):
    """(skor, vektör) çiftlerinden Qdrant isabetine benzer nesneler üretir."""

    return [SimpleNamespace(score=score, vector=vector) for score, vector in score_vector_pairs]


class CosineSimilarityTests(unittest.TestCase):
    def test_identical_vectors_are_one(self):
        self.assertAlmostEqual(rag_service._cosine_similarity([0.6, 0.8], [0.6, 0.8]), 1.0)

    def test_orthogonal_vectors_are_zero(self):
        self.assertAlmostEqual(rag_service._cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)


class MmrSelectTests(unittest.TestCase):
    """2026-08-22: aynı kazanımın birbirine çok benzeyen "tanımlama"
    satırları düz "en yüksek skorlu top_k" seçiminde tüm slotları doldurup
    temanın asıl zengin, konu-alakalı-ama-kelime-farklı içeriğine hiç yer
    bırakmıyordu (gerçek sorgularla ölçüldü: bir senaryo 5/5 -> 0/5). Bu
    testler, MMR'nin gerçekten "alakalı ama zaten seçilenlerden farklı"
    adayı tercih ettiğini - salt skor sıralamasından farklı bir sonuç
    ürettiğini - doğruluyor.
    """

    def test_returns_everything_when_pool_is_not_larger_than_k(self):
        hits = _mmr_hits((0.9, [1.0, 0.0]), (0.8, [0.0, 1.0]))
        self.assertEqual(rag_service._mmr_select(hits, 5), hits)

    def test_prefers_diverse_candidate_over_a_near_duplicate(self):
        # top her zaman ilk seçilir (en yüksek skor). near_duplicate top'a
        # neredeyse özdeş yönde (redundancy ~0,99); diverse daha düşük
        # skorlu ama top'tan tamamen farklı bir yönde (redundancy 0).
        # Varsayılan lambda (0,6) ile diverse kazanmalı - salt skor
        # sıralaması (near_duplicate 0,85 > diverse 0,70) tersini seçerdi.
        top = SimpleNamespace(score=0.95, vector=[1.0, 0.0])
        near_duplicate = SimpleNamespace(score=0.85, vector=[0.99, 0.01])
        diverse = SimpleNamespace(score=0.70, vector=[0.0, 1.0])
        selected = rag_service._mmr_select([top, near_duplicate, diverse], 2)
        self.assertEqual(selected, [top, diverse])

    def test_lambda_one_falls_back_to_pure_relevance_ranking(self):
        # lambda=1,0 çeşitlilik terimini tamamen sıfırlar - saf skor
        # sıralamasıyla aynı sonucu vermeli (near_duplicate > diverse).
        top = SimpleNamespace(score=0.95, vector=[1.0, 0.0])
        near_duplicate = SimpleNamespace(score=0.85, vector=[0.99, 0.01])
        diverse = SimpleNamespace(score=0.70, vector=[0.0, 1.0])
        selected = rag_service._mmr_select([top, near_duplicate, diverse], 2, lambda_param=1.0)
        self.assertEqual(selected, [top, near_duplicate])

    def test_family_of_near_duplicates_yields_only_one_representative(self):
        # Altı "kazanım tanımlama" benzeri isabet (hepsi birbirine çok
        # yakın), artı bir tane gerçekten farklı ("uygulama" benzeri)
        # isabet. k=3 istendiğinde MMR ailenin tamamını değil, en
        # yükseğini + çeşitliliği seçmeli.
        family = [
            SimpleNamespace(score=0.90 - 0.01 * i, vector=[0.99 - 0.001 * i, 0.02 * i])
            for i in range(6)
        ]
        rich = SimpleNamespace(score=0.68, vector=[0.1, 0.99])
        selected = rag_service._mmr_select([*family, rich], 3)
        self.assertIn(rich, selected)
        self.assertEqual(len(selected), 3)


class _FakeQdrant:
    """`_retrieve_hits`in tek çağırdığı yüzeyi taklit eder - gerçek Qdrant
    kurmadan `query_points`e giden argümanları ve dönen `.points`i kontrol
    etmek için."""

    def __init__(self, points):
        self._points = points
        self.calls: list[dict] = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=self._points)


class SparseVectorFromWeightsTests(unittest.TestCase):
    """`_sparse_vector_from_weights` - bge-m3'ün `lexical_weights` çıktısını
    (`{token_id_str: weight}`) Qdrant'ın `SparseVector`ına çevirir (2026-08-22,
    hibrit arama). Anahtarların STRING olması `FlagEmbedding`in kaynağından
    doğrulandı (`M3Embedder._process_token_weights`: `idx = str(idx)`)."""

    def test_converts_string_keys_to_int_indices(self):
        from qdrant_client.models import SparseVector

        result = rag_service._sparse_vector_from_weights({"5": 0.9, "12": 0.4})
        self.assertIsInstance(result, SparseVector)
        self.assertEqual(result.indices, [5, 12])
        self.assertEqual(result.values, [0.9, 0.4])

    def test_empty_weights_gives_empty_sparse_vector(self):
        result = rag_service._sparse_vector_from_weights({})
        self.assertEqual(result.indices, [])
        self.assertEqual(result.values, [])


class DenseVectorOfTests(unittest.TestCase):
    """`_dense_vector_of` - named-vector (dense+sparse) bir Qdrant isabetinden
    `_mmr_select`in ihtiyaç duyduğu düz dense listesini çıkarır."""

    def test_extracts_dense_from_named_vector_dict(self):
        hit = SimpleNamespace(vector={"dense": [1.0, 2.0], "sparse": object()})
        self.assertEqual(rag_service._dense_vector_of(hit), [1.0, 2.0])

    def test_passes_plain_list_through_unchanged(self):
        # Eski (adsız/tek dense) koleksiyon şemasına geriye dönük tolerans.
        hit = SimpleNamespace(vector=[1.0, 2.0])
        self.assertEqual(rag_service._dense_vector_of(hit), [1.0, 2.0])


class RetrieveHitsTests(unittest.TestCase):
    """`_retrieve_hits` - `_retrieve_for`/`_run_batch_query`nin ortak tek-öğe
    getirim adımı. 2026-08-22: hibrit (dense+sparse) arama - Qdrant'ın
    Prefetch/FusionQuery(RRF) Query API'sini kullanır (yerel/embedded modda
    elle doğrulandı, bkz. commit mesajı)."""

    def test_calls_query_points_with_hybrid_prefetch_and_fusion(self):
        from qdrant_client.models import Fusion, FusionQuery, SparseVector

        qdrant = _FakeQdrant([])
        rag_service._retrieve_hits(qdrant, [1.0, 0.0], {"5": 0.9, "9": 0.2}, 5, None)

        self.assertEqual(len(qdrant.calls), 1)
        call = qdrant.calls[0]
        self.assertEqual(call["collection_name"], rag_service.QDRANT_COLLECTION_NAME)
        pool_size = max(5 * rag_service._MMR_CANDIDATE_MULTIPLIER, rag_service._MMR_MIN_CANDIDATE_POOL)
        self.assertEqual(call["limit"], pool_size)
        self.assertTrue(call["with_payload"])
        self.assertTrue(call["with_vectors"])

        prefetch = call["prefetch"]
        self.assertEqual(len(prefetch), 2)
        dense_leg = next(p for p in prefetch if p.using == "dense")
        sparse_leg = next(p for p in prefetch if p.using == "sparse")
        self.assertEqual(dense_leg.query, [1.0, 0.0])
        self.assertEqual(dense_leg.limit, pool_size)
        self.assertIsInstance(sparse_leg.query, SparseVector)
        self.assertEqual(sparse_leg.query.indices, [5, 9])
        self.assertEqual(sparse_leg.query.values, [0.9, 0.2])
        self.assertEqual(sparse_leg.limit, pool_size)

        self.assertIsInstance(call["query"], FusionQuery)
        self.assertEqual(call["query"].fusion, Fusion.RRF)

    def test_filter_is_passed_to_both_prefetch_legs(self):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qdrant = _FakeQdrant([])
        program_filter = Filter(must=[FieldCondition(key="program_id", match=MatchValue(value="tde-9-tymm"))])
        rag_service._retrieve_hits(qdrant, [1.0, 0.0], {}, 5, program_filter)
        prefetch = qdrant.calls[0]["prefetch"]
        self.assertTrue(all(leg.filter == program_filter for leg in prefetch))

    def test_no_hits_returns_empty_list_without_touching_mmr(self):
        qdrant = _FakeQdrant([])
        self.assertEqual(rag_service._retrieve_hits(qdrant, [1.0, 0.0], {}, 5, None), [])

    def test_unwraps_named_dense_vector_then_applies_drop_weak_hits_and_mmr(self):
        # named-vector koleksiyonda Qdrant `.vector`ı {"dense":..,"sparse":..}
        # sözlüğü olarak döner (yerel modda elle doğrulandı) - _retrieve_hits
        # bunu MMR'ye vermeden önce düz dense listesine çevirmeli. top +
        # near_duplicate + diverse (bkz. MmrSelectTests) - MMR near_duplicate
        # yerine diverse'i seçmeli; zayıf kuyruk (göreli eşiğin altı) elenmeli.
        def _named_hit(score, dense_vec):
            return SimpleNamespace(
                score=score,
                vector={"dense": dense_vec, "sparse": SimpleNamespace()},
                payload={"marker": score},
            )

        top = _named_hit(0.95, [1.0, 0.0])
        near_duplicate = _named_hit(0.90, [0.99, 0.02])
        diverse = _named_hit(0.70, [0.0, 1.0])
        weak = _named_hit(0.10, [0.5, 0.5])
        qdrant = _FakeQdrant([top, near_duplicate, diverse, weak])

        selected = rag_service._retrieve_hits(qdrant, [1.0, 0.0], {}, 2, None)

        selected_markers = {hit.payload["marker"] for hit in selected}
        self.assertEqual(selected_markers, {0.95, 0.70})
        for hit in selected:
            # Sarmalanmış isabet - .vector artık DÜZ liste, sözlük değil.
            self.assertIsInstance(hit.vector, list)


if __name__ == "__main__":
    unittest.main()
