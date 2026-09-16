"""Tests for the pure indexing/retrieval helpers of the local RAG stack.

`local/curriculum.py` (document titles, skill/theme keys) and
`local/rag_common.py` (point ids, relative score floor) import only the
standard library at module level - every heavy dependency (docling, qdrant,
sentence-transformers) is deferred into function bodies - so these helpers are
testable without the ML environment. `ingest_pdf` and `RAGService` are NOT
tested here; they need the running stack.
"""

import json
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local"))

import curriculum  # noqa: E402 - local/ yukarıda sys.path'e eklendi
import rag_common  # noqa: E402

# Eski hattın ölçülmüş göreli eşiği (0,60) - testler o ölçümlerle yazıldı.
_MEASURED_FLOOR = 0.60


def _hits(*scores):
    """Qdrant azalan skor sırasıyla döndürür; testler de öyle beslemeli."""

    return [rag_common.Hit(point_id=str(index), payload={}, retrieval_score=score) for index, score in enumerate(scores)]


class DocumentTitleTests(unittest.TestCase):
    """Belgenin resmî adı - öğretmenin raporunda kaynak olarak görünen değer."""

    def test_registered_program_resolves_to_its_official_title(self):
        title = curriculum.resolve_document_title("tde-9-tymm")
        self.assertIn("Türk Dili ve Edebiyatı Dersi Öğretim Programı", title)
        self.assertIn("2024", title)

    def test_title_is_not_a_file_name(self):
        # Resmî bir rapor dayanağını "tdeogr.pdf" diye gösteremez.
        for program_id, title in curriculum.DOCUMENT_TITLES.items():
            with self.subTest(program=program_id):
                self.assertNotIn(".pdf", title.lower())

    def test_override_wins_over_the_registry(self):
        self.assertEqual(
            curriculum.resolve_document_title("tde-9-tymm", "Başka Belge (2025)"),
            "Başka Belge (2025)",
        )

    def test_unknown_program_raises_instead_of_falling_back(self):
        # Sessiz geri düşüş olsaydı yanlış adlı parçalar dizine girer ve o ana
        # kadarki her rapor kaynağını yanlış göstermiş olurdu. Hata,
        # indekslemeden ÖNCE verilmeli.
        with self.assertRaises(ValueError) as caught:
            curriculum.resolve_document_title("bilinmeyen-program")
        self.assertIn("DOCUMENT_TITLES", str(caught.exception))

    def test_blank_override_falls_back_to_the_registry(self):
        self.assertEqual(
            curriculum.resolve_document_title("tde-9-tymm", "   "),
            curriculum.DOCUMENT_TITLES["tde-9-tymm"],
        )

    def test_renaming_a_document_changes_its_point_ids(self):
        # Bu, `--replace` bayrağının VAROLUŞ SEBEBİ: ad değişince parçalar yeni
        # kimlik alır, eskiler üzerine YAZILMAZ ve dizinde aynı içerik iki adla
        # kalır. Getirim bunu hatasızca yutar, yalnız sonuç bozulur.
        old = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 3, "metin")
        new = rag_common.deterministic_point_id(
            "tde-9-tymm", curriculum.DOCUMENT_TITLES["tde-9-tymm"], 3, "metin"
        )
        self.assertNotEqual(old, new)


class DeterministicPointIdTests(unittest.TestCase):
    def test_same_input_gives_same_id(self):
        first = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        second = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        self.assertEqual(first, second)

    def test_id_is_a_valid_uuid_string(self):
        point_id = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 0, "metin")
        self.assertEqual(str(uuid.UUID(point_id)), point_id)  # Qdrant ID olarak kabul etmeli.

    def test_scheme_is_frozen(self):
        # Altın değer: ad alanı veya anahtar biçimi değişirse aynı içerik farklı
        # ID üretir, yani mevcut dizindeki noktalar bir daha ASLA üzerine
        # yazılamaz (sessizce ikizlenir). Bu test o değişikliği gürültülü yapar.
        self.assertEqual(
            rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 0, "Sözün İnceliği"),
            "74dd1935-7f09-5563-831b-e57bfe01d01e",
        )

    def test_every_key_field_changes_the_id(self):
        base = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "metin")
        variants = {
            "program_id": rag_common.deterministic_point_id("tde-10-tymm", "tdeogr.pdf", 7, "metin"),
            "document_name": rag_common.deterministic_point_id("tde-9-tymm", "baska.pdf", 7, "metin"),
            "chunk_index": rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 8, "metin"),
            "text": rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 7, "baska metin"),
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
        first = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 3, "aynı başlık satırı")
        second = rag_common.deterministic_point_id("tde-9-tymm", "tdeogr.pdf", 9, "aynı başlık satırı")
        self.assertNotEqual(first, second)


class SkillMatchKeyTests(unittest.TestCase):
    """Belgedeki başlık ile katalogdaki `skill` alanı aynı anahtara düşmeli."""

    def test_catalog_skill_and_document_heading_agree(self):
        # Katalog "Dinleme/İzleme" yazıyor, belge başlığı da öyle - ama biri
        # eğik çizgi/boşlukta farklılaşırsa filtre sessizce hiçbir şey elemez.
        self.assertEqual(
            curriculum.skill_match_key("Dinleme/İzleme"),
            curriculum.skill_match_key("Dinleme / İzleme"),
        )

    def test_case_differences_collapse(self):
        self.assertEqual(
            curriculum.skill_match_key("OKUMA"), curriculum.skill_match_key("Okuma")
        )

    def test_turkish_capital_i_does_not_split(self):
        # casefold() tek başına "İ"yi i + U+0307 yapar; anahtar bozulurdu.
        self.assertNotIn("̇", curriculum.skill_match_key("İZLEME"))
        self.assertEqual(
            curriculum.skill_match_key("İZLEME"), curriculum.skill_match_key("izleme")
        )

    def test_every_known_skill_has_a_distinct_key(self):
        keys = [curriculum.skill_match_key(name) for name in curriculum.SKILL_HEADINGS]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(set(keys), set(curriculum.KNOWN_SKILL_KEYS))

    def test_unrelated_text_is_not_a_skill(self):
        self.assertNotIn(
            curriculum.skill_match_key("Öğrenme-Öğretme Uygulamaları"),
            curriculum.KNOWN_SKILL_KEYS,
        )


class DetectSkillKeyTests(unittest.TestCase):
    def test_skill_heading_is_found_anywhere_in_the_chain(self):
        # Docling başlık zinciri hiyerarşik gelir; beceri en sonda olabilir.
        self.assertEqual(
            curriculum.detect_skill_key(["3. TEMA:  ANLAMIN YAPI TAŞLARI", "Okuma"]), "okuma"
        )

    def test_sibling_skills_get_different_keys(self):
        # Filtrenin tüm varlık sebebi: bu iki liste metinsel olarak neredeyse
        # aynı, ayrımı yalnız başlık taşıyor.
        self.assertNotEqual(
            curriculum.detect_skill_key(["Okuma"]),
            curriculum.detect_skill_key(["Dinleme/İzleme"]),
        )

    def test_non_skill_section_returns_none(self):
        # Tema tanıtımı ve uygulama bölümleri HER beceri için geçerli kanıt;
        # None olmaları onları filtreden muaf tutuyor.
        self.assertIsNone(curriculum.detect_skill_key(["3. TEMA:  SÖZÜN İNCELİĞİ"]))
        self.assertIsNone(curriculum.detect_skill_key(["Öğrenme-Öğretme Uygulamaları"]))

    def test_missing_or_empty_headings_are_safe(self):
        self.assertIsNone(curriculum.detect_skill_key(None))
        self.assertIsNone(curriculum.detect_skill_key([]))


    def test_subsection_heading_without_the_skill_name_still_resolves(self):
        # Canlı ölçümde tam olarak bu sızdı: alt süreç bileşeni başlıkları
        # ("c) TDE1.2.3. Çıkarım yapar.") Docling'in başlık zincirinde üst
        # beceri başlığını ("Dinleme/İzleme") TAŞIMIYOR - yalnız kendi alt
        # başlığını taşıyor. Yalnız üst-başlık eşleşmesi bunu hiç yakalamazdı.
        self.assertEqual(
            curriculum.detect_skill_key(["c) TDE1.2.3. Çıkarım yapar."]), "dinlemeizleme"
        )
        self.assertEqual(
            curriculum.detect_skill_key(["a) TDE1.2.1. Ön bilgilerle bağlantı kurar."]),
            "dinlemeizleme",
        )
        self.assertEqual(
            curriculum.detect_skill_key(["ç) TDE4.4.2. Bir şey yapar."]), "yazma"
        )

    def test_code_prefix_is_read_from_body_text_too(self):
        # Bir bölümün üst-düzey özet parçası ("Okuma" başlıklı) gövdesinde
        # "TDE2.1. ... TDE2.2. ..." yazıyor olsa bile başlık zaten "Okuma" -
        # burada asıl test, başlık YOKKEN yalnız gövdeden çözülebilmesi.
        self.assertEqual(curriculum.detect_skill_key(None, "TDE4.1. Yapısını incelikle ördüğü"), "yazma")
        self.assertEqual(curriculum.detect_skill_key([], "TDE3.2. Muhatabını ikna eder."), "konuşma")

    def test_unknown_code_prefix_stays_none(self):
        # TDE9 yalnız 1-4 arası beceri kodu kullanıyor; beşinci bir kod
        # (belge yapısı hakkında yanlış varsayımda bulunmak yerine) None
        # kalmalı, rastgele bir beceriye atanmamalı.
        self.assertIsNone(curriculum.detect_skill_key(["x) TDE9.9.9. Bilinmeyen."]))

    def test_code_prefix_digit_mapping_matches_the_catalog(self):
        # `_CODE_PREFIX_TO_SKILL`in elle bakımlanan bir kopya OLMADIĞINI,
        # kataloğun kendisiyle aynı gerçeği söylediğini doğrular - bkz.
        # `SkillRegistryContractTests` (aynı kaynağın diğer yarısı).
        expected = {"1": "dinlemeizleme", "2": "okuma", "3": "konuşma", "4": "yazma"}
        for digit, skill_key in expected.items():
            with self.subTest(digit=digit):
                self.assertEqual(
                    curriculum.detect_skill_key([f"x) TDE{digit}.1.1. Örnek."]), skill_key
                )


class SkillRegistryContractTests(unittest.TestCase):
    """`_SKILL_HEADINGS` ile kazanım kataloğu arasındaki sessiz kayma koruması.

    Filtre, katalogdaki `skill` değerinin sunucudaki anahtarla eşleşmesine
    dayanıyor. MEB adlandırmayı değiştirir ya da katalog yeni bir beceriyle
    genişlerse eşleşme kaybolur ve filtre HİÇBİR ŞEY elemez - hatasız,
    sessizce. Tek fark edilme yolu bu test.
    """

    @staticmethod
    def _catalog_skills():
        catalog = Path(__file__).resolve().parent.parent / "shared" / "pilot" / "tde9"
        data = json.loads((catalog / "learning-outcomes-template.json").read_text(encoding="utf-8"))
        return sorted({str(outcome.get("skill") or "") for outcome in data["learning_outcomes"]})

    def test_every_catalog_skill_is_known_to_the_server(self):
        for skill in self._catalog_skills():
            with self.subTest(skill=skill):
                self.assertIn(
                    curriculum.skill_match_key(skill),
                    curriculum.KNOWN_SKILL_KEYS,
                    f"Katalogdaki {skill!r} becerisi curriculum.SKILL_HEADINGS'te yok; "
                    "filtre bu beceride sessizce devre dışı kalır.",
                )

    def test_catalog_actually_carries_the_four_skills(self):
        # Testin kendisinin boşa dönmediğini garanti eder: katalog `skill`
        # alanını kaybederse yukarıdaki döngü sıfır kez çalışıp yeşil kalırdı.
        self.assertEqual(len(self._catalog_skills()), len(curriculum.SKILL_HEADINGS))


class DropWeakHitsTests(unittest.TestCase):
    def test_default_floor_keeps_the_topically_relevant_tail(self):
        # 2026-08-22: 0,78 -> 0,60 -> 0,68 -> 0,60. Ne 0,78 (fazla agresif) ne
        # 0,68 (hâlâ bazı senaryolarda yetersiz) doğru dengeydi - kök sorun bir
        # SAYI ayarıyla çözülemeyen yapısal bir tekrar sorunuydu, gerçek çözüm
        # sunucu tarafındaki yeniden sıralama (önce MMR, yerel hatta reranker).
        # Bu eşiğin işi artık yalnız gerçekten alakasız kuyruğu elemek. 0,60 bu
        # gerçek ölçüm verisinde (Anlam Arayışı/TDE2.1) kuyruğun tamamını
        # tutuyor - hangisinin nihai listeye gireceğine yeniden sıralama karar verir.
        hits = _hits(0.9424, 0.8601, 0.7609, 0.7471, 0.6634, 0.6578, 0.6266, 0.6144)
        kept = rag_common.drop_weak_hits(hits, _MEASURED_FLOOR)
        self.assertEqual(len(kept), 8)

    def test_old_0_78_ratio_still_cuts_at_the_measured_break(self):
        # Tarihi ölçüm (bkz. eski yorum) hâlâ geçerli bir davranış - yalnız
        # artık modül varsayılanı değil, `floor_ratio` ile açıkça istenmesi
        # gerekiyor.
        hits = _hits(0.9424, 0.8601, 0.7609, 0.7471, 0.6634, 0.6578, 0.6266, 0.6144)
        kept = rag_common.drop_weak_hits(hits, floor_ratio=0.78)
        self.assertEqual([hit.retrieval_score for hit in kept], [0.9424, 0.8601, 0.7609, 0.7471])

    def test_keeps_everything_when_the_tail_is_flat(self):
        # Gerçek ölçüm (Sözün İnceliği / TDE2.2): kuyruk düz, kopuş yok.
        # Mutlak bir eşiğin yapamayacağı şey tam olarak bu - oran uyarlanıyor.
        hits = _hits(0.8706, 0.8692, 0.7747, 0.7460, 0.7455, 0.7377, 0.7329, 0.7256)
        self.assertEqual(len(rag_common.drop_weak_hits(hits, _MEASURED_FLOOR)), 8)

    def test_never_returns_empty_when_there_were_hits(self):
        # Boş dönmek raporda boş bir hücre demek - bu fonksiyonun asla
        # üretmemesi gereken sonuç. floor_ratio=1.0 en agresif kırpma.
        hits = _hits(0.90, 0.10, 0.05)
        kept = rag_common.drop_weak_hits(hits, floor_ratio=1.0)
        self.assertEqual([hit.retrieval_score for hit in kept], [0.90])

    def test_empty_input_stays_empty(self):
        self.assertEqual(rag_common.drop_weak_hits([], _MEASURED_FLOOR), [])

    def test_single_hit_is_kept(self):
        hits = _hits(0.61)
        self.assertEqual(len(rag_common.drop_weak_hits(hits, _MEASURED_FLOOR)), 1)

    def test_non_positive_top_score_is_left_alone(self):
        # Kosinüs negatif olabilir; orada `top * floor_ratio` eşiği YÜKSELTİR
        # (negatifin negatifle çarpımı pozitife döner), yani oranla kırpmak
        # anlamını yitirir - liste olduğu gibi geçmeli.
        hits = _hits(-0.10, -0.40, -0.90)
        self.assertEqual(len(rag_common.drop_weak_hits(hits, _MEASURED_FLOOR)), 3)


if __name__ == "__main__":
    unittest.main()
