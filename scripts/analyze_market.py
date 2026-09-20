"""Audited snapshot analysis. No strategy score, calibrated probability, or order routing."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from ta_data.core import normalize, read_api, schedule, weekly, utc
from ta_engine.indicators import features, BBI_CONFIG
from ta_engine.analyze import model_rows, num
from ta_engine.patterns import scan_patterns, latest_summary, fuse_setups
from ta_engine.backtest import event_study
from ta_engine.book_stage import book_view

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def records(d):return json.loads(d.to_json(orient='records',date_format='iso',force_ascii=False))
def checked(root,item):
    path=root/item['rows_file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Snapshot hash mismatch: '+item['id'])
    return path

def related_frame(path,item,asof,root):
    if utc(item['fetched_at'])>utc(asof):raise ValueError('Snapshot fetched after as_of')
    if item['format']=='eastmoney':
        j=json.loads(path.read_text(encoding='utf8'))['data'];d=pd.DataFrame([s.split(',') for s in j['klines']],columns=['session_date','open','close','high','low','volume','amount','amplitude','provider_change_pct','provider_change','turnover'])
    else:
        d=read_api(path).rename(columns={'date':'session_date','日期':'session_date','开盘':'open','最高':'high','最低':'low','收盘':'close','成交量':'volume'});d['session_date']=pd.to_datetime(d.session_date).dt.strftime('%Y-%m-%d')
    for c in ['open','high','low','close','volume']:d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d.sort_values('session_date').reset_index(drop=True)
    market=item.get('market','CN');tz={'CN':'Asia/Shanghai','HK':'Asia/Hong_Kong','US':'America/New_York'}[market]
    end=max(pd.Timestamp(d.session_date.max()),utc(asof).tz_convert(tz).tz_localize(None).normalize())+pd.Timedelta(days=7)
    cal=schedule(market,d.session_date.min(),end.strftime('%Y-%m-%d')).reset_index(drop=True)
    d=d.merge(cal,on='session_date',how='left');pos={s:i for i,s in enumerate(cal.session_date)}
    valid=np.isfinite(d[['open','high','low','close']]).all(axis=1)&(d[['open','high','low','close']]>0).all(axis=1)&(d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))&~d.session_date.duplicated(keep=False)
    d['price_usable']=valid&d.bar_final_after.notna()&(d.bar_final_after<=utc(asof));d['volume_usable']=d.price_usable&np.isfinite(d.volume)&(d.volume>0)
    d['segment_id']=(d.session_date.map(pos).diff().ne(1)|~d.price_usable|~d.price_usable.shift(fill_value=True)).cumsum()
    d['available_at']=utc(item['fetched_at']);d['observed_at']=utc(item['fetched_at']);d['is_final']=d.bar_final_after<=utc(asof)
    d['market']=market;d['symbol']=item.get('symbol',item['id']);d['timeframe']='1d';d['source_api']=item['format'];d['price_basis']=item.get('price_basis','provider_series');d['currency']=item.get('price_unit','provider units')
    last=d.loc[d.price_usable,'session_date'].max();expected=cal.loc[cal.bar_final_after<=utc(asof),'session_date']
    return d,dict(status='RESEARCH_DATA_AVAILABLE',last_final_usable=last,stale_sessions=int((expected>last).sum()) if pd.notna(last) else len(expected),rejected_rows=int((~d.price_usable).sum()),calendar_scope=market+' cash-session proxy; instrument-specific sessions require verification',series_construction_verified=False,volume_unit=item.get('volume_label','provider volume; not independently audited'))

def full_weeks(d,asof):
    w=weekly(d,asof)
    if w.empty:return w
    groups={str(k):g for k,g in d.groupby(pd.to_datetime(d.session_date).dt.to_period('W-FRI'))}
    w['segment_id']=[groups[x].segment_id.iloc[-1] for x in w.week]
    # An excluded partial week breaks weekly indicator continuity as well.
    cal=schedule(str(d.market.iloc[0]),str(d.session_date.min()),str(d.session_date.max()))
    expected=pd.to_datetime(cal.session_date).dt.to_period('W-FRI').astype(str).drop_duplicates().tolist()
    positions={key:i for i,key in enumerate(expected)}
    gap=w.week.map(positions).diff().ne(1)
    w['segment_id']=(gap|w.segment_id.diff().ne(0)).cumsum()
    return w

def support_card(d,tf):
    if d.empty:return dict(timeframe=tf,state='INSUFFICIENT',sufficient_to_buy=False)
    r=d.iloc[-1]
    return dict(timeframe=tf,state='SUPPORT_ONLY',support_present=bool(r.bbi_support_present),sufficient_to_buy=False,buy_action=None,bbi=num(r.bbi),reference_bbi=num(r.bbi_prior),prior_above_run=int(r.bbi_prior_above_run),required_bars=int(r.bbi_required_run),prior_uptrend=bool(r.bbi_prior_uptrend),exact_touch=bool(r.bbi_exact_touch),close_holds_reference=bool(r.bbi_close_holds_reference),observation_band=[num(r.bbi_band_lo),num(r.bbi_band_hi)],tradeable_buy_price=None,bar_end=r.session_date)

def returns(d):
    q=d.copy();q['session_date']=pd.to_datetime(q.session_date).dt.strftime('%Y-%m-%d');q=q.set_index('session_date').sort_index();r=q.close.pct_change(fill_method=None)
    return r.where(q.engine_segment.eq(q.engine_segment.shift()))

def correlations(frames):
    equity=frames['equity_daily'];er=returns(equity)
    out=[]
    for key,d in frames.items():
        if key in ['equity_daily','equity_weekly']:continue
        fr=returns(d)
        for lag in [0,1]:
            joined=pd.concat([er.rename('equity'),fr.shift(lag).rename('related')],axis=1).sort_index()
            joined=joined.reindex(er.index)  # windows use the stock's trading sessions, never union insertion order
            for n in [20,60,120]:
                q=joined.tail(n).dropna();out.append(dict(series=key,window_sessions=n,lag_sessions=lag,samples=len(q),complete=len(q)==n,pearson=num(q.equity.corr(q.related)) if len(q)>=3 else None))
    return out

def run(bundle,out,target=None,technical_only=False):
    root=Path(bundle).parent;b=json.loads(Path(bundle).read_text(encoding='utf8'));asof=b['as_of'];out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if target and pd.Timestamp(target).date()<=utc(asof).tz_convert({'CN':'Asia/Shanghai','HK':'Asia/Hong_Kong','US':'America/New_York'}[b['market']]).date():raise ValueError('Forecast target must be after snapshot local date; use an explicitly retrospective workflow otherwise')
    if target and target not in schedule(b['market'],target,(pd.Timestamp(target)+pd.Timedelta(days=7)).strftime('%Y-%m-%d')).session_date.tolist():raise ValueError('Target is not a known trading session')
    frames={};models=[];audits={};items={};warnings=[];pattern_files={};pattern_latest={};study_files={}
    for item in b['items']:
        key=item['id'];items[key]=item
        if item['status']!='FETCH_OK':warnings.append(key+': '+item['status']);continue
        path=checked(root,item)
        if item['kind']=='equity':
            meta=json.loads((root/item['meta_file']).read_text(encoding='utf8'));raw=read_api(path);dates=pd.to_datetime(raw['date'] if 'date' in raw else raw['日期']).dt.strftime('%Y-%m-%d')
            d,audit=normalize(raw,meta,dates.min(),utc(asof).tz_convert({'CN':'Asia/Shanghai','HK':'Asia/Hong_Kong','US':'America/New_York'}[b['market']]).strftime('%Y-%m-%d'),asof)
            parts=[('equity_daily',d,'daily'),('equity_weekly',full_weeks(d,asof),'weekly')]
        else:
            d,audit=related_frame(path,item,asof,root);parts=[(key,d,'daily')]
            warnings.append(key+': 相关序列构造、权重、换月或交易时段须按其品种单独核验。')
        audits[key]=audit
        if audit.get('stale_sessions',0)>0:warnings.append(key+': 行情缺少最近'+str(audit['stale_sessions'])+'个已完成交易日；不得称为最新行情。')
        for framekey,q,tf in parts:
            if q.empty:warnings.append(framekey+': 无完整有效K线');continue
            f,e=features(q,asof)
            if f.empty:warnings.append(framekey+': 指标输入不足');continue
            f,patterns=scan_patterns(f,e)
            frames[framekey]=f;save(out/(framekey+'.json'),records(f))
            pp=framekey+'.patterns.json';save(out/pp,patterns);pattern_files[framekey]=pp;pattern_latest[framekey]=latest_summary(patterns)
            study=event_study(f,patterns);sp=framekey+'.event-study.json';save(out/sp,study);study_files[framekey]=sp
            for m in model_rows(f,e,tf):
                m.update(series=framekey,series_name=item['name'],axis_label=('价格轴：前复权 '+{'CN':'CNY','HK':'HKD','US':'USD'}[b['market']] if item['kind']=='equity' else '价格轴：'+item.get('price_unit','供应商单位')),volume_label='成交量：百万股' if item['kind']=='equity' else item.get('volume_label','成交量：百万供应商单位'))
                models.append(m)
    if 'equity_daily' not in frames:raise ValueError('No usable equity data; see preserved source bundle')
    conflicts=[]
    for series in frames:
        group=[m for m in models if m['series']==series and m['applicable']];bull=[m['rule_id'] for m in group if m['direction']=='BULLISH'];bear=[m['rule_id'] for m in group if m['direction']=='BEARISH']
        if bull and bear:conflicts.append(dict(series=series,bullish=bull,bearish=bear,resolution='保留全部正反证据；不按模型数量投票，不推导未经校准的概率。'))
    states={k:str(v.iloc[-1].structure) for k,v in frames.items()}
    if states.get('equity_daily')!=states.get('equity_weekly'):conflicts.append(dict(type='CROSS_TIMEFRAME_DIFFERENCE',daily=states.get('equity_daily'),weekly=states.get('equity_weekly')))
    result=dict(schema_version=2,name=b['name'],symbol=b['symbol'],market=b['market'],as_of=asof,target_date=target,technical_only=technical_only,fundamental_status='OUT_OF_SCOPE_BY_REQUEST' if technical_only else 'UNKNOWN',decision='REQUIRES_EVIDENCE_SYNTHESIS',empirically_validated=False,live_trading_enabled=False,models=models,conflicts=conflicts,price_cards=[support_card(frames.get('equity_'+tf,pd.DataFrame()),tf) for tf in ['daily','weekly']],audits=audits,warnings=warnings,frames={k:k+'.json' for k in frames},pattern_files=pattern_files,latest_patterns=pattern_latest,event_study_files=study_files,source_bundle_sha256=hashlib.sha256(Path(bundle).read_bytes()).hexdigest(),source_items=b['items'],correlations=correlations(frames) if len(frames)>2 else [])
    result['fusion_setups']=fuse_setups(frames['equity_daily'],frames.get('equity_weekly'),json.loads((out/pattern_files['equity_daily']).read_text(encoding='utf8')))
    result['mode']=b.get('mode','OBSERVED_SNAPSHOT')
    result['bbi_config']=BBI_CONFIG
    save(out/'book-evidence.json',book_view(result,{k:records(v) for k,v in frames.items()}))
    result['book_evidence_file']='book-evidence.json'
    save(out/'analysis.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--target-date');p.add_argument('--technical-only',action='store_true');a=p.parse_args();run(a.bundle,a.out,a.target_date,a.technical_only);print(a.out/'analysis.json')
