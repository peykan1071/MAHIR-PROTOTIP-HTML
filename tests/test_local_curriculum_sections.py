"""`local/curriculum.py` - tema içi bölüm türleri, kazanım kodları, metin temizliği,
süreç bileşeni bölücüsü ve bağlam ön eki.

Bu yardımcılar chunking stratejisinin saf kısmı: Docling'in ürettiği
`(başlıklar, metin)` sırasını belge yapısına göre etiketler. Fixture'lar
docs/tde2026.pdf'in 1. tema (s.65-71) kuru koşusundan ve s.20 ham metninden
kısaltılarak alındı - canlıda görülen üç arıza (satır içi başlık, sayfa geçişi
devamı, heceleme) burada sabitlenir.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local"))

import curriculum  # noqa: E402 - local/ yukarıda sys.path'e eklendi


class SectionTitleTests(unittest.TestCase):
    def test_inline_and_heading_titles_map_to_kinds(self):
        cases = {
            "PROGRAMLAR ARASI BİLEŞENLER": "programlar_arasi",
            "Okuryazarlık Becerileri": "programlar_arasi",
            "İÇERİK ÇERÇEVESİ “Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:": "icerik_cercevesi",
            "Anahtar Kavramlar açık ve örtük ileti, çağrışım": "anahtar_kavramlar",
            "ÖĞRENME KANITLARI": "ogrenme_kanitlari",
            "(Ölçme ve Değerlendirme)": "ogrenme_kanitlari",
            "ÖĞRENME-ÖĞRETME YAŞANTILARI": "ogrenme_ogretme",
            "ÖĞRENME-ÖĞRETME Y AŞANTILARI": "ogrenme_ogretme",  # pypdf sahte boşluğu
            "Temel Kabuller": "ogrenme_ogretme",
            "Ön Değerlendirme Süreci Öğrencilerin temaya ilişkin": "ogrenme_ogretme",
            "Öğrenme-Öğretme Uygulamaları": "ogrenme_ogretme",
            "Süreç Çerçevesi: Bu tema çerçevesinde": "ogrenme_ogretme",
            "Tema Sonu Değerlendirme": "tema_sonu",
            "Zenginleştirme": "farklilastirma",
            "Destekleme Öğrencilere içeriği daha basit": "farklilastirma",
            "ÖĞRETMEN YANSITMALARI": "ogretmen_yansitmalari",
        }
        for title, kind in cases.items():
            with self.subTest(title=title):
                self.assertEqual(curriculum.section_kind_of_title(title), kind)

    def test_skill_headings_do_not_change_the_section(self):
        # "Okuma"/"Dinleme/İzleme" hem kazanım listesinde hem uygulamalarda geçer.
        for title in ("Okuma", "Dinleme/İzleme", "Konuşma", "Yazma", "Metin Tahlili (Anlama)", "TDE2.2"):
            with self.subTest(title=title):
                self.assertIsNone(curriculum.section_kind_of_title(title))


class ClassifySectionsTests(unittest.TestCase):
    def test_state_persists_until_the_next_title(self):
        pieces = curriculum.classify_sections([
            (["1. TEMA: SÖZÜN İNCELİĞİ"], "Edebiyat dünyasına giriş niteliğindeki bu temada..."),
            (["PROGRAMLAR ARASI BİLEŞENLER"], "Sosyal-Duygusal Öğrenme Becerileri SDB1.1. Kendini Tanıma"),
            (["Okuryazarlık Becerileri"], "OB1. Bilgi Okuryazarlığı"),
            (["Dinleme/İzleme"], "TDE1.1. 'Sözün İnceliği' temasında ... yönetebilme TDE1.2. 'Sözün İnceliği' ... oluşturabilme"),
            (["Okuma"], "TDE2.1. ... okumayı yönetebilme\nTDE2.2. ... anlam oluşturabilme"),
        ])
        self.assertEqual([p.section_kind for p in pieces],
                         ["tema_giris", "programlar_arasi", "programlar_arasi", "ogrenme_ciktilari", "ogrenme_ciktilari"])
        self.assertEqual(pieces[3].outcome_codes, ["TDE1.1", "TDE1.2"])
        self.assertEqual(pieces[4].outcome_codes, ["TDE2.1", "TDE2.2"])

    def test_inline_title_in_the_middle_splits_the_chunk(self):
        # Canlı bulgu: "Yazma" kazanım listesi + İÇERİK ÇERÇEVESİ tek Docling parçasıydı.
        pieces = curriculum.classify_sections([
            (["Yazma"], "- TDE4.1. Edebî söyleyişin ... yönetebilme\n- TDE4.4. ... değerlendirebilme\n"
                        "İÇERİK ÇERÇEVESİ “Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:\n• Okuma\n"
                        "Anahtar Kavramlar açık ve örtük ileti, çağrışım, edebî dil"),
        ], initial_kind="programlar_arasi")
        self.assertEqual([p.section_kind for p in pieces], ["ogrenme_ciktilari", "icerik_cercevesi", "anahtar_kavramlar"])
        self.assertEqual(pieces[0].outcome_codes, ["TDE4.1", "TDE4.4"])
        self.assertEqual(pieces[1].outcome_codes, [])
        self.assertTrue(pieces[2].text.startswith("Anahtar Kavramlar"))
        self.assertEqual(pieces[0].headings, ["Yazma"])
        self.assertEqual(pieces[1].headings, [])

    def test_continuation_chunk_inherits_kind_and_codes_and_ignores_its_heading(self):
        # Canlı bulgu: s.70'ten sarkan TDE3.x metni s.71'de "Destekleme" başlığını almıştı.
        pieces = curriculum.classify_sections([
            (["Öğrenme-Öğretme Uygulamaları"], "Bu temada öğrencilerin paragraf türlerini bildiği kabul edilmektedir."),
            (["TDE3.1, TDE3.2, TDE3.3, TDE3.4"], "Öğrencilere deneme metinlerinden hareketle ... edebiyat ve psi-"),
            (["Destekleme"], "koloji, sanatsal ifade ve etkileşim ... geri bildirim verilir."),
            (["Tema Sonu Değerlendirme"], "Temanın sonunda öğrencilerden öğrenme günlüğü yazmaları istenir.\n"
                                          "Zenginleştirme İlgi duyan öğrencilerden ... istenebilir.\n"
                                          "Destekleme Öğrencilere içeriği daha basit ve görsel ögelerle desteklenmiş"),
        ])
        kinds = [p.section_kind for p in pieces]
        self.assertEqual(kinds, ["ogrenme_ogretme", "ogrenme_ogretme", "ogrenme_ogretme", "tema_sonu", "farklilastirma", "farklilastirma"])
        self.assertEqual(pieces[2].outcome_codes, ["TDE3.1", "TDE3.2", "TDE3.3", "TDE3.4"])
        self.assertTrue(pieces[4].text.startswith("Zenginleştirme"))
        self.assertTrue(pieces[5].text.startswith("Destekleme"))

    def test_outcome_list_is_detected_without_an_explicit_title(self):
        pieces = curriculum.classify_sections([(["Dinleme/İzleme"], "TDE1.1. x yönetebilme\nTDE1.2. y oluşturabilme")],
                                              initial_kind="programlar_arasi")
        self.assertEqual(pieces[0].section_kind, "ogrenme_ciktilari")

    def test_outcome_list_rule_does_not_fire_inside_practices(self):
        # Uygulamalar bölümünde bir cümle içinde kod geçmesi bölümü değiştirmez.
        pieces = curriculum.classify_sections([(["TDE2.1"], "Dikkat çekmek için yakın dönem bir Türk şiiri dinletilir.")],
                                              initial_kind="ogrenme_ogretme")
        self.assertEqual(pieces[0].section_kind, "ogrenme_ogretme")
        self.assertEqual(pieces[0].outcome_codes, ["TDE2.1"])


class RecoverInlineTitlesTests(unittest.TestCase):
    """Docling run-in etiketleri düşürür; pypdf akışından geri konur."""

    _PYPDF = (
        "TDE4.4. Edebî söyleyişin inceliğini yansıttığı yazısında yazma sürecini değerlendirebilme\n"
        "İÇERİK ÇERÇEVESİ “Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:\n"
        "• Okuma\n"
        "Anahtar Kavramlar açık ve örtük ileti, çağrışım, edebî dil, gerçeklik\n"
        "Ön Değerlendirme Süreci Öğrencilerin temaya ilişkin temel kabullerini belirlemek için kısa cevaplı so-\n"
        "rular, kavram haritası gibi yöntemler uygulanabilir.\n"
        "Destekleme Öğrencilere içeriği daha basit ve görsel ögelerle desteklenmiş metinler verilir.\n"
    )

    def setUp(self):
        self.reference = curriculum.squash(self._PYPDF)

    def test_dropped_labels_are_reinserted_as_their_own_line(self):
        docling = (
            "- TDE4.4. Edebî söyleyişin inceliğini yansıttığı yazısında yazma sürecini değerlendirebilme\n"
            "“Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:\n"
            "açık ve örtük ileti, çağrışım, edebî dil, gerçeklik\n"
        )
        text, cursor = curriculum.recover_inline_titles(docling, self.reference)
        self.assertEqual(
            text.split("\n")[:5],
            [
                "- TDE4.4. Edebî söyleyişin inceliğini yansıttığı yazısında yazma sürecini değerlendirebilme",
                "İÇERİK ÇERÇEVESİ",
                "“Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:",
                "Anahtar Kavramlar",
                "açık ve örtük ileti, çağrışım, edebî dil, gerçeklik",
            ],
        )
        self.assertGreater(cursor, 0)

    def test_run_in_label_with_hyphenated_line_is_recovered(self):
        # Docling "kısa cevaplı so - rular" yazar; hizalama tire/boşluk bağımsız.
        docling = "Öğrencilerin temaya ilişkin temel kabullerini belirlemek için kısa cevaplı so - rular, kavram haritası gibi yöntemler uygulanabilir."
        text, _ = curriculum.recover_inline_titles(docling, self.reference)
        self.assertTrue(text.startswith("Ön Değerlendirme Süreci\nÖğrencilerin temaya"))

    def test_label_already_present_is_not_duplicated(self):
        docling = "Destekleme Öğrencilere içeriği daha basit ve görsel ögelerle desteklenmiş metinler verilir."
        text, _ = curriculum.recover_inline_titles(docling, self.reference)
        self.assertEqual(text, docling)

    def test_unmatched_line_is_left_alone(self):
        docling = "Bu satır referans metinde hiç yok ve olduğu gibi kalmalı."
        text, cursor = curriculum.recover_inline_titles(docling, self.reference, cursor=5)
        self.assertEqual((text, cursor), (docling, 5))

    def test_recovered_titles_feed_the_classifier(self):
        docling = (
            "- TDE4.4. Edebî söyleyişin inceliğini yansıttığı yazısında yazma sürecini değerlendirebilme\n"
            "“Sözün İnceliği” temasının içerik çerçevesi şu şekildedir:\n"
            "açık ve örtük ileti, çağrışım, edebî dil, gerçeklik\n"
        )
        text, _ = curriculum.recover_inline_titles(docling, self.reference)
        pieces = curriculum.classify_sections([(["Yazma"], text)], initial_kind="programlar_arasi")
        self.assertEqual([p.section_kind for p in pieces], ["ogrenme_ciktilari", "icerik_cercevesi", "anahtar_kavramlar"])


class OutcomeCodeTests(unittest.TestCase):
    def test_component_codes_collapse_to_the_parent_outcome(self):
        self.assertEqual(curriculum.extract_outcome_codes(["c) TDE1.2.3. Çıkarım yapar."], "a) TDE1.2.1. x"), ["TDE1.2"])

    def test_codes_come_from_headings_and_text_sorted_numerically(self):
        self.assertEqual(
            curriculum.extract_outcome_codes(["TDE4.1, TDE4.2, TDE4.3, TDE4.4"], "TDE1.2 ve TDE1.10 ile TDE4.1"),
            ["TDE1.2", "TDE1.10", "TDE4.1", "TDE4.2", "TDE4.3", "TDE4.4"],
        )

    def test_no_codes_gives_empty_list(self):
        self.assertEqual(curriculum.extract_outcome_codes(None, "kod yok"), [])


class TextCleanupTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = curriculum.build_vocabulary(
            "yazma süreci düzenledikleri yapı taşları hayatın dünyası yaşantıları sorular"
        )

    def test_hyphenation_is_joined_only_when_the_word_is_known(self):
        text = "yazısında sü - reci yönetebilme; düzen-\nledikleri metinleri; kısa cevaplı so-\nrular"
        self.assertEqual(
            curriculum.dehyphenate(text, self.vocabulary),
            "yazısında süreci yönetebilme; düzenledikleri metinleri; kısa cevaplı sorular",
        )

    def test_real_dashes_survive(self):
        for text in ("sözlü - yazılı anlatım", "TDE3.1 - TDE3.2 arası", "öz - değerlendirme"):
            with self.subTest(text=text):
                self.assertEqual(curriculum.dehyphenate(text, self.vocabulary), text)

    def test_spurious_pdf_spaces_are_closed_with_vocabulary_approval(self):
        self.assertEqual(curriculum.fix_spurious_spaces("ANLAMIN Y API TAŞLARI", self.vocabulary), "ANLAMIN YAPI TAŞLARI")
        self.assertEqual(curriculum.fix_spurious_spaces("HAY ATIN AYNASI", self.vocabulary), "HAYATIN AYNASI")
        self.assertEqual(curriculum.fix_spurious_spaces("OKURUN DÜNY ASI", self.vocabulary), "OKURUN DÜNYASI")
        self.assertEqual(curriculum.fix_spurious_spaces("Y AŞANTILARI", self.vocabulary), "YAŞANTILARI")

    def test_ordinary_two_words_are_not_glued(self):
        self.assertEqual(curriculum.fix_spurious_spaces("VE ANLAM ARAYIŞI", self.vocabulary), "VE ANLAM ARAYIŞI")


_PAGE_20 = """20
TÜRK DİLİ VE EDEBİYATI DERSİ ÖĞRETİM PROGRAMI
METİN TAHLİLİ
DİNLEME/İZLEME
TDE1.1. Dinlemeyi/İzlemeyi Yönetebilme
a) TDE1.1.1. Seçim yapar.
• Metni dinlemeye/izlemeye başlamadan önce dinleme/izleme amacını belirler.
b)  TDE1.1.2. İlişkiyi sürdürür.
• Dinleme/izleme kurallarını uygulayarak dinlemeyi/izlemeyi sürdürür.
TDE1.2. Anlam Oluşturabilme
a) TDE1.2.1. Ön bilgilerle bağlantı kurar.
• Dinleme/izleme metnindeki bilgiler ile ön bilgileri arasında bağlantı kurar.
b) TDE1.2.2. Tahmin eder.
• Dinlediği/izlediği metindeki söz varlığının anlamını bağlamdan hareketle belirler.
c) TDE1.2.3. Çıkarım yapar.
• Dinlediği/izlediği metinde açıkça sunulan bilgileri belirler.
"""
_PAGE_21 = """21
TÜRK DİLİ VE EDEBİYATI DERSİ ÖĞRETİM PROGRAMI
• Metindeki örtük iletileri çıkarır.
ç) TDE1.2.4. Karşılaştırır.
• Metindeki bilgileri ön bilgileriyle karşılaştı-
rır.
OKUMA
TDE2.1. Okumayı Yönetebilme
a) TDE2.1.1. Seçim yapar.
• Okuma amacını belirler.
"""


class ProcessComponentSplitTests(unittest.TestCase):
    def setUp(self):
        self.vocabulary = curriculum.build_vocabulary(_PAGE_20 + _PAGE_21 + " karşılaştırır")

    def test_one_block_per_outcome_with_page_tracking(self):
        blocks = curriculum.split_process_components([(20, _PAGE_20), (21, _PAGE_21)], self.vocabulary)
        self.assertEqual([b.code for b in blocks], ["TDE1.1", "TDE1.2", "TDE2.1"])
        self.assertEqual(blocks[0].pages, [20])
        self.assertEqual(blocks[1].pages, [20, 21], "TDE1.2 iki sayfaya yayılıyor")
        self.assertEqual(blocks[2].pages, [21])
        self.assertTrue(blocks[1].text.startswith("TDE1.2. Anlam Oluşturabilme\na) TDE1.2.1."))
        self.assertIn("ç) TDE1.2.4. Karşılaştırır.", blocks[1].text)
        self.assertEqual(blocks[1].title, "TDE1.2. Anlam Oluşturabilme")

    def test_running_headers_and_skill_banners_are_dropped(self):
        blocks = curriculum.split_process_components([(20, _PAGE_20), (21, _PAGE_21)], self.vocabulary)
        joined = "\n".join(b.text for b in blocks)
        for noise in ("TÜRK DİLİ VE EDEBİYATI DERSİ ÖĞRETİM PROGRAMI", "METİN TAHLİLİ", "DİNLEME/İZLEME", "\nOKUMA\n", "\n20\n"):
            self.assertNotIn(noise, joined)

    def test_hyphenated_line_break_inside_a_block_is_joined(self):
        blocks = curriculum.split_process_components([(20, _PAGE_20), (21, _PAGE_21)], self.vocabulary)
        self.assertIn("ön bilgileriyle karşılaştırır.", blocks[1].text)

    def test_oversized_block_splits_at_component_boundaries_and_repeats_the_title(self):
        blocks = curriculum.split_process_components([(20, _PAGE_20), (21, _PAGE_21)], self.vocabulary, max_chars=150)
        tde12 = [b for b in blocks if b.code == "TDE1.2"]
        self.assertGreater(len(tde12), 1)
        for block in tde12:
            self.assertTrue(block.text.startswith("TDE1.2. Anlam Oluşturabilme\n"))
            self.assertRegex(block.text.split("\n")[1], r"^[a-zçğ]\) TDE1\.2\.\d")


class ContextPrefixTests(unittest.TestCase):
    def test_prefix_carries_grade_theme_section_codes_and_skill(self):
        prefix = curriculum.context_prefix("9", 1, "SÖZÜN İNCELİĞİ", "ogrenme_ogretme", ["TDE2.2"], "okuma", ["TDE2.2", "Süreç Çerçevesi"])
        self.assertEqual(prefix, "9. Sınıf | 1. Tema: SÖZÜN İNCELİĞİ | Öğrenme-Öğretme Yaşantıları | TDE2.2 | Okuma | Süreç Çerçevesi")

    def test_component_prefix_has_no_grade_or_theme(self):
        prefix = curriculum.context_prefix(None, None, None, "surec_bilesenleri", ["TDE1.2"], "dinlemeizleme", [])
        self.assertEqual(prefix, "Öğrenme Çıktıları ve Süreç Bileşenleri | TDE1.2 | Dinleme/İzleme")

    def test_headings_already_in_the_prefix_are_not_repeated(self):
        prefix = curriculum.context_prefix("9", 2, "ANLAM ARAYIŞI", "ogrenme_ciktilari", ["TDE2.1"], "okuma", ["Okuma"])
        self.assertEqual(prefix.count("Okuma"), 1)


class IndexPlanTests(unittest.TestCase):
    def test_tde9_plan_indexes_components_before_theme_pages(self):
        plan = curriculum.resolve_index_plan("tde-9-tymm")
        self.assertEqual([(r.start_page, r.end_page, r.kind) for r in plan], [(20, 27, "surec_bilesenleri"), (65, 96, None)])

    def test_unknown_program_has_no_plan(self):
        self.assertIsNone(curriculum.resolve_index_plan("baska-program"))


if __name__ == "__main__":
    unittest.main()
