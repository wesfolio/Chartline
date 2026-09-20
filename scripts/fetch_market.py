"""Capture immutable public market snapshots; never place orders."""
import argparse, hashlib, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def now(): return datetime.now(timezone.utc).isoformat()
def save(path, obj): path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--market',choices=['CN','HK','US'],required=True);p.add_argument('--symbol',required=True);p.add_argument('--name',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--related-config',type=Path);a=p.parse_args()
    if a.market=='CN':
        if not re.fullmatch(r'[036]\d{5}',a.symbol): p.error('Only verified Shanghai/Shenzhen six-digit symbols are supported')
        api='stock_zh_a_daily';kwargs=dict(symbol=('sh' if a.symbol.startswith('6') else 'sz')+a.symbol,start_date='20200101',end_date=datetime.now().strftime('%Y%m%d'),adjust='qfq')
    elif a.market=='HK':
        if not re.fullmatch(r'\d{5}',a.symbol):p.error('HK symbol must have five digits')
        api='stock_hk_daily';kwargs=dict(symbol=a.symbol,adjust='qfq')
    else:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9.\-]{0,15}',a.symbol):p.error('Invalid US symbol')
        api='stock_us_daily';kwargs=dict(symbol=a.symbol.upper(),adjust='qfq')
    a.out.mkdir(parents=True,exist_ok=False);items=[]
    def worker(key,name,job,kind):
        path=a.out/(key+'-job.json');save(path,job)
        try:
            subprocess.run([sys.executable,str(Path(__file__).parent/'ta_data/worker.py'),str(path),str(a.out/key)],timeout=75,check=True)
            meta=json.loads((a.out/key/'result.json').read_text(encoding='utf8'))
            item=dict(id=key,name=name,kind=kind,status=meta['status'],format='akshare',meta_file=f'{key}/result.json',rows_file=f'{key}/api-return.json',fetched_at=meta['finished_at'])
            if meta['status']=='FETCH_OK':item['sha256']=sha(a.out/item['rows_file'])
        except Exception as exc:item=dict(id=key,name=name,kind=kind,status='FETCH_ERROR',error=type(exc).__name__)
        items.append(item)
    worker('equity',a.name,dict(api=api,market=a.market,symbol=a.symbol,kwargs=kwargs),'equity')
    if a.related_config:
        config=json.loads(a.related_config.read_text(encoding='utf8'));series=config.get('series')
        if not isinstance(series,list) or not series:raise ValueError('related-config requires a non-empty series list')
        import requests
        for spec in series:
            key=spec['id'];name=spec['name'];transport=spec['transport'];market=spec.get('market','CN');symbol=str(spec.get('symbol',key))
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',key):raise ValueError('Unsafe related-series id')
            if transport=='akshare':
                worker(key,name,dict(api=spec['api'],market=market,symbol=symbol,kwargs=spec.get('kwargs',{})),'related')
                items[-1].update(price_basis=spec.get('price_basis','provider_series'),price_unit=spec.get('price_unit','provider units'),volume_label=spec.get('volume_label','provider volume'),role=spec.get('role','related_market'),market=market,symbol=symbol)
                continue
            if transport!='eastmoney':raise ValueError('transport must be akshare or eastmoney')
            code=spec['secid']
            url='https://push2his.eastmoney.com/api/qt/stock/kline/get'
            params=dict(secid=code,klt=101,fqt=0,beg=spec.get('beg','20200101'),end=spec.get('end','20500101'),lmt=spec.get('limit',2000),fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61')
            try:
                r=requests.get(url,params=params,timeout=(8,25));r.raise_for_status();j=r.json()
                if not j.get('data',{}).get('klines'):raise ValueError('Empty futures response')
                path=a.out/(key+'.json');save(path,j)
                items.append(dict(id=key,name=name,kind='related',status='FETCH_OK',format='eastmoney',rows_file=path.name,sha256=sha(path),fetched_at=now(),source_url=r.url,symbol=symbol,market=market,price_basis=spec.get('price_basis','provider_series'),price_unit=spec.get('price_unit','provider units'),volume_label=spec.get('volume_label','provider volume'),role=spec.get('role','related_market')))
            except Exception as exc:items.append(dict(id=key,name=name,kind='related',status='FETCH_ERROR',error=type(exc).__name__,market=market,symbol=symbol,role=spec.get('role','related_market')))
    save(a.out/'bundle.json',dict(schema_version=2,as_of=now(),market=a.market,symbol=a.symbol,name=a.name,related_config=str(a.related_config) if a.related_config else None,items=items))
    print(a.out/'bundle.json')

if __name__=='__main__':main()
