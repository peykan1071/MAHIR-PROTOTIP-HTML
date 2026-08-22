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

    2026-08-22 (2. sürüm): Görev "BAĞLAM'dan İKİ çıplak terim seç"ten "her
    terim için `exactTerm`+`pedagogicalRole`+`gapRationale`/
    `strengthRationale` taşıyan yapılandırılmış bir kanıt listesi döndür"e
    geçti (kullanıcının paylaştığı prompt taslağı, `agents/prompts.py`ye
    birebir uygulandı). ÖNEMLİ bir gözlem: bu yeni promptun metninde artık
    ÖNCEKİ sürümdeki gibi açıkça yazılı bir "öneri/etkinlik cümlesi
    olmasın", "kod UYDURMA" maddesi YOK - yalnızca "başarı oranını terim
    olarak alma" ve dolaylı "spekülasyon yapma" uyarıları var. Bu KASITLI
    bir gevşetme değil; kullanıcının prompt taslağı böyle geldi ve olduğu
    gibi uygulandı. Charter güvencesi bu yüzden artık PROMPT METNİNDE değil
    KOD TARAFINDA duruyor: `_compose_grounded_pedagogical_answer` her
    gerekçeyi `charter_guard.strip_recommendation_sentences`den geçirir,
    ardından `_answer_matches_outcome_scope` kod uydurma/beceri kayması gibi
    kalan riskleri denetler. `test_prompt_no_longer_states_an_explicit_
    recommendation_ban` bu boşluğu bilerek belgeliyor.
    """

    DIAGNOSIS_PROMPT = prompts.DIAGNOSIS_SYSTEM_PROMPT
    STRENGTH_PROMPT = prompts.STRENGTH_SYSTEM_PROMPT

    def test_bloom_taxonomy_is_gone(self):
        # Kaldırma gerekçesi ölçüldü: 8/8 yanıt Bloom cümlesiyle açılıyordu,
        # tema adı 0/8 yanıtta geçiyordu. Yapılandırılmış kanıt seçiminde bu
        # dile zaten yer yok ama gerileme koruması olarak kalsın.
        for term in ("Bloom", "bilişsel düzey", "basamak", "Hatırlama", "Yaratma"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.DIAGNOSIS_PROMPT)

    def test_prompt_gives_no_theme_name_as_an_example(self):
        # BU BİR HATA KAYDIDIR (önceki sürümden). Açılış kuralı önce
        # örnekle yazılmıştı; model örneği KOPYALADI ve başka bir temanın
        # teşhisini doğruymuş gibi gösterdi. Bu risk artık yapısal olarak
        # da kapalı (tema adını model değil MAHİR'in şablonu yazıyor) ama
        # prompt'ta yine de kopyalanabilir somut bir tema adı bulunmamalı.
        for theme in ("Sözün İnceliği", "Anlam Arayışı", "Anlamın Yapı Taşları", "Dilin Zenginliği"):
            with self.subTest(theme=theme):
                self.assertNotIn(theme, self.DIAGNOSIS_PROMPT)

    def test_grounding_to_context_is_required(self):
        self.assertIn("BAĞLAMA VE VERİYE DEMİRLE", self.DIAGNOSIS_PROMPT)
        self.assertIn("BİREBİR geçen terimleri", self.DIAGNOSIS_PROMPT)
        self.assertIn("Soru metnini görmediğini unutma", self.DIAGNOSIS_PROMPT)

    def test_success_rate_leaking_as_a_term_is_banned(self):
        # Bu oturumun ayrı bir kök nedeni: SORU'daki başarı oranı modelin
        # "kanıt terimi" olarak seçtiği bir tuzaktı (bkz. approved_data_
        # analyzer.py::_build_rag_question'ın 2026-08-22 notu).
        self.assertIn("Başarı oranını", self.DIAGNOSIS_PROMPT)
        self.assertIn("kanıt terimi olarak alma", self.DIAGNOSIS_PROMPT)
        self.assertIn("Başarı oranını", self.STRENGTH_PROMPT)
        self.assertIn("terim olarak seçme", self.STRENGTH_PROMPT)

    def test_not_found_sentinel_is_json_not_plain_text(self):
        # Eski sürümde "Bu bilgi belgede bulunmuyor." düz metniydi;
        # `apply_llm` artık `_is_not_found_response` ile bu JSON durumunu
        # ayrıca tanıyor (bkz. pipeline.py).
        for prompt in (self.DIAGNOSIS_PROMPT, self.STRENGTH_PROMPT):
            with self.subTest(prompt=prompt[:20]):
                self.assertIn('"status": "not_found"', prompt)

    def test_output_schema_requires_structured_evidence(self):
        # Kök nedenin kendisi: prompt artık çıplak iki terim değil, her biri
        # `exactTerm`+`pedagogicalRole`+gerekçe taşıyan bir `evidence` listesi
        # istemeli - `_compose_grounded_pedagogical_answer` yalnız bu biçimi
        # ayrıştırabiliyor.
        for prompt in (self.DIAGNOSIS_PROMPT, self.STRENGTH_PROMPT):
            with self.subTest(prompt=prompt[:20]):
                self.assertIn('"status": "success"', prompt)
                self.assertIn('"evidence"', prompt)
                self.assertIn('"exactTerm"', prompt)
                self.assertIn('"pedagogicalRole"', prompt)
        self.assertIn('"gapRationale"', self.DIAGNOSIS_PROMPT)
        self.assertIn('"strengthRationale"', self.STRENGTH_PROMPT)

    def test_evidence_count_is_bounded_at_one_to_two_not_forced_to_two(self):
        # 2026-08-22 canlı ölçüm, 3. sürüm: madde eklenmeden ÖNCE model 8
        # turun 6'sında yalnızca BİR kanıt öğesi döndürdü (`evidence` dizisi
        # şemada örnekle 2 gösteriliyordu ama KURAL olarak yazılı değildi) -
        # `_compose_grounded_pedagogical_answer` o zaman tam 2 öğe şart
        # koştuğundan bu, ölçülen 2/8 başarı oranına yol açtı.
        #
        # 4. sürüm: "TAM OLARAK İKİ" zorunluluğu GEVŞETİLDİ - dar kapsamlı
        # bazı kazanımlarda BAĞLAM'da gerçekten TEK güçlü aday bulunuyordu,
        # model ikinciyi uydurmak yerine tamamen `not_found` deyip
        # öğretmene hiçbir yorum göstermiyordu. Artık BİR veya İKİ kabul
        # ediliyor; kural hâlâ İKİDEN FAZLASINI (üç ve üzeri) yasaklıyor.
        for prompt in (self.DIAGNOSIS_PROMPT, self.STRENGTH_PROMPT):
            with self.subTest(prompt=prompt[:20]):
                self.assertNotIn("TAM OLARAK İKİ", prompt)
                self.assertIn("EN AZ BİR, EN ÇOK İKİ", prompt)

    def test_prompt_no_longer_states_an_explicit_recommendation_ban(self):
        # Bu bir HATA KAYDI DEĞİL - bilinçli bir gözlem (bkz. sınıf notu).
        # Önceki sürümde burada "öneri/etkinlik CÜMLESİ olmasın", "kod
        # UYDURMA" gibi açık charter maddeleri vardı; bu yeni promptta yok.
        # Charter güvencesi artık kod tarafında (`_compose_grounded_
        # pedagogical_answer`'ın `strip_recommendation_sentences` çağrısı +
        # `_answer_matches_outcome_scope`).
        self.assertNotIn("YAPILACAK İŞ", self.DIAGNOSIS_PROMPT)
        self.assertNotIn("Kod UYDURMA", self.DIAGNOSIS_PROMPT)


if __name__ == "__main__":
    unittest.main()
