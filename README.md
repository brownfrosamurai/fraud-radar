# Fraud Radar

Real-time fraud scoring demo (Slice 0 walking skeleton).

## Run

```bash
docker compose up --build
```

Open <http://localhost:3000> — one card polls the score API, shows ALLOW/REVIEW/BLOCK, and the burst button injects 50 high-risk rows with a 30s cooldown.

API: <http://localhost:8000/health> · OpenAPI: <http://localhost:8000/docs>

## Dev without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

```bash
cd dashboard && npm install && npm run dev
```

## Tests

```bash
pytest api/tests -v
cd dashboard && npm test
```
