"""Tests for the agent trace on the `/mahir-analyze` route.

Faz 4'ün iddiası: hattı üç fazda kurduk ama öğretmen çalıştığını göremiyordu.
Buradaki testler o yüzden yanıt GÖVDESİNE bakıyor - iz bağlamda doğru üretilip
son adımda düşürülürse (Faz 3'te `sources` alanında tam olarak bu oldu) birim
testleri bunu göremez.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend.app import file_receiver

_QUESTIONS = [
    {
        "number": number,
        "maxScore": 10,
        "outcomeCode": "M9.OB1",
        "outcomeDescription": "M9.OB1 kazanım metni",
        "outcomeTheme": "1. Tema: Sayılar",
        "outcomeSkill": "Okuma",
        "parentOutcomeDescription": "M9.OB1 kazanım metni",
    }
    for number in (1, 2, 3)
]
_PAYLOAD = {
    "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
    "questions": _QUESTIONS,
    "students": [{"studentRef": "Ö-001", "scores": [8, 6, 7]}],
}

_no_remote = None


def setUpModule():
    """LLM turu kapalı: burada sınanan şey izin TAŞINMASI, üretimi değil."""

    global _no_remote
    _no_remote = patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", "")
    _no_remote.start()


def tearDownModule():
    _no_remote.stop()


def _post(server, payload):
    port = server.server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mahir-analyze",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class AnalysisRouteTraceTests(unittest.TestCase):
    def setUp(self):
        self.server = file_receiver.create_server(host="127.0.0.1", port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        # addCleanup LIFO: server_close önce eklenmeli ki shutdown ondan ÖNCE koşsun.
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_trace_travels_next_to_the_analysis_not_inside_it(self):
        status, body = _post(self.server, _PAYLOAD)
        self.assertEqual(status, 200)
        self.assertIn("trace", body)
        # Rapor sözleşmesi teknik alanlarla kirlenmemeli: kaydedilmiş eski
        # çalışmalar ve eşdeğerlik testleri buna bağlı.
        self.assertNotIn("trace", body["analysis"])

    def test_all_five_agents_reach_the_browser_named(self):
        _status, body = _post(self.server, _PAYLOAD)
        self.assertEqual(
            [entry["label"] for entry in body["trace"]["agents"]],
            [
                "Belge Anlama",
                "Program Eşleştirme",
                "Ölçme ve Değerlendirme",
                "Pedagojik Analiz",
                "Raporlama",
            ],
        )

    def test_trace_never_carries_student_rows_over_the_wire(self):
        _status, body = _post(self.server, _PAYLOAD)
        blob = json.dumps(body["trace"], ensure_ascii=False)
        self.assertNotIn("Ö-001", blob)
        self.assertNotIn("scores", blob)

    def test_route_reports_the_server_side_total(self):
        # Tarayıcı kendi toplamını ölçüyor; aradaki fark ağ ve JSON taşıması.
        # Sunucu toplamı gövdeye çıkmazsa o fark hesaplanamaz.
        _status, body = _post(self.server, _PAYLOAD)
        self.assertGreaterEqual(body["trace"]["totalMs"], 0.0)

    def test_validation_error_still_answers_422_without_a_trace(self):
        # Öğretmenin düzeltmesi gereken veri hatası; hat hiç koşmadı, iz de yok.
        broken = {**_PAYLOAD, "students": [{"studentRef": "Ö-001", "scores": [8]}]}
        status, body = _post(self.server, broken)
        self.assertEqual(status, 422)
        self.assertFalse(body["ok"])
        self.assertNotIn("trace", body)

    def test_required_agent_failure_answers_500_with_the_partial_trace(self):
        # `PipelineError` kısmi bağlamı tam da bunun için taşıyor: arıza ANINDA
        # hangi ajanın düştüğü ve hangilerinin atlandığı, hatanın kendisi kadar
        # değerli. Yalnız log'a yazmak bunu çağıran katmandan gizlerdi.
        from backend.app.agents.orchestrator import PIPELINE

        class Boom:
            name = "olcme-degerlendirme"
            label = "Ölçme ve Değerlendirme"
            description = "Ölçme"
            required = True

            def run(self, context):
                raise RuntimeError("ölçme motoru düştü")

        broken = tuple(
            Boom() if agent.name == "olcme-degerlendirme" else agent for agent in PIPELINE
        )
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            status, body = _post(self.server, _PAYLOAD)

        self.assertEqual(status, 500)
        self.assertFalse(body["ok"])
        agents = {entry["agent"]: entry for entry in body["trace"]["agents"]}
        self.assertTrue(agents["olcme-degerlendirme"]["failed"])
        self.assertTrue(agents["pedagojik-analiz"]["skipped"])
        # Arızadan ÖNCEKİ ajanların ürettiği hâlâ görünür olmalı.
        self.assertEqual(agents["belge-anlama"]["outputs"]["questionCount"], 3)


if __name__ == "__main__":
    unittest.main()
