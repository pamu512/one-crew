# One Crew

Overnight researcher and board artist for one-person YouTube / TikTok studios. Parallel + Gemini. Never posts.

**Demo runtime is Gemini 3.5 Flash + ADK + Vertex Imagen. The floor does not publish.**

**License:** Apache-2.0

You paste a short hook. The researcher calls the official `parallel-web` Python SDK and writes a receipt **once**. Each finding is stamped exactly one of: **grounded** (Parallel URL on the row), **mainstream** (widely repeated, may be bias, not a source), **fringe** (included and tagged, never sold as fact). Mainstream rows also carry **lean**, **interests**, and **who_repeats** as separate fields — filled only from a Parallel hit, otherwise `missing`. Lean is not the stamp. Widely repeated is not who_repeats. The same receipt must show a Parallel **hit** and a Parallel **miss**. The boarder then makes four real Imagen shots from the script plus those Parallel refs — not a mood dump. If Parallel, Vertex, or Imagen is down: **HOLD**. No invented source, no collage, no invented stamp, no invented lean.

![Architecture](docs/architecture.svg)

## Who it's for

A bedroom creator who needs receipts before they cut. Sample first-open packet: **oc-pickle-debt**.

## How it works

1. First-open is the seeded `oc-pickle-debt` packet (grounded ranking hit, mainstream 3am-kitchen, fringe NASA miss, four shot frames). GET never calls Parallel or Imagen.
2. A live shift is `POST /api/shifts` and requires `SHIFT_TOKEN` + `X-Shift-Token`. Unset token → 403.
3. **Google ADK** crew: researcher then boarder, on **Vertex Gemini 3.5 Flash**.
4. Write-once receipt. Second stamp is an error.
5. Missing Parallel, Vertex, or Imagen → fail-closed HOLD.
6. The floor has no publish control. Nothing is posted.

## How to run locally

Python 3.11+. No secrets. Locally Parallel / Vertex / Imagen are missing. First-open still shows the seeded packet. That is the demo.

```bash
cp .env.example .env

python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# API + floor on :43158
PYTHONPATH=backend python -m onecrew
```

Open [http://127.0.0.1:43158](http://127.0.0.1:43158). Read the receipt on `oc-pickle-debt`. The floor has no publish button.

```bash
PYTHONPATH=backend python -m onecrew &
curl -s http://127.0.0.1:43158/api/health
curl -s http://127.0.0.1:43158/api/packets | python -m json.tool | head

# Live spend — off unless SHIFT_TOKEN is set
# export SHIFT_TOKEN=your-shared-secret
# curl -s -X POST http://127.0.0.1:43158/api/shifts \
#   -H 'content-type: application/json' \
#   -H "X-Shift-Token: $SHIFT_TOKEN" \
#   -d '{"goal":"Research the hook. Do not post."}'
```

### Tests

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests -q
```

31 tests lock write-once receipts, stamps, hit+miss, GET-never-spends, POST 403, HOLD, and the seed packet.

### ADK web (optional)

```bash
cd backend
adk web --port 43159
```

### Docker

```bash
docker compose up --build
```

Serves the floor on `43158`.

## Deploy to Cloud Run

Vertex + ADC. Export `YOUR_GCP_PROJECT`. Do not bake keys or a project id into the image.

```bash
export PROJECT_ID=YOUR_GCP_PROJECT
export REGION=us-central1

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com firestore.googleapis.com aiplatform.googleapis.com

gcloud firestore databases create --location=$REGION || true

gcloud run deploy onecrew \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,GEMINI_MODEL=gemini-3.5-flash,GOOGLE_GENAI_USE_VERTEXAI=true"
```

Leave `SHIFT_TOKEN` unset on the public service so `POST /api/shifts` is 403. The floor still shows the seeded packet. Do not add an unauthenticated control that bills Parallel or Imagen.

`GOOGLE_CLOUD_PROJECT` comes from the environment only.

## Environment variables

| Variable | Purpose |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | Default `true`. Vertex is the model rail. |
| `GOOGLE_CLOUD_PROJECT` | Operator export only. Empty if unset. |
| `GOOGLE_CLOUD_LOCATION` | Vertex / Cloud Run region |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC JSON locally; Cloud Run uses the runtime SA |
| `GEMINI_MODEL` | Default `gemini-3.5-flash` |
| `PARALLEL_API_KEY` | Official Parallel SDK. Empty → Parallel rail down. |
| `SHIFT_TOKEN` | Unset → live spend disabled (403). Set → require header `X-Shift-Token`. |

## Repository map

```
sample_data/packet.json    first-open oc-pickle-debt
sample_data/frames/        four seeded shot boards
backend/onecrew/           FastAPI + ADK crew + receipt lock
backend/tests/             31 locks
docs/architecture.svg
docs/architecture.png
DEMO.md
LICENSE
```

## What this is not

Not a publisher. Not a collage toy. The floor does not post.
