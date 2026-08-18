#!/usr/bin/env python3
"""Harvest UK OSM vehicle-dimension restrictions as review candidates.

These are NOT treated as authoritative map ratings. The output is a review queue
for later checking against signage, highway-authority data and community reports.
"""
from __future__ import annotations
import json, math, re, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'osm-restriction-candidates.geojson'
USER_AGENT = 'UKCampervanRoadMap/1.0'

REF_HEIGHT = 2.10
REF_LENGTH = 5.304
REF_MIRRORS = 2.297
# Keep a useful margin above the reference vehicle so near-misses are reviewable.
HEIGHT_CUTOFF = 2.60
WIDTH_CUTOFF = 2.60
LENGTH_CUTOFF = 6.50

ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
]

# Small enough to reduce public Overpass load; together these cover Great Britain.
TILES = [
    (49.8, -6.8, 52.5, -2.0),
    (49.8, -2.0, 52.5, 2.0),
    (52.5, -6.8, 55.0, -2.0),
    (52.5, -2.0, 55.0, 2.0),
    (55.0, -7.8, 57.5, -2.5),
    (55.0, -2.5, 57.5, 1.0),
    (57.5, -8.8, 61.0, -3.0),
    (57.5, -3.0, 61.0, 0.5),
]

SPECIAL = {'default', 'unsigned', 'none', 'signals', 'below_default'}

def parse_dimension(value):
    if value is None:
        return None
    s = str(value).strip().lower().replace(',', '.')
    if not s or s in SPECIAL:
        return None
    # OSM numeric dimensions without units are metres.
    if re.fullmatch(r'\d+(?:\.\d+)?', s):
        return float(s)
    m = re.search(r'(\d+(?:\.\d+)?)\s*m(?:etre|eter)?s?\b', s)
    if m:
        return float(m.group(1))
    ft = re.search(r"(\d+)\s*(?:ft|feet|['’])\s*(?:(\d+)\s*(?:in|inch|inches|[\"”]))?", s)
    if ft:
        return int(ft.group(1))*0.3048 + int(ft.group(2) or 0)*0.0254
    return None

def fetch_json(query):
    body = ('data=' + urllib.parse.quote(query)).encode()
    last = None
    for endpoint in ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=body, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            })
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r), endpoint
        except Exception as exc:
            last = exc
            print(f'WARN {endpoint}: {exc}')
            time.sleep(2)
    raise RuntimeError(f'All Overpass endpoints failed: {last}')

def query_for_bbox(s,w,n,e):
    box = f'({s},{w},{n},{e})'
    return f'''[out:json][timeout:30];(
      nwr["maxheight"]{box};
      nwr["maxwidth"]{box};
      nwr["maxlength"]{box};
      node["barrier"="height_restrictor"]{box};
    );out center tags qt;'''

def candidate_from_element(el):
    tags = el.get('tags') or {}
    lat = el.get('lat', (el.get('center') or {}).get('lat'))
    lon = el.get('lon', (el.get('center') or {}).get('lon'))
    if lat is None or lon is None:
        return None

    dims = {
        'height': parse_dimension(tags.get('maxheight')),
        'width': parse_dimension(tags.get('maxwidth')),
        'length': parse_dimension(tags.get('maxlength')),
    }
    raw = {k: tags.get('max'+k) for k in ('height','width','length') if tags.get('max'+k) is not None}
    barrier = tags.get('barrier') == 'height_restrictor'

    interesting = (
        (dims['height'] is not None and dims['height'] <= HEIGHT_CUTOFF) or
        (dims['width'] is not None and dims['width'] <= WIDTH_CUTOFF) or
        (dims['length'] is not None and dims['length'] <= LENGTH_CUTOFF) or
        barrier
    )
    if not interesting:
        return None

    conflicts = []
    cautions = []
    if dims['height'] is not None:
        (conflicts if dims['height'] <= REF_HEIGHT else cautions).append('height')
    if dims['width'] is not None:
        # Mirrors can fold; treat <= body width as conflict, <= mirrors as strong caution.
        if dims['width'] <= 1.904: conflicts.append('width')
        else: cautions.append('width')
    if dims['length'] is not None:
        (conflicts if dims['length'] < REF_LENGTH else cautions).append('length')
    if barrier and dims['height'] is None:
        cautions.append('height barrier')

    severity = 'conflict' if conflicts else 'caution'
    return {
        'type': 'Feature',
        'geometry': {'type':'Point','coordinates':[lon,lat]},
        'properties': {
            'osm_type': el.get('type'), 'osm_id': el.get('id'),
            'name': tags.get('name') or tags.get('ref') or tags.get('addr:street') or 'Mapped vehicle restriction',
            'road': tags.get('ref') or tags.get('name') or tags.get('addr:street'),
            'severity': severity,
            'conflicts': conflicts, 'cautions': cautions,
            'height_m': round(dims['height'],3) if dims['height'] is not None else None,
            'width_m': round(dims['width'],3) if dims['width'] is not None else None,
            'length_m': round(dims['length'],3) if dims['length'] is not None else None,
            'raw': raw,
            'barrier': tags.get('barrier'),
            'highway': tags.get('highway'),
            'access': tags.get('access'),
            'motor_vehicle': tags.get('motor_vehicle'),
            'source': 'OpenStreetMap candidate — requires review',
            'osm_url': f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        }
    }

def main():
    found = {}
    failures = 0
    for i, bbox in enumerate(TILES, 1):
        print(f'Tile {i}/{len(TILES)} {bbox}')
        try:
            data, endpoint = fetch_json(query_for_bbox(*bbox))
            print(f'  {len(data.get("elements", []))} raw elements via {endpoint}')
            for el in data.get('elements', []):
                c = candidate_from_element(el)
                if c:
                    found[(c['properties']['osm_type'], c['properties']['osm_id'])] = c
        except Exception as exc:
            failures += 1
            print(f'ERROR tile {bbox}: {exc}')
        time.sleep(2)

    features = sorted(found.values(), key=lambda f: (
        f['properties']['severity'] != 'conflict',
        f['properties'].get('height_m') or 99,
        f['properties'].get('width_m') or 99,
        f['properties'].get('length_m') or 99,
    ))
    payload = {
        'type':'FeatureCollection',
        'metadata': {
            'purpose':'Review queue only; OSM data is not automatically promoted to road ratings.',
            'reference_vehicle': {'height_m':REF_HEIGHT,'length_m':REF_LENGTH,'mirrors_m':REF_MIRRORS},
            'cutoffs': {'height_m':HEIGHT_CUTOFF,'width_m':WIDTH_CUTOFF,'length_m':LENGTH_CUTOFF},
            'failed_tiles': failures,
        },
        'features': features,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {len(features)} OSM restriction candidates ({failures} failed tiles)')

if __name__ == '__main__':
    main()
