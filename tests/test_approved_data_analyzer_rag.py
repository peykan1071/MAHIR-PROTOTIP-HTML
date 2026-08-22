"""Tests for RAG-sourced conceptual context attached to weak outcomes."""

import json
import unittest
from typing import ClassVar
from unittest.mock import patch

from backend.app.approved_data_analyzer import (
    _build_rag_question,
    _build_rag_retrieval_query,
    _normalize_theme_for_rag,
    _strip_recommendation_sentences,
    analyze_approved_data,
)
from backend.app.agents.pipeline import (
    _answer_matches_outcome_scope,
    _compose_grounded_pedagogical_answer,
    _term_is_grounded,
)

_FAKE_REMOTE_URL = "https://fake.example/web_query"


def _evidence_json(terms, rationales, key="gapRationale"):
    """2026-08-22 (2. sürüm) yapılandırılmış kanıt şemasını üretir - testler
    her seferinde tam JSON'u elle yazmasın diye. `key`, zayıf çıktılar için
    `"gapRationale"`, güçlü çıktılar için `"strengthRationale"`."""

    evidence = [{"exactTerm": term, key: rationale} for term, rationale in zip(terms, rationales)]
    return json.dumps({"status": "success", "evidence": evidence})


def _llm_reply(*answers):
    """`run_agent_prompts` yerine gecen sahte: kuyruga gelen her prompt'a sirayla
    verilen yaniti, ADIYLA birlikte dondurur.

    Ada gore eslestirme kasitli: yeni tur getirimli (pedagoji) ve getirimsiz
    (olcme anomali) prompt'lari AYNI istekte tasiyor, yani sira eslestirmesi
    kirilgan olurdu.
    """

    def fake(items, remote_url):
        diagnoses = [item for item in items if str(item.get("name", "")).startswith("pedagoji/")]
        results = []
        for item in items:
            if not str(item.get("name", "")).startswith("pedagoji/"):
                results.append({"name": item["name"], "answer": "", "sources": [], "strippedSentences": 0})
                continue
            index = diagnoses.index(item)
            answer, sources = answers[index] if index < len(answers) else ("", [])
            # Kaynak listesi bossa getirim isabet vermemistir; yanit da bos
            # gitmeli - `apply_llm` kaynaga bakarak `kaynak-yok` diyor.
            if not sources:
                answer = ""
            results.append({
                "name": item["name"],
                "answer": answer,
                "sources": sources,
                "strippedSentences": 0,
            })
        return True, "Ajan yanıtları üretildi.", results

    return fake


def _llm_reply_sequence(*per_call_answers):
    """`_llm_reply` gibi ama HER ÇAĞRIDA bir sonraki demeti kullanır - ilk
    deneme/yeniden deneme (retry) senaryolarını test etmek için: ilk çağrı
    `per_call_answers[0]`i, ikinci çağrı (retry) `per_call_answers[1]`i
    kullanır. Demet biterse son öğe tekrar kullanılır."""

    call_count = 0

    def fake(items, remote_url):
        nonlocal call_count
        index = min(call_count, len(per_call_answers) - 1)
        call_count += 1
        answers = per_call_answers[index]
        diagnoses = [item for item in items if str(item.get("name", "")).startswith("pedagoji/")]
        results = []
        for item in items:
            if not str(item.get("name", "")).startswith("pedagoji/"):
                results.append({"name": item["name"], "answer": "", "sources": [], "strippedSentences": 0})
                continue
            idx = diagnoses.index(item)
            answer, sources = answers[idx] if idx < len(answers) else ("", [])
            if not sources:
                answer = ""
            results.append({
                "name": item["name"],
                "answer": answer,
                "sources": sources,
                "strippedSentences": 0,
            })
        return True, "Ajan yanıtları üretildi.", results

    return fake


def _diagnosis_prompts(mock_call):
    """Kuyruktan yalnizca pedagoji prompt'larini suzer."""

    items = mock_call.call_args[0][0]
    return [item for item in items if str(item.get("name", "")).startswith("pedagoji/")]



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
        "students": [{"studentRef": "Ö-001", "scores": [30]}],
    }


def _llm_patch(**kwargs):
    """LLM turunu yamalar - hattın GERÇEKTEN çağırdığı yer burası.

    Bu testler bir zamanlar `rag_client.query_rag_contexts`i yamalıyordu; Faz
    3'te getirim ajan kuyruğuna taşınınca o fonksiyon çağrılmaz oldu ve yamalar
    sessizce etkisizleşti. `assert_not_called` iddiaları boşa döndü, arıza
    testleri ise mock yerine çözülemeyen bir alan adına düşüp DNS hatası
    sayesinde "geçmeye" başladı. Tek yamalama noktası bu yüzden burada.
    """

    return patch("backend.app.agents.llm.run_agent_prompts", **kwargs)


class RagContextAttachmentTests(unittest.TestCase):
    def test_structured_evidence_builds_deterministic_diagnosis(self):
        outcome = {
            "outcomeCode": "TDE2.2",
            "outcomeTheme": "2. Tema: Anlam Arayışı",
            "successRate": 0.20,
        }
        answer = _evidence_json(
            ["ana duygu", "ana düşünce"],
            ["Ana duygu net kurulamıyor.", "Ana düşünce belirlenemiyor."],
        )
        sources = [{"excerpt": "Metinde konu, ana duygu ve ana düşünce bir bütünün parçalarıdır."}]
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn('"Anlam Arayışı"', result)
        self.assertIn("%20 olarak hesaplanmıştır", result)
        self.assertIn("Eksikliğin şiddeti: Kritik.", result)
        self.assertIn("Ana duygu net kurulamıyor.", result)
        self.assertNotIn("etkinlik", result)

    def test_unverified_evidence_term_is_rejected(self):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "Metinde ana duygu ve ana düşünce belirlenir."}]
        answer = _evidence_json(
            ["ana duygu", "edebiyat atölyesi"], ["Ana duygu eksik.", "Edebiyat atölyesi eksik."]
        )
        self.assertEqual(_compose_grounded_pedagogical_answer(answer, outcome, sources), "")

    def test_status_not_found_is_rejected(self):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        answer = json.dumps({"status": "not_found"})
        self.assertEqual(
            _compose_grounded_pedagogical_answer(answer, outcome, [{"excerpt": "ana duygu"}]), ""
        )

    def test_recommendation_language_in_rationale_is_stripped_and_then_rejected(self):
        # gapRationale tamamen öneri cümlesiyse strip_recommendation_sentences
        # onu boşaltır - boş gerekçe TÜM yanıtı reddettirir (bkz.
        # _compose_grounded_pedagogical_answer docstring'i).
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "Metinde ana duygu ve ana düşünce belirlenir."}]
        answer = _evidence_json(
            ["ana duygu", "ana düşünce"],
            ["Bu eksiklik giderilmelidir ve telafi programı önerilir.", "Ana düşünce eksik."],
        )
        self.assertEqual(_compose_grounded_pedagogical_answer(answer, outcome, sources), "")

    def test_non_json_model_paragraph_is_rejected_when_structured_evidence_is_expected(self):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        self.assertEqual(
            _compose_grounded_pedagogical_answer(
                "Öğrenciler için bir etkinlik önerilir.", outcome, [{"excerpt": "ana duygu"}]
            ),
            "",
        )

    def test_valid_json_is_used_and_trailing_model_prose_is_ignored(self):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.40}
        sources = [{"excerpt": "Okuma stratejisi ile metinleri inceleme birlikte ele alınır."}]
        answer = (
            _evidence_json(
                ["Okuma stratejisi", "metinleri inceleme"],
                ["Okuma stratejisi tutarsız uygulanıyor.", "Metinleri inceleme yüzeysel kalıyor."],
            )
            + "\n\nBu bölüm modelin kaynak dışına çıkabilen serbest açıklamasıdır."
        )
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn("Okuma stratejisi ve metinleri inceleme", result)
        self.assertNotIn("serbest açıklama", result)

    def test_ragcontext_field_always_present_even_without_remote_url(self):
        # MAHIR_RAG_REMOTE_URL artık koda gömülü bir varsayılana sahip (bkz.
        # approved_data_analyzer.py) - "yapılandırılmamış" durumu burada
        # açıkça boş string'e çekilerek test ediliyor, gerçek ağ çağrısı yapılmaz.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            with _llm_patch() as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_unregistered_course_never_calls_rag(self):
        payload = {
            "exam": {"courseName": "Fen Bilimleri", "componentType": "written"},
            "questions": [{"number": 1, "maxScore": 100}],
            "students": [{"studentRef": "Ö-001", "scores": [10]}],
        }
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with _llm_patch() as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_strong_outcome_gets_grounded_context(self):
        payload = _weak_tde_payload()
        payload["exam"]["examType"] = "Dinleme/İzleme Sınavı"
        payload["exam"]["examSequence"] = "2. Dinleme/İzleme Sınavı"
        payload["exam"]["componentType"] = "listening"
        payload["students"][0]["scores"] = [90]  # successRate 0.90 >= eşik (0.70)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with _llm_patch(side_effect=_llm_reply(("Seçili çıktı güçlü düzeydedir.", [{"documentName": "x"}]))) as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_called_once()
        prompt = _diagnosis_prompts(mock_query)[0]
        self.assertIn("Dinleme/İzleme Sınavı", prompt["user"])
        self.assertIn("SINAV SIRASI: 2. Dinleme/İzleme Sınavı", prompt["user"])
        self.assertIn("TDE1.2", prompt["user"])
        self.assertEqual(result["outcomes"][0]["ragContext"], "Seçili çıktı güçlü düzeydedir.")

    def test_foreign_code_or_skill_is_rejected(self):
        outcome = {
            "outcomeCode": "TDE3.3", "componentType": "speaking",
            "outcomeDescription": "konuşmada kural uygulayabilme",
        }
        self.assertFalse(_answer_matches_outcome_scope("TDE2.2.3 okuma becerileri eksiktir.", outcome))
        self.assertTrue(_answer_matches_outcome_scope("TDE3.3 konuşma becerisi güçlüdür.", outcome))

    def test_overlong_pedagogical_answer_is_rejected(self):
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        answer = " ".join(["kanıt"] * 71)
        self.assertFalse(_answer_matches_outcome_scope(answer, outcome))

    def test_causal_overclaim_and_student_count_are_rejected(self):
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        self.assertFalse(_answer_matches_outcome_scope("Düşüklüğün temel nedeni yetersiz bilgidir.", outcome))
        self.assertFalse(_answer_matches_outcome_scope("Zorluk çeken öğrencilerin sayısı yüksektir.", outcome))

    def test_activity_or_remediation_language_is_rejected(self):
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        self.assertFalse(_answer_matches_outcome_scope("Bu çıktı için etkinlik önerilir.", outcome))
        self.assertFalse(_answer_matches_outcome_scope("Telafi çalışması yapılmalıdır.", outcome))

    def test_concise_evidence_bounded_diagnosis_is_accepted(self):
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        self.assertTrue(
            _answer_matches_outcome_scope(
                "Açık ve örtük iletiyi belirleme performansı yüzde 30 düzeyindedir. "
                "Eksikliğin şiddeti: Kritik. Bu sınırlılık sonraki anlam oluşturma süreçleri için risk taşır.",
                outcome,
            )
        )

    def test_listening_rejects_interview_and_reading_drift(self):
        outcome = {
            "outcomeCode": "TDE1.2", "componentType": "listening",
            "outcomeDescription": "dinlediği/izlediği metinde anlam oluşturabilme",
        }
        self.assertFalse(_answer_matches_outcome_scope("Öğrenciler mülakatta konuşur ve iletiyi belirler.", outcome))
        self.assertTrue(_answer_matches_outcome_scope("Öğrenciler mülakat metnini dinleyerek iletiyi belirler.", outcome))
        self.assertFalse(_answer_matches_outcome_scope("Okuma stratejileri uygulanmalıdır.", outcome))
        self.assertTrue(_answer_matches_outcome_scope("Dinlediği metindeki açık ve örtük iletiyi belirler.", outcome))

    def test_rejected_listening_drift_is_reported_without_the_unsafe_context(self):
        payload = _weak_tde_payload()
        payload["exam"]["examType"] = "Dinleme/İzleme Sınavı"
        payload["exam"]["componentType"] = "listening"
        canned = ("Öğrenciler mülakatta konuşarak açık ve örtük iletiyi belirler.", [{"documentName": "x"}])
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply(canned)):
                result = analyze_approved_data(payload)
        context = result["outcomes"][0]["ragContext"]
        self.assertIn("doğrulanmış bir kaynak bağlamı oluşturulamadı", context)
        self.assertNotIn("mülakat", context)
        self.assertEqual(result["outcomes"][0]["ragSources"], [])

    def test_weak_registered_outcome_attaches_answer(self):
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Bu kazanım dinleme becerisini kapsar.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply((canned[2]["answer"], canned[2]["sources"]))) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_called_once()
        prompts = _diagnosis_prompts(mock_query)
        self.assertEqual(len(prompts), 1)
        self.assertIn("Sözün İnceliği", prompts[0]["user"])
        self.assertIn("TDE1.2", prompts[0]["user"])
        self.assertEqual(mock_query.call_args[0][1], _FAKE_REMOTE_URL)
        # Getirim filtreleri prompt'un kendi `retrieval` blogunda gidiyor.
        self.assertEqual(prompts[0]["retrieval"]["programId"], "tde-9-tymm")
        self.assertEqual(prompts[0]["retrieval"]["grade"], "9")
        self.assertEqual(prompts[0]["retrieval"]["theme"], "SÖZÜN İNCELİĞİ")
        self.assertEqual(result["outcomes"][0]["ragContext"], "Bu kazanım dinleme becerisini kapsar.")

    def test_outcome_description_reaches_both_question_and_retrieval_query(self):
        # Kazanım metni müfredat PDF'iyle aynı dilde yazıldığı için hem getirimin
        # hem de bilişsel düzey teşhisinin asıl dayanağı - çıktı bazında toplama
        # sırasında düşürülürse RAG elinde yalnızca çıplak bir kod kalıyor.
        canned = (True, "Yanıt üretildi.", {"answer": "teşhis", "sources": [{"documentName": "x"}]})
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply((canned[2]["answer"], canned[2]["sources"]))) as mock_query:
                analyze_approved_data(_weak_tde_payload())
        item = _diagnosis_prompts(mock_query)[0]
        self.assertIn("anlam oluşturabilme", item["user"])
        self.assertIn("anlam oluşturabilme", item["retrieval"]["query"])

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

    def test_process_component_query_carries_child_and_parent_outcome(self):
        outcome = {
            "outcomeTheme": "2. Tema: Anlam Arayışı",
            "outcomeCode": "TDE2.2.3",
            "outcomeDescription": "Çıkarım yapar.",
            "parentOutcomeCode": "TDE2.2",
            "parentOutcomeDescription": "Anlam oluşturabilme",
            "outcomeSkill": "Okuma",
        }
        retrieval_query = _build_rag_retrieval_query(outcome)
        self.assertIn("TDE2.2.3", retrieval_query)
        self.assertIn("TDE2.2", retrieval_query)
        self.assertIn("Çıkarım yapar", retrieval_query)
        self.assertIn("Anlam oluşturabilme", retrieval_query)

    def test_no_answer_in_document_leaves_ragcontext_empty(self):
        canned = (True, "Yanıt üretildi.", {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []})
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply((canned[2]["answer"], canned[2]["sources"]))):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_answer_prefixed_with_no_answer_phrase_is_discarded(self):
        # Model önce kaynak yetersizliğini bildirip ardından metin ekliyorsa iki
        # ifade birbiriyle çelişir. Devamı doğru görünse bile kanıtlı kabul
        # edilmez; olası halüsinasyonun rapora taşınması engellenir.
        canned = (
            True,
            "Yanıt üretildi.",
            {
                "answer": "Bu bilgi belgede bulunmuyor.\n\nTDE1.2 dinleme becerisini kapsar.",
                "sources": [{"documentName": "x"}],
            },
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply((canned[2]["answer"], canned[2]["sources"]))):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_answer_only_the_no_answer_phrase_with_sources_still_leaves_ragcontext_empty(self):
        # Kırpmadan sonra hiçbir şey kalmıyorsa (model gerçekten hiçbir şey
        # bulamadıysa, kaynaklar dolu gelse bile) yine boş bırakılmalı.
        canned = (
            True,
            "Yanıt üretildi.",
            {"answer": "Bu bilgi belgede bulunmuyor.", "sources": [{"documentName": "x"}]},
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=_llm_reply((canned[2]["answer"], canned[2]["sources"]))):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_unresolved_theme_skips_rag_call_entirely(self):
        # Tema kataloğa göre çözülemiyorsa grade-only bir aramaya düşülmemeli -
        # bu, 9. sınıfın 4 farklı temasından herhangi birinin içeriğini
        # getirebilir ve yanlış temadan "kaynaklı" görünen bir teşhis üretebilir.
        payload = _weak_tde_payload()
        payload["questions"][0]["outcomeTheme"] = ""
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with _llm_patch() as mock_query:
                result = analyze_approved_data(payload)
        mock_query.assert_not_called()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")

    def test_rag_failure_leaves_ragcontext_empty_and_does_not_raise(self):
        # LLM turu başarısız: analiz yine de tamamlanmalı, yalnız teşhis boş kalır.
        failure = (False, "Uzak RAG sunucusuna ulaşılamadı.", None)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with _llm_patch(return_value=failure) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_called_once()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")
        # Sayılar arızadan etkilenmemeli - teşhis bir zenginleştirme.
        self.assertEqual(result["outcomes"][0]["successRate"], 0.30)

    def test_rag_exception_leaves_ragcontext_empty_and_does_not_raise(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with _llm_patch(side_effect=RuntimeError("boom")) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())
        mock_query.assert_called_once()
        self.assertEqual(result["outcomes"][0]["ragContext"], "")
        self.assertEqual(result["outcomes"][0]["successRate"], 0.30)


def _two_weak_outcomes_payload():
    """İki farklı temadan iki zayıf çıktı - parti davranışını görebilmek için."""

    return {
        "exam": {"courseName": "Türk Dili ve Edebiyatı", "grade": "9", "componentType": "written"},
        "questions": [
            {
                "number": 1,
                "maxScore": 100,
                "outcomeCode": "TDE1.2",
                "outcomeTheme": "1. Tema: Sözün İnceliği",
                "outcomeSkill": "Okuma",
                "outcomeDescription": "metinlerde anlam oluşturabilme",
            },
            {
                "number": 2,
                "maxScore": 100,
                "outcomeCode": "TDE2.1",
                "outcomeTheme": "2. Tema: Anlam Arayışı",
                "outcomeSkill": "Okuma",
                "outcomeDescription": "metinlerde okumayı yönetebilme",
            },
        ],
        "students": [{"studentRef": "Ö-001", "scores": [30, 40]}],
    }


class DiagnosisGroundingRetryTests(unittest.TestCase):
    """2026-08-22 (3. sürüm): doğrulanamayan ilk deneme TEK bir ek turla
    yeniden sorulur - canlıda ölçülen ~%40 ilk-üretim reddetme oranını
    düşürmek için (bkz. `PedagogicalAnalysisAgent._evaluate_diagnosis_result`).
    Toleransı gevşetmek yerine üretimi tekrarlamak seçildi: doğrulama kuralı
    değişmiyor, modele ikinci bir şans veriliyor.
    """

    _SOURCES: ClassVar[list[dict[str, str]]] = [
        {"documentName": "mufredat.pdf", "excerpt": "Sözün İnceliği temasında anlam oluşturma ele alınır."}
    ]

    def test_ungrounded_first_attempt_is_retried_and_succeeds(self):
        bad = _evidence_json(
            ["dinleme becerisi", "kelime dağarcığı"], ["İlk deneme 1.", "İlk deneme 2."]
        )
        good = _evidence_json(
            ["Sözün İnceliği", "anlam oluşturma"], ["İkinci deneme 1.", "İkinci deneme 2."]
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch(
                "backend.app.agents.llm.run_agent_prompts",
                side_effect=_llm_reply_sequence([(bad, self._SOURCES)], [(good, self._SOURCES)]),
            ) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())

        self.assertEqual(mock_query.call_count, 2)
        context = result["outcomes"][0]["ragContext"]
        self.assertIn("anlam oluşturma", context)
        self.assertNotIn("doğrulanmış bir kaynak bağlamı oluşturulamadı", context)
        retry_items = mock_query.call_args_list[1][0][0]
        self.assertEqual(len(retry_items), 1)
        self.assertIn("BİREBİR", retry_items[0]["user"])
        # Getirim (aynı BAĞLAM) retry'de DEĞİŞMEMELİ - sorun modelin BAĞLAM'ı
        # yanlış kullanmasıydı, hangi BAĞLAM'ın getirildiği değil.
        self.assertEqual(retry_items[0]["retrieval"], _diagnosis_prompts(mock_query)[0]["retrieval"])

    def test_ungrounded_after_retry_is_rejected_and_tried_only_twice(self):
        bad = _evidence_json(
            ["dinleme becerisi", "kelime dağarcığı"], ["İlk deneme 1.", "İlk deneme 2."]
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch(
                "backend.app.agents.llm.run_agent_prompts",
                side_effect=_llm_reply_sequence([(bad, self._SOURCES)]),
            ) as mock_query:
                result = analyze_approved_data(_weak_tde_payload())

        self.assertEqual(mock_query.call_count, 2)
        context = result["outcomes"][0]["ragContext"]
        self.assertIn("doğrulanmış bir kaynak bağlamı oluşturulamadı", context)
        self.assertEqual(result["outcomes"][0]["ragSources"], [])

    def test_first_attempt_success_never_triggers_a_retry_call(self):
        good = _evidence_json(
            ["Sözün İnceliği", "anlam oluşturma"], ["Birinci deneme 1.", "Birinci deneme 2."]
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch(
                "backend.app.agents.llm.run_agent_prompts",
                side_effect=_llm_reply_sequence([(good, self._SOURCES)]),
            ) as mock_query:
                analyze_approved_data(_weak_tde_payload())

        mock_query.assert_called_once()


class TermGroundingTests(unittest.TestCase):
    """`_term_is_grounded`in Türkçe çekim eki toleransı - kalibrasyon verisi
    gerçek sorgulardan (2026-08-22).

    Önceki birebir alt-dize kontrolü, model doğru BAĞLAM ifadesini seçse
    bile ek farkı yüzünden (ör. "görsellerden"/"görsellerinden") reddediyordu.
    Bu testler hem gerçek-ama-farklı-ekli ifadelerin artık kabul edildiğini
    HEM DE gerçek uydurmaların (SORU'nun kendi cümlesi, modelin kendi
    "BAĞLAM" etiketini içeriğe sızdırması) hâlâ reddedildiğini kilitliyor -
    ikisi birbirine çok yakın karakter-benzerliği skorlarına sahip
    olabildiğinden (`difflib` ile ölçüldü: "ön bilgileri ile bağlantı
    kurar" 0,71 - "bağlamanın kontrol listesi" 0,77) salt bir eşik/skor
    yaklaşımı yerine sözcük sözcük eşleştirme kullanılıyor.
    """

    _SOZUN_INCELIGI_EVIDENCE = (
        "TDE1.1. 'Sözün İnceliği' temasında ele alınan metinlerde dinlemeyi/izlemeyi yönetebil-me "
        "TDE1.2. 'Sözün İnceliği' temasında ele alınan metinlerde anlam oluşturabilme "
        "'Sözün İnceliği' temasında ele alınan dinlediği/izlediği metnin başlık ve "
        "görsellerinden hareketle metnin yazılış amacını tahmin eder. "
        "'Sözün İnceliği' temasında ele alınan dinleme/izleme metnindeki bilgiler ile "
        "ön bilgileri arasında bağlantı kurar. "
        "Öğrenciler, dinleme/izleme öncesinde hazırlanan kontrol listesini gözden geçirir."
    )
    _ANLAM_YAPI_EVIDENCE = "TDE1.3. 'Anlamın Yapı Taşları' temasında ele alınan metinleri çözümleyebilme"

    def test_case_ending_difference_is_tolerated(self):
        self.assertTrue(_term_is_grounded("görsellerden hareketle", self._SOZUN_INCELIGI_EVIDENCE))

    def test_clitic_split_versus_merged_is_tolerated(self):
        # Kaynak "bilgilerle" (bitişik "-le"), model "bilgileri ile" (ayrı) yazdı.
        self.assertTrue(
            _term_is_grounded("ön bilgileri ile bağlantı kurar", self._SOZUN_INCELIGI_EVIDENCE)
        )

    def test_success_rate_leaking_from_the_question_is_rejected(self):
        self.assertFalse(_term_is_grounded("%30 başarı oranı", self._SOZUN_INCELIGI_EVIDENCE))

    def test_sarmal_risk_leaking_from_the_question_is_rejected(self):
        self.assertFalse(_term_is_grounded("sarmal risk", self._SOZUN_INCELIGI_EVIDENCE))

    def test_baglam_label_leaking_into_the_term_is_rejected(self):
        # "bağlamanın" ("BAĞLAM" etiketinin kendisi + iyelik eki) karakter
        # düzeyinde gerçek "bağlantı" sözcüğüne şaşırtıcı derecede yakın
        # (difflib: 0,78) - salt bir benzerlik eşiği bunu kaçırırdı.
        self.assertFalse(_term_is_grounded("bağlamanın kontrol listesi", self._SOZUN_INCELIGI_EVIDENCE))

    def test_unrelated_invented_word_is_rejected(self):
        self.assertFalse(_term_is_grounded("kısaltma", self._SOZUN_INCELIGI_EVIDENCE))

    def test_vowel_drop_suffix_case_is_a_known_gap(self):
        # "metni" (ünlü düşmesiyle çekimlenmiş) ile kaynaktaki "metinleri"
        # arasındaki ortak önek çok kısa kalıyor (yalnız "met") - bu, kabul
        # edilen bir kalan sınır: nadir bir ünlü düşmesi durumu, eşik
        # gevşetilirse gerçek uydurmaları (yukarısı) da içeri alırdı.
        self.assertFalse(_term_is_grounded("metni çözümleyebilme", self._ANLAM_YAPI_EVIDENCE))

    def test_empty_term_is_rejected(self):
        self.assertFalse(_term_is_grounded("   ", self._SOZUN_INCELIGI_EVIDENCE))


class RagBatchingTests(unittest.TestCase):
    # Zayıf çıktılar tek istekte, tek vLLM partisinde yanıtlanıyor: ölçüldü,
    # sıcak konteynerde tek sorgunun 7-8,6 sn'si üretim ve bu ~29 token/s tek
    # dizilik çözme hızı - diziler birlikte çözülünce N sorgu ~1 sorgu kadar
    # sürüyor (8 zayıf çıktı için ölçülen taban: 241 sn).
    def test_all_weak_outcomes_go_out_in_one_call(self):
        canned = (
            True,
            "Yanıt üretildi.",
            [
                {"answer": "birinci teşhis", "sources": [{"documentName": "x"}]},
                {"answer": "ikinci teşhis", "sources": [{"documentName": "y"}]},
            ],
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                      side_effect=_llm_reply(*[(r["answer"], r["sources"]) for r in canned[2]])) as mock_batch:
                with patch("backend.app.rag_client.query_rag_context") as mock_single:
                    result = analyze_approved_data(_two_weak_outcomes_payload())

        mock_batch.assert_called_once()
        self.assertEqual(len(_diagnosis_prompts(mock_batch)), 2)
        contexts = [item["ragContext"] for item in result["outcomes"]]
        self.assertEqual(contexts, ["birinci teşhis", "ikinci teşhis"])

    def test_results_map_back_to_the_right_outcome(self):
        # Sıra kayması, bir kazanımın teşhisini başka bir kazanıma yazmak
        # demek olurdu - RAG'in daha önce düzeltilen "yanlış temadan veri"
        # hatasının aynısı, bu kez tamamen kod tarafında.
        canned = (
            True,
            "Yanıt üretildi.",
            [
                {"answer": "SÖZÜN İNCELİĞİ teşhisi", "sources": [{"documentName": "x"}]},
                {"answer": "ANLAM ARAYIŞI teşhisi", "sources": [{"documentName": "y"}]},
            ],
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                      side_effect=_llm_reply(*[(r["answer"], r["sources"]) for r in canned[2]])) as mock_batch:
                result = analyze_approved_data(_two_weak_outcomes_payload())

        sent_themes = [item["retrieval"]["theme"] for item in _diagnosis_prompts(mock_batch)]
        self.assertEqual(sent_themes, ["SÖZÜN İNCELİĞİ", "ANLAM ARAYIŞI"])
        by_code = {item["outcomeCode"]: item["ragContext"] for item in result["outcomes"]}
        self.assertEqual(by_code["TDE1.2"], "SÖZÜN İNCELİĞİ teşhisi")
        self.assertEqual(by_code["TDE2.1"], "ANLAM ARAYIŞI teşhisi")

    def test_unresolved_theme_outcome_is_kept_out_of_the_batch(self):
        payload = _two_weak_outcomes_payload()
        payload["questions"][0]["outcomeTheme"] = ""
        canned = (True, "Yanıt üretildi.", [{"answer": "teşhis", "sources": [{"documentName": "y"}]}])
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                      side_effect=_llm_reply(*[(r["answer"], r["sources"]) for r in canned[2]])) as mock_batch:
                result = analyze_approved_data(payload)

        sent = _diagnosis_prompts(mock_batch)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["retrieval"]["theme"], "ANLAM ARAYIŞI")
        by_code = {item["outcomeCode"]: item["ragContext"] for item in result["outcomes"]}
        self.assertEqual(by_code["TDE1.2"], "")
        self.assertEqual(by_code["TDE2.1"], "teşhis")

    def test_llm_round_failure_leaves_every_ragcontext_empty_without_raising(self):
        # DAVRANIŞ DEĞİŞİKLİĞİ (Faz 3): eskiden parti başarısız olunca çıktılar
        # TEK TEK yeniden sorgulanıyordu. Tek istekli mimaride o geri çekilme
        # yolu kaldırıldı - N çıktı için N ağ turu, "ek GPU maliyeti yok"
        # kısıtıyla çelişiyordu ve asıl senaryoyu (geçici ağ arızası) tek tek
        # denemek de kurtarmıyor.
        #
        # Korunan güvence: teşhis bir ZENGİNLEŞTİRME. Tur başarısız olursa
        # hücreler boş kalır, analiz eksiksiz üretilir ve istisna fırlamaz.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                       return_value=(False, "Uzak RAG sunucusuna ulaşılamadı.", None)):
                result = analyze_approved_data(_two_weak_outcomes_payload())

        self.assertEqual([item["ragContext"] for item in result["outcomes"]], ["", ""])
        # Analizin geri kalanı eksiksiz.
        self.assertEqual(len(result["outcomes"]), 2)
        self.assertEqual(len(result["questions"]), 2)

    def test_llm_round_exception_is_swallowed_too(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                       side_effect=RuntimeError("bağlantı koptu")):
                result = analyze_approved_data(_two_weak_outcomes_payload())

        self.assertEqual([item["ragContext"] for item in result["outcomes"]], ["", ""])
        self.assertEqual(len(result["outcomes"]), 2)

    def test_one_empty_result_does_not_affect_the_others(self):
        # Getirimi boş çıkan öğe partiye girmiyor ve kendi no_answer sonucunu
        # alıyor - diğerlerinin teşhisi bundan etkilenmemeli.
        canned = (
            True,
            "Yanıt üretildi.",
            [
                {"answer": "Bu bilgi belgede bulunmuyor.", "sources": []},
                {"answer": "ikinci teşhis", "sources": [{"documentName": "y"}]},
            ],
        )
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                       side_effect=_llm_reply(*[(r["answer"], r["sources"]) for r in canned[2]])):
                result = analyze_approved_data(_two_weak_outcomes_payload())

        contexts = [item["ragContext"] for item in result["outcomes"]]
        self.assertEqual(contexts, ["", "ikinci teşhis"])


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

    def test_remediation_need_closing_is_dropped_but_gelisim_ihtiyaci_is_kept(self):
        # "eksikliği giderme ihtiyacı ortaya çıkmaktadır" canlı ölçümde hem
        # prompt'tan hem de desenden kaçtı. Tetikleyici "ihtiyaç" OLAMAZ:
        # "gelişim ihtiyacı" MAHİR'in raporundaki kendi terimi.
        answer, dropped = _strip_recommendation_sentences(
            "Bu eksikliği giderme ihtiyacı ortaya çıkmaktadır. "
            "Bu kazanımda net bir gelişim ihtiyacı vardır."
        )
        self.assertEqual(dropped, 1)
        self.assertEqual(answer, "Bu kazanımda net bir gelişim ihtiyacı vardır.")

    def test_diagnostic_gerektirir_is_not_dropped(self):
        # "gerektirir" teşhis dilinde meşru - "gerekir"le karıştırılmamalı.
        answer, dropped = _strip_recommendation_sentences(
            "Bu kazanım üst düzey analiz becerisi gerektirir."
        )
        self.assertEqual(dropped, 0)
        self.assertEqual(answer, "Bu kazanım üst düzey analiz becerisi gerektirir.")

    def test_all_recommendation_answer_is_discarded_and_leaves_ragcontext_empty(self):
        # Charter süzgeci artık ortak LLM katmanında (agents/llm.py) çalışıyor
        # ve burada mock'landığı için, süzgeçten SONRAKİ hâl simüle ediliyor:
        # yanıtın tamamı öneriyse geriye boş string kalır ve hat o çıktıyı
        # atlamalı - charter ihlali içeren bir metni raporlamaktansa hücreyi
        # boş bırakmak doğrusu. Süzgecin kendisi tests/test_agent_llm.py'de.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_REMOTE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts",
                       side_effect=_llm_reply(("", [{"documentName": "x"}]))):
                result = analyze_approved_data(_weak_tde_payload())
        self.assertEqual(result["outcomes"][0]["ragContext"], "")


class NoBloomTests(unittest.TestCase):
    """Bloom taksonomisi kaldırıldı; geri sızmadığını yapısal olarak koruyoruz.

    Neden kaldırıldı: canlı ölçümde sekiz yanıtın TAMAMI Bloom cümlesiyle
    açılıyor, yanıt başına 2-8 kez basamak adı geçiyor, buna karşılık temanın
    adı 0/8 yanıtta geçiyor ve yalnız 2/8 yanıt müfredattan somut bir öğe
    anıyordu. Model, ona zaten söylediğimiz şeyi tekrarlamaya harcanıyordu.
    """

    def _question(self, description="metinlerde anlam oluşturabilme", rate=0.4):
        return _build_rag_question({
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "outcomeCode": "TDE1.2",
            "outcomeDescription": description,
            "successRate": rate,
        })

    def test_question_no_longer_injects_a_cognitive_level(self):
        for description in (
            "metinlerde anlam oluşturabilme",
            "metinleri çözümleyebilme",
            "öğrendiklerini yansıtabilme",
            "bir şeyler yapar",
        ):
            with self.subTest(description=description):
                question = self._question(description)
                self.assertNotIn("bilişsel düzey", question)
                self.assertNotIn("Bloom", question)

    def test_question_no_longer_carries_success_rate_or_severity(self):
        # 2026-08-22: model artık paragraf yazmıyor, yalnız BAĞLAM'dan iki
        # terim seçiyor; oranı/şiddeti MAHİR kendi hesaplıyor
        # (_compose_grounded_pedagogical_answer). Canlı ölçümde bu sayılar
        # sorudayken model tekrar tekrar "%40 başarı oranı"/"Kritik" gibi
        # SORU'nun kendi cümlesini "evidenceTerms" diye seçip BAĞLAM'daki
        # gerçek müfredat metnini hiç kullanmadı - kaldırılması bu tuzağı
        # ortadan kaldırıyor (bkz. _build_rag_question docstring'i).
        for rate in (0.2, 0.4, 0.6):
            with self.subTest(rate=rate):
                question = self._question(rate=rate)
                self.assertNotIn("şiddet etiketi", question)
                self.assertNotIn("%", question)

    def test_question_asks_for_curriculum_grounding(self):
        # Eski kapanış emri modelin yanıtı bilişsel kıyasa harcamasına yol
        # açıyordu; yenisi getirilen müfredat metnine demirlemeyi istiyor.
        question = self._question()
        self.assertIn("BAĞLAM", question)
        self.assertIn("adıyla anarak", question)

    def test_bloom_helpers_are_gone_for_good(self):
        # Yardımcı geri gelirse prompt'a da geri sızması an meselesi.
        import backend.app.approved_data_analyzer as analyzer

        self.assertFalse(hasattr(analyzer, "_bloom_level_for"))
        self.assertFalse(hasattr(analyzer, "_BLOOM_LEVELS_BY_VERB"))

    def test_retrieval_query_stays_free_of_instruction_text(self):
        retrieval_query = _build_rag_retrieval_query({
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "outcomeCode": "TDE1.2",
            "outcomeDescription": "metinlerde anlam oluşturabilme",
            "successRate": 0.4,
        })
        self.assertNotIn("bilişsel düzey", retrieval_query)
        self.assertNotIn("şiddet etiketi", retrieval_query)
        self.assertNotIn("BAĞLAM", retrieval_query)


class RagContextSeverityTests(unittest.TestCase):
    """Şiddet etiketinin eşiğe dayalı, belirlenimci hesabı.

    2026-08-22 öncesi bu hesap `_build_rag_question`da yapılıp SORU içinde
    modele veriliyordu (modele bırakıldığında %55'lik vakaların yarısına
    "Kritik" dediği canlı ölçümle görülmüştü). Artık model paragrafın
    kendisini yazmıyor - yalnız BAĞLAM'dan iki terim seçiyor - ve modele
    verilen bu sayı, kendi cümlesini ("%40 başarı oranı" gibi)
    "evidenceTerms" olarak seçmesine yol açan bir tuzağa dönüştü. Hesap bu
    yüzden tamamen MAHİR'in tarafına (`_compose_grounded_pedagogical_answer`)
    taşındı; eşik davranışı burada, o fonksiyona karşı test ediliyor.
    """

    def _answer_for(self, success_rate):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": success_rate}
        sources = [{"excerpt": "ana duygu ve ana düşünce"}]
        answer = _evidence_json(
            ["ana duygu", "ana düşünce"], ["Ana duygu eksik.", "Ana düşünce eksik."]
        )
        return _compose_grounded_pedagogical_answer(answer, outcome, sources)

    def test_below_fifty_percent_is_critical(self):
        self.assertIn("Eksikliğin şiddeti: Kritik.", self._answer_for(0.35))

    def test_fifty_to_sixtynine_percent_is_moderate(self):
        self.assertIn("Eksikliğin şiddeti: Orta.", self._answer_for(0.55))

    def test_exactly_fifty_percent_is_moderate(self):
        # Sınır değer, mahir-report-export-common.js'teki "< 0.50 => Öncelikli"
        # kuralıyla aynı yönde kırılmalı.
        self.assertIn("Eksikliğin şiddeti: Orta.", self._answer_for(0.50))

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
