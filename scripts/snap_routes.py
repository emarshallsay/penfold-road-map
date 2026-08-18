#!/usr/bin/env python3
"""Create a road-following GeoJSON file from the Penfold waypoint datasets.

The source GeoJSON coordinates are treated as via points. OSRM returns full
road geometry between those points. If routing fails or looks implausible, the
original geometry is retained and marked as unsnapped.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "roads.geojson", ROOT / "roads-expansion-1.geojson", ROOT / "roads-expansion-2.geojson"]
OUTPUT = ROOT / "roads-snapped.geojson"
OSRM = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
USER_AGENT = "PenfoldRoadMap/1.0 (github.com/emarshallsay/penfold-road-map)"


def haversine(a, b):
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def waypoint_chain_length(coords):
    return sum(haversine(a, b) for a, b in zip(coords, coords[1:]))


def route_geometry(coords):
    coord_text = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    query = urllib.parse.urlencode({
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
        "alternatives": "false",
    })
    url = f"{OSRM}/route/v1/driving/{coord_text}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.load(response)
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RuntimeError(payload.get("code", "No route"))
    route = payload["routes"][0]
    return route["geometry"]["coordinates"], float(route.get("distance", 0))


def main():
    features = []
    for path in SOURCES:
        if path.exists():
            features.extend(json.loads(path.read_text(encoding="utf-8")).get("features", []))

    snapped = 0
    retained = 0
    for i, feature in enumerate(features, 1):
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        props = feature.setdefault("properties", {})
        props.pop("snap_error", None)

        if geometry.get("type") != "LineString" or len(coords) < 2:
            props["geometry_status"] = "original"
            retained += 1
            continue

        try:
            routed, distance = route_geometry(coords)
            chain = max(waypoint_chain_length(coords), 1)
            # Reject a route if it is wildly longer than the intended waypoint chain.
            # This catches bad snaps/ferries/detours without penalising normal winding roads.
            if distance > chain * 3.0 + 5000:
                raise RuntimeError(f"implausible route: {distance/1000:.1f} km vs {chain/1000:.1f} km waypoint chain")
            feature["geometry"] = {"type": "LineString", "coordinates": routed}
            props["geometry_status"] = "road-snapped"
            props["route_distance_km"] = round(distance / 1000, 1)
            snapped += 1
        except Exception as exc:
            props["geometry_status"] = "original"
            props["snap_error"] = str(exc)[:180]
            retained += 1
            print(f"WARN {props.get('name', feature.get('id'))}: {exc}")

        print(f"{i}/{len(features)} {props.get('name', feature.get('id'))}: {props['geometry_status']}")
        # Be polite to the public demo router; results are committed and reused.
        time.sleep(0.75)

    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {snapped} snapped, {retained} retained")


if __name__ == "__main__":
    main()
