import json,copy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from ta_engine.indicators import features,smooth,next_close_intersection
from ta_engine.analyze import price_card,model_rows,read_input

NOW='2026-09-14T05:49:57+00:00'
def frame(n=100,prices=None):
    c=np.array(prices if prices is not None else [10.]*n,dtype=float);n=len(c)
    return pd.DataFrame(dict(session_date=pd.bdate_range('2023-01-02',periods=n).strftime('%Y-%m-%d'),open=c,high=c+1,low=c-1,close=c,volume=np.full(n,1000.),volume_usable=True,price_usable=True,segment_id=0,is_final=True,available_at='2026-09-14T00:00:00Z',bar_final_after='2023-12-31T00:00:00Z',market='CN',symbol='SYNTHETIC',timeframe='1d',price_basis='raw',source_api='synthetic'))

def test_bbi_seed_and_known_value():
    d,_=features(frame(prices=np.arange(10,50)),NOW)
    assert d.bbi.iloc[:23].isna().all()
    assert d.bbi.iloc[23]==pytest.approx(np.mean([np.arange(10,34)[-n:].mean() for n in [3,6,12,24]]))

def test_sma_seed_ema_and_gap():
    s=pd.Series([1.,2.,3.,4.,np.nan,10.,10.,10.]);r=smooth(s,3,.5)
    assert r.iloc[2]==2 and r.iloc[3]==3 and r.iloc[4:7].isna().all() and r.iloc[7]==10

def test_atr_uses_previous_close_and_wilder_seed():
    raw=frame(35);raw.loc[1,['open','close','high','low']]=[14,14,15,13]
    d,_=features(raw,NOW)
    assert pd.isna(d.tr.iloc[0]);assert d.tr.iloc[1]==5 and d.tr.iloc[2]==5
    assert d.atr.iloc[:14].isna().all();assert d.atr.iloc[14]==pytest.approx((5+5+12*2)/14)
    assert d.scale.iloc[15]==d.atr.iloc[14]

@pytest.mark.parametrize('kind,expected',[('flat',50),('up',100),('down',0)])
def test_rsi_edges(kind,expected):
    c=np.full(40,100.) if kind=='flat' else np.arange(100,140,dtype=float) if kind=='up' else np.arange(140,100,-1,dtype=float)
    d,_=features(frame(prices=c),NOW)
    assert d.rsi.iloc[:14].isna().all() and d.rsi.iloc[-1]==expected

def test_macd_constant_zero_and_warmup():
    d,_=features(frame(),NOW)
    assert d.dif.iloc[:25].isna().all() and d.dea.iloc[:33].isna().all()
    assert d.dif.iloc[-1]==0 and d.dea.iloc[-1]==0 and d['hist'].iloc[-1]==0

def test_volume_excludes_current_bar():
    raw=frame();raw.loc[25,'volume']=10000
    d,_=features(raw,NOW);assert d.rvol.iloc[25]==10
    raw.loc[24,'volume_usable']=False;d,_=features(raw,NOW);assert pd.isna(d.rvol.iloc[25])

def test_segment_restarts_all_warmup():
    raw=frame(100);raw.loc[50:,'segment_id']=1
    d,_=features(raw,NOW);assert d.bbi.iloc[50:73].isna().all();assert d.bbi.iloc[73]==10
    assert d.dea.iloc[50:83].isna().all()

def test_invalid_price_row_breaks_window_without_filling():
    raw=frame();raw.loc[50,'price_usable']=False
    d,_=features(raw,NOW);assert len(d)==99 and d.loc[d.session_date==raw.session_date.iloc[60],'bbi'].isna().all()

def test_future_suffix_invariance():
    raw=frame(prices=100+np.sin(np.arange(100)/3)*4+np.arange(100)*.1)
    a,ea=features(raw.iloc[:70],NOW);b,eb=features(raw,NOW)
    pd.testing.assert_frame_equal(a,b.iloc[:70].reset_index(drop=True))
    assert ea==[e for e in eb if e['known_pos']<70]

def test_pivot_two_bar_delay_and_no_tied_plateau():
    raw=frame(30);raw.loc[20,'high']=15
    _,ea=features(raw.iloc[:22],NOW);_,eb=features(raw.iloc[:23],NOW)
    assert not ea and len(eb)==1 and eb[0]['pivot_pos']==20 and eb[0]['known_pos']==22
    raw.loc[21,'high']=15;_,e=features(raw,NOW);assert not e

def test_ambiguous_pivot_excluded():
    raw=frame(30);raw.loc[20,['high','low']]=[15,5]
    _,events=features(raw,NOW);assert not events

def test_observed_cutoff_and_naive_time():
    raw=frame();raw.loc[80:,'available_at']='2027-01-01T00:00Z'
    d,_=features(raw,NOW);assert len(d)==80
    with pytest.raises(ValueError):features(raw,'2026-09-14')

def test_unfinished_bar_excluded():
    raw=frame();raw.loc[99,'is_final']=False
    d,_=features(raw,NOW);assert len(d)==99

@pytest.mark.parametrize('field',['symbol','price_basis','source_api','timeframe'])
def test_mixed_identity_rejected(field):
    raw=frame();raw.loc[1,field]='different'
    with pytest.raises(ValueError,match='Mixed'):features(raw,NOW)

def test_touch_plan_unchanged_by_current_close():
    raw=frame();a,_=features(raw,NOW);raw.loc[99,['open','high','low','close']]=[10,15,9,14]
    b,_=features(raw,NOW)
    assert a.plan_lo.iloc[-1]==b.plan_lo.iloc[-1] and a.plan_hi.iloc[-1]==b.plan_hi.iloc[-1]
    assert a.bbi.iloc[-1]!=b.bbi.iloc[-1]

def test_next_close_algebra_is_condition_only():
    c=np.arange(100,130,dtype=float);x=next_close_intersection(c)
    seq=np.r_[c,x];assert x==pytest.approx(np.mean([seq[-n:].mean() for n in [3,6,12,24]]))
    assert next_close_intersection([1]*22) is None

@pytest.mark.parametrize('fund',['UNKNOWN','USER_ASSUMED','CONTRADICTED'])
def test_candidate_premise_and_execution_gates(fund):
    d,_=features(frame(),NOW)
    entry=dict(fundamental_status=fund,corporate_action_verified=False,tick_grid_verified=False,tradeable_mapping_verified=False,price_basis='qfq',mode='FROZEN_DEMONSTRATION')
    p=price_card(d,'UP',entry,'daily')
    assert p['tradeable_price_band'] is None and not p['live_enabled']
    assert p['state']=='BLOCKED' and not p['sufficient_to_buy']

def test_weekly_down_does_not_become_uptrend_buy():
    d,_=features(frame(),NOW);e=dict(fundamental_status='USER_ASSUMED',price_basis='raw',mode='FROZEN_DEMONSTRATION')
    assert price_card(d,'DOWN',e,'daily')['technical_state']=='TREND_NOT_ESTABLISHED'

def test_unknown_weekly_and_unsubstantiated_verified_premise():
    d,_=features(frame(),NOW);e=dict(fundamental_status='VERIFIED_SUPPORT',price_basis='raw',mode='FROZEN_DEMONSTRATION')
    c=price_card(d,'UNKNOWN',e,'daily')
    assert c['state']=='BLOCKED' and c['primary_weekly_structure']=='UNKNOWN'
    assert '声称已核验但未提供基本面证据' in c['blockers']

def test_naive_input_timestamp_rejected():
    raw=frame();raw.loc[0,'available_at']='2026-09-14'
    with pytest.raises(ValueError,match='timezone'):features(raw,NOW)

def test_price_up_rsi_extreme_not_automatic_bearish():
    d,e=features(frame(prices=np.arange(100,200)),NOW)
    r=next(x for x in model_rows(d,e,'daily') if x['rule_id']=='Q30')
    assert r['values']['rsi']==100 and r['direction']=='NEUTRAL'

