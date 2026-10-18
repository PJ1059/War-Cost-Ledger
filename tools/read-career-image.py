"""Read one Chinese career screenshot locally; never read/write the game account.

The output is a reviewable observation, not a current-account synchronisation.
A screenshot does not establish its owner, capture time, or a simultaneous MOD
history anchor. Those must be established before replacing a career KD baseline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import uuid

ROOT = Path(__file__).resolve().parents[1]
LABELS = {'敌方击杀数': 'kills', '终结族击杀数': 'terminid_kills',
          '机器人击杀数': 'automaton_kills', '光能者击杀数': 'illuminate_kills',
          '死亡次数': 'deaths'}
NUMBER = re.compile(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)\Z')


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if not c.isspace())


def numeric(text):
    value = normal(text)
    if not NUMBER.fullmatch(value):
        return None
    result = int(value.replace(',', ''))
    return result if result < 2**32 else None


def box(word, width, height):
    coordinates = [word.get(k) for k in ('x', 'y', 'width', 'height')]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in coordinates):
        raise ValueError('OCR_WORD_GEOMETRY_INVALID')
    x, y, w, h = coordinates
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError('OCR_WORD_OUTSIDE_IMAGE')
    return (x, y, x + w, y + h)


def number_groups(words, width, height):
    """Windows Chinese OCR often emits 351 / comma / 849 as three words."""
    groups, current = [], []
    def flush():
        if current:
            raw = ''.join(text for text, _ in current)
            value = numeric(raw)
            digits = [rect for text, rect in current if any('0' <= c <= '9' for c in text)]
            aligned = all(abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
                          <= 0.4 * max(a[3] - a[1], b[3] - b[1])
                          for a in digits for b in digits)
            if value is not None and aligned:
                rectangles = [rect for _, rect in current]
                groups.append((value, (min(r[0] for r in rectangles), min(r[1] for r in rectangles),
                                      max(r[2] for r in rectangles), max(r[3] for r in rectangles)), raw))
            current.clear()
    for word in words:
        rect, text = box(word, width, height), normal(word['text'])
        if not re.fullmatch(r'[0-9,]+', text):
            flush()
            continue
        if current:
            previous = current[-1][1]
            if rect[0] - previous[2] > max(rect[3] - rect[1], previous[3] - previous[1]):
                flush()
        current.append((text, rect))
    flush()
    return groups


def extract(payload):
    if payload.get('version') != 1 or payload.get('engine') != 'windows.media.ocr':
        raise ValueError('OCR_FORMAT_UNSUPPORTED')
    width, height = payload.get('width'), payload.get('height')
    if type(width) is not int or type(height) is not int or not (0 < width <= 10000 and 0 < height <= 10000):
        raise ValueError('OCR_IMAGE_SIZE_INVALID')
    labels, numbers = {}, []
    for line in payload['lines']:
        words = line['words']
        if not words:
            continue
        numbers.extend(number_groups(words, width, height))
        label_words = []
        for word in words:
            rect = box(word, width, height)
            if not re.fullmatch(r'[0-9,]+', normal(word['text'])):
                label_words.append((word['text'], rect))
        label = normal(''.join(t for t, _ in label_words)).rstrip(':：')
        if label in LABELS:
            key = LABELS[label]
            if key in labels:
                raise ValueError('CAREER_LABEL_DUPLICATE:' + key)
            rectangles = [r for _, r in label_words]
            labels[key] = (min(r[0] for r in rectangles), min(r[1] for r in rectangles),
                           max(r[2] for r in rectangles), max(r[3] for r in rectangles))
    missing = set(LABELS.values()) - labels.keys()
    if missing:
        raise ValueError('CAREER_LABELS_MISSING:' + ','.join(sorted(missing)))
    totals, bindings, used = {}, {}, set()
    for key, rect in labels.items():
        center = (rect[1] + rect[3]) / 2
        candidates = []
        for index, (value, other, raw) in enumerate(numbers):
            tolerance = 0.5 * max(rect[3] - rect[1], other[3] - other[1])
            if other[0] > rect[2] and abs((other[1] + other[3]) / 2 - center) <= tolerance:
                candidates.append((index, value, other, raw))
        if len(candidates) != 1:
            raise ValueError('CAREER_VALUE_NOT_UNIQUE:' + key)
        index, value, other, raw = candidates[0]
        if index in used:
            raise ValueError('CAREER_VALUE_REUSED')
        used.add(index)
        totals[key] = value
        bindings[key] = {'label_bounds': rect, 'value_bounds': other, 'raw_value': raw}
    if totals['kills'] != sum(totals[k] for k in ('terminid_kills', 'automaton_kills', 'illuminate_kills')):
        raise ValueError('CAREER_FACTION_SUM_MISMATCH')
    # A second player's card or distant panel must not supply one missing row.
    lefts = [r[0] for r in labels.values()]
    rights = [b['value_bounds'][2] for b in bindings.values()]
    if max(lefts) - min(lefts) > width * 0.08 or max(rights) - min(rights) > width * 0.08:
        raise ValueError('CAREER_COLUMNS_INCONSISTENT')
    expected_order = ['kills', 'terminid_kills', 'automaton_kills', 'illuminate_kills', 'deaths']
    if any(labels[a][1] >= labels[b][1] for a, b in zip(expected_order, expected_order[1:])):
        raise ValueError('CAREER_ROW_ORDER_INVALID')
    return {'totals': totals, 'bindings': bindings, 'faction_sum_verified': True,
            'row_binding_verified': True, 'owner_verified': False,
            'synchronous_mod_anchor_verified': False, 'ready_to_sync': False}


def read_image(image, output):
    image, output = Path(image).resolve(), Path(output).resolve()
    image_bytes = image.read_bytes()
    image_sha = hashlib.sha256(image_bytes).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    ocr_path = output / ('ocr-' + token + '.json')
    ps = Path(os.environ['WINDIR']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.run([str(ps), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(ROOT / 'tools/career-image-ocr.ps1'),
                    '-ImagePath', str(image), '-OutputPath', str(ocr_path)],
                   check=True, capture_output=True, timeout=45)
    if hashlib.sha256(image.read_bytes()).hexdigest() != image_sha:
        raise ValueError('CAREER_IMAGE_CHANGED_DURING_OCR')
    parsed = extract(json.loads(ocr_path.read_text('utf8')))
    result = {'version': 1, 'source': 'career_screenshot_local_ocr',
              'processed_at': datetime.now(timezone.utc).isoformat(),
              'image': str(image), 'image_sha256': image_sha, 'ocr': str(ocr_path),
              'account_modified': False, 'game_memory_reads': 0, 'uploaded': False, **parsed}
    report = output / ('career-image-' + token + '.json')
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    return report, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/career-image-reader')
    args = parser.parse_args()
    try:
        report, result = read_image(args.image, args.output)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, '生涯截图读取失败：' + str(error) + '。账号未修改。\n')
    print(json.dumps({'report': str(report), **result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
