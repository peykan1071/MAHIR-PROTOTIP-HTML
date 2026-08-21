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
from backend.app.agents.pipeline import _sanitize_anomaly_finding
from backend.app.approved_data_analyzer import (
    analyze_approved_data,
    analyze_approved_data_traced,
)

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
    """`run_agent_prompts` yerine geçer; gönderilen kuyruğu kaydeder.

    Dönen sözlük GERÇEK `run_agent_prompts` çıktısının tüm alanlarını taşır.
    Eksik bırakmak bedava değil: Faz 3'te sahte yanıtta `sources` yoktu, gerçek
    uçtan gelen alan istemcide düşürülüyordu ve hiçbir birim testi görmedi -
    canlı koşuda 0/8 teşhisle ortaya çıktı.
    """

    calls = []

    def fake(items, remote_url):
        calls.append(items)
        return True, "ok", [
            {
                "name": item["name"],
                "answer": answer,
                "sources": [{"documentName": "x"}] if "retrieval" in item else [],
                "strippedSentences": 0,
                "promptChars": len(item.get("system", "")) + len(item.get("user", "")),
                "answerChars": len(answer),
                "durationMs": 1.0,
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

    def test_strong_outcomes_are_also_sent_in_the_single_round(self):
        # İki soruluk sınavda anomali örüntüsü yoktur; buna rağmen güçlü
        # öğrenme çıktıları, başarıyı sürdürme ve zenginleştirme bağlamı için
        # Pedagojik Analiz Ajanı tarafından aynı tek LLM turuna alınır.
        payload = _tde_payload()
        payload["questions"] = payload["questions"][:2]
        payload["students"] = [{"studentRef": "Ö-001", "scores": [10, 10]}]

        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(payload)

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 2)
        self.assertTrue(all(item["name"].startswith("pedagoji/") for item in calls[0]))

    def test_no_request_when_remote_is_not_configured(self):
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                result = analyze_approved_data(_tde_payload())

        self.assertEqual(calls, [])
        self.assertEqual(result["summary"]["anomalies"], "")


class LlmTraceTests(unittest.TestCase):
    """Faz 2'de söz verilen `AgentTrace.llm_calls` gerçekten doluyor mu."""

    def _trace(self, answer=""):
        calls, fake = _capture(answer=answer)
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                _analysis, trace = analyze_approved_data_traced(_tde_payload())
        return {entry["agent"]: entry for entry in trace["agents"]}

    def test_llm_calls_land_on_the_agent_that_queued_the_prompt(self):
        # Sahiplik prompt ADINDAN çıkarılsaydı teşhisler ("pedagoji/...")
        # hiçbir ajana bağlanamaz, anomali ise doğru ajana denk gelip sorunu
        # gizlerdi.
        # Üç zayıf çıktı -> üç teşhis prompt'u; anomali prompt'u tek.
        agents = self._trace(answer="teşhis")
        self.assertEqual(len(agents["olcme-degerlendirme"]["llmCalls"]), 1)
        self.assertEqual(len(agents["pedagojik-analiz"]["llmCalls"]), 3)

    def test_agents_without_an_llm_role_stay_empty(self):
        agents = self._trace(answer="teşhis")
        for name in ("belge-anlama", "program-eslestirme", "raporlama"):
            with self.subTest(agent=name):
                self.assertEqual(agents[name]["llmCalls"], [])

    def test_llm_call_records_carry_counts_but_no_text(self):
        agents = self._trace(answer="Öğrenme kaybı vardır.")
        record = agents["pedagojik-analiz"]["llmCalls"][0]
        self.assertGreater(record["promptChars"], 0)
        self.assertIn("answerChars", record)
        self.assertNotIn("Öğrenme kaybı", repr(record), "İz, yanıt metnini taşımamalı.")

    def test_the_shared_round_is_traced_as_one_request(self):
        # Faz 3'ün asıl iddiası burada görünür hâle geliyor: dört LLM istemi,
        # TEK tur. Süre ajanlara bölüştürülmüyor - paylaştırmak uydurma olurdu.
        calls, fake = _capture(answer="teşhis")
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                _analysis, trace = analyze_approved_data_traced(_tde_payload())

        self.assertEqual(trace["llmRound"]["promptCount"], 4)
        self.assertEqual(trace["llmRound"]["resultCount"], 4)
        self.assertTrue(trace["llmRound"]["ok"])
        self.assertGreaterEqual(trace["llmRound"]["durationMs"], 0.0)

    def test_no_round_leaves_the_record_empty(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            _analysis, trace = analyze_approved_data_traced(_tde_payload())
        self.assertEqual(trace["llmRound"], {})

    def test_failed_round_is_traced_as_not_ok(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch(
                "backend.app.agents.llm.run_agent_prompts",
                return_value=(False, "ulaşılamadı", None),
            ):
                _analysis, trace = analyze_approved_data_traced(_tde_payload())
        self.assertFalse(trace["llmRound"]["ok"])
        self.assertEqual(trace["llmRound"]["resultCount"], 0)

    def test_failed_round_leaves_llm_calls_empty(self):
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch(
                "backend.app.agents.llm.run_agent_prompts",
                return_value=(False, "ulaşılamadı", None),
            ):
                _analysis, trace = analyze_approved_data_traced(_tde_payload())
        for entry in trace["agents"]:
            with self.subTest(agent=entry["agent"]):
                self.assertEqual(entry["llmCalls"], [])


class DiagnosisSourceTests(unittest.TestCase):
    """Teşhisin dayandığı belge/sayfa öğretmene ulaşıyor mu.

    Veri uçtan zaten geliyordu; `apply_llm` yalnız "kaynak var mı" diye bakıp
    listeyi atıyordu - teşhis raporda görünüyor ama neye dayandığı görünmüyordu.
    """

    def _outcomes(self, sources):
        def fake(items, remote_url):
            return True, "ok", [
                {
                    "name": item["name"],
                    "answer": "teşhis" if "retrieval" in item else "",
                    "sources": sources if "retrieval" in item else [],
                    "strippedSentences": 0,
                }
                for item in items
            ]

        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                return analyze_approved_data(_tde_payload())["outcomes"]

    def test_document_and_pages_reach_the_analysis(self):
        outcomes = self._outcomes([
            {"documentName": "tdeogr.pdf", "pages": [66]},
            {"documentName": "tdeogr.pdf", "pages": [67]},
        ])
        self.assertEqual(
            outcomes[0]["ragSources"], [{"documentName": "tdeogr.pdf", "pages": [66, 67]}]
        )

    def test_hits_from_one_document_collapse_to_a_single_entry(self):
        # Sekiz isabet çoğu zaman aynı belgenin komşu sayfalarından gelir;
        # hepsini ayrı satır göstermek raporu kaynak listesiyle doldururdu.
        outcomes = self._outcomes([{"documentName": "tdeogr.pdf", "pages": [66]}] * 8)
        self.assertEqual(len(outcomes[0]["ragSources"]), 1)
        self.assertEqual(outcomes[0]["ragSources"][0]["pages"], [66])

    def test_two_documents_stay_separate(self):
        outcomes = self._outcomes([
            {"documentName": "tdeogr.pdf", "pages": [66]},
            {"documentName": "ek-kilavuz.pdf", "pages": [4, 3]},
        ])
        by_name = {item["documentName"]: item["pages"] for item in outcomes[0]["ragSources"]}
        self.assertEqual(by_name["tdeogr.pdf"], [66])
        self.assertEqual(by_name["ek-kilavuz.pdf"], [3, 4], "Sayfalar sıralı olmalı.")

    def test_malformed_source_entries_are_dropped_not_raised(self):
        # Uzak uç sözleşmeyi bozarsa alan boş kalır; analiz kesilmez.
        outcomes = self._outcomes([
            {"documentName": "", "pages": [5]},
            {"pages": [7]},
            {"documentName": "tdeogr.pdf", "pages": ["altmışaltı", -3, None]},
            "bozuk",
        ])
        self.assertEqual(
            outcomes[0]["ragSources"], [{"documentName": "tdeogr.pdf", "pages": []}]
        )

    def test_field_is_always_present_even_without_a_diagnosis(self):
        # Alan varlığı öngörülebilir olmalı - `ragContext` ile aynı ilke.
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", ""):
            outcomes = analyze_approved_data(_tde_payload())["outcomes"]
        for outcome in outcomes:
            with self.subTest(code=outcome["outcomeCode"]):
                self.assertEqual(outcome["ragSources"], [])


class AnomalyAgentTests(unittest.TestCase):
    def test_only_existing_question_numbers_are_accepted(self):
        answer = "\n".join((
            "- Soru 2: diğer sorulardan ayrışıyor.",
            "- Soru 99: puanlama hatası olabilir.",
            "Genel olarak sınav sorunludur.",
        ))
        self.assertEqual(
            _sanitize_anomaly_finding(answer, {1, 2, 3}),
            "- Soru 2: diğer sorulardan ayrışıyor.",
        )

    def test_at_most_three_valid_anomaly_lines_are_kept(self):
        answer = "\n".join(f"- Soru {number}: gözlem." for number in range(1, 6))
        cleaned = _sanitize_anomaly_finding(answer, {1, 2, 3, 4, 5})
        self.assertEqual(cleaned.count("- Soru"), 3)
        self.assertNotIn("Soru 4", cleaned)

    def test_free_text_anomaly_claim_is_rejected(self):
        self.assertEqual(
            _sanitize_anomaly_finding("Bu sınavda ciddi bir sorun vardır.", {1, 2, 3}),
            "",
        )

    def test_no_llm_prompt_carries_institutional_identity(self):
        payload = _tde_payload()
        payload["exam"].update({
            "schoolName": "Örnek Kimlikli Okul",
            "teacherName": "Örnek Kimlikli Öğretmen",
            "province": "Örnek İl",
            "district": "Örnek İlçe",
            "documentNumber": "EVRAK-123",
        })
        calls, fake = _capture()
        with patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", _FAKE_URL):
            with patch("backend.app.agents.llm.run_agent_prompts", side_effect=fake):
                analyze_approved_data(payload)

        blob = "\n".join(item["system"] + item["user"] for item in calls[0])
        for private_value in (
            "Örnek Kimlikli Okul", "Örnek Kimlikli Öğretmen", "Örnek İl", "Örnek İlçe", "EVRAK-123"
        ):
            self.assertNotIn(private_value, blob)

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


class DiagnosisPromptContractTests(unittest.TestCase):
    """Teşhis prompt'unun taşıması ve TAŞIMAMASI gerekenler.

    Prompt metni üretim davranışının kendisi: canlı ölçüm olmadan kalitesi
    doğrulanamaz ama sözleşmesi doğrulanabilir. Buradaki testler, ölçümle
    kazanılmış kararların bir sonraki düzenlemede sessizce geri alınmasını
    engelliyor.
    """

    PROMPT = prompts.DIAGNOSIS_SYSTEM_PROMPT

    def test_bloom_taxonomy_is_gone(self):
        # Kaldırma gerekçesi ölçüldü: 8/8 yanıt Bloom cümlesiyle açılıyordu,
        # tema adı 0/8 yanıtta geçiyordu.
        for term in ("Bloom", "bilişsel düzey", "basamak", "Hatırlama", "Yaratma"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.PROMPT)

    def test_grounding_is_required_not_suggested(self):
        # Teşhisi değerli kılan tek şey: yalnız getirimin bilebileceği içeriği
        # kullanması. İstek "yapabilirsin" değil, ZORUNLULUK olmalı.
        self.assertIn("DEMİRLE", self.PROMPT)
        self.assertIn("ZORUNDA", self.PROMPT)
        self.assertIn("BAŞARISIZ sayılır", self.PROMPT)

    def test_filler_words_are_banned(self):
        # Ölçüm: "belirli" 14 kez, 8 yanıtın 4'ünde.
        for word in ("belirli", "genellikle", "bazı", "birtakım"):
            with self.subTest(word=word):
                self.assertIn(f'"{word}"', self.PROMPT)

    def test_length_budget_is_stated_as_a_hard_cap(self):
        # İlk sürüm "40-70 kelime" diyordu ve 8 yanıtın 3'ü 73-75 kelimeye
        # çıktı; sınırın katı olduğunu söylemek gerekiyor.
        self.assertIn("EN ÇOK 70 KELİME", self.PROMPT)
        self.assertIn("40 kelimenin altına da düşme", self.PROMPT)

    def test_theme_name_must_open_the_answer(self):
        # Ölçüm: demirleme zorunluluğu tek başına tema adını yanıta sokmadı
        # (2/8). Açılışı şart koşunca 7-8/8'e çıktı.
        self.assertIn("tema adını tırnak içinde YAZARAK başla", self.PROMPT)
        self.assertIn("SORU'dan birebir kopyala", self.PROMPT)

    def test_prompt_gives_no_theme_name_as_an_example(self):
        # BU BİR HATA KAYDIDIR. Açılış kuralı önce örnekle yazılmıştı
        # (ör. "'Sözün İnceliği' temasında..."); model örneği KOPYALADI ve
        # 4. Tema kazanımlarına "'Sözün İnceliği' temasında" diye başladı -
        # yani öğretmene BAŞKA bir temanın teşhisini doğruymuş gibi gösterdi.
        # Prompt'ta kopyalanabilir somut bir tema adı bulunmamalı.
        for theme in ("Sözün İnceliği", "Anlam Arayışı", "Anlamın Yapı Taşları", "Dilin Zenginliği"):
            with self.subTest(theme=theme):
                self.assertNotIn(theme, self.PROMPT)

    def test_inventing_outcome_codes_is_forbidden(self):
        # Ölçümde model sarmal risk cümlesinde var olmayan kodlar üretti
        # (ör. teşhis ettiği kazanımı "gelecekteki kazanım" diye andı).
        self.assertIn("kod UYDURMA", self.PROMPT)

    def test_activity_names_are_banned_not_just_recommendations(self):
        # Charter süzgeci "gerekli olan"ı bilerek koruyor (teşhis dili), ama
        # ölçümde model "gerekli olan ... analiz ETKİNLİKLERİNE" yazdı: öneri
        # kipi olmadan etkinlik ADLANDIRMAK da charter ihlali.
        self.assertIn("YAPILACAK İŞ", self.PROMPT)
        self.assertIn("ne önererek ne de betimleyerek", self.PROMPT)

    def test_measured_mechanisms_survived(self):
        # Bunlar ölçümde çalışıyordu (8/8 doğru şiddet, 0 öneri sızıntısı);
        # prompt yeniden yazılırken düşmemeleri şart.
        self.assertIn("Eksikliğin şiddeti: <etiket>.", self.PROMPT)
        self.assertIn("Bu bilgi belgede bulunmuyor.", self.PROMPT)
        self.assertIn("ÇÖZÜM ÖNERME", self.PROMPT)
        self.assertIn("tek akıcı paragraf", self.PROMPT)


if __name__ == "__main__":
    unittest.main()
