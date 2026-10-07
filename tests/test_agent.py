import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import agent, domain
from app.db import connection

HEADERS = {'Authorization': 'Bearer test-customer'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path/'test.db'))
    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setenv('DEMO_CUSTOMER_TOKEN', 'test-customer')
    monkeypatch.setenv('SUPPORT_TOKEN', 'test-support')
    with TestClient(app) as client:
        yield client


def ask(client, text, **kwargs):
    response = client.post('/chat', headers=HEADERS, json={'message': text, **kwargs})
    assert response.status_code == 200
    return response.json()


def test_requires_auth(client):
    assert client.post('/chat', json={'message': 'Track ORD-1001'}).status_code in (401,403)


def test_cross_customer_order_hidden(client):
    result = ask(client, 'Track ORD-2001')
    assert 'not found' in result['reply']
    assert 'Watch' not in str(result)


@pytest.mark.parametrize('order,reason', [('ORD-1002','expired'),('ORD-1003','not been delivered'),('ORD-1004','Final-sale')])
def test_ineligible(client, order, reason):
    result = ask(client, 'Return '+order)
    assert result['proposal'] is None
    assert reason in result['reply']


def test_confirmation_idempotency_and_processing(client):
    result = ask(client, 'Return ORD-1001')
    proposal = result['proposal']['proposal_id']
    assert client.get('/returns', headers=HEADERS).json() == []
    assert client.post('/returns/confirm', headers=HEADERS, json={'proposal_id': proposal}).status_code == 400
    body = {'proposal_id': proposal, 'confirmed': True}
    first = client.post('/returns/confirm', headers=HEADERS, json=body).json()
    second = client.post('/returns/confirm', headers=HEADERS, json=body).json()
    assert first['id'] == second['id']
    assert domain.process_pending() == 1
    assert domain.process_pending() == 0
    assert client.get('/returns', headers=HEADERS).json()[0]['status'] == 'processed_simulated'


def test_expired_proposal(client):
    proposal = ask(client, 'Return ORD-1001')['proposal']['proposal_id']
    with connection() as db:
        db.execute('UPDATE proposals SET created_at=?', (time.time()-1000,))
    r = client.post('/returns/confirm', headers=HEADERS, json={'proposal_id':proposal,'confirmed':True})
    assert r.status_code == 400
    assert 'expired' in r.json()['detail']


def test_other_customer_proposal_denied(client):
    proposal = domain.propose('customer-2', 'ORD-2001')['proposal_id']
    assert client.post('/returns/confirm', headers=HEADERS, json={'proposal_id':proposal,'confirmed':True}).status_code == 400


def test_history_and_sources(client):
    first = ask(client, 'Track ORD-1001')
    second = ask(client, 'Return it', conversation_id=first['conversation_id'])
    assert second['proposal']['order_id'] == 'ORD-1001'
    assert any(s['id']=='returns-v1' for s in second['sources'])


def test_unknown_conversation(client):
    assert client.post('/chat', headers=HEADERS, json={'message':'hello','conversation_id':'missing'}).status_code == 404


def test_support_access_and_handoff(client):
    ask(client, 'I need a human')
    assert client.get('/support',headers=HEADERS).status_code == 403
    assert len(client.get('/support',headers={'Authorization':'Bearer test-support'}).json()['tickets']) == 1


def test_tools_reject_extra_identity_and_unknown_tools(client):
    assert 'error' in agent.execute('customer-1','lookup_order',{'order_id':'ORD-2001','customer_id':'customer-2'})
    assert 'error' in agent.execute('customer-1','create_refund',{})


def test_llm_tool_loop(client,monkeypatch):
    monkeypatch.setenv('AGENT_MODE','llm')
    responses = iter([
        {'choices':[{'message':{'content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'lookup_order','arguments':'{"order_id":"ORD-2001"}'}}]}}]},
        {'choices':[{'message':{'content':'Order not found for this customer.'}}]},
    ])
    monkeypatch.setattr(agent,'completion',lambda messages: next(responses))
    result=ask(client,'Show ORD-2001')
    assert result['mode']=='llm'
    assert result['trace'][0]['result']=={'error':'Order not found for this customer.'}


def test_llm_failure_fallback(client,monkeypatch):
    monkeypatch.setenv('AGENT_MODE','llm')
    def fail(messages):
        raise RuntimeError('Model unavailable')
    monkeypatch.setattr(agent,'completion',fail)
    result=ask(client,'Return ORD-1001')
    assert result['mode']=='llm_fallback'
    assert client.get('/returns',headers=HEADERS).json()==[]
