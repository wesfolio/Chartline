import copy
import numpy as np
import pandas as pd
import pytest
from analyze_market import correlations,full_weeks
from ta_engine.decision import validate_decision,forecast_outcome
from ta_engine.indicators import features
from ta_engine.patterns import geometry
from test_engine import frame,NOW

def test_correlation_uses_chronological_stock_window():
    dates=pd.bdate_range('2025-01-01',periods=200).strftime('%Y-%m-%d')
    closes=100*np.cumprod(1+np.sin(np.arange(200))*.01)
    related=pd.DataFrame(dict(session_date=dates,close=closes,engine_segment=1))
    stock=related.iloc[70:].copy()
    out=correlations({'equity_daily':stock,'equity_weekly':stock,'other':related})
    r=next(x for x in out if x['window_sessions']==60 and x['lag_sessions']==0)
    assert r['samples']==60 and r['pearson']==pytest.approx(1)

def test_full_holiday_week_does_not_reset_weekly_indicators():
    from ta_data.core import normalize
    import json
    from pathlib import Path
    base=Path(__file__).parent/'fixtures'
    bundle=json.loads((base/'bundle.json').read_text(encoding='utf8'))
    item=next(x for x in bundle['items'] if x['kind']=='equity')
    meta=json.loads((base/item['meta_file']).read_text(encoding='utf8'))
    from ta_data.core import read_api
    raw=read_api(base/item['rows_file'])
    d,_=normalize(raw,meta,'2020-01-01','2026-09-17',bundle['as_of'])
    w=full_weeks(d,bundle['as_of']);f,_=features(w,bundle['as_of'])
    assert np.isfinite(f.iloc[-1].dea)
    # A genuinely missing completed week must still break continuity.
    remove=w.iloc[-10].week
    broken=d.loc[pd.to_datetime(d.session_date).dt.to_period('W-FRI').astype(str)!=remove]
    wb=full_weeks(broken,bundle['as_of'])
    assert wb.segment_id.iloc[-1]>wb.segment_id.iloc[0]

def conclusion_fixture():
    a=dict(market='CN',target_date='2026-09-18',audits={'equity':{'stale_sessions':0}})
    n={'conclusion':dict(direction='BULLISH',target_date='2026-09-18',reference_close=10.,confidence='低',support='结构',opposition='阻力',resolution='趋势优先',invalidation='跌破支撑',coverage_review={'Q'+str(i).zfill(2):dict(status='NOT_APPLICABLE',reason='测试样本') for i in range(1,42)},actions=[dict(action='BUY',condition='收盘确认',price_source='支撑',price_range=[9.,10.],price_basis='RESEARCH_ADJUSTED',confirmation_timing='CLOSE',execution='NEXT_SESSION')])}
    from ta_engine.book_stage import MODEL_IDS,FROZEN_FIELDS
    n['book_judgment']={k:n['conclusion'][k] for k in FROZEN_FIELDS}
    n['book_judgment'].update(model_review={k:copy.deepcopy(n['conclusion']['coverage_review'][k]) for k in MODEL_IDS},evidence_rule_ids=['Q09'])
    n['timing_review']='独立方向已保存，择时不改方向'
    return a,n,{'equity_daily':[dict(session_date='2026-09-17',close=10.)]}

def test_formal_conclusion_and_timing_gate():
    a,n,f=conclusion_fixture();assert validate_decision(a,n,f)['direction']=='BULLISH'
    n['conclusion']['actions'][0]['execution']='SAME_SESSION'
    with pytest.raises(ValueError,match='earlier'):validate_decision(a,n,f)

def test_missing_coverage_or_conclusion_rejected():
    a,n,f=conclusion_fixture()
    with pytest.raises(ValueError,match='conclusion'):validate_decision(a,{},f)
    del n['conclusion']['coverage_review']['Q21']
    with pytest.raises(ValueError,match='every'):validate_decision(a,n,f)

def test_flat_not_direction_hit():
    assert forecast_outcome(10,10,'BULLISH')['correct'] is False
    assert forecast_outcome(10,11,'BULLISH')['correct'] is True

def test_moving_averages_and_bare_shadows():
    d,_=features(frame(70,prices=np.linspace(10,20,70)),NOW)
    assert np.isfinite(d.iloc[-1].sma50) and np.isfinite(d.iloc[-1].ema20)
    x=pd.DataFrame([dict(open=10,close=11,high=11,low=9,scale=1),dict(open=11,close=10,high=12,low=10,scale=1),dict(open=10,close=10,high=10,low=9,scale=1)])
    g=geometry(x)
    assert list(g.appearance16)==['BULL_LOWER_SHADOW_ONLY','BEAR_UPPER_SHADOW_ONLY','T_DOJI']

def test_all_source_pages_figures_and_rules_have_traceable_mapping():
    from audit_sources import audit
    assert audit()['source_pages']==36


def test_timing_cannot_change_book_direction():
    a,n,f=conclusion_fixture();n['conclusion']['direction']='BEARISH'
    with pytest.raises(ValueError,match='frozen'):validate_decision(a,n,f)

def test_book_judgment_rejects_bbi_and_missing_model():
    a,n,f=conclusion_fixture();n['book_judgment']['support']='BBI上行'
    with pytest.raises(ValueError,match='exclude BBI'):validate_decision(a,n,f)
    a,n,f=conclusion_fixture();del n['book_judgment']['model_review']['Q24']
    with pytest.raises(ValueError,match='27'):validate_decision(a,n,f)

def test_book_evidence_invariant_to_bbi_changes():
    from ta_engine.book_stage import book_view
    a={'models':[{'rule_id':'Q09','reasoning':'价格结构'},{'rule_id':'Q36','values':{'bbi':9}}],'price_cards':[{'bbi':9}]}
    f={'equity_daily':[{'close':10,'bbi':9,'above_bbi':True,'structure':'UP'}]}
    original=book_view(a,f)
    a['models'][1]['values']['bbi']=100;a['price_cards'][0]['bbi']=100
    f['equity_daily'][0].update(bbi=100,above_bbi=False)
    assert book_view(a,f)==original
    import json
    assert 'BBI' not in json.dumps(original).upper()
    assert len(original['model_catalog']['models'])==27

def test_bbi_allowed_only_in_last_timing_review():
    a,n,f=conclusion_fixture();n['timing_review']='BBI未触线，暂不买入'
    assert validate_decision(a,n,f)
    n['summary']='BBI提高看涨强度'
    with pytest.raises(ValueError,match='final timing'):validate_decision(a,n,f)
