import hmac
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from . import agent, domain
from .db import connection, initialize

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('customer_agent')
bearer = HTTPBearer()


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title='Customer Agent — local portfolio demo', lifespan=lifespan)


def customer(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not hmac.compare_digest(auth.credentials, os.getenv('DEMO_CUSTOMER_TOKEN', 'local-customer-demo')):
        raise HTTPException(401, 'Invalid customer token')
    return 'customer-1'


def support(auth: HTTPAuthorizationCredentials = Depends(bearer)):
    if not hmac.compare_digest(auth.credentials, os.getenv('SUPPORT_TOKEN', 'local-support-demo')):
        raise HTTPException(403, 'Support access required')
    return 'support'


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=50)


class Confirmation(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=50)
    confirmed: bool = False


class Handoff(BaseModel):
    summary: str = Field(min_length=1, max_length=3000)


@app.get('/')
def index():
    return FileResponse(Path(__file__).with_name('index.html'))


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': os.getenv('AGENT_MODE', 'demo')}


@app.post('/chat')
def chat(body: Chat, who=Depends(customer)):
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    conversation = body.conversation_id or str(uuid.uuid4())
    with connection() as db:
        if body.conversation_id:
            row = db.execute('SELECT * FROM conversations WHERE id=? AND customer_id=?', (conversation, who)).fetchone()
            if not row:
                raise HTTPException(404, 'Conversation not found')
            last_order = row['last_order']
        else:
            db.execute('INSERT INTO conversations VALUES (?,?,NULL)', (conversation, who))
            last_order = None
        rows = db.execute('SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 10', (conversation,)).fetchall()
        history = [dict(row) for row in reversed(rows)]
    result = agent.run(who, body.message, history, last_order)
    with connection() as db:
        db.executemany('INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)', [(conversation, 'user', body.message), (conversation, 'assistant', result['reply'])])
        db.execute('UPDATE conversations SET last_order=? WHERE id=? AND customer_id=?', (result.pop('last_order'), conversation, who))
    elapsed = round((time.perf_counter()-started)*1000, 2)
    # No tokens, full user messages, or order payloads in logs.
    log.info(json.dumps({'request_id': request_id, 'latency_ms': elapsed, 'mode': result['mode'], 'tools': [t['tool'] for t in result['trace']], 'usage': result['usage']}))
    return {**result, 'conversation_id': conversation, 'request_id': request_id, 'latency_ms': elapsed}


@app.post('/returns/confirm')
def confirm(body: Confirmation, who=Depends(customer)):
    if not body.confirmed:
        raise HTTPException(400, 'Explicit confirmation required')
    try:
        return domain.confirm(who, body.proposal_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get('/returns')
def returns(who=Depends(customer)):
    with connection() as db:
        return [dict(row) for row in db.execute('SELECT id,order_id,status FROM returns WHERE customer_id=? ORDER BY created_at DESC', (who,))]


@app.post('/handoff')
def handoff(body: Handoff, who=Depends(customer)):
    return domain.handoff(who, body.summary)


@app.get('/support')
def dashboard(_=Depends(support)):
    with connection() as db:
        return {'returns': [dict(row) for row in db.execute('SELECT * FROM returns')], 'tickets': [dict(row) for row in db.execute('SELECT * FROM handoffs')]}
