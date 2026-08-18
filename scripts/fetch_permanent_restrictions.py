#!/usr/bin/env python3
from __future__ import annotations
import json, re, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'permanent-restrictions.geojson'
PENFOLD_HEIGHT=2.10
CAUTION_HEIGHT=2.40

SOURCES=[{
  'name':'Highland Council bridge height restrictions',
  'url':'https://services1.arcgis.com/MfbPb778y5QTu2Wv/arcgis/rest/services/BridgeHeightRestrictions/FeatureServer/0/query',
  'params':{'where':'1=1','outFields':'Bridge_Code,Signed_Headroom,Bridge_Name','outSR':'4326','f':'geojson'},
  'source_url':'https://opendata.scot/datasets/highland%2Bcouncil-bridge%2Bheight%2Brestrictions/'
}]

def parse_height(value):
    if value is None: return None
    s=str(value).strip().lower().replace('metres','m').replace('metre','m')
    m=re.search(r'(\d+(?:\.\d+)?)\s*m',s)
    if m:return float(m.group(1))
    ft=re.search(r"(\d+)\s*['’]\s*(\d+)?",s)
    if ft:return int(ft.group(1))*0.3048+(int(ft.group(2) or 0))*0.0254
    n=re.fullmatch(r'\d+(?:\.\d+)?',s)
    return float(s) if n else None

def fetch_geojson(src):
    url=src['url']+'?'+urllib.parse.urlencode(src['params'])
    req=urllib.request.Request(url,headers={'User-Agent':'PenfoldRoadMap/1.0','Accept':'application/geo+json,application/json'})
    with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)

def main():
    out=[]
    for src in SOURCES:
        data=fetch_geojson(src)
        for f in data.get('features',[]):
            p=f.get('properties') or {}
            h=parse_height(p.get('Signed_Headroom'))
            if h is None or h>CAUTION_HEIGHT: continue
            status='conflict' if h<=PENFOLD_HEIGHT else 'caution'
            out.append({'type':'Feature','geometry':f.get('geometry'),'properties':{
                'kind':'height','value_m':round(h,2),'status':status,
                'name':p.get('Bridge_Name') or p.get('Bridge_Code') or 'Height-restricted bridge',
                'reference':p.get('Bridge_Code'),'raw_value':p.get('Signed_Headroom'),
                'source':src['name'],'source_url':src['source_url']
            }})
    OUT.write_text(json.dumps({'type':'FeatureCollection','features':out},ensure_ascii=False),encoding='utf-8')
    print(f'Wrote {len(out)} Penfold-relevant permanent restrictions')
if __name__=='__main__':main()
