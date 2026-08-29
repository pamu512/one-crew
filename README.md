# One Crew

Pick topic, platform, length, depth, then how you want it to lean. You get a timed VO, cited sources, and a shot list cut from that VO.

One Crew is a research companion. Five picks, then a write-once timeline, then a **timed VO**, then a **shot list** from that VO. Imagen fills key frames. Not a receipt-join. Not a leftover stills collage. The crew does not post.

**Demo runtime is Gemini 3.5 Flash + ADK + Vertex Imagen. The floor never posts.**

**License:** Apache-2.0

## Front door

Required picks, in this order, before any Parallel or Imagen spend. No defaults. Any missing pick = no run.

1. **Topic** (free text, required, no default) — e.g. "Explain what's going on with the Hormuz strait". Empty or whitespace = no run.
2. **Platform** (TikTok, YouTube, Instagram / Meta, podcast — no free-text, no default) — `tiktok` | `youtube` | `youtube_shorts` | `instagram_reels` | `instagram_stories` | `instagram_feed` | `facebook_reels` | `facebook_feed` | `threads` | `podcast`
3. **Length / cut** — `tiktok-length` | `shorts` | `weekly_update` | `one_time_short_episode` | `full_length_documentary`
4. **Depth** — `1y` | `2-3y` | `5y` | `decade` | `few_decades` | `pre-1980_pre-internet`
5. **Script lean** (voice of the script only) — `centered_independent` | `left` | `right` | `far_right` | `far_left` | `unhinged_fringe`

Then the researcher writes a timeline and stamps each source row: grounded / mainstream / fringe, lean-of-the-source, interests, independent, vested_interest, propaganda, and causal links only when Parallel sourced them. Missing stays missing.

The floor writes a **timed VO** in the requested lean, sized to that surface + length, with beats, timecodes, and citations pointing at those rows. Lean changes the spoken wording, not the stamps. Then a **shot list** is cut from that VO: one shot per beat/scene. TikTok / Shorts generate every beat. Episode / documentary generate one Imagen key frame per scene — never 400 images (cap is the event cap, max 40 on a YouTube documentary). The full shot list still shows. A Stories board is not a documentary board. A Reels board is not a YouTube long-form board. If Imagen or Vertex is down, the shot list stays and images stay missing — they are not invented. Boards are not optional.

Requested script lean does **not** restamp sources. Unhinged / fringe voice still cannot invent sources or mark propaganda as grounded. Centered_independent still must show missing when Parallel missed. Do not hide fringe or propaganda to match a centered ask. Do not invent a lobby to match a far-right / far-left ask.

The floor never posts.

![Architecture](docs/architecture.svg)

## Who it's for

A one-person shop that needs a script with receipts. Sample first-open packet: **oc-hormuz-decade** (youtube · one_time_short_episode · decade · centered_independent).

## How it works

1. First-open shows the five picks (topic first), a timed Hormuz VO with citations, a mixed source list (Parallel hit **and** miss on the same receipt), and the shot list cut from that VO. GET never calls Parallel or Imagen.
2. `POST /api/shifts` requires `SHIFT_TOKEN` + `X-Shift-Token` and all five picks. Unset token → 403. Empty, whitespace, or omitted topic → 400. Any missing pick → 400. No spend.
3. **Google ADK** crew: researcher then boarder, on **Vertex Gemini 3.5 Flash**. Flow is picks → timeline + sources → timed VO → shot list.
4. Write-once receipt. Script lean cannot change a source stamp.
5. Missing Parallel — or a pre-1980 miss → fail-closed HOLD. Unhinged lean still fail-closed if Parallel missed. Missing Imagen/Vertex → shot list kept, images missing.
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

Open [http://127.0.0.1:43158](http://127.0.0.1:43158). Read the timed Hormuz VO, the cited sources, and the shot list. The floor has no publish button.

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

Tests lock: no run without all five picks (empty/whitespace/omitted topic is 400 and does not spend); right vs left VO wording differs and stamps stay identical; TikTok VO is short and an episode has running timecodes; every beat cites a finding id; unhinged/centered cannot hide fringe or propaganda; the boarder cannot return the leftover tanker-lane set; Imagen down keeps the shot list and leaves images missing; HOLD writes an empty script.

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
sample_data/frames/        storyboard frames cut from the seed script
backend/onecrew/           FastAPI + ADK crew + receipt lock
backend/tests/             locks
docs/architecture.svg
DEMO.md
LICENSE
```

## What this is not

Not a publisher. Not a collage toy. The floor does not post.
