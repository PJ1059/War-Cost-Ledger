"""Build a small read-only demolition matcher table from the official Runtime SDK.

The SDK's damage outer radius is the local-candidate limit. Its larger shockwave
radius is retained only for rejecting possible competing explosions. A type name
does not establish who caused an explosion or whether it closed a particular hole.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


PADDING_METRES = 1.5
MAX_RADIUS_METRES = 46.5


def _nonnegative_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('EXPLOSION_CATALOGUE_NUMBER: ' + label)
    if not math.isfinite(value) or value < 0:
        raise ValueError('EXPLOSION_CATALOGUE_NUMBER: ' + label)
    return value


def build(sdk_path):
    """Return serializable metadata and ``by_name`` entries for runtime lookup.

    ``sdk_path`` is the SDK directory containing ExplosionCatalogue.json. Both
    catalogue names and legacy event aliases are accepted. An ambiguous alias
    uses the smallest candidate radius, largest competitor radius, and requires
    every matching definition to have positive demolition damage.
    """
    source = Path(sdk_path) / 'ExplosionCatalogue.json'
    raw = source.read_bytes()
    catalogue = json.loads(raw.decode('utf-8'))
    by_name = {}
    for item in catalogue['explosions']:
        name = item['name']
        legacy = item.get('legacyName')
        if not isinstance(name, str) or not name:
            raise ValueError('EXPLOSION_CATALOGUE_NAME')
        if legacy is not None and (not isinstance(legacy, str) or not legacy):
            raise ValueError('EXPLOSION_CATALOGUE_LEGACY_NAME')
        stats = item['stats']
        outer = _nonnegative_number(stats['outerRadius'], name + '.outerRadius')
        shockwave = _nonnegative_number(stats['shockwaveRadius'], name + '.shockwaveRadius')
        # Smoke and several non-damaging definitions have a null damage link.
        damage = stats.get('damage')
        demolition = 0 if damage is None else _nonnegative_number(
            damage['demolition'], name + '.demolition')
        radius = min(MAX_RADIUS_METRES, outer + PADDING_METRES)
        conflict_radius = min(MAX_RADIUS_METRES, max(outer, shockwave) + PADDING_METRES)
        for alias in {name, legacy} - {None}:
            entry = by_name.get(alias)
            if entry is None:
                by_name[alias] = {'radius': radius, 'conflict_radius': conflict_radius,
                                  'eligible': demolition > 0}
            else:
                entry['radius'] = min(entry['radius'], radius)
                entry['conflict_radius'] = max(entry['conflict_radius'], conflict_radius)
                entry['eligible'] = entry['eligible'] and demolition > 0
    return {'revision': 1, 'source_file': source.name,
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'source_build': catalogue.get('build'),
            'by_name': dict(sorted(by_name.items()))}
