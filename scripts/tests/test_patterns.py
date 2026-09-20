import pandas as pd
import numpy as np
from ta_engine.patterns import geometry,candle_events,scan_patterns
from ta_engine.backtest import event_study,simulate_long
from test_engine import frame,NOW
from ta_engine.indicators import features

def ready(rows):
    d=pd.DataFrame(rows);n=len(d);d['session_date']=pd.bdate_range('2026-01-02',periods=n).strftime('%Y-%m-%d');d['available_at']='2026-09-14T00:00:00Z';d['scale']=1.;d['atr']=1.;d['structure']='UNKNOWN';d['rvol']=1.;return geometry(d)

def test_doji_spinning_hammer_geometry():
    d=ready([dict(open=10,high=11,low=9,close=10),dict(open=10,high=10.4,low=8,close=10.3)])
    assert d.iloc[0].doji
    assert d.iloc[1].umbrella_shape
    assert 'DOJI' in d.iloc[0].candle_labels

def test_hammer_requires_prior_down_and_future_confirmation():
    rows=[dict(open=10,high=10.3,low=9.7,close=9.8),dict(open=9.8,high=10,low=8,close=9.6),dict(open=9.7,high=10.8,low=9.5,close=10.5)]
    d=ready(rows);d.loc[0,'structure']='DOWN'
    ev=candle_events(d);h=next(x for x in ev if x['pattern']=='HAMMER')
    assert h['known_pos']==1 and h['state']=='CONFIRMED' and h['confirmation_pos']==2

def test_window_created_bar_cannot_fill_itself():
    d=ready([dict(open=9,high=10,low=8,close=9),dict(open=12,high=13,low=11,close=12),dict(open=11,high=12,low=9,close=10)])
    w=next(x for x in candle_events(d) if x['rule_id']=='Q23')
    assert w['known_pos']==1 and w['values']['filled_at']==d.iloc[2].session_date

def test_double_bottom_causal_confirmation():
    raw=frame(45,prices=np.linspace(12,14,45));d,_=features(raw,NOW)
    piv=[dict(kind='LOW',pivot_date=d.iloc[16].session_date,known_date=d.iloc[18].session_date,price=10.,pivot_pos=16,known_pos=18,known_at=str(d.iloc[18].available_at),segment=int(d.iloc[0].engine_segment),rsi=30),dict(kind='HIGH',pivot_date=d.iloc[24].session_date,known_date=d.iloc[26].session_date,price=13.,pivot_pos=24,known_pos=26,known_at=str(d.iloc[26].available_at),segment=int(d.iloc[0].engine_segment),rsi=50),dict(kind='LOW',pivot_date=d.iloc[32].session_date,known_date=d.iloc[34].session_date,price=10.2,pivot_pos=32,known_pos=34,known_at=str(d.iloc[34].available_at),segment=int(d.iloc[0].engine_segment),rsi=35)]
    d.loc[35:37,'close']=[12.5,13.3,14]
    _,events=scan_patterns(d,piv);q=next(x for x in events if x['pattern']=='DOUBLE_BOTTOM')
    assert q['known_pos']==34 and q['state'] in ['CONFIRMED','RETEST_CONFIRMED'] and q['confirmation_pos']>=35 and q['values']['reference_target']>13

def test_event_study_never_enters_on_signal_close():
    d=ready([dict(open=10,high=11,low=9,close=10),dict(open=12,high=13,low=11,close=12),dict(open=13,high=14,low=12,close=13)])
    ev=[dict(id='x',rule_id='Q25',pattern='DOUBLE_BOTTOM',direction='BULLISH',state='CONFIRMED',confirmation_pos=0,terminal_date=d.iloc[0].session_date)]
    study=event_study(d,ev,horizons=(1,));assert study[0]['entry_open']==12 and study[0]['entry_date']==d.iloc[1].session_date
    sim=simulate_long(d,ev,{})
    assert sim['status']=='EXECUTION_PROFILE_REQUIRED'
