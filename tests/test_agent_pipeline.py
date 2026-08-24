"""Tests for the five-agent pipeline: equivalence, boundaries, isolation, trace.

The single most important test here is equivalence. The pipeline exists to
replace a 600-line monolith without changing a number the teacher sees, so
every other property is worthless if `run_pipeline` and `analyze_approved_data`
disagree on the output.
"""

import unittest
from unittest.mock import patch

from backend.app.agents import PIPELINE, run_pipeline, trace_of
from backend.app.agents.orchestrator import PipelineError
from backend.app.agents.base import AgentContext, AgentIssue, AgentResult
from backend.app.approved_data_analyzer import (
    analyze_approved_data,
    analyze_approved_data_traced,
)


def _question(number, code, theme="1. Tema: Sayılar", max_score=10):
    return {
        "number": number,
        "maxScore": max_score,
        "outcomeCode": code,
        "outcomeDescription": f"{code} kazanım metni",
        "outcomeTheme": theme,
        "outcomeSkill": "Okuma",
        "parentOutcomeDescription": f"{code} kazanım metni",
    }


_QUESTIONS = [
    _question(2, "M9.OB2"),
    _question(5, "M9.OB2"),
    _question(8, "M9.OB2"),
    _question(9, "M9.OB3", theme="2. Tema: Geometri"),
]
_STUDENTS = [
    {"studentRef": "Ö-001", "scores": [8, 6, 7, 5]},
    {"studentRef": "Ö-002", "scores": [6, 6, 7, 9]},
    {"studentRef": "Ö-003", "scores": [3, 9, 4, 10]},
]


def _payload(**extra):
    return {
        "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
        "questions": _QUESTIONS,
        "students": _STUDENTS,
        **extra,
    }


_no_remote = None


def setUpModule():
    """Bu dosya hattın DETERMİNİSTİK davranışını sınıyor; LLM turu kapalı.

    Ölçme Ajanı artık her analizde anomali prompt'u kuyruğa yazıyor. Uzak adres
    tanımlı kalırsa bu testler gerçek GPU'ya istek atar - yavaş, pahalı ve ağa
    bağımlı olur (ölçüldü: 10 sn yerine 149 sn). LLM turunun kendisi
    `test_agent_llm_round.py`de sahte sunucuya karşı sınanıyor.
    """

    global _no_remote
    _no_remote = patch("backend.app.approved_data_analyzer.MAHIR_RAG_REMOTE_URL", "")
    _no_remote.start()


def tearDownModule():
    _no_remote.stop()


def _run(payload):
    return run_pipeline(payload, component_type="written", profile_id="")


class EquivalenceTests(unittest.TestCase):
    """Yeni hat, bugünkü tek parça analizle BİREBİR aynı çıktıyı vermeli."""

    def test_pipeline_output_matches_monolith_exactly(self):
        payload = _payload()
        self.assertEqual(_run(payload).analysis, analyze_approved_data(payload))

    def test_equivalence_holds_with_corrected_cells(self):
        payload = _payload(correctedCells={"0": 2, "3": 1})
        self.assertEqual(_run(payload).analysis, analyze_approved_data(payload))

    def test_equivalence_holds_for_a_single_question_and_student(self):
        payload = {
            "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
            "questions": [_question(1, "M9.OB1")],
            "students": [{"studentRef": "Ö-001", "scores": [7]}],
        }
        self.assertEqual(_run(payload).analysis, analyze_approved_data(payload))

    def test_equivalence_holds_when_no_outcome_is_selected(self):
        # Çıktı seçilmemiş sorular soru bazında gruplanır ("Soru N").
        questions = [{**_question(1, ""), "outcomeTheme": "", "outcomeDescription": ""}]
        payload = {
            "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
            "questions": questions,
            "students": [{"studentRef": "Ö-001", "scores": [4]}],
        }
        self.assertEqual(_run(payload).analysis, analyze_approved_data(payload))

    def test_measurement_is_bit_identical_not_merely_close(self):
        # Kayan nokta toplama sırası değişirse oranlar 1e-16 kayar ve
        # "Kanıtları Gör" bloğundaki yeniden üretim tutmaz. assertEqual
        # (assertAlmostEqual değil) bu yüzden kasıtlı.
        pipeline = _run(_payload()).analysis
        monolith = analyze_approved_data(_payload())
        for left, right in zip(pipeline["outcomes"], monolith["outcomes"]):
            self.assertEqual(left["successRate"], right["successRate"])
            self.assertEqual(left["evidence"], right["evidence"])


class GoldenValueTests(unittest.TestCase):
    """Elle doğrulanabilir sabit değerler.

    `EquivalenceTests` hattı tek parça analizle karşılaştırıyor; ama artık
    `analyze_approved_data` da hatta delege ettiği için o karşılaştırma
    kendini kendisiyle denemek anlamına geliyor. Asıl güvence bu sınıf:
    sayılar fixture'dan elle hesaplanabiliyor ve hat onları üretmek zorunda.

    Fixture: 4 soru x 10 puan x 3 öğrenci.
      S2: 8+6+3 = 17/30   S5: 6+6+9 = 21/30
      S8: 7+7+4 = 18/30   S9: 5+9+10 = 24/30
      M9.OB2 (S2+S5+S8) = 56/90   M9.OB3 (S9) = 24/30
      Öğrenci toplamları 26, 28, 26 -> ortalama 80/3 = 26,67; azami 40.
    """

    def setUp(self):
        self.analysis = _run(_payload()).analysis

    def test_summary_numbers(self):
        summary = self.analysis["summary"]
        self.assertEqual(summary["examMaxScore"], 40.0)
        self.assertEqual(summary["classAverage"], 26.67)
        self.assertEqual(summary["participatingStudentCount"], 3)
        self.assertEqual(summary["questionCount"], 4)

    def test_question_totals(self):
        expected = {2: (17.0, 30.0), 5: (21.0, 30.0), 8: (18.0, 30.0), 9: (24.0, 30.0)}
        for question in self.analysis["questions"]:
            with self.subTest(question=question["number"]):
                earned, possible = expected[question["number"]]
                self.assertEqual(question["earnedScore"], earned)
                self.assertEqual(question["possibleScore"], possible)
                self.assertEqual(question["successRate"], earned / possible)

    def test_outcome_totals_and_evidence(self):
        by_code = {item["outcomeCode"]: item for item in self.analysis["outcomes"]}
        self.assertEqual(by_code["M9.OB2"]["earnedScore"], 56.0)
        self.assertEqual(by_code["M9.OB2"]["possibleScore"], 90.0)
        self.assertEqual(by_code["M9.OB2"]["successRate"], 56.0 / 90.0)
        self.assertEqual(by_code["M9.OB2"]["evidence"]["questionNumbers"], [2, 5, 8])
        self.assertEqual(by_code["M9.OB3"]["evidence"]["questionNumbers"], [9])

    def test_evidence_reproduces_the_percentage(self):
        # "Bu %62 nereden geldi?" - kanıttaki puanlar oranı vermeli.
        for outcome in self.analysis["outcomes"]:
            with self.subTest(outcome=outcome["outcomeCode"]):
                evidence = outcome["evidence"]
                self.assertEqual(
                    evidence["earnedScore"] / evidence["possibleScore"],
                    outcome["successRate"],
                )


class CedBackboneTests(unittest.TestCase):
    def test_ced_is_built_and_carries_every_question_and_student(self):
        context = _run(_payload())
        self.assertEqual(len(context.ced.questions), 4)
        self.assertEqual(len(context.ced.student_results), 3)
        self.assertEqual(context.ced.assessment.question_count, 4)
        self.assertEqual(context.ced.assessment.total_score, 40.0)

    def test_ced_question_ids_are_unique(self):
        # measurement_engine puanları bu kimlikle eşliyor; yinelenme sessiz
        # veri karışması demek.
        ced = _run(_payload()).ced
        ids = [question.id for question in ced.questions]
        self.assertEqual(len(set(ids)), len(ids))

    def test_ced_never_carries_student_identity(self):
        # Analiz katmanı kimlik alanlarını reddediyor; CED o kapının arkasında
        # kimliği yeniden doğuran yer olmamalı.
        for student in _run(_payload()).ced.student_results:
            self.assertEqual(student.full_name, "")
            self.assertRegex(student.student_no, r"^Ö-\d{3,}$")

    def test_outcome_ids_group_by_theme_and_code(self):
        ced = _run(_payload()).ced
        self.assertEqual(ced.questions[0].learning_outcome_ids, ["1. Tema: Sayılar | M9.OB2"])
        self.assertEqual(ced.questions[3].learning_outcome_ids, ["2. Tema: Geometri | M9.OB3"])


class TraceTests(unittest.TestCase):
    def test_every_agent_leaves_a_trace_in_order(self):
        context = _run(_payload())
        self.assertEqual(
            [entry.agent for entry in context.trace],
            [agent.name for agent in PIPELINE],
        )

    def test_trace_records_what_each_agent_produced(self):
        context = _run(_payload())
        self.assertEqual(context.trace_for("belge-anlama").outputs["questionCount"], 4)
        self.assertEqual(context.trace_for("olcme-degerlendirme").outputs["measuredOutcomeCount"], 2)
        self.assertEqual(context.trace_for("pedagojik-analiz").outputs["outcomeCount"], 2)

    def test_trace_measures_duration(self):
        for entry in _run(_payload()).trace:
            with self.subTest(agent=entry.agent):
                self.assertGreaterEqual(entry.duration_ms, 0.0)

    def test_trace_carries_no_student_rows(self):
        # İz, gizlilik kapısının arkasına açılan bir yan kapı olmamalı.
        for entry in _run(_payload()).trace:
            blob = repr(entry.to_dict())
            self.assertNotIn("Ö-001", blob)
            self.assertNotIn("scores", blob)

    def test_corrected_cell_total_is_visible_in_the_trace(self):
        context = _run(_payload(correctedCells={"0": 2, "3": 1}))
        self.assertEqual(context.trace_for("olcme-degerlendirme").outputs["correctedCellTotal"], 3)


class TraceWireFormatTests(unittest.TestCase):
    """`/mahir-analyze` yanıtına giden iz biçimi - öğretmenin gördüğü yüzeyin girdisi."""

    def test_traced_analysis_matches_the_plain_one(self):
        # İz eklemek analizin kendisini değiştirmemeli; eşdeğerlik güvencesi
        # `analyze_approved_data`nın delege ettiği yeni yolda da geçerli.
        payload = _payload()
        analysis, _trace = analyze_approved_data_traced(payload)
        self.assertEqual(analysis, analyze_approved_data(payload))

    def test_every_agent_reaches_the_wire_with_a_turkish_label(self):
        _analysis, trace = analyze_approved_data_traced(_payload())
        self.assertEqual(
            [entry["label"] for entry in trace["agents"]],
            [
                "Belge Anlama",
                "Program Eşleştirme",
                "Ölçme ve Değerlendirme",
                "Pedagojik Analiz",
                "Raporlama",
            ],
        )

    def test_wire_entry_carries_what_the_surface_needs(self):
        _analysis, trace = analyze_approved_data_traced(_payload())
        entry = next(item for item in trace["agents"] if item["agent"] == "olcme-degerlendirme")
        self.assertEqual(entry["outputs"]["measuredQuestionCount"], 4)
        self.assertGreaterEqual(entry["durationMs"], 0.0)
        self.assertEqual(entry["llmCalls"], [], "LLM turu kapalıyken kayıt olmamalı.")
        self.assertFalse(entry["failed"])
        self.assertFalse(entry["skipped"])

    def test_trace_reports_the_total_wall_clock(self):
        # Ajan süreleri milisaniye, ortak LLM turu saniyeler mertebesinde;
        # toplamı ayrıca taşımak tarayıcının "zaman nerede geçti"yi ek bir
        # alan olmadan gösterebilmesini sağlıyor.
        _analysis, trace = analyze_approved_data_traced(_payload())
        self.assertGreaterEqual(trace["totalMs"], 0.0)
        # Ajan süreleri dış sözleşmede onda bir milisaniyeye yuvarlanır.
        # Toplarken oluşabilen 0.30000000000000004 benzeri ikili kayan nokta
        # artığını aynı sözleşme hassasiyetine indirerek kararsızlığı önle.
        agent_total = round(
            sum(entry["durationMs"] for entry in trace["agents"]),
            1,
        )
        self.assertGreaterEqual(
            trace["totalMs"], agent_total, "Toplam, ajan sürelerinin altına düşemez."
        )

    def test_general_evaluation_path_still_reports_a_total(self):
        # Hat koşmayan yol: iz boş ama alanın varlığı öngörülebilir kalmalı.
        from backend.app.approved_data_analyzer import empty_trace

        self.assertNotIn("totalMs", empty_trace())
        _analysis, trace = analyze_approved_data_traced(_payload())
        self.assertIn("totalMs", trace)

    def test_wire_trace_carries_no_student_rows(self):
        # Gizlilik kuralı `to_dict` kadar `to_wire` için de geçerli - tarayıcıya
        # giden biçim, gizlilik kapısının arkasına açılan bir yan kapı olmamalı.
        _analysis, trace = analyze_approved_data_traced(_payload())
        blob = repr(trace)
        self.assertNotIn("Ö-001", blob)
        self.assertNotIn("scores", blob)

    def test_agent_findings_reach_the_wire_as_issues(self):
        questions = [dict(_question(1, "M9.OB1"), outcomeCode="")]
        _analysis, trace = analyze_approved_data_traced({
            "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
            "questions": questions,
            "students": [{"studentRef": "Ö-001", "scores": [4]}],
        })
        self.assertTrue(any(issue["code"] == "cikti-secilmemis" for issue in trace["issues"]))

    def test_skipped_agents_reach_the_wire_named(self):
        # Zorunlu ajan düştüğünde de iz üretiliyor; "neden çalışmadı"
        # gösterilebilmesi için atlananların da adı ve etiketi olmalı.
        broken = _pipeline_with("olcme-degerlendirme", "Ölçme", required=True)
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            with self.assertRaises(PipelineError) as caught:
                _run(_payload())

        agents = trace_of(caught.exception.context)["agents"]
        self.assertEqual(len(agents), 5)
        skipped = [entry for entry in agents if entry["skipped"]]
        self.assertEqual(
            [entry["label"] for entry in skipped], ["Pedagojik Analiz", "Raporlama"]
        )


def _pipeline_with(name, description, required):
    """Adı verilen ajanı hep patlayan bir taklitle değiştirir.

    `label` bilerek verilmiyor: orkestratör etiketi olmayan bir ajanda slug'a
    düşmeli ve iz üretmeyi sürdürmeli - dışarıdan eklenen bir ajan yüzeyi
    çökertmemeli.
    """

    class Boom:
        def run(self, context):
            raise RuntimeError("uzak servis düştü")

    Boom.name, Boom.description, Boom.required = name, description, required
    return tuple(Boom() if agent.name == name else agent for agent in PIPELINE)


class FailureIsolationTests(unittest.TestCase):
    """Zorunlu/isteğe bağlı ayrımı: hangi arıza analizi düşürür, hangisi düşürmez."""

    _pipeline_with = staticmethod(_pipeline_with)

    def test_optional_agent_failure_still_produces_a_report(self):
        # Pedagojik Analiz isteğe bağlı: yorumsuz bir rapor hâlâ işe yarar.
        broken = self._pipeline_with("pedagojik-analiz", "Pedagojik analiz", required=False)
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            context = _run(_payload())

        self.assertTrue(context.trace_for("pedagojik-analiz").failed)
        self.assertFalse(context.trace_for("raporlama").failed)
        self.assertTrue(context.analysis, "Rapor yine de üretilmeliydi.")
        # Ölçme sonuçları korunuyor, yalnız yorum kısmı boş.
        self.assertEqual(len(context.analysis["questions"]), 4)
        self.assertEqual(context.analysis["outcomes"], [])

    def test_optional_agent_failure_is_reported_as_a_turkish_issue(self):
        broken = self._pipeline_with("program-eslestirme", "Program eşleştirme", required=False)
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            context = _run(_payload())

        failure = next(issue for issue in context.issues if issue.code == "ajan-arizasi")
        self.assertEqual(failure.agent, "program-eslestirme")
        self.assertIn("tamamlanamadı", failure.message)
        self.assertEqual(failure.severity, "error")

    def test_required_agent_failure_aborts_instead_of_half_reporting(self):
        # Sayılar yoksa yarım rapor göstermek hatadan kötüdür.
        broken = self._pipeline_with("olcme-degerlendirme", "Ölçme", required=True)
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            with self.assertRaises(PipelineError) as caught:
                _run(_payload())
        self.assertIn("olcme-degerlendirme", str(caught.exception))

    def test_agents_after_a_required_failure_are_marked_skipped(self):
        # "Neden çalışmadı" da izlenebilir olmalı: atlanan ajanlar ize
        # yazılıyor ve arıza anındaki bağlam hata nesnesiyle taşınıyor.
        broken = self._pipeline_with("olcme-degerlendirme", "Ölçme", required=True)
        with patch("backend.app.agents.orchestrator.PIPELINE", broken):
            with self.assertRaises(PipelineError) as caught:
                _run(_payload())

        trace = caught.exception.context.trace
        self.assertEqual(len(trace), 5, "Atlanan ajanlar da ize yazılmalı.")
        self.assertTrue(caught.exception.context.trace_for("olcme-degerlendirme").failed)
        for name in ("pedagojik-analiz", "raporlama"):
            with self.subTest(agent=name):
                entry = caught.exception.context.trace_for(name)
                self.assertTrue(entry.skipped)
                self.assertFalse(entry.failed, "Atlanan ajan 'başarısız' sayılmamalı.")
        # Arızadan ÖNCEKİ ajanların sonuçları bağlamda duruyor.
        self.assertEqual(caught.exception.context.trace_for("belge-anlama").outputs["questionCount"], 4)

    def test_value_error_is_raised_not_swallowed(self):
        # Öğretmenin düzeltmesi gereken veri hatası sessizce geçilirse,
        # öğretmen yanlış veriyle üretilmiş raporu doğru sanır.
        payload = _payload(students=[{"studentRef": "Ö-001", "scores": [8, 6]}])
        with self.assertRaises(ValueError):
            _run(payload)

    def test_data_error_names_the_agent_that_hit_it(self):
        payload = _payload(students=[{"studentRef": "bozuk", "scores": [8, 6, 7, 5]}])
        with self.assertRaises(ValueError):
            _run(payload)


class AgentBoundaryTests(unittest.TestCase):
    def test_program_agent_reports_unmapped_questions_without_failing(self):
        questions = [{**_question(1, ""), "outcomeTheme": "", "outcomeDescription": ""}]
        context = _run({
            "exam": {"courseName": "Matematik", "grade": "9", "componentType": "written"},
            "questions": questions,
            "students": [{"studentRef": "Ö-001", "scores": [4]}],
        })
        trace = context.trace_for("program-eslestirme")
        self.assertEqual(trace.outputs["unmappedQuestionCount"], 1)
        self.assertFalse(trace.failed)
        self.assertTrue(any(issue.code == "cikti-secilmemis" for issue in context.issues))

    def test_reporting_agent_does_not_recompute_outcome_rates(self):
        # Şartname: Raporlama Ajanı ölçme analizi yapmaz. Ölçme sonucunu
        # bozarsak rapor da bozulmalı - yani rapor gerçekten devraldığını
        # kullanıyor, kendi hesaplamıyor.
        context = AgentContext(payload=_payload(), ced=None)
        context.scratch["componentType"] = "written"
        context.scratch["profileId"] = ""
        for agent in PIPELINE[:-1]:
            agent.run(context)
        context.scratch["outcomeResults"][0]["successRate"] = 0.123
        PIPELINE[-1].run(context)
        self.assertEqual(context.analysis["outcomes"][0]["successRate"], 0.123)


if __name__ == "__main__":
    unittest.main()
