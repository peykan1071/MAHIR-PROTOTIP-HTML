"""Tests for the single LLM round shared by every agent.

Faz 3'ün iddiası tek cümle: kaç ajan LLM kullanırsa kullansın, bir analizde
BİR istek atılır. Buradaki testlerin çoğu bunu koruyor - iddia sessizce
bozulursa (bir ajan kendi çağrısını yaparsa) analiz süresi ajan başına ~3 sn
büyür ve kimse fark etmez.
"""

import unittest
from unittest.mock import patch

import rag_service
from backend.app.agents import prompts
from backend.app.approved_data_analyzer import analyze_approved_data

_FAKE_URL = "https://fake.example/web_query"


def _question(number, code, theme="1. Tema: Sözün İnceliği", max_score=10):
    return {
        "number": number,
        "maxScore": max_score,
        "outcomeCode": code,
        "outcomeDescription": f"{code} kazanım metni",
        "outcomeTheme": theme,
        "outcomeSkill": "Okuma",
        "parentOutcomeDescription": f"{code} kazanım metni",
    }


def _tde_payload(scores=(3, 4, 2)):
    """Kayıtlı TDE9 programı + üç zayıf soru: hem teşhis hem anomali tetiklenir."""

    return {
        "exam": {
            "courseName": "Türk Dili ve Edebiyatı",
            "grade": "9",
            "componentType": "written",
        },
        "questions": [
            _question(1, "TDE1.2"),
            _question(2, "TDE2.1", theme="2. Tema: Anlam Arayışı"),
            _question(3, "TDE2.2", theme="2. Tema: Anlam Arayışı"),
        ],
        "students": [{"studentRef": "Ö-001", "scores": list(scores)}],
    }


def _capture(answer=""):
    """`run_agent_prompts` yerine geçer; gönderilen kuyruğu kaydeder."""

    calls = []

    def fake(items, remote_url):
        calls.append(items)
        return True, "ok", [
            {
                "name": item["name"],
                "answer": answer,
                "sources": [{"documentName": "x"}] if "retrieval" in item else [],
                "strippedSentences": 0,
            }
            for item in items
        ]

    return calls, fake


class SingleRoundTests(unittest.TestCase):
    def test_every_agent_prompt_travels_in_one_request(self):
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(_tde_payload())

        self.assertEqual(len(calls), 1, "Bir analizde tek LLM isteği atılmalı.")

    def test_retrieval_and_plain_prompts_share_the_same_request(self):
        # Ölçme'nin anomali prompt'u getirimsiz, Pedagojik'inkiler getirimli.
        # İkisi ayrı isteklere düşerse maliyet ajan başına büyümeye başlar.
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(_tde_payload())

        queue = calls[0]
        plain = [item for item in queue if "retrieval" not in item]
        grounded = [item for item in queue if "retrieval" in item]
        self.assertEqual(len(plain), 1, "Anomali prompt'u getirimsiz olmalı.")
        self.assertEqual(plain[0]["name"], "olcme-degerlendirme")
        self.assertTrue(grounded, "Teşhis prompt'ları getirimli olmalı.")
        self.assertTrue(all(item["name"].startswith("pedagoji/") for item in grounded))

    def test_unregistered_course_queues_only_the_anomaly_prompt(self):
        # Kayıtsız derste indekslenmiş referans materyal yok; teşhis prompt'u
        # üretilmez ama anomali tespiti her ders için anlamlı.
        payload = _tde_payload()
        payload["exam"]["courseName"] = "Matematik"
        for index, question in enumerate(payload["questions"], 1):
            question["outcomeCode"] = f"M9.{index}"

        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(payload)

        self.assertEqual([item["name"] for item in calls[0]], ["olcme-degerlendirme"])

    def test_no_request_at_all_when_queue_is_empty(self):
        # İki soruluk sınav: anomali için örüntü yok. Güçlü sonuçlar olduğu
        # için teşhis de yok -> hiç istek atılmamalı.
        payload = _tde_payload()
        payload["questions"] = payload["questions"][:2]
        payload["students"] = [{"studentRef": "Ö-001", "scores": [10, 10]}]

        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(payload)

        self.assertEqual(calls, [], "Kuyruk boşsa ağ turu harcanmamalı.")

    def test_no_request_when_remote_is_not_configured(self):
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                result = analyze_approved_data(_tde_payload())

        self.assertEqual(calls, [])
        self.assertEqual(result["summary"]["anomalies"], "")


class AnomalyAgentTests(unittest.TestCase):
    def test_anomaly_prompt_carries_no_student_data(self):
        # Gizlilik kapısı kimlik alanlarını reddediyor; bu prompt o sınırın
        # arkasına yan kapı açmamalı. Yalnız SORU düzeyinde toplu değer gider.
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(_tde_payload(scores=(3, 4, 2)))

        anomaly = next(item for item in calls[0] if item["name"] == "olcme-degerlendirme")
        blob = anomaly["system"] + anomaly["user"]
        self.assertNotIn("Ö-001", blob)
        self.assertNotIn("studentRef", blob)
        # Soru düzeyinde toplu değerler olmalı.
        self.assertIn("Soru 1", anomaly["user"])
        self.assertIn("başarı oranı", anomaly["user"])

    def test_findings_reach_the_summary_without_touching_any_number(self):
        calls, fake = _capture(answer="- Soru 3: sınıfın tamamı sıfır aldı.")
        payload = _tde_payload()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                enriched = analyze_approved_data(payload)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            plain = analyze_approved_data(payload)

        self.assertIn("Soru 3", enriched["summary"]["anomalies"])
        # Anomali bulgusu HİÇBİR sayıyı değiştirmemeli.
        self.assertEqual(enriched["questions"], plain["questions"])
        for left, right in zip(enriched["outcomes"], plain["outcomes"]):
            self.assertEqual(left["successRate"], right["successRate"])
            self.assertEqual(left["evidence"], right["evidence"])

    def test_no_finding_leaves_the_field_empty(self):
        calls, fake = _capture(answer="Belirgin bir tutarsızlık görülmedi.")
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                result = analyze_approved_data(_tde_payload())

        self.assertEqual(result["summary"]["anomalies"], "")

    def test_short_exams_never_queue_an_anomaly_prompt(self):
        self.assertIsNone(prompts.build_anomaly_prompt([{"number": 1}, {"number": 2}]))


class PromptDriftTests(unittest.TestCase):
    def test_diagnosis_prompt_matches_the_server_copy(self):
        # Teşhis prompt'u iki yerde: istemcide (birleşik `agents` biçimi system
        # prompt'u çağırandan alıyor) ve sunucuda (eski `queries` biçimi için).
        # Ayrışırlarsa iki yol sessizce farklı teşhisler üretmeye başlar.
        self.assertEqual(prompts.DIAGNOSIS_SYSTEM_PROMPT, rag_service.SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
