"""Check source traceability, not empirical or semantic completeness."""
import csv
import json
from pathlib import Path

def audit(root=None):
    root=Path(root or Path(__file__).resolve().parents[1])
    ref=root/'references'
    def read(name):
        with (ref/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    pages=read('原页覆盖矩阵.csv');figures=read('图表覆盖矩阵.csv');coverage=read('implementation-coverage.csv')
    expected_pages={f'A{i}' for i in range(1,16)}|{f'B{i}' for i in range(1,22)}
    expected_figures={f'G{i:02d}' for i in range(1,47)}
    expected_rules={f'Q{i:02d}' for i in range(1,42)}
    assert len(pages)==36 and {x['source_page'] for x in pages}==expected_pages
    assert len(figures)==46 and {x['figure_id'] for x in figures}==expected_figures
    assert len(coverage)==41 and {x['规则ID'] for x in coverage}==expected_rules
    spec=json.loads((ref/'rules.v0.4.json').read_text(encoding='utf8'))
    assert {x['id'] for x in spec['rules']}==expected_rules
    for row in pages+figures:
        assert row['source_page'] in expected_pages
        assert row['rule_ids'].split() and set(row['rule_ids'].split())<=expected_rules
    for row in pages:
        ids=set(row['figure_ids'].split())
        # Text-only pages may leave figure IDs blank.
        assert ids<=expected_figures,(row['source_page'],ids)
    for row in figures:
        page=next(x for x in pages if x['source_page']==row['source_page'])
        assert row['figure_id'] in page['figure_ids'].split()
    return dict(source_pages=36,numbered_figures=46,engineering_rules=41,
                meaning='Traceability only; not textbook completeness or profitability')

if __name__=='__main__':print(json.dumps(audit(),ensure_ascii=False))
