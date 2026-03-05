import json, re
from pathlib import Path

def tokenize(text):
    text = (text or '').lower()
    return re.findall(r"[a-z0-9][a-z0-9_-]{0,63}", text)

report_path = Path(r"C:\MiniMem-main\MiniMem\MiniMem_data\benchmarks\locomo\locomo10.sample20.report.json")
jsonl_path = Path(r"C:\MiniMem-main\MiniMem\MiniMem_data\benchmarks\locomo\locomo10.eval.jsonl")

report = json.loads(report_path.read_text(encoding='utf-8'))
case_ids = [c['case_id'] for c in report.get('cases', [])]

rows = {}
with jsonl_path.open('r', encoding='utf-8-sig') as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get('case_id')
        if cid:
            rows[cid] = row

missing = [cid for cid in case_ids if cid not in rows]
if missing:
    print('missing case_ids', missing)

for c in report.get('cases', []):
    cid = c['case_id']
    row = rows.get(cid)
    if not row:
        continue
    query = row.get('query') or row.get('question')
    expected_ids = row.get('expected_message_ids') or row.get('supporting_message_ids') or row.get('supporting_turn_ids')
    if isinstance(expected_ids, str):
        expected_ids = [x.strip() for x in re.split(r"[,;\s]+", expected_ids) if x.strip()]
    expected_ids = expected_ids or []
    msg_map = {m.get('message_id'): m for m in row.get('memories', []) if isinstance(m, dict)}
    q_tokens = tokenize(query)
    if not q_tokens:
        q_tokens = [query.lower()]
    print('\n', cid, 'hit' if c.get('hit') else 'miss', 'rank', c.get('rank'))
    print('Q:', query)
    for mid in expected_ids[:3]:
        msg = msg_map.get(mid)
        if not msg:
            continue
        content = msg.get('content','')
        m_tokens = tokenize(content)
        overlap = sorted(set(q_tokens) & set(m_tokens))
        print('  expected', mid)
        print('  msg:', content)
        print('  overlap:', overlap)
        cov = (len(overlap)/len(set(q_tokens))) if q_tokens else 0
        print('  overlap_ratio:', round(cov,3))