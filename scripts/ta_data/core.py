"""Normalize and audit daily snapshots without filling prices or hiding rejected rows."""
from pathlib import Path
from functools import lru_cache
import json, hashlib
import numpy as np
import pandas as pd
import exchange_calendars as xc

PROFILES={
 'CN':dict(calendar='XSHG',timezone='Asia/Shanghai',currency='CNY',auction_minutes=0,publication_grace_minutes=20,calendar_scope='Mainland daily-session proxy; Shenzhen-specific intraday rules not modelled'),
 'HK':dict(calendar='XHKG',timezone='Asia/Hong_Kong',currency='HKD',auction_minutes=10,publication_grace_minutes=20,calendar_scope='Cash equities, including conservative closing-auction allowance'),
 'US':dict(calendar='XNYS',timezone='America/New_York',currency='USD',auction_minutes=0,publication_grace_minutes=20,calendar_scope='US regular-session proxy, including XNAS samples; extended hours excluded'),
}
ALIASES={'日期':'session_date','date':'session_date','开盘':'open','最高':'high','最低':'low','收盘':'close','成交量':'provider_volume','volume':'provider_volume','成交额':'amount','换手率':'turnover'}
SUPPORTED={'stock_zh_a_hist','stock_hk_hist','stock_us_hist','stock_zh_a_daily','stock_hk_daily','stock_us_daily','stock_zh_a_hist_tx'}
CONFIG=Path(__file__).resolve().parents[1]/'configs'
CALENDAR_OVERLAY=json.loads((CONFIG/'calendar-overrides.json').read_text(encoding='utf8'))
PRECISION_OVERRIDES=json.loads((CONFIG/'precision-overrides.json').read_text(encoding='utf8'))

def utc(value):
    t=pd.Timestamp(value)
    if t.tzinfo is None:raise ValueError('as_of/fetched_at must include timezone')
    return t.tz_convert('UTC')

def read_api(path):
    # JSON schema explicitly saved by pandas; retain column names, not inferred CSV units.
    j=json.loads(Path(path).read_text(encoding='utf8'))
    df=pd.DataFrame(j['data'])
    return df.drop(columns=['index'],errors='ignore')

@lru_cache(maxsize=24)
def schedule(market,start,end):
    profile=PROFILES[market]
    cal=xc.get_calendar(profile['calendar'],start=start,end=end)
    s=cal.schedule.copy();s.index=pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    s['session_date']=s.index.strftime('%Y-%m-%d')
    closures={x['session_date'] for x in CALENDAR_OVERLAY['closures'] if x['market']==market}
    s=s.loc[~s['session_date'].isin(closures)].copy()
    s['session_close']=pd.to_datetime(s['close'],utc=True)
    s['bar_final_after']=s['session_close']+pd.Timedelta(minutes=profile['auction_minutes']+profile['publication_grace_minutes'])
    return s[['session_date','session_close','bar_final_after']].copy()

def verify_override(meta,override):
    j=meta['job']
    return (j['api']==override['api'] and j['market']==override['market'] and j['symbol']==override['symbol']
            and meta.get('akshare_version')==override['akshare_version']
            and meta.get('adapter_source_sha256')==override['adapter_source_sha256'])

def unit_contract(meta,overrides):
    j=meta['job'];api=j['api'];market=j['market']
    if api not in SUPPORTED:raise ValueError('Unknown adapter; no unit guessing')
    multiplier=100.0 if api=='stock_zh_a_hist' else 1.0
    status='documented_or_adapter_contract';note='CN EM lots to shares' if multiplier==100 else 'Adapter equity-volume convention: shares'
    for item in overrides:
        if verify_override(meta,item):multiplier=float(item['multiplier']);status='version_and_source_hash_pinned_crosscheck';note=item['id'];break
    if api=='stock_us_hist':status='unverified';note='EM US volume units require independent audit before use'
    return multiplier,status,note

def normalize(df,meta,start,end,as_of,overrides=()):
    j=meta['job'];market=j['market'];symbol=str(j['symbol']);api=j['api'];profile=PROFILES[market]
    if j.get('kind')=='factor':raise ValueError('Factor tables are not OHLCV')
    as_of=utc(as_of);fetched=utc(meta['finished_at'])
    if fetched>as_of:raise ValueError('Cannot treat a later fetched snapshot as observed at an earlier as_of')
    d=df.rename(columns=ALIASES).copy()
    required={'session_date','open','high','low','close','provider_volume'}
    if not required<=set(d.columns):raise ValueError('Missing columns: '+','.join(sorted(required-set(d.columns))))
    d['source_row_index']=np.arange(len(d))
    date=pd.to_datetime(d['session_date'],errors='coerce')
    d['session_date']=date.dt.strftime('%Y-%m-%d')
    malformed_dates=int(date.isna().sum())
    # Malformed dates cannot be assigned to a requested slice: retained in schema audit, raw is immutable.
    d=d.loc[d['session_date'].notna() & d['session_date'].between(start,end)].copy()
    for k in ['open','high','low','close','provider_volume']:d[k]=pd.to_numeric(d[k],errors='coerce')
    d['amount']=pd.to_numeric(d['amount'],errors='coerce') if 'amount' in d else np.nan
    d=d.sort_values(['session_date','source_row_index']).reset_index(drop=True)
    # Calendar extends to Friday beyond requested end so an incomplete week cannot appear complete.
    a=pd.Timestamp(start)-pd.Timedelta(days=7);b=pd.Timestamp(end)+pd.Timedelta(days=7)
    s=schedule(market,a.strftime('%Y-%m-%d'),b.strftime('%Y-%m-%d')).reset_index(drop=True)
    d=d.merge(s,on='session_date',how='left',validate='many_to_one')
    flags=[[] for _ in range(len(d))]
    def flag(mask,name):
        for i in np.flatnonzero(np.asarray(mask,dtype=bool)):flags[int(i)].append(name)
    duplicate=d['session_date'].duplicated(keep=False);flag(duplicate,'DUPLICATE_SESSION')
    # Preserve original prices. Repair only source-pinned, tiny invariant-breaking float tails.
    prices=['open','high','low','close']
    for col in prices:d['provider_'+col]=d[col]
    for item in PRECISION_OVERRIDES:
        if verify_override(meta,item) and j['kwargs'].get('adjust','')=='':
            rounded=d[prices].round(item['decimals'])
            bad=(d['low']>d[['open','close']].min(axis=1))|(d['high']<d[['open','close']].max(axis=1))|(d['high']<d['low'])
            repaired_order=(rounded['low']<=rounded[['open','close']].min(axis=1))&(rounded['high']>=rounded[['open','close']].max(axis=1))&(rounded['high']>=rounded['low'])
            repair=bad & ((rounded-d[prices]).abs().max(axis=1)<=item['max_abs_change']) & repaired_order
            d.loc[repair,prices]=rounded.loc[repair,prices]
            flag(repair,'SINA_HK_FLOAT_TAIL_REPAIRED')
            break
    finite=np.isfinite(d[['open','high','low','close']]).all(axis=1);flag(~finite,'NONFINITE_OHLC')
    ordered=(d['low']<=d[['open','close']].min(axis=1)+1e-6)&(d['high']>=d[['open','close']].max(axis=1)-1e-6)&(d['high']>=d['low'])
    flag(finite&~ordered,'OHLC_ORDER_ERROR')
    adjust=j['kwargs'].get('adjust','');basis={'':'raw','qfq':'qfq','hfq':'hfq'}.get(adjust)
    if basis is None:raise ValueError('Unsupported price basis')
    nonpositive=(d[['open','high','low','close']]<=0).any(axis=1)
    flag(nonpositive,'NONPOSITIVE_RAW_PRICE' if basis=='raw' else 'NONPOSITIVE_ADJUSTED_PRICE')
    calendar_known=d['session_close'].notna();flag(~calendar_known,'NOT_IN_CALENDAR')
    final=calendar_known & (d['bar_final_after']<=as_of);flag(calendar_known&~final,'UNFINISHED_OR_GRACE_PERIOD')
    vfinite=np.isfinite(d['provider_volume']) & (d['provider_volume']>=0);flag(~vfinite,'INVALID_VOLUME');flag(d['provider_volume']==0,'ZERO_VOLUME')
    multiplier,unit_status,unit_note=unit_contract(meta,overrides)
    d['volume']=d['provider_volume']*multiplier;d['volume_multiplier']=multiplier;d['volume_unit']='shares';d['volume_unit_status']=unit_status;d['volume_note']=unit_note
    vwap=d['amount']/d['volume'].replace(0,np.nan)
    # Only raw prices can be compared with raw monetary turnover.
    vwap_bad=(d['amount']>0)&(d['volume']>0)&((vwap<d['low']*.98)|(vwap>d['high']*1.02)) if basis=='raw' else pd.Series(False,index=d.index)
    flag(vwap_bad,'AMOUNT_VOLUME_PRICE_INCONSISTENT')
    d['implied_vwap']=vwap
    if unit_status=='unverified':flag(pd.Series(True,index=d.index),'UNVERIFIED_VOLUME_UNIT')
    d['market']=market;d['symbol']=symbol;d['timeframe']='1d';d['currency']=profile['currency'];d['price_basis']=basis;d['source_api']=api
    d['calendar_version']=xc.__version__+':'+profile['calendar']+'+'+CALENDAR_OVERLAY['version'];d['calendar_scope']=profile['calendar_scope']
    d['observed_at']=fetched;d['available_at']=d['bar_final_after'].where(d['bar_final_after']>fetched,fetched)
    d.loc[~calendar_known,'available_at']=pd.NaT
    d['historical_availability']='unknown_before_snapshot';d['historical_model_available_at']=d['bar_final_after']
    d['is_final']=final;d['price_usable']=finite&ordered&~nonpositive&calendar_known&final&~duplicate&(d['provider_volume']!=0)
    d['volume_usable']=d['price_usable']&vfinite&(d['provider_volume']>0)&~vwap_bad&(unit_status!='unverified')
    d['source_snapshot_sha256']=meta.get('api_return_sha256','');d['tick_size']=np.nan
    d['corporate_action_verified']=False;d['point_in_time_history_verified']=False
    # Missing days remain unclassified. Segment boundaries stop rolling calculations crossing gaps silently.
    expected=s.loc[s['session_date'].between(start,end)&(s['bar_final_after']<=as_of),'session_date'].tolist()
    observed=set(d.loc[d['price_usable'],'session_date']);missing=sorted(set(expected)-observed)
    session_position={v:i for i,v in enumerate(s['session_date'])};seg=0;prev=None;gaps=[];segments=[]
    for _,row in d.iterrows():
        pos=session_position.get(row['session_date']);gap=0 if prev is None or pos is None else max(pos-prev-1,0)
        if gap or not row['price_usable']:seg+=1
        gaps.append(gap);segments.append(seg)
        if row['price_usable']:prev=pos
        else:prev=None;seg+=1
    d['gap_before_sessions']=gaps;d['segment_id']=segments;flag(d['gap_before_sessions']>0,'GAP_BEFORE_UNCLASSIFIED')
    d['quality_flags']=[json.dumps(x,ensure_ascii=False) for x in flags]
    all_flags={name:sum(name in x for x in flags) for name in sorted({y for x in flags for y in x})}
    valid=d.loc[d['price_usable']];last=valid['session_date'].max() if len(valid) else None
    freshness=sum(x>last for x in expected) if last else len(expected)
    audit=dict(market=market,symbol=symbol,api=api,price_basis=basis,requested_start=start,requested_end=end,as_of=as_of.isoformat(),fetched_at=fetched.isoformat(),rows_in_slice=len(d),price_usable_rows=int(d['price_usable'].sum()),volume_usable_rows=int(d['volume_usable'].sum()),first_available=d['session_date'].min() if len(d) else None,last_available=d['session_date'].max() if len(d) else None,last_final_usable=last,expected_last_final=expected[-1] if expected else None,stale_sessions=freshness,missing_sessions=missing,malformed_dates_in_api_return=malformed_dates,flags=all_flags,volume_multiplier=multiplier,volume_unit_status=unit_status,volume_note=unit_note,status='RESEARCH_DATA_AVAILABLE' if len(valid)>0 else 'DATA_INSUFFICIENT',live_enabled=False,strict_point_in_time_history=False,corporate_action_truth_verified=False)
    if malformed_dates:audit['schema_warning']='Malformed dates retained only in immutable raw; scope of missing rows unknown'
    return d,audit

def weekly(d,as_of):
    """Only full market-calendar weeks; a suspension/missing day prevents a complete weekly bar."""
    if d.empty:return pd.DataFrame()
    markets=d['market'].unique();symbols=d['symbol'].unique();bases=d['price_basis'].unique();sources=d['source_api'].unique()
    if not all(len(v)==1 for v in (markets,symbols,bases,sources)):raise ValueError('Do not blend symbols, bases or providers')
    as_of=utc(as_of);market=markets[0]
    lo=pd.Timestamp(d['session_date'].min())-pd.Timedelta(days=7);hi=pd.Timestamp(d['session_date'].max())+pd.Timedelta(days=7)
    s=schedule(market,lo.strftime('%Y-%m-%d'),hi.strftime('%Y-%m-%d')).copy()
    s['week']=pd.to_datetime(s['session_date']).dt.to_period('W-FRI').astype(str)
    q=d.loc[d['price_usable'] & (d['available_at']<=as_of)].copy();q['week']=pd.to_datetime(q['session_date']).dt.to_period('W-FRI').astype(str)
    rows=[]
    for week,group in q.groupby('week',sort=True):
        required=s.loc[s['week']==week];g=group.sort_values('session_date')
        if not set(required['session_date'])==set(g['session_date']):continue
        if required['bar_final_after'].max()>as_of:continue
        rows.append(dict(market=market,symbol=symbols[0],timeframe='1w',week=week,session_date=g['session_date'].iloc[-1],open=float(g['open'].iloc[0]),high=float(g['high'].max()),low=float(g['low'].min()),close=float(g['close'].iloc[-1]),volume=float(g['volume'].sum()) if g['volume_usable'].all() else None,volume_usable=bool(g['volume_usable'].all()),volume_unit='shares',price_basis=bases[0],source_api=sources[0],currency=g['currency'].iloc[0],available_at=max(g['available_at'].max(),required['bar_final_after'].max()),bar_final_after=required['bar_final_after'].max(),observed_at=g['observed_at'].max(),is_final=True,price_usable=True,point_in_time_history_verified=False,session_count=len(g)))
    return pd.DataFrame(rows)

def select_asof(d,as_of,mode='observed'):
    as_of=utc(as_of)
    if mode=='observed':return d.loc[d['price_usable']&(d['available_at']<=as_of)].copy()
    if mode=='historical_model':
        q=d.loc[d['price_usable']&(d['historical_model_available_at']<=as_of)].copy();q.attrs['warning']='Retrospective availability assumption; not verified point-in-time history';return q
    raise ValueError('mode must be observed or explicitly historical_model')

def normalized_hash(d):
    # File bytes may vary by parquet writer; the canonical row representation is also pinned.
    return hashlib.sha256(d.to_json(orient='records',date_format='iso',double_precision=15).encode()).hexdigest()
