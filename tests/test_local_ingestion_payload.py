"""`local/ingestion_pipeline.py` - parça -> Qdrant payload eşlemesi ve bölüm etiketleri.

Servis tarafı (`local/rag_service.py`) sınıf/tema/beceri filtrelerini payload
anahtarlarına (`grade`, `theme_key`, `skill_key`) göre kurar; indeksleme bu
anahtarları yazmazsa filtre sessizce boş döner ve teşhis "belgede bulunmuyor"a
düşer. Bu testler anahtar sözleşmesini Docling/gömme/Qdrant olmadan sabitler.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_LOCAL_DIR = Path(__file__).resolve().parents[1] / "local"


def _load_ingestion():
    name = "local_ingestion_pipeline"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _LOCAL_DIR / "ingestion_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclass annotation çözümü modülü sys.modules'ta arar
    spec.loader.exec_module(module)
    return module


class ChunkPayloadTests(unittest.TestCase):
    def setUp(self):
        self.ingestion = _load_ingestion()

    def _record(self, **overrides):
        fields = {
            "text": "TDE2.1. Metnin anlamını çözümler.",
            "contextualized_text": "Okuma\nTDE2.1. Metnin anlamını çözümler.",
            "headings": ["3. TEMA: ANLAMIN YAPI TAŞLARI", "Okuma"],
            "pages": [66, 67],
            "source_kind": "text",
            "chunk_index": 4,
        }
        fields.update(overrides)
        return self.ingestion.ChunkRecord(**fields)

    def test_payload_carries_curriculum_keys_next_to_the_existing_ones(self):
        record = self._record(grade="9", theme="ANLAMIN Y API TAŞLARI", skill_key="okuma")
        payload = record.payload("Program (2024)", "tde-9-tymm", "2026-09-16T00:00:00+00:00")

        self.assertEqual(payload["document_name"], "Program (2024)")
        self.assertEqual(payload["program_id"], "tde-9-tymm")
        self.assertEqual(payload["pages"], [66, 67])
        self.assertEqual(payload["chunk_index"], 4)
        self.assertEqual(payload["grade"], "9")
        self.assertEqual(payload["theme"], "ANLAMIN Y API TAŞLARI")
        # pypdf'in sahte boşluğu anahtardan düşer - filtre boşluksuz anahtarla eşleşir.
        self.assertEqual(payload["theme_key"], "ANLAMINYAPITAŞLARI")
        self.assertEqual(payload["skill_key"], "okuma")

    def test_payload_carries_section_kind_and_outcome_codes(self):
        record = self._record(section_kind="ogrenme_ogretme", outcome_codes=["TDE2.1", "TDE2.2"])
        payload = record.payload("Program (2024)", "tde-9-tymm", "t")
        self.assertEqual(payload["section_kind"], "ogrenme_ogretme")
        self.assertEqual(payload["outcome_codes"], ["TDE2.1", "TDE2.2"])
        self.assertIsNot(payload["outcome_codes"], record.outcome_codes, "payload kopya taşımalı")

    def test_untagged_document_writes_null_keys(self):
        # Müfredat deseni olmayan belge (ör. README): alanlar var ama None -
        # `must_not skill_key` filtresi bu parçaları korur, `must grade` ise eler.
        payload = self._record().payload("Belge", "readme-test", "t")
        self.assertIsNone(payload["grade"])
        self.assertIsNone(payload["theme"])
        self.assertIsNone(payload["theme_key"])
        self.assertIsNone(payload["skill_key"])
        self.assertIsNone(payload["section_kind"])
        self.assertEqual(payload["outcome_codes"], [])

    def test_write_points_uses_the_record_payload_and_deterministic_ids(self):
        records = [self._record(chunk_index=0, grade="9", theme="Tema", skill_key="okuma"), self._record(chunk_index=1, text="ikinci")]
        client = MagicMock()

        # qdrant-client bu test ortamında kurulu olmayabilir (CI yalnız kök
        # requirements.txt'i kurar); model sınıfları burada yalnız veri taşıyıcı.
        fake_models = types.ModuleType("qdrant_client.models")
        for name in ("PointStruct", "Filter", "FieldCondition", "MatchValue"):
            setattr(fake_models, name, type(name, (types.SimpleNamespace,), {}))
        fake_qdrant = types.ModuleType("qdrant_client")
        fake_qdrant.models = fake_models
        with patch.dict(sys.modules, {"qdrant_client": fake_qdrant, "qdrant_client.models": fake_models}):
            written = self.ingestion._write_points(client, "koleksiyon", records, [[0.1], [0.2]], "Belge", "tde-9-tymm", replace=True)

        self.assertEqual(written, 2)
        client.delete.assert_called_once()  # replace=True -> eski program parçaları silinir
        points = client.upsert.call_args.kwargs["points"]
        self.assertEqual([point.payload["theme_key"] for point in points], ["TEMA", None])
        self.assertEqual(
            points[0].id,
            self.ingestion.deterministic_point_id("tde-9-tymm", "Belge", 0, records[0].text),
        )
        self.assertEqual(set(points[0].payload), {
            "text", "contextualized_text", "document_name", "program_id", "pages", "headings",
            "chunk_index", "source_kind", "grade", "theme", "theme_key", "skill_key", "section_kind", "outcome_codes",
            "ingested_at",
        })


class CurriculumSectionTests(unittest.TestCase):
    def setUp(self):
        self.ingestion = _load_ingestion()

    def test_label_names_grade_and_theme(self):
        section = self.ingestion.CurriculumSection(grade="9", theme="SÖZÜN İNCELİĞİ", pdf_bytes=b"", page_offset=64, page_count=9)
        self.assertEqual(section.label, "9. sınıf / SÖZÜN İNCELİĞİ")
        self.assertEqual(self.ingestion.CurriculumSection(None, None, b"", 0, 3).label, "belge")

    def test_documents_without_headings_become_one_untagged_section(self):
        # Desen yoksa tek bölüm, offset korunur - bugünkü (README) davranış.
        ingestion = self.ingestion
        original_grade, original_theme = ingestion.detect_grade_sections, ingestion.detect_theme_sections
        ingestion.detect_grade_sections = lambda pdf_bytes: [(None, 1, 37)]
        ingestion.detect_theme_sections = lambda pdf_bytes: [(None, 1, 37)]
        try:
            sections = ingestion.split_curriculum_sections(b"pdf", page_offset=10)
        finally:
            ingestion.detect_grade_sections, ingestion.detect_theme_sections = original_grade, original_theme

        self.assertEqual(len(sections), 1)
        self.assertIsNone(sections[0].grade)
        self.assertEqual((sections[0].page_offset, sections[0].page_count), (10, 37))
        self.assertEqual(sections[0].pdf_bytes, b"pdf")

    def test_grade_and_theme_offsets_compose_to_original_pages(self):
        # 9. sınıf s.60-97 içinde 2. tema s.75-83 ise bölümün 1. sayfası orijinal s.75.
        ingestion = self.ingestion
        original = (ingestion.detect_grade_sections, ingestion.detect_theme_sections, ingestion.slice_pdf_pages)
        ingestion.detect_grade_sections = lambda pdf_bytes: [("9", 60, 97), ("10", 98, 130)]
        ingestion.detect_theme_sections = lambda pdf_bytes: [("TEMA A", 1, 15), ("TEMA B", 16, 24)] if pdf_bytes == b"g9" else [(None, 1, 33)]
        ingestion.slice_pdf_pages = lambda pdf_bytes, start, end: {(60, 97): b"g9", (98, 130): b"g10", (1, 15): b"a", (16, 24): b"b"}[(start, end)]
        try:
            sections = ingestion.split_curriculum_sections(b"pdf", page_offset=0)
        finally:
            ingestion.detect_grade_sections, ingestion.detect_theme_sections, ingestion.slice_pdf_pages = original

        self.assertEqual([(s.grade, s.theme, s.page_offset + 1, s.page_count) for s in sections], [
            ("9", "TEMA A", 60, 15),
            ("9", "TEMA B", 75, 9),
            ("10", None, 98, 33),
        ])


if __name__ == "__main__":
    unittest.main()
