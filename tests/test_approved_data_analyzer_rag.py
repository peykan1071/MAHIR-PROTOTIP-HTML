"""Tests for RAG-sourced conceptual context attached to weak outcomes."""

import unittest
from unittest.mock import patch

from backend.app.approved_data_analyzer import (
    _build_rag_question,
    _build_rag_retrieval_query,
    _normalize_theme_for_rag,
    _strip_recommendation_sentences,
    analyze_approved_data,
)

_FAKE_REMOTE_URL = "https://fake.example/web_query"


def _weak_tde_payload():
    return {
        "exam": {"courseName": "Türk Dili ve Edebiyatı", "grade": "9", "componentType": "written"},
        "questions": [
            {
                "number": 1,
                "maxScore": 100,
                "outcomeCode": "TDE1.2",
                "outcomeTheme": "1. Tema: Sözün İnceliği",
                "outcomeSkill": "Dinleme/İzleme",
                "outcomeDescription": "“Sözün İnceliği” temasında ele alınan metinlerde anlam oluşturabilme",
                "parentOutcomeDescription": (
                    "“Sözün İnceliği” temasında ele alınan metinlerde anlam oluşturabilme"
                ),
            }
        ],
        "students": [{"studentNo": "1", "scores": [30]}],
    }


class RagContextAttachmentTests(unittest.TestCase):
    def test_ragcontext_field_always_present_even_without_remote_url(self):
        # MAHIR_RAG_REMOTE_URL artık koda gömülü bir varsayılana sahip (bkz.
        # approved_data_analyzer.py) - "yapılandırılmamış" durumu burada
        # açıkça boş string'e çekilerek test ediliyor, gerçek ağ çağrısı yapılmaz.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_unregistered_course_never_calls_rag(self):
        payload = {
            "exam": {"courseName": "Fen Bilimleri", "componentType": "written"},
            "questions": [{"number": 1, "maxScore": 100}],
            "students": [{"studentNo": "1", "scores": [10]}],
        }
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_strong_outcome_is_not_queried(self):
        payload = _weak_tde_payload()
        payload["students"][0]["scores"] = [90]  # successRate 0.90 >= eşik (0.70)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_weak_registered_outcome_attaches_answer(self):
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Bu kazanım dinleme becerisini kapsar.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_called_once()
        called_question, called_program_id, called_url = mock_query.call_args[0]
        called_kwargs = mock_query.call_args[1]
        self.assertIn("Sözün İnceliği", called_question)
        self.assertIn("TDE1.2", called_question)
        self.assertEqual(called_program_id, "tde-9-tymm")
        self.assertEqual(called_url, _FAKE_REMOTE_URL)
        self.assertEqual(called_kwargs["grade"], "9")
        self.assertEqual(called_kwargs["theme"], "SÖZÜN İNCELİĞİ")
        self.assertEqual(result["outcomes"][0]["ragContext"], "Bu kazanım dinleme becerisini kapsar.")

    def test_outcome_description_reaches_both_question_and_retrieval_query(self):
        # Kazanım metni müfredat PDF'iyle aynı dilde yazıldığı için hem getirimin
        # hem de bilişsel düzey teşhisinin asıl dayanağı - çıktı bazında toplama
        # sırasında düşürülürse RAG elinde yalnızca çıplak bir kod kalıyor.
        canned = (True, "Yanıt üretildi.", {"answer": "teşhis", "sources": [{"documentName": "x"}]})
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned) as mock_query:
                analyze_approved_data(_weak_tde_payload())
        called_question = mock_query.call_args[0][0]
        retrieval_query = mock_query.call_args[1]["retrieval_query"]
        self.assertIn("anlam oluşturabilme", called_question)
        self.assertIn("anlam oluşturabilme", retrieval_query)

    def test_retrieval_query_carries_no_success_rate_or_imperative(self):
        # Getirim sorgusu üretim talimatından ayrı: başarı oranının ve "teşhis et"
        # emrinin müfredat metninde karşılığı yok, gömme vektörünü uzaklaştırıyor.
        outcome = {
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "outcomeCode": "TDE1.2",
            "outcomeSkill": "Dinleme/İzleme",
            "outcomeDescription": "metinlerde anlam oluşturabilme",
            "parentOutcomeDescription": "metinlerde anlam oluşturabilme",
            "successRate": 0.3,
        }
        retrieval_query = _build_rag_retrieval_query(outcome)
        self.assertNotIn("%", retrieval_query)
        self.assertNotIn("teşhis", retrieval_query)
        self.assertIn("TDE1.2", retrieval_query)
        # Süreç bileşeni seçilmediğinde script.js üst kazanım metnini kazanımın
        # kendisiyle dolduruyor - aynı cümle iki kez gönderilmemeli.
        self.assertEqual(retrieval_query.count("metinlerde anlam oluşturabilme"), 1)

    def test_no_answer_in_document_leaves_ragcontext_empty(self):
        canned = (True, "Yanıt üretildi.", {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []})
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_answer_prefixed_with_no_answer_phrase_is_stripped_not_discarded(self):
        # Gerçek dizine karşı doğrulandı: model doğru bağlamla beslendiğinde bile
        # cevabı neredeyse her zaman "Bu bilgi belgede bulunmuyor." ile başlatıp
        # ardından gerçek bir teşhisle devam ediyor - kaynaklar dolu geldiği
        # sürece bu, gerçek bir "bulunamadı" değil, atılmaması gereken geçerli
        # bir cevap.
        canned = (
            True,
            "Yanıt üretildi.",
            {
                "answer": "Bu bilgi belgede bulunmuyor.\n\nTDE1.2 dinleme becerisini kapsar.",
                "sources": [{"documentName": "x"}],
            },
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "TDE1.2 dinleme becerisini kapsar.")

    def test_answer_only_the_no_answer_phrase_with_sources_still_leaves_ragcontext_empty(self):
        # Kırpmadan sonra hiçbir şey kalmıyorsa (model gerçekten hiçbir şey
        # bulamadıysa, kaynaklar dolu gelse bile) yine boş bırakılmalı.
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Bu bilgi belgede bulunmuyor.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_unresolved_theme_skips_rag_call_entirely(self):
        # Tema kataloğa göre çözülemiyorsa grade-only bir aramaya düşülmemeli -
        # bu, 9. sınıfın 4 farklı temasından herhangi birinin içeriğini
        # getirebilir ve yanlış temadan "kaynaklı" görünen bir teşhis üretebilir.
        payload = _weak_tde_payload()
        payload["questions"][0]["outcomeTheme"] = ""
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context") as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_rag_failure_leaves_ragcontext_empty_and_does_not_raise(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch(
                "backend.app.rag_client.query_rag_context",
                return_value=(False, "Uzak RAG sunucusuna ulaşılamadı.", None),
            ):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_rag_exception_leaves_ragcontext_empty_and_does_not_raise(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", side_effect=RuntimeError("boom")):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")


class RecommendationStrippingTests(unittest.TestCase):
    # DEVELOPMENT_CHARTER.md: MAHİR yöntem/telafi programı önermez. Canlı
    # ölçümde 8 yanıtın 2'si öneri cümlesiyle bitti - prompt tek başına yetmiyor.
    def test_trailing_recommendation_sentence_is_dropped(self):
        answer, dropped = _strip_recommendation_sentences(
            "Kazanımın bilişsel düzeyi Anlama. Eksikliğin şiddeti: Kritik. "
            "Bu nedenle okuma stratejileri uygulama programları önerilir."
        )
        self.assertEqual(dropped, 1)
        self.assertNotIn("önerilir", answer)
        self.assertIn("Eksikliğin şiddeti: Kritik.", answer)

    def test_necessity_phrasing_is_dropped(self):
        answer, dropped = _strip_recommendation_sentences(
            "Öğrenme kaybı vardır. Daha kapsamlı bir yaklaşımla eğitim verilmelidir."
        )
        self.assertEqual(dropped, 1)
        self.assertEqual(answer, "Öğrenme kaybı vardır.")

    def test_gereklidir_is_dropped_but_gerekli_olan_is_kept(self):
        # Canlı ölçümde "... ek destek ve öğretim gereklidir." hem prompt'tan
        # hem de ilk desenden kaçtı; "gerekli olan" ise teşhis dilinde meşru.
        answer, dropped = _strip_recommendation_sentences(
            "Öğrencilere ek destek ve öğretim gereklidir. "
            "Kazanım için gerekli olan bilişsel yeterlilik kazandırılamamıştır."
        )
        self.assertEqual(dropped, 1)
        self.assertEqual(answer, "Kazanım için gerekli olan bilişsel yeterlilik kazandırılamamıştır.")

    def test_diagnostic_gerektirir_is_not_dropped(self):
        # "gerektirir" teşhis dilinde meşru - "gerekir"le karıştırılmamalı.
        answer, dropped = _strip_recommendation_sentences(
            "Bu kazanım üst düzey analiz becerisi gerektirir."
        )
        self.assertEqual(dropped, 0)
        self.assertEqual(answer, "Bu kazanım üst düzey analiz becerisi gerektirir.")

    def test_all_recommendation_answer_is_discarded_and_leaves_ragcontext_empty(self):
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Ek okuma çalışmaları yapılmalıdır.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.rag_client.query_rag_context", return_value=canned):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")


class RagQuestionSeverityTests(unittest.TestCase):
    # Şiddet etiketi eşiğe dayalı belirlenimci bir karar; modele bırakıldığında
    # %55'lik vakaların yarısına "Kritik" dediği canlı ölçümle görüldü.
    def _question_for(self, success_rate):
        return _build_rag_question({
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "outcomeCode": "TDE1.2",
            "outcomeSkill": "Okuma",
            "outcomeDescription": "metinlerde anlam oluşturabilme",
            "successRate": success_rate,
        })

    def test_below_fifty_percent_is_critical(self):
        self.assertIn("şiddet etiketi: Kritik", self._question_for(0.35))

    def test_fifty_to_sixtynine_percent_is_moderate(self):
        self.assertIn("şiddet etiketi: Orta", self._question_for(0.55))

    def test_exactly_fifty_percent_is_moderate(self):
        # Sınır değer, mahir-report-export-common.js'teki "< 0.50 => Öncelikli"
        # kuralıyla aynı yönde kırılmalı.
        self.assertIn("şiddet etiketi: Orta", self._question_for(0.50))

    def test_severity_label_is_absent_from_retrieval_query(self):
        retrieval_query = _build_rag_retrieval_query({
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "outcomeCode": "TDE1.2",
            "outcomeSkill": "Okuma",
            "outcomeDescription": "metinlerde anlam oluşturabilme",
            "successRate": 0.35,
        })
        self.assertNotIn("şiddet", retrieval_query)


class NormalizeThemeForRagTests(unittest.TestCase):
    def test_strips_tema_prefix_and_uppercases(self):
        self.assertEqual(_normalize_theme_for_rag("1. Tema: Sözün İnceliği"), "SÖZÜN İNCELİĞİ")

    def test_turkish_dotted_and_dotless_i_both_uppercase_correctly(self):
        # Standart Unicode .upper() Türkçe 'i'/'ı' ayrımını kaybediyor (ikisi de
        # düz "I"ya dönüşür) - rag_service.py'nin PDF'ten çıkardığı tema
        # etiketleriyle eşleşmesi için 'i' -> 'İ', 'ı' -> 'I' olmalı.
        self.assertEqual(_normalize_theme_for_rag("Dilin Zenginliği"), "DİLİN ZENGİNLİĞİ")
        self.assertEqual(_normalize_theme_for_rag("Anlamın Yapı Taşları"), "ANLAMIN YAPI TAŞLARI")


if __name__ == "__main__":
    unittest.main()
