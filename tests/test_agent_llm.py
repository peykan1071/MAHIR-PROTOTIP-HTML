"""Tests for the shared LLM layer the agents talk to.

Driven against a real local HTTP server rather than a mock, because the two
things most worth proving are wire-level: that every agent's prompt goes out in
ONE request (that is the whole cost argument for having five LLM agents), and
that the charter filter is applied to every answer on the way back.
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend.app.agents import llm

_received: list[dict] = []
_response: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _received.append(json.loads(self.rfile.read(length) or b"{}"))
        body = json.dumps(_response).encode("utf-8")
        self.send_response(int(_response.get("_status", 200)))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # test çıktısını kirletmesin
        pass


class AgentLlmTests(unittest.TestCase):
    def setUp(self):
        _received.clear()
        _response.clear()
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _reply(self, answers, ok=True, message="Ajan yanıtları üretildi.", status=200):
        _response.update({
            "ok": ok,
            "message": message,
            "structuredData": {"results": [{"name": n, "answer": a} for n, a in answers]},
            "_status": status,
        })

    def _prompts(self, count):
        return [llm.build_prompt(f"ajan-{i}", "sistem", f"kullanici {i}") for i in range(count)]

    # --- Maliyet iddiasının kanıtı: hepsi TEK istekte gidiyor ---

    def test_all_prompts_travel_in_a_single_request(self):
        self._reply([(f"ajan-{i}", "teşhis") for i in range(5)])
        ok, _message, results = llm.run_agent_prompts(self._prompts(5), self.url)

        self.assertTrue(ok)
        self.assertEqual(len(_received), 1, "Beş prompt tek istekte gitmeliydi.")
        self.assertEqual(len(_received[0]["agents"]), 5)
        self.assertEqual(len(results), 5)

    def test_request_uses_the_agents_body_shape(self):
        self._reply([("ajan-0", "teşhis")])
        llm.run_agent_prompts(self._prompts(1), self.url)
        sent = _received[0]["agents"][0]
        self.assertEqual(sorted(sent), ["name", "system", "user"])
        self.assertEqual(sent["name"], "ajan-0")

    def test_local_only_fields_never_reach_the_wire(self):
        # `agent` alanı LLM kaydının hangi ajanın izine düşeceğini söylüyor -
        # yerel bir yönlendirme bilgisi. Uzak uç nokta onu tanımıyor; gövdeye
        # sızması hem sözleşmeyi bozar hem de "ne gönderdiğimizi biliyoruz"
        # güvencesini zayıflatır.
        self._reply([("a", "x")])
        prompt = llm.build_prompt("a", "s", "u")
        prompt["agent"] = "olcme-degerlendirme"
        llm.run_agent_prompts([prompt], self.url)

        sent = _received[0]["agents"][0]
        self.assertNotIn("agent", sent)
        self.assertEqual(sorted(sent), ["name", "system", "user"])

    def test_retrieval_block_does_reach_the_wire(self):
        # Beyaz liste, tanınan alanları elemekle "koruma" yapmamalı: getirim
        # bloğu düşerse teşhisler bağlamsız üretilir ve kimse fark etmez.
        self._reply([("a", "x")])
        prompt = llm.build_prompt("a", "s", "u")
        prompt["retrieval"] = {"programId": "tde9", "topK": 8}
        llm.run_agent_prompts([prompt], self.url)
        self.assertEqual(_received[0]["agents"][0]["retrieval"], {"programId": "tde9", "topK": 8})

    def test_max_tokens_is_sent_only_when_asked(self):
        self._reply([("a", "x")])
        llm.run_agent_prompts([llm.build_prompt("a", "s", "u", max_tokens=256)], self.url)
        self.assertEqual(_received[0]["agents"][0]["maxTokens"], 256)

    def test_sources_are_passed_through(self):
        # Getirim isabetleri düşerse çağıran taraf "kaynak yok" sanıp her
        # teşhisi eler - getirim mükemmel çalışsa bile rapor boş kalır.
        _response.update({
            "ok": True,
            "message": "ok",
            "structuredData": {"results": [
                {"name": "ajan-0", "answer": "teşhis", "sources": [{"documentName": "tdeogr.pdf"}]}
            ]},
        })
        _ok, _message, results = llm.run_agent_prompts(self._prompts(1), self.url)
        self.assertEqual(results[0]["sources"], [{"documentName": "tdeogr.pdf"}])

    def test_missing_sources_becomes_an_empty_list(self):
        self._reply([("ajan-0", "teşhis")])  # sunucu `sources` göndermezse
        _ok, _message, results = llm.run_agent_prompts(self._prompts(1), self.url)
        self.assertEqual(results[0]["sources"], [])

    def test_results_keep_input_order(self):
        self._reply([("ajan-0", "birinci"), ("ajan-1", "ikinci"), ("ajan-2", "üçüncü")])
        _ok, _message, results = llm.run_agent_prompts(self._prompts(3), self.url)
        self.assertEqual([item["name"] for item in results], ["ajan-0", "ajan-1", "ajan-2"])
        self.assertEqual([item["answer"] for item in results], ["birinci", "ikinci", "üçüncü"])

    # --- Charter süzgeci her yanıta uygulanıyor ---

    def test_charter_filter_is_applied_to_every_answer(self):
        self._reply([
            ("a", "Öğrenme kaybı vardır. Ek çalışma yapılması önerilir."),
            ("b", "Analiz düzeyinde eksiklik var. Telafi programı uygulanmalıdır."),
        ])
        _ok, _message, results = llm.run_agent_prompts(self._prompts(2), self.url)

        self.assertEqual(results[0]["answer"], "Öğrenme kaybı vardır.")
        self.assertEqual(results[0]["strippedSentences"], 1)
        self.assertEqual(results[1]["answer"], "Analiz düzeyinde eksiklik var.")
        self.assertEqual(results[1]["strippedSentences"], 1)

    def test_diagnostic_language_survives_the_filter(self):
        # "gerektirir" reçete değil teşhis - elenmemeli.
        self._reply([("a", "Bu kazanım analiz becerisi gerektirir.")])
        _ok, _message, results = llm.run_agent_prompts(self._prompts(1), self.url)
        self.assertEqual(results[0]["answer"], "Bu kazanım analiz becerisi gerektirir.")
        self.assertEqual(results[0]["strippedSentences"], 0)

    # --- Asla istisna fırlatmaz ---

    def test_remote_failure_returns_false_without_raising(self):
        self._reply([], ok=False, message="Ajan yanıtları üretilemedi: patladı", status=500)
        ok, message, results = llm.run_agent_prompts(self._prompts(2), self.url)
        self.assertFalse(ok)
        self.assertIsNone(results)
        self.assertIn("üretilemedi", message)

    def test_unreachable_remote_returns_false_without_raising(self):
        ok, message, results = llm.run_agent_prompts(self._prompts(1), "http://127.0.0.1:9")
        self.assertFalse(ok)
        self.assertIsNone(results)
        self.assertIn("ulaşılamadı", message)

    def test_count_mismatch_drops_everything(self):
        # Eşleştirme sıraya dayalı; sayı tutmuyorsa yanlış ajana yanlış yanıt
        # bağlamaktansa hepsini düşür.
        self._reply([("ajan-0", "tek yanıt")])
        ok, message, results = llm.run_agent_prompts(self._prompts(3), self.url)
        self.assertFalse(ok)
        self.assertIsNone(results)
        self.assertIn("eşleşmedi", message)

    def test_empty_and_oversized_batches_never_reach_the_network(self):
        for items, fragment in (([], "yok"), (self._prompts(17), "en çok")):
            with self.subTest(count=len(items)):
                ok, message, results = llm.run_agent_prompts(items, self.url)
                self.assertFalse(ok)
                self.assertIsNone(results)
                self.assertIn(fragment, message)
        self.assertEqual(_received, [], "Geçersiz parti ağ turu harcamamalı.")

    # --- İz kaydı ---

    def test_trace_entry_carries_counts_but_no_text(self):
        self._reply([("a", "Öğrenme kaybı vardır. Telafi önerilir.")])
        _ok, _message, results = llm.run_agent_prompts(self._prompts(1), self.url)
        entry = llm.trace_entry(results[0])

        self.assertEqual(entry["agent"], "ajan-0")
        self.assertEqual(entry["strippedSentences"], 1)
        self.assertGreater(entry["promptChars"], 0)
        blob = repr(entry)
        self.assertNotIn("Öğrenme kaybı", blob, "İz, yanıt metnini taşımamalı.")
        self.assertNotIn("kullanici", blob, "İz, prompt metnini taşımamalı.")


if __name__ == "__main__":
    unittest.main()
