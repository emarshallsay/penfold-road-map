#!/usr/bin/env python3
"""Generate road-following GeoJSON, reusing unchanged snapped features."""
from __future__ import annotations
import hashlib,json,math,os,time,urllib.parse,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[ROOT/'roads.geojson',*sorted(ROOT.glob('roads-expansion-*.geojson'))]
OUTPUT=ROOT/'roads-snapped.geojson'
OSRM=os.environ.get('OSRM_URL','https://router.project-osrm.org')
USER_AGENT='PenfoldRoadMap/1.0 (github.com/emarshallsay/penfold-road-map)'

def haversine(a,b):
    lon1,lat1=map(math.radians,a);lon2,lat2=map(math.radians,b);dlon=lon2-lon1;dlat=lat2-lat1
    h=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000*2*math.asin(math.sqrt(h))
def chain_length(c):return sum(haversine(a,b) for a,b in zip(c,c[1:]))
def signature(feature):
    raw={'id':feature.get('id'),'name':(feature.get('properties') or {}).get('name'),'geometry':feature.get('geometry')}
    return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:20]
def key(feature):return str(feature.get('id') or (feature.get('properties') or {}).get('name'))
def route_geometry(coords):
    text=';'.join(f'{lon:.6f},{lat:.6f}' for lon,lat in coords)
    q=urllib.parse.urlencode({'overview':'full','geometries':'geojson','steps':'false','alternatives':'false'})
    req=urllib.request.Request(f'{OSRM}/route/v1/driving/{text}?{q}',headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r: payload=json.load(r)
    if payload.get('code')!='Ok' or not payload.get('routes'):raise RuntimeError(payload.get('code','No route'))
    route=payload['routes'][0];return route['geometry']['coordinates'],float(route.get('distance',0))

def main():
    source=[]
    for p in SOURCES:
        if p.exists():source.extend(json.loads(p.read_text(encoding='utf-8')).get('features',[]))
    previous={}
    if OUTPUT.exists():
        try: previous={key(f):f for f in json.loads(OUTPUT.read_text(encoding='utf-8')).get('features',[])}
        except Exception: pass
    result=[];snapped=reused=retained=0
    for i,src in enumerate(source,1):
        sig=signature(src);k=key(src);old=previous.get(k)
        if old and (old.get('properties') or {}).get('source_signature')==sig:
            result.append(old);reused+=1;print(f'{i}/{len(source)} {k}: reused');continue
        feature=json.loads(json.dumps(src));geom=feature.get('geometry') or {};coords=geom.get('coordinates') or [];props=feature.setdefault('properties',{})
        props['source_signature']=sig;props.pop('snap_error',None)
        if geom.get('type')!='LineString' or len(coords)<2:
            props['geometry_status']='original';retained+=1;result.append(feature);continue
        try:
            routed,distance=route_geometry(coords);chain=max(chain_length(coords),1)
            if distance>chain*3.0+5000:raise RuntimeError(f'implausible route: {distance/1000:.1f} km vs {chain/1000:.1f} km waypoint chain')
            feature['geometry']={'type':'LineString','coordinates':routed};props['geometry_status']='road-snapped';props['route_distance_km']=round(distance/1000,1);snapped+=1
        except Exception as exc:
            props['geometry_status']='original';props['snap_error']=str(exc)[:180];retained+=1;print(f'WARN {k}: {exc}')
        result.append(feature);print(f'{i}/{len(source)} {k}: {props["geometry_status"]}');time.sleep(0.75)
    OUTPUT.write_text(json.dumps({'type':'FeatureCollection','features':result},ensure_ascii=False),encoding='utf-8')
    print(f'Wrote {len(result)} features: {snapped} newly snapped, {reused} reused, {retained} retained')
if __name__=='__main__':main()
