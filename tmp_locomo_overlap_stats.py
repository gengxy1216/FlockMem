import json, re
from pathlib import Path

def tokenize(text: str):
    raw = str(text or '').lower().strip()
    if not raw:
        return []
    tokens = [
        t for t in re.findall(r"[a-z0-9][a-z0-9_-]{0,63}|[\u4e00-\u9fff]{1,4}", raw) if t
    ]
    chars = re.findall(r"[\u4e00-\u9fff]", raw)
    for i in range(len(chars)-1):
        tokens.append(chars[i] + chars[i+1])
    if chars:
        tokens.append(''.join(chars))
    stop = {"我","你","他","她","它","吗","呢","啊","呀","的","了"}
    return [t for t in tokens if t and t not in stop]

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

hit_ratios = []
miss_ratios = []

for c in report.get('cases', []):
    cid = c['case_id']
    row = rows.get(cid)
    if not row:
        continue
    query = row.get('query') or row.get('question')
    q_tokens = set(tokenize(query)) or {str(query).lower()}
    expected_ids = row.get('expected_message_ids') or row.get('supporting_message_ids') or row.get('supporting_turn_ids')
    if isinstance(expected_ids, str):
        expected_ids = [x.strip() for x in re.split(r"[,;\s]+", expected_ids) if x.strip()]
    expected_ids = expected_ids or []
    msg_map = {m.get('message_id'): m for m in row.get('memories', []) if isinstance(m, dict)}
    best_ratio = 0.0
    for mid in expected_ids:
        msg = msg_map.get(mid)
        if not msg:
            continue
        m_tokens = set(tokenize(msg.get('content',''))) or {str(msg.get('content','')).lower()}
        overlap = q_tokens & m_tokens
        ratio = len(overlap) / len(q_tokens) if q_tokens else 0.0
        if ratio > best_ratio:
            best_ratio = ratio
    if c.get('hit'):
        hit_ratios.append(best_ratio)
    else:
        miss_ratios.append(best_ratio)

import statistics as st
print('hit_count', len(hit_ratios), 'miss_count', len(miss_ratios))
print('hit_avg_overlap', round(st.mean(hit_ratios),3) if hit_ratios else None)
print('miss_avg_overlap', round(st.mean(miss_ratios),3) if miss_ratios else None)
print('miss_min_overlap', round(min(miss_ratios),3) if miss_ratios else None)
print('miss_max_overlap', round(max(miss_ratios),3) if miss_ratios else None)