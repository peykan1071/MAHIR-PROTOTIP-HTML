"""Sunucu tarafı `agents` sözleşmesinin karakterizasyon testleri.

`backend/app/agents/llm.py` şu sözleşmeye bağlı: `{"agents": [...]}` gönderir,
`structuredData.results` içinde GİRİŞ SIRASIYLA `{name, answer, sources}` bekler.
Bu dosya o sözleşmenin sunucu tarafındaki anlamını - hangi öğenin LLM'e gittiği,
bağlamın user mesajına nasıl eklendiği, isabetsiz öğenin ne aldığı, sınırlar -
uygulamadan bağımsız biçimde sabitler.

Testler `_Backend` adaptörü üzerinden yazıldı: gövdeler uygulamaya değil
sözleşmeye bakar. Sunucu tarafı taşındığında yalnız adaptör değişir, test
gövdeleri aynen koşar - refactor öncesi/sonrası kanıt bu şekilde üretilir.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

NO_ANSWER_TEXT = "Bu bilgi belgede bulunmuyor."
_LOCAL_DIR = Path(__file__).resolve().parents[1] / "local"


def _load_local_service():
    """`local/rag_service.py`'yi dosya yolundan bir kez yükler (paket değil; kendi sys.path'ini kurar)."""

    name = "local_rag_service"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _LOCAL_DIR / "rag_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass/annotation çözümü modülü sys.modules'ta arar
    spec.loader.exec_module(module)
    return module


class _Hit:
    """`_build_sources` için minimum Qdrant isabeti (payload + score)."""

    def __init__(self, payload, score):
        self.payload = payload
        self.score = score


class _Backend:
    """Sözleşme adaptörü - sunucu tarafı uygulamasını test gövdelerinden ayırır.

    `contexts`/`sources`: öğe indeksine göre getirim sonucu (yoksa isabetsiz).
    `reply`: konuşma (mesaj listesi) -> yanıt metni.
    `conversations`: LLM'e gerçekten gönderilen konuşmalar, gönderim sırasıyla.
    `max_tokens_seen`: her üretim çağrısında kullanılan `max_tokens`.
    """

    def __init__(self, contexts=None, sources=None, reply=None, retrieval_error=None):
        self.contexts = dict(contexts or {})
        self.sources = dict(sources or {})
        self.reply = reply or (lambda conversation: "yanıt")
        self.retrieval_error = retrieval_error
        self.conversations = []
        self.max_tokens_seen = []
        self.llm_error = None

    # --- uygulamaya bağlı kısım: local/rag_service.py ---

    def _service(self, items):
        module = _load_local_service()
        # local/.env makineye özgü; sözleşme testi varsayılanlarla koşar
        # (LLM_MAX_TOKENS=1024 tavanı, 8k pencere). Var olmayan dosya -> yalnız varsayılanlar.
        with patch.dict(os.environ, {}, clear=False):
            for key in list(os.environ):
                if key.startswith(("LLM_", "RAG_", "RERANKER_", "EMBEDDING_", "QDRANT_", "OCR_")):
                    os.environ.pop(key)
            settings = module.Settings.from_env(_LOCAL_DIR / ".env.does-not-exist")
        service = module.RAGService(settings)
        backend = self
        # `retrieve()` öğe sırasıyla, yalnız `retrieval` taşıyanlar için çağrılır.
        pending = [index for index, item in enumerate(items) if isinstance(item.get("retrieval"), dict)]

        def fake_retrieve(question, top_k=None, program_id=None, document_name=None, rerank=None, **_filters):
            if backend.retrieval_error:
                raise module.RetrievalError(backend.retrieval_error)
            index = pending.pop(0)
            if index not in backend.contexts:
                return module.RetrievalResult(hits=[], reranked=False, pool_size=0)
            hit = module.Hit(
                point_id=str(index),
                payload={"contextualized_text": backend.contexts[index], "text": backend.contexts[index], "_index": index},
                retrieval_score=1.0,
            )
            return module.RetrievalResult(hits=[hit], reranked=False, pool_size=1)

        def fake_chat(messages, max_tokens):
            if backend.llm_error:
                raise backend.llm_error
            backend.conversations.append(messages)
            backend.max_tokens_seen.append(max_tokens)
            return backend.reply(messages)

        service.retrieve = fake_retrieve
        service._chat = fake_chat
        return module, service

    def run(self, items):
        """`(ok, message, results)` - HTTP zarfının `structuredData.results` kısmı."""

        module, service = self._service(items)
        # Kaynak listesi isabetin payload'ından türetilir; sözleşme testi kaynağı
        # olduğu gibi geri bekler - üretimi adaptörde kısa devre ederiz.
        with patch.object(module, "build_agent_sources", lambda hits: self.sources[hits[0].payload["_index"]]):
            return service.run_agent_prompts(items)

    def reject(self, items):
        return _load_local_service().reject_agent_prompts(items)

    def build_sources(self, hits):
        module = _load_local_service()
        return module.build_agent_sources(
            [module.Hit(point_id="p", payload=hit.payload, retrieval_score=hit.score) for hit in hits]
        )

    def warmup(self):
        """`{"warmup": true}` gövdesine HTTP zarfı: `(status, body_dict)`."""

        module, service = self._service([])
        service.warm_up = lambda: None  # modelleri indirmeden
        return module.handle_agents_request(service, {"warmup": True})


def _item(name, user="kullanıcı metni", system="sistem", retrieval=None, max_tokens=None):
    item = {"name": name, "system": system, "user": user}
    if retrieval is not None:
        item["retrieval"] = retrieval
    if max_tokens is not None:
        item["maxTokens"] = max_tokens
    return item


_RETRIEVAL = {"programId": "tde-9-tymm", "grade": "9", "theme": "Anlamın Yapı Taşları", "query": "q", "topK": 8}


class AgentBatchContractTests(unittest.TestCase):
    def test_results_keep_input_order_and_echo_names(self):
        backend = _Backend(reply=lambda conversation: conversation[1]["content"].upper())
        ok, message, results = backend.run([_item("olcme", user="a"), _item("pedagoji", user="b")])

        self.assertTrue(ok, message)
        self.assertEqual([result["name"] for result in results], ["olcme", "pedagoji"])
        self.assertEqual([result["answer"] for result in results], ["A", "B"])

    def test_item_without_retrieval_goes_out_as_plain_prompt(self):
        backend = _Backend()
        backend.run([_item("olcme", system="S", user="U")])

        self.assertEqual(len(backend.conversations), 1)
        self.assertEqual(backend.conversations[0][0], {"role": "system", "content": "S"})
        self.assertEqual(backend.conversations[0][1], {"role": "user", "content": "U"})

    def test_retrieved_context_is_prepended_to_the_user_message(self):
        backend = _Backend(contexts={0: "MÜFREDAT PARÇASI"}, sources={0: [{"documentName": "x"}]})
        ok, _message, results = backend.run([_item("pedagoji", user="TEŞHİS ET", retrieval=_RETRIEVAL)])

        self.assertTrue(ok)
        self.assertEqual(backend.conversations[0][1]["content"], "BAĞLAM:\nMÜFREDAT PARÇASI\n\nTEŞHİS ET")
        self.assertEqual(results[0]["sources"], [{"documentName": "x"}])

    def test_item_with_empty_retrieval_never_reaches_the_llm(self):
        backend = _Backend(contexts={1: "bağlam"}, sources={1: [{"documentName": "y"}]})
        items = [
            _item("bos", retrieval=_RETRIEVAL),
            _item("dolu", user="U2", retrieval=_RETRIEVAL),
            _item("duz", user="U3"),
        ]
        ok, _message, results = backend.run(items)

        self.assertTrue(ok)
        self.assertEqual(len(backend.conversations), 2, "İsabetsiz öğe partiye girmemeli.")
        self.assertEqual(results[0], {"name": "bos", "answer": NO_ANSWER_TEXT, "sources": []})
        self.assertEqual(results[1]["name"], "dolu")
        self.assertNotEqual(results[1]["answer"], NO_ANSWER_TEXT)
        self.assertEqual(results[2]["name"], "duz")
        self.assertNotEqual(results[2]["answer"], NO_ANSWER_TEXT)

    def test_answers_are_stripped(self):
        backend = _Backend(reply=lambda conversation: "  teşhis \n")
        _ok, _message, results = backend.run([_item("olcme")])
        self.assertEqual(results[0]["answer"], "teşhis")

    def test_max_tokens_is_honoured_up_to_the_ceiling(self):
        backend = _Backend()
        backend.run([_item("olcme", max_tokens=256)])
        self.assertEqual(backend.max_tokens_seen, [256])

    def test_max_tokens_above_the_ceiling_is_clamped_to_1024(self):
        backend = _Backend()
        backend.run([_item("olcme", max_tokens=4096)])
        self.assertEqual(backend.max_tokens_seen, [1024])

    def test_missing_max_tokens_uses_the_ceiling(self):
        backend = _Backend()
        backend.run([_item("olcme")])
        self.assertEqual(backend.max_tokens_seen, [1024])

    def test_retrieval_failure_fails_the_whole_batch(self):
        backend = _Backend(retrieval_error="Belge dizininden okunamadı: x")
        ok, message, results = backend.run([_item("a", retrieval=_RETRIEVAL), _item("b")])

        self.assertFalse(ok)
        self.assertIn("okunamadı", message)
        self.assertIsNone(results)
        self.assertEqual(backend.conversations, [], "Getirim düşerse üretim başlamamalı.")

    def test_generation_failure_returns_false_with_a_turkish_message(self):
        backend = _Backend()
        backend.llm_error = RuntimeError("CUDA OOM")
        ok, message, results = backend.run([_item("a")])

        self.assertFalse(ok)
        self.assertIn("Ajan yanıtları üretilemedi", message)
        self.assertIsNone(results)

    def test_all_items_without_retrieval_never_touch_retrieval(self):
        backend = _Backend(retrieval_error="çağrılmamalıydı")
        ok, _message, _results = backend.run([_item("a"), _item("b")])
        self.assertTrue(ok, "retrieval taşımayan parti getirim katmanına hiç dokunmamalı.")


class AgentPromptValidationTests(unittest.TestCase):
    def setUp(self):
        self.backend = _Backend()

    def test_valid_batch_passes(self):
        self.assertEqual(self.backend.reject([_item("a"), _item("b")]), "")

    def test_more_than_16_prompts_are_rejected(self):
        self.assertIn("16", self.backend.reject([_item(str(i)) for i in range(17)]))
        self.assertEqual(self.backend.reject([_item(str(i)) for i in range(16)]), "")

    def test_non_dict_item_is_rejected_with_its_position(self):
        self.assertIn("2.", self.backend.reject([_item("a"), "bozuk"]))

    def test_missing_system_or_user_is_rejected(self):
        self.assertIn("system ve user", self.backend.reject([_item("a", system="   ")]))
        self.assertIn("system ve user", self.backend.reject([_item("a", user="")]))

    def test_prompt_over_8000_chars_is_rejected(self):
        self.assertIn("8000", self.backend.reject([_item("a", system="s" * 4000, user="u" * 4001)]))
        self.assertEqual(self.backend.reject([_item("a", system="s" * 4000, user="u" * 4000)]), "")


class SourceShapeTests(unittest.TestCase):
    def test_sources_carry_the_camel_case_schema(self):
        hit = _Hit(
            {
                "document_name": "Program",
                "grade": "9",
                "theme": "Tema",
                "pages": [3, 4],
                "headings": ["Okuma"],
                "text": "x" * 500,
            },
            0.87,
        )
        [source] = _Backend().build_sources([hit])

        self.assertEqual(
            set(source), {"documentName", "grade", "theme", "pages", "headings", "excerpt", "score"}
        )
        self.assertEqual(source["documentName"], "Program")
        self.assertEqual(source["pages"], [3, 4])
        self.assertEqual(len(source["excerpt"]), 300)
        self.assertEqual(source["score"], 0.87)

    def test_missing_payload_fields_are_safe(self):
        [source] = _Backend().build_sources([_Hit({}, 0.5)])
        self.assertIsNone(source["documentName"])
        self.assertEqual(source["pages"], [])
        self.assertEqual(source["headings"], [])
        self.assertEqual(source["excerpt"], "")


class WarmUpEnvelopeTests(unittest.TestCase):
    def test_warmup_returns_ready_without_running_a_query(self):
        status, body = _Backend().warmup()

        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["structuredData"], {"ready": True})
        self.assertIsInstance(body["message"], str)


if __name__ == "__main__":
    unittest.main()
