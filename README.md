# Customer Agent Lab — step-by-step setup

A complete local portfolio MVP aligned with the Klaviyo AI Engineer II job description you supplied. It supports authenticated order lookup, grounded policy retrieval, proposed returns, explicit confirmation, durable queued work, human handoff, conversation persistence, and a small evaluation suite.

This is an independent learning project, not a Klaviyo product or integration. All customer records are synthetic. Returns are simulated; no emails, store actions, or payments are sent.

## 1. Install your development tools

Use Python 3.12, VS Code or another editor, and Terminal. Docker Desktop is optional for the Redis/Celery workflow. The commands below target macOS/Linux. On Windows, use PowerShell and the alternate activation/copy commands shown below.

Confirm Python is installed:

```bash
python3 --version
```

If Python is missing, install Python 3.12 from https://www.python.org/downloads/ and reopen Terminal. On Windows, use `py -3.12` instead of `python3` for the first environment command.

## 2. Extract the project

Download `customer-agent.zip` and extract it. Open Terminal inside the extracted `customer-agent` folder. For example, if you extracted it into Downloads:

```bash
cd ~/Downloads/customer-agent
```

Check that `requirements.txt`, `README.md`, and the `app` folder are inside this directory. Do not run subsequent commands from inside the `app` folder.

If you want to type the code yourself, open `BUILD_FROM_SCRATCH.md`: it contains every source file in creation order, with a numbered explanation of what each file does. You do not need to retype the files to run the downloaded project.

## 3. Create an isolated Python environment

Run each line separately:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

Windows equivalents:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

Your terminal should now show `(.venv)`. Every new terminal used for Python commands needs this activation step.

## 4. Install the dependencies

```bash
python -m pip install --upgrade pip
```

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` pins the top-level package versions tested when this project was created. Transitive dependencies are not fully locked; for deployment, create and review a complete lock file for your target platform.

## 5. Create your configuration

```bash
cp .env.example .env
```

Windows:

```powershell
Copy-Item .env.example .env
```

Keep `AGENT_MODE=demo` for your first run. You do not need an API key in this mode. Demo mode uses a small rule-based router; it is not an LLM. The known local tokens are intentionally provided for the sample customer and support user. Do not expose this app publicly with these defaults.

## 6. Start the application

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Leave this terminal running. Open http://127.0.0.1:8000 in your browser.

API documentation: http://127.0.0.1:8000/docs

Health endpoint: http://127.0.0.1:8000/health

The app creates a local SQLite database and seeds five synthetic orders on first startup. SQLite keeps the first setup simple. PostgreSQL/pgvector is a future upgrade, not implemented here.

## 7. Try the complete customer workflow

The Customer demo token is prefilled as `local-customer-demo`. If you changed `DEMO_CUSTOMER_TOKEN`, update the browser input too.

Send these messages separately:

```text
Track ORD-1001
```

Expected: headphones are delivered.

```text
What is your return policy?
```

Expected: policy text and a source ID. Retrieval uses keyword overlap, not vector embeddings.

```text
Can I return ORD-1001?
```

Expected: an eligible proposal and a **Confirm return** button. No return exists yet.

Click **Confirm return**, then **Refresh my returns**.

Expected: a return with status `queued`. Repeating the same confirmation does not create a second return. A queued return is normal until a processor runs.

Try the negative cases:

| Message | Expected result |
| --- | --- |
| Return ORD-1002 | Outside the 30-day window |
| Return ORD-1003 | Not delivered yet |
| Return ORD-1004 | Final-sale restriction |
| Track ORD-2001 | Order not found for this customer |
| I need a human | Support ticket created |

For conversation memory, start a new conversation, send `Track ORD-1001`, and then `Return it`. Demo mode handles these documented patterns; broader natural language needs LLM mode. “Yes” in chat does not submit a return; use the confirmation button.

## 8. Inspect support requests

Enter `local-support-demo` in the Support token box and click **Load dashboard**. This shows submitted return records and human-support tickets. The customer token cannot open this endpoint.

The handoff is a saved local ticket, not a real customer-service integration. The direct handoff button saves your input or a conversation reference; it does not generate a full conversation summary automatically.

## 9. Process the queued return locally

Open a second Terminal in the project folder and activate `.venv`. Run:

```bash
python -c "from app.main import app; from app.domain import process_pending; print({'processed': process_pending()})"
```

Refresh your returns in the browser. The status should change to `processed_simulated`. Running the command again reports zero unless you created another eligible return.

This command is the simple local processor. The next step adds actual asynchronous processing with Redis and Celery.

## 10. Run the full local stack with Docker, Redis, and Celery

Stop the local Uvicorn server using Ctrl+C to free port 8000. Install and start Docker Desktop if needed: https://docs.docker.com/desktop/

From the project folder:

```bash
docker compose up --build
```

Open http://127.0.0.1:8000 again. Docker uses its own database volume, so the local Python records do not appear in this version. Repeat the eligible return flow and wait about 5–10 seconds. Click **Refresh my returns**; the status should become `processed_simulated` automatically.

The API writes the queued record to SQLite first. Celery beat publishes a processing task every five seconds. The worker scans and changes queued rows atomically. If Redis is unavailable, the queued database rows remain available for processing after recovery. This is a small durable-work-queue demonstration, not a general external-side-effect outbox implementation.

Use a second terminal to inspect logs:

```bash
docker compose logs -f worker
```

Stop the stack, preserving demo data:

```bash
docker compose down
```

Do not use `down -v` unless you intend to delete the Docker demo database. The combined worker/beat process and shared SQLite volume are for one-machine development. Production needs separate scheduling, workers, and a production database.

## 11. Enable real LLM tool calling

Open `.env` in your editor. Change these values:

```dotenv
AGENT_MODE=llm
OPENAI_API_KEY=your_own_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Use a model your API account can access that supports Chat Completions function calling. The model name is configurable; model availability can change. API usage is billed separately from a ChatGPT subscription. Never paste the key into source code, the browser, GitHub, or chat.

Restart the Python server. With Docker, recreate containers so they receive the new environment:

```bash
docker compose up --build --force-recreate
```

Try:

```text
My headphones from ORD-1001 arrived damaged. Please check your policy and help me return them.
```

Open **Tool trace and retrieved sources**. You should see mode `llm`, actual tool executions, token counts, and latency. The LLM can choose lookup, policy search, eligibility, proposal, and handoff tools. It has no confirmation or refund tool; actual return creation requires the authenticated UI confirmation request.

If the provider fails, you will see `llm_fallback`. The app does not silently call the rules router while claiming an AI response. A fallback does not automatically create a support ticket; use the support button.

The provider request has a 25-second per-request timeout, one retry for transient errors, a five-model-turn limit, and an eight-tool-call limit. This bounds calls but is not a strict end-to-end latency deadline. No live model call was made while generating this project; you must verify the live integration with your account.

## 12. Run the automated tests

Use your activated Python environment:

```bash
python -m pytest -q
```

The initial test run passed 14 tests. Coverage includes authorization, cross-customer access, ineligible orders, explicit confirmation, expired proposals, idempotency, conversation context, support permissions, validated tools, mocked LLM tool execution, and provider failure fallback.

These tests do not establish hallucination resistance or prompt-injection immunity. Server-side rules protect order access and return creation even when a model gives a poor answer. A Starlette/httpx deprecation warning may appear with the tested versions; the tests still pass.

## 13. Run the workflow evaluation

```bash
python scripts/evaluate.py --mode demo
```

Open the generated `evaluation-results.json`. It records each prompt, expected and actual tool use, pass/fail, reply, and latency. It uses a temporary database and does not modify your demo records.

After configuring your key, run the live model evaluation explicitly:

```bash
python scripts/evaluate.py --mode llm
```

This makes paid API calls. The twelve cases are a regression smoke test, not a representative benchmark. A valid agent may choose a different sequence of tools; inspect failures and adjust the evaluation rubric deliberately. Add 50–100 diverse cases, human-rated grounding checks, ambiguous requests, adversarial requests, injected policy text, and simulated tool failures before making quality claims.

Token usage is captured. Dollar cost is not computed because it depends on current model pricing. Twelve samples are too few for a reliable production p95 estimate.

## 14. Understand the files in this order

| File | What you learn |
| --- | --- |
| `app/db.py` | Tables, persistence, synthetic data, parameterized SQL |
| `app/domain.py` | Retrieval, ownership checks, eligibility, proposals, confirmation, queue processing |
| `app/agent.py` | Tool schemas, validated dispatch, demo routing, LLM orchestration, fallbacks |
| `app/main.py` | HTTP routes, authentication dependencies, context history, structured logs |
| `app/index.html` | Chat, explicit confirmation, request status, support dashboard |
| `app/worker.py` | Celery scheduling, retries, idempotent processing |
| `tests/test_agent.py` | Behavioral and security regression checks |
| `scripts/evaluate.py` | Repeatable workflow evaluation and latency reporting |
| `compose.yaml` | Running API, Redis, and worker together |

Read `BUILD_FROM_SCRATCH.md` for all source code in one place. Docstrings and inline comments explain the critical checks; the numbered walkthrough explains how the blocks fit together.

## 15. How this relates to the Klaviyo role

| Job requirement | Working implementation | Remaining portfolio upgrade |
| --- | --- | --- |
| Python backend and APIs | FastAPI routes | Load tests and production deployment |
| Agentic tools and context | Bounded LLM loop and stored history | Better context selection and concurrency control |
| Retrieval and grounding | Policy search with source IDs | PostgreSQL/pgvector, hybrid retrieval, citation validation |
| Deterministic versus LLM decisions | Eligibility and authorization always run in code | More business workflows |
| Evaluations | Tests and twelve workflow cases | Human evaluation, representative data, grounding metrics |
| Async processing | Celery, Redis, durable queued records | External service retries, dead-letter handling, operational alerts |
| Reliability | Confirmation, deduplication, timeouts, fallbacks | Rate limits, total deadlines, circuit breakers |
| Observability | Request IDs, tool names, token counts, latency logs | OpenTelemetry, Prometheus/Grafana, alerting |
| Cloud and CI/CD | Docker and GitHub Actions test workflow | AWS deployment, infrastructure automation, secret management |

The UI intentionally uses plain HTML/JavaScript to keep attention on the backend-heavy role. React is not required by the supplied job description. This implementation does not include fine-tuning, reinforcement learning, Kubernetes, vector embeddings, or AWS resources.

## 16. Before a real public deployment

Keep this demo on localhost. For a real service, replace the two shared demo tokens with proper user login and per-user authorization; use PostgreSQL with migrations; move secrets to a secret manager; add TLS, rate limits, retention rules, abuse controls, and monitoring. Implement atomic job claiming and idempotency at external providers before any actual refund or email side effect. Model text remains probabilistic and must be evaluated. Do not use real customer data in this demo.

## 17. Troubleshooting

| Problem | Fix |
| --- | --- |
| `No module named fastapi` | Activate `.venv`, run dependency installation, and run from the project root |
| `Address already in use` | Stop the other server; alternatively use `--port 8001` locally |
| 401/403 response | Use the token corresponding to customer or support access |
| Return stays queued | Run the local processor or start Docker's worker; inspect worker logs |
| Model fallback | Check API key, billing, model access, and network; restart after `.env` edits |
| No Confirm button | Check eligibility; an existing return also prevents a new proposal |
| Demo dates look old | Seeded dates are preserved; use a fresh disposable demo database if needed |
| Docker connection error | Start Docker Desktop and retry `docker compose up --build` |

## Sources used for API patterns

- FastAPI security: https://fastapi.tiangolo.com/tutorial/security/first-steps/
- OpenAI function calling: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI Chat Completions reference: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- Celery tasks and retries: https://docs.celeryq.dev/en/stable/userguide/tasks.html

## Suggested interview description

“I built a local customer-support agent with Python APIs, policy retrieval, validated tool calls, and a confirmed return workflow. I separated probabilistic language interpretation from deterministic authorization and eligibility checks, added durable asynchronous processing, and evaluated access controls and workflow behavior.”

Add measured LLM accuracy, latency, or cost only after running and documenting your own evaluations. Do not describe this local demo as production customer experience.
