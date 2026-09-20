from pathlib import Path
import json
import pandas as pd
import pytest
from analyze_market import run,checked,returns,correlations

FIXTURE=Path(__file__).parent/'fixtures/bundle.json'

def test_frozen_three_markets_and_bbi(tmp_path):
    a=run(FIXTURE,tmp_path/'analysis','2026-09-18',True)
    assert a['technical_only'] and a['fundamental_status']=='OUT_OF_SCOPE_BY_REQUEST'
    assert a['mode']=='FROZEN_TEST_ONLY'
    assert a['audits']['hog_main']['stale_sessions']==0
    assert len(a['frames'])==6
    assert len(a['models'])==36
    assert a['price_cards'][0]['bbi']==pytest.approx(expected_bbi(FIXTURE.parent / "equity/api-return.json"))
    assert a['price_cards'][1]['bar_end']=='2026-09-11'
    assert all(not c['sufficient_to_buy'] for c in a['price_cards'])
    assert len(a['correlations'])==24
    main=json.loads((tmp_path/'analysis/hog_main.json').read_text(encoding='utf8'))[-1]
    assert main['bbi']==pytest.approx(expected_bbi(FIXTURE.parent / "hog_main.json"))
    assert all(m['axis_label'].find('HKD')<0 for m in a['models'])

def test_hash_change_refused(tmp_path):
    (tmp_path/'x').write_text('changed')
    with pytest.raises(ValueError,match='hash'):checked(tmp_path,dict(rows_file='x',sha256='bad',id='x'))

def test_returns_do_not_bridge_gaps():
    d=pd.DataFrame(dict(session_date=['2026-09-14','2026-09-15','2026-09-17'],close=[10.,11.,22.],engine_segment=[1,1,2]))
    r=returns(d)
    assert r.iloc[1]==pytest.approx(.1) and pd.isna(r.iloc[2])

def test_late_snapshot_cannot_forecast_prior_day(tmp_path):
    with pytest.raises(ValueError,match='after snapshot'):run(FIXTURE,tmp_path/'bad','2026-09-16',True)

def test_non_session_target_rejected(tmp_path):
    with pytest.raises(ValueError,match='trading session'):run(FIXTURE,tmp_path/'bad','2026-09-19',True)


def expected_bbi(path):
    data = json.loads(path.read_text(encoding='utf8'))
    closes = ([r['close'] for r in data['data']] if 'schema' in data else
              [float(r.split(',')[2]) for r in data['data']['klines']])
    return sum(sum(closes[-n:]) / n for n in (3, 6, 12, 24)) / 4
