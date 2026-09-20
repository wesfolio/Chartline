import numpy as np
import pandas as pd
from ta_engine.patterns import geometry,candle_events,reversal_patterns,consolidation_patterns,flags_and_rounding,triple_and_diamond

def bars(rows):
    d=pd.DataFrame(rows);n=len(d);d['session_date']=pd.bdate_range('2025-01-02',periods=n).strftime('%Y-%m-%d');d['available_at']='2026-09-17T00:00:00Z';d['scale']=1.;d['atr']=1.;d['structure']='UNKNOWN';d['rvol']=1.;d['rsi']=50.;d['rsi_divergence']='NONE';return geometry(d)
def pivot(d,kind,pos,price):return dict(kind=kind,pivot_pos=pos,known_pos=pos+2,pivot_date=d.iloc[pos].session_date,known_date=d.iloc[pos+2].session_date,price=float(price),known_at=str(d.iloc[pos+2].available_at),rsi=50)

def test_dark_cloud_piercing_and_recovery_subtype():
    d=bars([dict(open=10,high=10.3,low=9.7,close=10),dict(open=10,high=12.2,low=9.8,close=12),dict(open=12.5,high=12.6,low=10.5,close=10.8),dict(open=10,high=10.2,low=8.8,close=9),dict(open=8.7,high=10.0,low=8.5,close=9.8)])
    d.loc[0,'structure']='UP';d.loc[2,'structure']='DOWN'
    ev=candle_events(d)
    assert any(x['pattern']=='DARK_CLOUD_COVER' for x in ev)
    assert any(x['pattern']=='PIERCING_LINE' for x in ev)

def test_morning_doji_star_abandoned_baby_and_harami():
    d=bars([dict(open=12,high=12.2,low=11.8,close=12),dict(open=12,high=12.1,low=9.5,close=10),dict(open=8.8,high=8.9,low=8.7,close=8.8),dict(open=9.2,high=11.5,low=9.1,close=11.2),dict(open=10,high=12.2,low=9.8,close=12),dict(open=11.5,high=11.7,low=11.2,close=11.4)])
    d.loc[0,'structure']='DOWN';d.loc[3,'structure']='UP'
    ev=candle_events(d)
    assert any(x['pattern']=='MORNING_DOJI_STAR' for x in ev)
    assert any(x['pattern']=='ABANDONED_BABY_BOTTOM' for x in ev)
    assert any(x['pattern']=='HARAMI' for x in ev)

def test_head_shoulders_and_rectangle_are_causal():
    rows=[dict(open=11,high=12,low=10,close=11) for _ in range(60)];d=bars(rows)
    ps=[pivot(d,'HIGH',10,14),pivot(d,'LOW',18,11),pivot(d,'HIGH',26,16),pivot(d,'LOW',34,11.5),pivot(d,'HIGH',42,14.2)]
    d.loc[45,'close']=10
    hs=next(x for x in reversal_patterns(d,ps) if x['pattern']=='HEAD_AND_SHOULDERS_TOP')
    assert hs['known_pos']==44 and hs['confirmation_pos']>44
    rd=bars([dict(open=11.,high=12.,low=10.,close=11.) for _ in range(25)]);rd.loc[20:,'close']=13.;rd.loc[20:,'high']=13.2
    rp=[pivot(rd,'HIGH',3,12),pivot(rd,'LOW',6,10),pivot(rd,'HIGH',10,12),pivot(rd,'LOW',14,10)]
    rect=next(x for x in consolidation_patterns(rd,rp) if x['pattern']=='RECTANGLE')
    assert rect['known_pos']==19 and rect['confirmation_pos']==20 and rect['values']['reference_target']==14

def test_flag_triangle_triple_and_rounding_catalog():
    close=list(np.linspace(10,15,6))+list(np.linspace(14.9,14.4,10))+[15.5,16,16.5,17]
    d=bars([dict(open=c-.1,high=c+.3,low=c-.3,close=c) for c in close])
    assert any(x['rule_id']=='Q27' for x in flags_and_rounding(d))
    curve=10+3*np.linspace(-1,1,20)**2;rd=bars([dict(open=c,high=c+.2,low=c-.2,close=c) for c in curve])
    assert any(x['pattern']=='ROUNDING_BOTTOM' for x in flags_and_rounding(rd))
    td=bars([dict(open=11,high=12,low=10,close=11) for _ in range(40)])
    tri=[pivot(td,'HIGH',5,14),pivot(td,'LOW',8,9),pivot(td,'HIGH',12,13),pivot(td,'LOW',15,10),pivot(td,'HIGH',20,12),pivot(td,'LOW',23,11)]
    assert any(x['pattern']=='SYMMETRICAL_TRIANGLE' for x in consolidation_patterns(td,tri))
    triple=[pivot(td,'HIGH',5,14),pivot(td,'LOW',9,11),pivot(td,'HIGH',13,14.2),pivot(td,'LOW',17,11.2),pivot(td,'HIGH',21,13.9)]
    assert any(x['pattern']=='TRIPLE_TOP' for x in triple_and_diamond(td,triple))
