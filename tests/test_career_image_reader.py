"""Fixture parsing plus a retained, real Windows OCR observation; no game IO."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_image', ROOT / 'tools/read-career-image.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def fixture():
    lines = []
    for row, (label, number) in enumerate(zip(reader.LABELS, (351849, 308255, 23438, 20156, 4633))):
        y = 40 + row * 50
        lines.append({'words': [{'text': label, 'x': 20, 'y': y, 'width': 160, 'height': 24}]})
        lines.append({'words': [{'text': format(number, ','), 'x': 310, 'y': y, 'width': 100, 'height': 24}]})
    return {'version': 1, 'engine': 'windows.media.ocr', 'width': 500, 'height': 400, 'lines': lines}


class CareerImageTests(unittest.TestCase):
    def test_values_and_no_automatic_sync(self):
        result = reader.extract(fixture())
        self.assertEqual(result['totals']['kills'], 351849)
        self.assertEqual(result['totals']['deaths'], 4633)
        self.assertFalse(result['ready_to_sync'])
        self.assertFalse(result['owner_verified'])

    def test_missing_deaths(self):
        data = fixture(); data['lines'] = data['lines'][:-2]
        with self.assertRaisesRegex(ValueError, 'LABELS_MISSING'):
            reader.extract(data)

    def test_faction_sum(self):
        data = fixture(); data['lines'][1]['words'][0]['text'] = '351,848'
        with self.assertRaisesRegex(ValueError, 'FACTION_SUM_MISMATCH'):
            reader.extract(data)

    def test_duplicate_label(self):
        data = fixture(); data['lines'].append(copy.deepcopy(data['lines'][0]))
        with self.assertRaisesRegex(ValueError, 'LABEL_DUPLICATE'):
            reader.extract(data)

    def test_two_numbers_same_row(self):
        data = fixture(); data['lines'][1]['words'].append(
            {'text': '55', 'x': 440, 'y': 40, 'width': 35, 'height': 24})
        with self.assertRaisesRegex(ValueError, 'VALUE_NOT_UNIQUE'):
            reader.extract(data)

    def test_another_card_column(self):
        data = fixture(); data['lines'][-1]['words'][0]['x'] = 220
        with self.assertRaisesRegex(ValueError, 'COLUMNS_INCONSISTENT'):
            reader.extract(data)

    def test_malformed_thousands(self):
        data = fixture(); data['lines'][1]['words'][0]['text'] = '35,1849'
        with self.assertRaisesRegex(ValueError, 'VALUE_NOT_UNIQUE'):
            reader.extract(data)

    def test_not_a_career_page(self):
        data = fixture(); data['lines'][0]['words'][0]['text'] = '杀敌数'
        with self.assertRaisesRegex(ValueError, 'LABELS_MISSING'):
            reader.extract(data)

    def test_words_not_on_same_row(self):
        data = fixture(); data['lines'][-1]['words'] = [
            {'text': '4', 'x': 310, 'y': 258, 'width': 12, 'height': 24},
            {'text': ',', 'x': 324, 'y': 258, 'width': 5, 'height': 6},
            {'text': '633', 'x': 330, 'y': 222, 'width': 50, 'height': 24}]
        with self.assertRaisesRegex(ValueError, 'VALUE_NOT_UNIQUE'):
            reader.extract(data)

    def test_comma_attached_to_cross_row_number(self):
        data = fixture(); data['lines'][-1]['words'] = [
            {'text': '4,', 'x': 310, 'y': 258, 'width': 18, 'height': 24},
            {'text': '633', 'x': 330, 'y': 222, 'width': 50, 'height': 24}]
        with self.assertRaisesRegex(ValueError, 'VALUE_NOT_UNIQUE'):
            reader.extract(data)

    def test_real_retained_ocr(self):
        path = ROOT / 'dist/career-image-reader/ocr-397dc153cd174bec98e1a49d4a35c7ab.json'
        if not path.exists():
            self.skipTest('Retained local OCR observation unavailable')
        data = json.loads(path.read_text('utf8'))
        result = reader.extract(data)
        self.assertEqual(result['totals'], {'kills': 351849, 'deaths': 4633,
            'terminid_kills': 308255, 'automaton_kills': 23438, 'illuminate_kills': 20156})


if __name__ == '__main__':
    unittest.main()
