import os
import json
import time
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from evermemos_lite.bootstrap.app_factory import create_app
from evermemos_lite.config.settings import LiteSettings

DOCS = [
    {
        'id':'d1',
        'title':'Q3 launch note',
        'text':'项目周会记录。我们在上海确认了Q3发布时间，灰度窗口是9月18日，回滚开关命名为 ROLLBACK_SWITCH_ALPHA。上线前要完成压测和告警演练。',
        'query':'Q3灰度窗口是几号？',
        'expect':['9月18日','ROLLBACK_SWITCH_ALPHA'],
    },
    {
        'id':'d2',
        'title':'Data pipeline incident',
        'text':'故障复盘。根因是ETL任务重复消费，修复提交号是 fix/etl-dedup-4421，最终在22:40恢复。补偿脚本名 backfill_orders_202603。',
        'query':'这次ETL故障的修复分支是什么？',
        'expect':['fix/etl-dedup-4421','backfill_orders_202603'],
    },
    {
        'id':'d3',
        'title':'Security checklist',
        'text':'安全清单。生产密钥轮换周期改为45天，审计任务ID为 SEC-AUDIT-771。外部供应商访问采用最小权限和双人审批。',
        'query':'审计任务ID是什么？',
        'expect':['SEC-AUDIT-771','45天'],
    },
    {
        'id':'d4',
        'title':'Mobile release',
        'text':'移动端发布计划。iOS构建号 3.9.12(812)，Android构建号 3.9.12(9012)。发布负责人是Lina，冻结窗口周四18:00。',
        'query':'iOS构建号是多少？',
        'expect':['3.9.12(812)','Lina'],
    },
    {
        'id':'d5',
        'title':'Cost optimization',
        'text':'成本优化会议。对象存储分层后月成本下降17%，关键动作是归档策略 policy/archive-cold-30d。预计两周内覆盖全部项目。',
        'query':'归档策略名称是什么？',
        'expect':['policy/archive-cold-30d','下降17%'],
    },
    {
        'id':'d6',
        'title':'Oncall playbook',
        'text':'值班手册。夜间告警先执行 runbook#P1-redis-latency，10分钟内无改善再升级到SRE。升级联系人群组为 sre-escalation-cn。',
        'query':'夜间Redis延迟要先执行哪个runbook？',
        'expect':['runbook#P1-redis-latency','sre-escalation-cn'],
    },
    {
        'id':'d7',
        'title':'Contract memo',
        'text':'法务备忘。合同附录B第7条新增数据保留上限180天，例外审批单号 LEGAL-EX-902。客户侧确认邮件主题为 DataRetentionUpdate。',
        'query':'例外审批单号是多少？',
        'expect':['LEGAL-EX-902','180天'],
    },
    {
        'id':'d8',
        'title':'ML eval note',
        'text':'模型评估。A/B中B方案F1=0.843，高于A方案0.817。最终采用配置实验名 exp-rerank-b-20260305。后续关注冷启动样本。',
        'query':'最终采用的实验名是什么？',
        'expect':['exp-rerank-b-20260305','0.843'],
    },
]

def make_client():
    td = tempfile.mkdtemp(prefix='skill-compare-')
    env = dict(os.environ)
    env.update({
        'LITE_DATA_DIR': str(Path(td)/'data'),
        'LITE_CONFIG_DIR': str(Path(td)/'cfg'),
        'LITE_CHAT_PROVIDER': 'openai',
        'LITE_CHAT_BASE_URL': 'https://chat.example/v1',
        'LITE_CHAT_API_KEY': 'chat-key',
        'LITE_CHAT_MODEL': 'chat-model-a',
        'LITE_EXTRACTOR_PROVIDER': 'rule',
        'LITE_EMBEDDING_PROVIDER': 'local',
        'LITE_EMBEDDING_MODEL': 'local-hash-384',
        'LITE_SKILL_ADAPTER_ENABLED': 'true',
        'LITE_SKILL_ADAPTER_WHITELIST': 'markitdown,pdf,pptx',
    })
    os.environ.clear(); os.environ.update(env)
    app = create_app(LiteSettings.from_env())
    return TestClient(app)

def ingest_plain(client):
    for i,d in enumerate(DOCS, start=1):
        payload = {
            'message_id': f'plain-{d["id"]}-{i}',
            'create_time': 1772677000+i,
            'sender': 'eval-user',
            'content': d['text'],
            'group_id': 'eval:skill-compare',
            'role': 'user',
        }
        r = client.post('/api/v1/memories', json=payload)
        assert r.status_code == 200, r.text

def ingest_skill(client):
    for d in DOCS:
        chunks = [x.strip() for x in d['text'].split('。') if x.strip()]
        payload = {
            'source_type': 'pdf',
            'source_uri': f'file:///tmp/{d["id"]}.pdf',
            'summary': d['title'],
            'chunks': chunks,
            'skill_name': 'pdf',
            'agent_id': 'eval-agent',
            'sender': 'eval-user',
            'group_id': 'eval:skill-compare',
            'task_id': d['id'],
            'trace_id': f'trace-{d["id"]}',
        }
        r = client.post('/api/v1/ingest/skill', json=payload)
        assert r.status_code == 200, r.text
        assert r.json().get('result',{}).get('accepted') is True, r.text

def evaluate(client, method):
    latencies=[]
    hit1=0
    hit3=0
    for d in DOCS:
        start=time.perf_counter()
        r = client.get('/api/v1/memories/search', params={
            'query': d['query'],
            'user_id': 'eval-user',
            'group_id': 'eval:skill-compare',
            'retrieve_method': method,
            'decision_mode': 'static',
            'top_k': 3,
        })
        latencies.append((time.perf_counter()-start)*1000.0)
        assert r.status_code == 200, r.text
        rows = r.json().get('result',{}).get('memories',[])
        def ok(row):
            text = (str(row.get('content','')) + ' ' + str(row.get('summary','')) + ' ' + str(row.get('episode','')))
            return any(token in text for token in d['expect'])
        if rows and ok(rows[0]):
            hit1 += 1
        if any(ok(x) for x in rows[:3]):
            hit3 += 1
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted)//2]
    p95 = latencies_sorted[min(len(latencies_sorted)-1, int(len(latencies_sorted)*0.95))]
    return {
        'method': method,
        'cases': len(DOCS),
        'recall_at_1': round(hit1/len(DOCS),4),
        'recall_at_3': round(hit3/len(DOCS),4),
        'p50_ms': round(p50,3),
        'p95_ms': round(p95,3),
        'avg_ms': round(sum(latencies)/len(latencies),3),
    }

out = {}
for mode in ('plain','skill'):
    client = make_client()
    if mode == 'plain':
        ingest_plain(client)
    else:
        ingest_skill(client)
    out[mode] = {
        'keyword': evaluate(client, 'keyword'),
        'hybrid': evaluate(client, 'hybrid'),
    }

print(json.dumps(out, ensure_ascii=False, indent=2))