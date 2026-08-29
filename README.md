# One Crew

One Crew is a research companion for a one-person shop. You decide how far back and how long the piece is. The crew returns a write-once timeline with stamps (grounded / mainstream / fringe, lean, interests, source independence, vested interest, propaganda) and causal links only when Parallel sourced them. Missing stays missing.

**Demo runtime is Gemini 3.5 Flash + ADK + Vertex Imagen. The floor never posts.**

**License:** Apache-2.0

## Front door

1. **Topic** — e.g. "Explain what's going on with the Hormuz strait".
2. **Depth** (required, no default): 1y / 2-3y / 5y / decade / few decades / pre-1980 pre-internet.
3. **Cut** (required, no default): `tiktok` | `youtube_shorts` | `weekly_update` | `one_time_short_episode` | `full_length_documentary`.

No depth chosen = no run. No cut chosen = no run. GET never spends Parallel or Imagen.

The receipt and any boards are sized to that cut. A TikTok packet is not a doc packet. A documentary depth+cut can be a long timeline.

Boards stay optional after the timeline — Imagen from the script/timeline plus Parallel refs, never a collage. The floor never posts.

![Architecture](docs/architecture.svg)

## Who it's for

A one-person shop that needs a receipt before they cut. Sample first-open packet: **oc-hormuz-decade** (topic Hormuz, depth=decade, cut=`one_time_short_episode`).

## How it works

1. First-open is the seeded `oc-hormuz-decade` packet: Hormuz topic, decade window, short-episode cut, grounded cause, mainstream lean present or missing honestly, fringe tagged, not-independent OPEC row marked propaganda, missing causal link. GET never calls Parallel or Imagen.
2. A live shift is `POST /api/shifts` and requires `SHIFT_TOKEN` + `X-Shift-Token` **and** a depth **and** a cut. Unset token → 403. No depth or no cut → 400. No spend.
3. **Google ADK** crew: researcher then optional boarder, on **Vertex Gemini 3.5 Flash**.
4. Write-once receipt. Second stamp is an error. Causal links are grounded only if Parallel sourced the link; otherwise missing. Do not invent a 40-year chain.
5. Each event row is stamped exactly one of: **grounded** (Parallel URL on the row), **mainstream** (widely repeated, may be bias, not a source), **fringe** (included and tagged, never sold as fact). Lean / interests / who_repeats, independent / vested_interest, and propaganda are Parallel-sourced or `missing`. Gemini must not stamp propaganda from tone.
6. Missing Parallel, Vertex, or Imagen — or a pre-1980 miss → fail-closed HOLD.
7. The floor has no publish control. Nothing is posted.

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

Open [http://127.0.0.1:43158](http://127.0.0.1:43158). Read the Hormuz decade short-episode timeline. The floor has no publish button.

```bash
PYTHONPATH=backend python -m onecrew &
curl -s http://127.0.0.1:43158/api/health
curl -s http://127.0.0.1:43158/api/packets | python -m json.tool | head

# Live spend — off unless SHIFT_TOKEN is set
# export SHIFT_TOKEN=your-shared-secret
# curl -s -X POST http://127.0.0.1:43158/api/shifts \
#   -H 'content-type: application/json' \
#   -H "X-Shift-Token: $SHIFT_TOKEN" \
#   -d '{"topic":"Explain what is going on with the Hormuz strait","depth":"decade","cut":"one_time_short_episode"}'
```

### Tests

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests -q
```

Tests lock the companion front door (depth + cut before spend), write-once receipts, causal links, stamps, hit+miss, GET-never-spends, POST 403, HOLD, and the Hormuz seed.

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
sample_data/packet.json    first-open oc-hormuz-decade
sample_data/frames/        seeded shot boards, sized to the cut
backend/onecrew/           FastAPI + ADK crew + receipt lock
backend/tests/             locks
docs/architecture.svg
docs/architecture.png
DEMO.md
LICENSE
```

## What this is not

Not a publisher. Not a collage toy. The floor does not post.
