# HuddleCart

One grocery order for the whole building. Neighbors join a pod, ask the HuddleCart agent for groceries in the pod chat, tap Add on product cards, and the leader places one order.

## How it's built

- `agent/` Python. LangGraph agent, LangChain tools, FastAPI routes, plain-code rules.
- `src/` Next.js screens (pod list, pod chat, cart, bags). `/api/*` is forwarded to the Python service.

### Agent graph (`agent/huddlecart/agent.py`)

```
load_pod -> understand -> search_catalog -> rank -> compose
```

| Step | AI or rules | What it does |
| --- | --- | --- |
| load_pod | tool | `get_pod_details` reads the pod from the database |
| understand | AI | turns "2 shrimp chips by tomorrow" into intent, items, quantity, deadline |
| search_catalog | tool | `search_products` per item and marketplace |
| rank | AI | picks the best match or says it's ambiguous |
| compose | rules | builds product cards, out-of-stock cards, pod suggestions |

Adding to the cart, prices, the $2 fee, cutoffs, stock gates, leader-only order steps, bag lists and Venmo links are all in `rules.py` and `api.py`. The model never changes the cart.

### Knowledge: context vs retrieval

- **Context:** house rules (fees, pickup, allowed stores, no alcohol). Small and the same for every request, so they live in the system prompt.
- **Database tool:** pod state (cutoff, delivery time, cart). Changes every minute, so the agent looks it up.
- **Retrieval:** the product catalog. Too big and changes too often to index, so `search_products` looks it up live with Tavily on Weee and Amazon, and falls back to a catalog snapshot. Tavily finds real product pages but can't confirm stock, so live results show "check stock" and evals run on the snapshot.

## Run it

```bash
cd agent && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export OPENAI_API_KEY=... TAVILY_API_KEY=... LANGSMITH_API_KEY=... LANGSMITH_TRACING=true LANGSMITH_PROJECT=huddlecart
HUDDLECART_SEARCH=live .venv/bin/uvicorn huddlecart.api:app --port 8000

# another terminal, repo root
npm install && npm run dev   # http://localhost:3000
```

## Deploy (Vercel)

Live at https://huddlecart.vercel.app. Next.js serves the screens and `api/index.py` serves the Python agent as a Vercel function. On Vercel the app state lives in one JSON row in Neon Postgres (`DATABASE_URL`); locally it's a JSON file.

```bash
vercel deploy --prod   # env vars: GOOGLE_API_KEY, TAVILY_API_KEY, LANGSMITH_*, HUDDLECART_SEARCH=live, DATABASE_URL
```

## Evals

```bash
cd agent
.venv/bin/python -m evals.run_evals golden      # 20 golden cases, rule scores
.venv/bin/python -m evals.run_evals judge       # Gemma judge on 10, agreement rate
.venv/bin/python -m evals.run_evals economics   # same 10 cases on fast and strong tiers
.venv/bin/python -m pytest tests                # rules unit tests
```

Golden cases are in `agent/evals/golden_cases.json`. Results land in `agent/evals/results/`.
