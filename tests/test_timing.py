"""Tests for the shared stage timer.

Ölçümün tek bir sert kuralı var: ölçtüğü şeyi DEĞİŞTİRMEMELİ. Bir süre
yardımcısının istisnayı yutması ya da alan doldururken patlaması, ölçmeye
çalıştığı akışı bozmak demektir - buradaki testlerin çoğu o sınırı koruyor.
"""

import io
import unittest
from contextlib import redirect_stdout

from backend.app.timing import format_fields, stage


def _captured(name, **fields):
    """`stage`i koşturur ve bastığı satırı döndürür."""

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        with stage(name, **fields):
            pass
    return buffer.getvalue().strip()


class StageOutputTests(unittest.TestCase):
    def test_line_carries_the_name_and_a_duration(self):
        line = _captured("ocr-yerel")
        self.assertTrue(line.startswith("[MAHIR][süre] ocr-yerel sure="))
        self.assertIn("s", line)

    def test_fields_given_up_front_reach_the_line(self):
        self.assertIn("dosya=3", _captured("ocr-yerel", dosya=3))

    def test_fields_filled_in_afterwards_reach_the_line(self):
        # Bazı alanlar ancak iş bittikten sonra biliniyor (kaç öğrenci okundu
        # gibi); sözlük bu yüzden dışarı veriliyor.
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with stage("ocr-yerel") as measured:
                measured["ogrenci"] = 35
        self.assertIn("ogrenci=35", buffer.getvalue())

    def test_empty_fields_are_dropped_rather_than_printed_blank(self):
        line = _captured("analiz-rota", ogrenci=0, sonuc="", eksik=None)
        self.assertIn("ogrenci=0", line, "Sıfır anlamlı bir ölçüm; elenmemeli.")
        self.assertNotIn("sonuc=", line)
        self.assertNotIn("eksik=", line)


class StageFailureTests(unittest.TestCase):
    """Ölçüm, ölçtüğü akışın davranışını değiştirmemeli."""

    def test_exception_is_re_raised_not_swallowed(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(ValueError) as caught:
                with stage("analiz-rota"):
                    raise ValueError("öğretmenin düzeltmesi gereken veri hatası")
        self.assertIn("öğretmenin düzeltmesi", str(caught.exception))

    def test_failure_is_still_measured_and_marked(self):
        # "45 sn sonra patladı" bilgisi, "45 sn sürdü" kadar değerli: zaman
        # aşımını yavaşlıktan ayıran şey bu. Yalnız başarı yolunda ölçmek en
        # çok merak edilen durumu karanlıkta bırakırdı.
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(RuntimeError):
                with stage("ocr-uzak", dosya=3):
                    raise RuntimeError("uzak servis düştü")
        line = buffer.getvalue()
        self.assertIn("sure=", line)
        self.assertIn("dosya=3", line)
        self.assertIn("hata=evet", line)

    def test_keyboard_interrupt_is_measured_too(self):
        # `except Exception` yazılsaydı Ctrl+C ölçülmeden geçerdi; uzun bir
        # OCR'ı yarıda kesmek tam da ölçmek istenen durumlardan biri.
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            with self.assertRaises(KeyboardInterrupt):
                with stage("ocr-uzak"):
                    raise KeyboardInterrupt
        self.assertIn("hata=evet", buffer.getvalue())


class FieldFormatTests(unittest.TestCase):
    def test_field_order_follows_insertion(self):
        self.assertEqual(format_fields({"dosya": 3, "ogrenci": 35}), "dosya=3 ogrenci=35")

    def test_no_fields_produces_an_empty_string(self):
        self.assertEqual(format_fields({}), "")


if __name__ == "__main__":
    unittest.main()
