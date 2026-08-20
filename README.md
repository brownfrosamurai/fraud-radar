# Fraud Radar

Real-time fraud scoring demo (Slice 1: Isolation Forest + percentile `model_score`).

## Run

```bash
docker compose up --build
```

Open http://localhost:3000

## Models

Isolation Forest is the default on `POST /score`. Optional `?model=autoencoder` (501 in Docker: the image has weights but not torch).

Holdout evaluation (test split only, never accuracy):

| Model | PR-AUC | Precision@0.9 | Recall@0.9 | F1@0.9 |
|---|---|---|---|---|
| Isolation Forest | 0.0297 | 0.0122 | 0.9067 | 0.0240 |
| Autoencoder | 0.0781 | 0.0088 | 0.8533 | 0.0175 |

`model_score` is a training-set percentile in `[0, 1]`. `decide()` composes that score with the amount rule.

Retrain (needs Kaggle credentials): `python -m ml.download_data && python -m ml.train`

## Dev without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ml]"
uvicorn api.main:app --reload
```

```bash
cd dashboard && npm install && npm run dev
```

## Tests

```bash
pytest -v
cd dashboard && npm test
```
