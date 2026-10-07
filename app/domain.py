"""Authoritative tools: the model cannot override ownership or business rules."""
import re
import time
import uuid
from datetime import date
from .db import connection

POLICIES = [
    {'id': 'returns-v1', 'title': 'Returns', 'text': 'Delivered items may be returned within 30 calendar days of delivery. Final-sale items are not eligible. A return requires customer confirmation. No refund is issued by this demo.'},
    {'id': 'shipping-v1', 'title': 'Shipping', 'text': 'Standard shipping normally takes 3 to 5 business days. Order status is available through order lookup. Delivery dates are estimates, not guarantees.'},
    {'id': 'damage-v1', 'title': 'Damaged items', 'text': 'For damaged items, request a return if eligible or contact a human support specialist. This demo does not automatically issue replacements or payments.'},
]


def retrieve(query):
    """Lexical retrieval baseline: no embeddings, no claims of semantic search."""
    words = set(re.findall(r'[a-z]+', query.lower()))
    ranked = []
    for doc in POLICIES:
        tokens = set(re.findall(r'[a-z]+', (doc['title']+' '+doc['text']).lower()))
        score = len(words & tokens)
        if score:
            ranked.append((score, doc))
    return [doc for _, doc in sorted(ranked, key=lambda x: x[0], reverse=True)[:2]]


def lookup(customer_id, order_id):
    with connection() as db:
        row = db.execute('SELECT * FROM orders WHERE id=? AND customer_id=?', (order_id, customer_id)).fetchone()
    if not row:
        return {'error': 'Order not found for this customer.'}
    result = dict(row)
    result.pop('customer_id')
    return result


def eligibility(customer_id, order_id):
    order = lookup(customer_id, order_id)
    if 'error' in order:
        return order
    if order['final_sale']:
        reason = 'Final-sale items are not eligible.'
    elif order['status'] != 'delivered' or not order['delivered_on']:
        reason = 'The order has not been delivered.'
    elif not 0 <= (date.today()-date.fromisoformat(order['delivered_on'])).days <= 30:
        reason = 'The 30-day return window has expired.'
    else:
        reason = 'Delivered within 30 days and not final sale.'
        return {'eligible': True, 'reason': reason, 'order_id': order_id, 'policy_id': 'returns-v1'}
    return {'eligible': False, 'reason': reason, 'order_id': order_id, 'policy_id': 'returns-v1'}


def propose(customer_id, order_id):
    result = eligibility(customer_id, order_id)
    if not result.get('eligible'):
        return result
    with connection() as db:
        existing = db.execute('SELECT id,status FROM returns WHERE order_id=? AND customer_id=?', (order_id, customer_id)).fetchone()
        if existing:
            return {'existing_return': dict(existing)}
        proposal_id = str(uuid.uuid4())
        db.execute('INSERT INTO proposals VALUES (?,?,?,?)', (proposal_id, customer_id, order_id, time.time()))
    return {**result, 'proposal_id': proposal_id, 'requires_confirmation': True}


def confirm(customer_id, proposal_id):
    with connection() as db:
        # Serializes competing confirmations in SQLite, preventing duplicate actions.
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM proposals WHERE id=? AND customer_id=?', (proposal_id, customer_id)).fetchone()
        if not row:
            raise ValueError('Proposal not found.')
        existing = db.execute('SELECT * FROM returns WHERE order_id=? AND customer_id=?', (row['order_id'], customer_id)).fetchone()
        if existing:
            return dict(existing)
        if time.time()-row['created_at'] > 900:
            raise ValueError('Proposal expired. Ask for the return again.')
        result = eligibility(customer_id, row['order_id'])
        if not result.get('eligible'):
            raise ValueError(result.get('reason', 'Return is no longer eligible.'))
        return_id = str(uuid.uuid4())
        db.execute('INSERT INTO returns VALUES (?,?,?,?,?)', (return_id, customer_id, row['order_id'], 'queued', time.time()))
        return dict(db.execute('SELECT * FROM returns WHERE id=?', (return_id,)).fetchone())


def process_pending():
    """Idempotent simulated processing. The DB queue survives broker outages."""
    with connection() as db:
        result = db.execute("UPDATE returns SET status='processed_simulated' WHERE status='queued'")
        return result.rowcount


def handoff(customer_id, summary):
    ticket_id = str(uuid.uuid4())
    with connection() as db:
        db.execute('INSERT INTO handoffs VALUES (?,?,?)', (ticket_id, customer_id, summary[:3000]))
    return {'ticket_id': ticket_id, 'status': 'awaiting_human'}
