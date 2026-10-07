"""Repeatable workflow evaluation against an isolated database, never your demo DB."""
import argparse
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app

CASES = [
    ('Track ORD-1001', 'lookup_order', False),
    ('Track ORD-1003', 'lookup_order', False),
    ('Return ORD-1001', 'propose_return', True),
    ('My ORD-1001 arrived damaged', 'propose_return', True),
    ('Return ORD-1002', 'propose_return', False),
    ('Return ORD-1003', 'propose_return', False),
    ('Return ORD-1004', 'propose_return', False),
    ('Track ORD-2001', 'lookup_order', False),
    ('Return ORD-2001', 'propose_return', False),
    ('What is your shipping policy?', 'search_policies', False),
    ('What is your return policy?', 'search_policies', False),
    ('I need a human', 'handoff', False),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['demo','llm'], default='demo')
    args = parser.parse_args()
    if args.mode == 'llm' and not os.getenv('OPENAI_API_KEY'):
        parser.error('Set OPENAI_API_KEY in .env before running a paid LLM evaluation.')
    os.environ['AGENT_MODE'] = args.mode
    os.environ['DEMO_CUSTOMER_TOKEN'] = 'evaluation-only'
    headers = {'Authorization':'Bearer evaluation-only'}
    results = []
    with tempfile.TemporaryDirectory() as directory:
        os.environ['DATABASE_PATH'] = str(Path(directory)/'evaluation.db')
        with TestClient(app) as client:
            for prompt, expected_tool, expected_proposal in CASES:
                response = client.post('/chat',headers=headers,json={'message':prompt})
                response.raise_for_status()
                data = response.json()
                tools = [t['tool'] for t in data['trace']]
                passed = expected_tool in tools and bool(data['proposal']) == expected_proposal
                if 'ORD-2001' in prompt:
                    passed = passed and 'Watch' not in json.dumps(data)
                results.append({'prompt':prompt,'passed':passed,'expected_tool':expected_tool,'tools':tools,'latency_ms':data['latency_ms'],'mode':data['mode'],'usage':data['usage'],'reply':data['reply']})
    latencies = sorted(row['latency_ms'] for row in results)
    report = {'mode':args.mode,'cases':len(results),'passed':sum(r['passed'] for r in results),'mean_latency_ms':round(statistics.mean(latencies),2),'p95_latency_ms':latencies[max(0,__import__('math').ceil(.95*len(latencies))-1)],'scope':'Small workflow regression set, not a comprehensive AI quality benchmark. LLM tool expectations may need human review.','results':results}
    Path('evaluation-results.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    return 0 if report['passed']==report['cases'] else 1


if __name__=='__main__':
    raise SystemExit(main())
