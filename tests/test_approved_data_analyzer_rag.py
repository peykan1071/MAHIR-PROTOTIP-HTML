"""Tests for RAG-sourced conceptual context attached to weak outcomes."""

import unittest
from unittest.mock import patch

from backend.app.approved_data_analyzer import (
    _build_rag_question,
    _build_rag_retrieval_query,
    _normalize_theme_for_rag,
    analyze_approved_data,
)
from backend.app.agents.pipeline import (
    _answer_matches_outcome_scope,
    _compose_grounded_pedagogical_answer,
)

_FAKE_REMOTE_URL = "https://fake.example/web_query"


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
                results.append({"name": item["name"], "answer": "", "sources": []})
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
    """Kanıt garantisi 2026-08-24'te ÖLÇÜLEN bir şeye dönüştü.

    Önceki tasarımda model kendi kullandığı terimleri `groundedTerms`
    alanında BEYAN ediyor, MAHİR de o beyanı kaynağa karşı doğruluyordu.
    Canlı ölçümde model beyanı defalarca yanlış doldurdu - kendi
    cümlesinden aldığı, hatta olumsuz çekimli ifadeler yazdı ("...
    kullanamaması", "...yer vermemesi"; müfredatta böyle geçmesi imkânsız)
    ve aslında kaynağa dayalı olan iyi teşhisler bu yüzden elendi.

    Artık beyan istenmiyor: `_grounded_word_overlap` teşhis metninin
    KENDİSİ ile kaynak alıntıları arasındaki ayırt edici sözcük örtüşmesini
    ölçüyor. Garanti modelin uyumuna hiç bağlı değil - model kanıtı
    "iddia" edemez, MAHİR ölçer.
    """

    def test_grounded_diagnosis_is_wrapped_with_deterministic_facts(self):
        outcome = {
            "outcomeCode": "TDE2.2",
            "outcomeTheme": "2. Tema: Anlam Arayışı",
            "successRate": 0.20,
        }
        # Model yalnız nitel teşhis yazar; tema/yüzde/şiddet MAHİR'den gelir.
        answer = (
            '{"diagnosis":"Ana duygu, ana düşünce ve bütünlük ilişkisi kurulamamaktadır."}'
        )
        sources = [{"excerpt": "Metinde konu, ana duygu ve ana düşünce bütünlük içinde ele alınır."}]
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn('"Anlam Arayışı"', result)
        self.assertIn("%20 olarak hesaplanmıştır", result)
        self.assertIn("Eksikliğin şiddeti: Kritik.", result)
        self.assertIn("Ana duygu, ana düşünce ve bütünlük ilişkisi kurulamamaktadır.", result)
        self.assertNotIn("etkinlik", result)

    def test_diagnosis_sharing_too_little_with_the_source_is_rejected(self):
        # Genel geçer, her kazanıma yazılabilecek bir cümle: kaynakla
        # ayırt edici hiçbir sözcük paylaşmıyor.
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "Metinde ana duygu ve ana düşünce belirlenir."}]
        answer = '{"diagnosis":"Öğrenciler bu alanda yeterli düzeye ulaşamamıştır."}'
        self.assertEqual(_compose_grounded_pedagogical_answer(answer, outcome, sources), "")

    def test_negated_curriculum_vocabulary_still_counts_as_grounded(self):
        # Zayıf çıktı teşhisleri DOĞASI gereği müfredatın olumlu ifadesini
        # olumsuzlar ("tahlil edebilme" -> "tahlil edememekte"). Sözcük
        # köküne dayalı ölçüm bunu doğru biçimde kanıtlı sayar.
        outcome = {"outcomeTheme": "3. Tema: Anlamın Yapı Taşları", "successRate": 0.03}
        sources = [{
            "excerpt": (
                "Öğrencilerin metinleri olay, kişi, mekân, zaman gibi yapı "
                "unsurları bakımından tahlil edebilmeleri amaçlanmaktadır."
            )
        }]
        answer = (
            '{"diagnosis":"Olay, kişi, mekân ve zaman unsurları bakımından tahlil '
            'edememektedirler."}'
        )
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn("tahlil edememektedirler", result)

    def test_non_json_model_paragraph_is_rejected(self):
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
            '{"diagnosis":"Okuma stratejisi ve inceleme birlikteliği sınırlı '
            'kalmaktadır."}\n\n'
            "Bu bölüm modelin kaynak dışına çıkabilen serbest açıklamasıdır."
        )
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn("Okuma stratejisi ve inceleme birlikteliği", result)
        self.assertNotIn("serbest açıklama", result)

    def test_causal_language_is_preserved(self):
        # Nedensellik yasağı kaldırıldı (kullanıcı isteği + DEVELOPMENT_
        # CHARTER.md güncellemesi) - model artık "nedeniyle" gibi bağlaçlar
        # kullanabilir, MAHİR bunları kırpmaz. Bu, kasıtlı davranış
        # değişikliğinin regresyon kaydı: eski filtre yanlışlıkla geri
        # gelirse burada yakalanır.
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "Metinde ana duygu ve ana düşünce bütünlük içinde ele alınır."}]
        answer = (
            '{"diagnosis":"Ana duygu, ana düşünce ve bütünlük ilişkisi '
            'kurulamamaktadır. Bu, ayırt edememe nedeniyle ortaya çıkmıştır."}'
        )
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn("Ana duygu, ana düşünce ve bütünlük ilişkisi kurulamamaktadır.", result)
        self.assertIn("nedeniyle", result)

    def test_dangling_reference_is_removed_when_the_first_sentence_is_stripped(self):
        # İlk cümle oran tekrarı içerdiği için kırpılır (bkz.
        # _RATE_MENTION_PATTERN - nedensellik artık kırpılmıyor, kalan tek
        # tetikleyici bu), geriye kalan metin "Bu eksiklik, ..." diye
        # başlıyordu - artık var olmayan bir cümleye atıf yapan, havada kalan
        # bir paragraf öğretmene gitmemeli. Bağlayıcı öbek atılmalı.
        outcome = {"outcomeTheme": "1. Tema: Sözün İnceliği", "successRate": 0.35}
        sources = [{
            "excerpt": (
                "Metnin başlık ve görsellerinden hareketle metnin yazılış amacını "
                "tahmin eder ve içeriğini karşılaştırır."
            )
        }]
        answer = (
            '{"diagnosis":"Tahmin etme yeteneği eksiktir; %35 başarı oranı bunu '
            'göstermektedir. Bu eksiklik, metnin görsellerinden ve başlıktan '
            'amacını belirlemesine engel oluyor."}'
        )
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertNotIn("Bu eksiklik, metnin görsellerinden", result)
        self.assertIn("Metnin görsellerinden ve başlıktan amacını belirlemesine engel oluyor.", result)

    def test_consonant_mutation_counts_as_the_same_root(self):
        # Türkçe ünsüz yumuşaması: sözcük ünlüyle başlayan ek alınca sondaki
        # sert ünsüz yumuşar (içeriK -> içeriĞi). Düz önek karşılaştırması
        # bunu kaçırıyordu; canlı ölçümde "içerik" ile "içeriği" eşleşmeyince
        # kanıt sayısı bir eksik çıkıp iyi bir teşhis reddedildi.
        from backend.app.agents.pipeline import _shares_root

        for stem, inflected in (
            ("içerik", "içeriği"),
            ("kitap", "kitabı"),
            ("amaç", "amacını"),
            ("kanat", "kanadı"),
        ):
            with self.subTest(stem=stem):
                self.assertTrue(_shares_root(stem, inflected))
        # Yumuşama toleransı alakasız sözcükleri birleştirmemeli.
        self.assertFalse(_shares_root("içerik", "inceleme"))

    def test_two_distinctive_words_are_enough_evidence(self):
        # Eşik 3'ten 2'ye çekildi: tema adı ve müfredat kalıp sözcükleri
        # ("ele alınan", "hareketle") artık sayılmadığından 3, fiilen çok
        # daha yüksek bir bar hâline gelmişti ve canlı ölçümde iyi bir
        # teşhis 2/3 ile reddedildi.
        outcome = {
            "outcomeCode": "TDE3.3",
            "outcomeTheme": "1. Tema: Sözün İnceliği",
            "successRate": 0.35,
            "componentType": "speaking",
        }
        sources = [{
            "excerpt": (
                "TDE3.2. Muhatabını ikna etmek için söyleyiş inceliklerine yer veren bir "
                "konuşma içeriği oluşturabilme. TDE3.3. Muhatabını ikna etmek için "
                "konuşmada kural uygulayabilme."
            )
        }]
        answer = '{"diagnosis":"Konuşmada kural uygulama ve içerik oluşturma sınırlı kalmaktadır."}'
        result = _compose_grounded_pedagogical_answer(answer, outcome, sources)
        self.assertIn("kural uygulama ve içerik oluşturma", result)

    def test_missing_diagnosis_is_rejected(self):
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "ana duygu"}]
        self.assertEqual(_compose_grounded_pedagogical_answer("{}", outcome, sources), "")

    def test_model_still_writing_placeholder_syntax_is_rejected(self):
        # 2026-08-24: canlı ölçümde model bir önceki tasarımın {TEMA}/{ORAN}/
        # {SIDDET} yer tutucularını hiç kullanmadı, gerçek değerleri kendi
        # uydurdu - bu yüzden yer tutucu sözleşmesi tamamen kaldırıldı. Model
        # yine de eski alışkanlıkla süslü parantez yazarsa (ör. "{TEMA}"),
        # bu çirkin bir kalıntı olarak öğretmene gitmesin diye tüm yanıt
        # reddedilir.
        outcome = {"outcomeTheme": "2. Tema: Anlam Arayışı", "successRate": 0.20}
        sources = [{"excerpt": "ana duygu metinde geçer."}]
        answer = '{"diagnosis":"{TEMA} temasında ana duygu belirsizdir.","groundedTerms":["ana duygu"]}'
        self.assertEqual(_compose_grounded_pedagogical_answer(answer, outcome, sources), "")

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
        # MAHİR'in ürettiği açılış+kapanış cümleleriyle sarıldığından (bkz.
        # `_compose_grounded_pedagogical_answer`) sınır 70'ten 90'a çıktı.
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        answer = " ".join(["kanıt"] * 91)
        self.assertFalse(_answer_matches_outcome_scope(answer, outcome))

    def test_causal_language_and_student_count_are_accepted(self):
        # Nedensellik/öğrenci-sayısı yasağı kaldırıldı - bu ifadeler artık
        # kapsam denetiminden geçer. Kasıtlı davranış değişikliğinin
        # regresyon kaydı.
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        self.assertTrue(_answer_matches_outcome_scope("Düşüklüğün temel nedeni yetersiz bilgidir.", outcome))
        self.assertTrue(_answer_matches_outcome_scope("Zorluk çeken öğrencilerin sayısı yüksektir.", outcome))

    def test_activity_or_remediation_language_is_accepted(self):
        # Öneri/etkinlik yasağı kaldırıldı (DEVELOPMENT_CHARTER.md güncellendi) -
        # bu ifadeler artık kapsam denetiminden geçer.
        outcome = {"outcomeCode": "TDE1.2", "successRate": 0.30}
        self.assertTrue(_answer_matches_outcome_scope("Bu çıktı için etkinlik önerilir.", outcome))
        self.assertTrue(_answer_matches_outcome_scope("Telafi çalışması yapılmalıdır.", outcome))

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
        # Beceri de gidiyor: aynı temada dört beceri listesi neredeyse birebir
        # aynı metni taşıyor, ayrımı sunucu tarafında yalnız bu alan sağlıyor.
        self.assertEqual(prompts[0]["retrieval"]["skill"], "Dinleme/İzleme")
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

    def test_question_still_carries_the_severity_label(self):
        # Şiddet mekanizması ölçümde 8/8 doğruydu - Bloom'la birlikte gitmemeli.
        self.assertIn("şiddet etiketi: Kritik", self._question(rate=0.4))
        self.assertIn("şiddet etiketi: Orta", self._question(rate=0.6))

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
