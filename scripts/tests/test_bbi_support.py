import pandas as pd
import pytest
from ta_engine.indicators import bbi_support
from ta_engine.analyze import price_card
from test_engine import frame,NOW
from ta_engine.indicators import features

def sample(closes,low=10,high=12):
    d=pd.DataFrame(dict(close=closes,bbi=10.,bbi_prior=10.,low=11.,high=12.))
    d.loc[len(d)-1,['low','high']]=[low,high]
    return d

def test_prior_run_excludes_current_bar():
    r=bbi_support(sample([11]*5),5).iloc[-1]
    assert r.bbi_prior_above_run==4 and not r.bbi_support_present

def test_established_run_then_touch_is_only_support():
    r=bbi_support(sample([11]*6),5).iloc[-1]
    assert r.bbi_prior_above_run==5 and r.bbi_support_present

@pytest.mark.parametrize('middle',[10.,9.])
def test_equal_or_below_breaks_continuity(middle):
    r=bbi_support(sample([11,11,middle,11,11,11]),5).iloc[-1]
    assert r.bbi_prior_above_run==2 and not r.bbi_support_present

def test_near_band_is_not_touch():
    r=bbi_support(sample([11]*6,low=10.01),5).iloc[-1]
    assert r.bbi_prior_uptrend and not r.bbi_exact_touch and not r.bbi_support_present

def test_break_below_at_close_withdraws_support():
    r=bbi_support(sample([11]*5+[9.9],low=9.8),5).iloc[-1]
    assert r.bbi_prior_uptrend and r.bbi_exact_touch and not r.bbi_support_present

def test_daily_and_weekly_thresholds_are_independent():
    d=sample([11]*4)
    assert bbi_support(d,3).iloc[-1].bbi_support_present
    assert not bbi_support(d,5).iloc[-1].bbi_support_present

def test_same_input_prefix_preserves_support():
    d=sample([11]*10)
    pd.testing.assert_frame_equal(bbi_support(d.iloc[:6],5),bbi_support(d,5).iloc[:6])

def test_all_other_flags_true_still_no_buy_action():
    d,_=features(frame(),NOW)
    for k,v in dict(bbi_prior_uptrend=True,bbi_support_present=True,bbi_exact_touch=True,bbi_close_holds_reference=True,bbi_prior_above_run=5,bbi_required_run=5).items():d.loc[d.index[-1],k]=v
    e=dict(fundamental_status='VERIFIED_SUPPORT',fundamental_evidence=['synthetic test premise'],corporate_action_verified=True,tick_grid_verified=True,tradeable_mapping_verified=True,price_basis='raw',mode='TEST')
    p=price_card(d,'UP',e,'daily')
    assert p['support_present'] and p['state']=='EVIDENCE_ONLY'
    assert p['buy_action'] is None and not p['sufficient_to_buy'] and p['numeric_score_weight'] is None

def test_weekly_up_cannot_substitute_for_daily_history():
    d,_=features(frame(),NOW);e=dict(fundamental_status='USER_ASSUMED',price_basis='raw',mode='TEST')
    p=price_card(d,'UP',e,'daily')
    assert not p['support_present'] and p['prior_above_bbi_run']==0
