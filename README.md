# One Crew

Pick platform, length, depth, then how you want it to lean. You get a script and cited sources.

One Crew is a research companion. It returns a **script** plus a write-once source list. You choose the four picks. The crew does not post.

**Demo runtime is Gemini 3.5 Flash + ADK + Vertex Imagen. The floor never posts.**

**License:** Apache-2.0

## Front door

Required picks, in this order, before any Parallel or Imagen spend. No defaults. Any missing pick = no run.

1. **Platform** — `tiktok` | `youtube` | `youtube_shorts` | `instagram` | `podcast`
2. **Length / cut** — `tiktok-length` | `shorts` | `weekly_update` | `one_time_short_episode` | `full_length_documentary`
3. **Depth** — `1y` | `2-3y` | `5y` | `decade` | `few_decades` | `pre-1980_pre-internet`
4. **Script lean** (voice of the script only) — `centered_independent` | `left` | `right` | `far_right` | `far_left` | `unhinged_fringe`

Then the researcher writes a timeline and stamps each source row: grounded / mainstream / fringe, lean-of-the-source, interests, independent, vested_interest, propaganda, and causal links only when Parallel sourced them. Missing stays missing.

The floor writes the **script** in the requested lean, sized to platform + length, with citations pointing at those rows.

Requested script lean does **not** restamp sources. Unhinged / fringe voice still cannot invent sources or mark propaganda as grounded. Centered_independent still must show missing when Parallel missed. Do not hide fringe or propaganda to match a centered ask. Do not invent a lobby to match a far-right / far-left ask.

Boards stay optional after the script. The floor never posts.

![Architecture](docs/architecture.svg)

## Who it's for

A one-person shop that needs a script with receipts. Sample first-open packet: **oc-hormuz-decade** (youtube · one_time_short_episode · decade · centered_independent).

## How it works

1. First-open shows the four picks, a script with citations, and a source list with mixed stamps. GET never calls Parallel or Imagen.
2. `POST /api/shifts` requires `SHIFT_TOKEN` + `X-Shift-Token` and all four picks. Unset token → 403. Any missing pick → 400. No spend.
3. **Google ADK** crew: researcher then optional boarder, on **Vertex Gemini 3.5 Flash**.
4. Write-once receipt. Script lean cannot change a source stamp.
5. Missing Parallel, Vertex, or Imagen — or a pre-1980 miss → fail-closed HOLD. Unhinged lean still fail-closed if Parallel missed.
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

Open [http://127.0.0.1:43158](http://127.0.0.1:43158). Read the Hormuz script and the cited source list. The floor has no publish button.

```bash
PYTHONPATH=backend python -m onecrew &
curl -s http://127.0.0.1:43158/api/health
curl -s http://127.0.0.1:43158/api/packets | python -m json.tool | head

# Live spend — off unless SHIFT_TOKEN is set
# export SHIFT_TOKEN=your-shared-secret
# curl -s -X POST http://127.0.0.1:43158/api/shifts \
#   -H 'content-type: application/json' \
#   -H "X-Shift-Token: $SHIFT_TOKEN" \
#   -d '{"topic":"Explain what is going on with the Hormuz strait","platform":"youtube","cut":"one_time_short_episode","depth":"decade","script_lean":"centered_independent"}'
```

### Tests

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests -q
```

Tests lock: no run without all four picks; script lean cannot change a source stamp; unhinged lean still fail-closed on missing Parallel.

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
sample_data/frames/        optional boards, sized to the cut
backend/onecrew/           FastAPI + ADK crew + receipt lock
backend/tests/             locks
docs/architecture.svg
DEMO.md
LICENSE
```

## What this is not

Not a publisher. Not a collage toy. The floor does not post.
