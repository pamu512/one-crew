# One Crew

One Crew is a research companion for a one-person shop. Before you record, you see:

1. a timed VO with citations
2. which lines already exist as someone else's media (`collision` yes / no / missing)
3. which sources are house organs, propaganda, fringe, or unsourced

The point is you can see the risk on the page. We do not clear copyright. We do not give legal advice. We do not license footage. A Parallel miss is not permission. `collision=missing` means we did not get a search, not that you are in the clear. The floor never posts, so we also do not publish the thing that would get you a claim.

**Demo runtime is Gemini 3.5 Flash + ADK + Vertex Imagen. License: Apache-2.0.**

## Required picks

Required, in this order, before any Parallel or Imagen spend. No defaults. Any missing pick = no run.

1. **Topic** (free text) — e.g. "Explain what's going on with the Hormuz strait". Empty or whitespace = no run.
2. **Platform** — `tiktok` | `youtube` | `youtube_shorts` | `instagram_reels` | `instagram_stories` | `instagram_feed` | `facebook_reels` | `facebook_feed` | `threads` | `podcast`
3. **Length / cut** — `tiktok-length` | `shorts` | `weekly_update` | `one_time_short_episode` | `full_length_documentary` | `feature_film`
4. **Depth** — `1y` | `2-3y` | `5y` | `decade` | `few_decades` | `pre-1980_pre-internet`
5. **Script lean** (voice only; does not restamp) — `centered_independent` | `left` | `right` | `far_right` | `far_left` | `unhinged_fringe`
6. **Tell** (required free text) — how the piece is told. Empty or whitespace = no run. Examples only, not a closed list and not an enum:
   - Narrator-led global overview of the US and Iran
   - One family in Bandar Abbas, kitchen radio on
   - Thriller on a tanker crossing Hormuz that might get hit
   - Weekly news desk, host only
   - Historical drama through one port family

Pairing is the **cut**, not a parse of tell. `full_length_documentary` and `weekly_update` are always nonfiction: host/reporter VO from the receipt, no invented characters, even if tell says "family thriller". `feature_film` is always fiction: may invent a frame labeled `(frame)` from whatever they typed. Shorts / tiktok / `one_time_short_episode`: news tell → no invented people; story tell → invent frame. Do not 400 because tell contains "thriller". On news/doc, subjects come from the receipt — do not invent a mother in Bandar Abbas if Parallel did not name her.

7. **Tone** (required free text unless `feature_film`) — host stance on news/doc. Empty tone on those cuts = no run. Examples only, not a closed list:
   - News desk
   - Make the viewer think
   - Question the decisions
   - Personal take
   - Grounded in the record

Tone is not `script_lean` and does not restamp sources. A questioning tone still cannot invent a source or hide fringe. Do not name an example "grounded in reality". `feature_film` does not require tone.

Then a write-once timeline (grounded / mainstream / fringe, house-organ, propaganda, causal links only when Parallel sourced them). Then a **full script you can record from** — scene headings, action/B-roll, host VO or screenplay dialogue — not one block per receipt row. Political `script_lean` changes the spoken argument, not the stamps and not the thickness. Then the collision search on factual VO lines. Then a **frame-by-frame shot list** (shot number, duration, camera, action, line). Each shot is `sourced` | `imagen` | `missing`. Prefer existing stills/clips from Parallel; genAI is the fallback. We do not license the tape we point at and we do not clear rights. TikTok / Shorts generate Imagen only for unsourced shots. Episode / documentary / feature keep the full list; Imagen fills unsourced key frames (cap documented, max 40 billable images, never 400). Parallel down leaves footage `missing` (no invented URL, no Imagen pretend-source). Imagen or Vertex down keeps the shot list and leaves images missing. Lean does not restamp sources or collisions. If the receipt is thin, the script names the hole. It does not invent history to fill pages.

Sample first-open: **oc-hormuz-decade** (youtube · one_time_short_episode · decade · centered_independent · tell "Narrator-led global overview of the US and Iran" · tone "Grounded in the record"). Seed collisions stay `missing` — GET never spends.

![Architecture](docs/architecture.svg)

## How it works

1. First-open shows the required picks, the Hormuz VO, source stamps, collision fields (`missing` until a live search), and the shot list. GET never calls Parallel or Imagen.
2. `POST /api/shifts` needs `SHIFT_TOKEN` + `X-Shift-Token` and the required picks. Unset token → 403. Any missing pick (including empty tell, or empty tone on news/doc) → 400. No spend.
3. **Google ADK** crew on **Vertex Gemini 3.5 Flash**: picks → timeline → timed VO → collision search → shot list.
4. Parallel down, or a pre-1980 miss → fail-closed HOLD. Collision rail down → every collision field `missing`, never `collision=no`. Unhinged lean still cannot invent a source.
5. The floor has no publish control. Nothing is posted.

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

Open [http://127.0.0.1:43158](http://127.0.0.1:43158). Read the timed Hormuz VO, the collision list, and the cited sources. The floor has no publish button.

```bash
PYTHONPATH=backend python -m onecrew &
curl -s http://127.0.0.1:43158/api/health
curl -s http://127.0.0.1:43158/api/packets | python -m json.tool | head

# Live spend — off unless SHIFT_TOKEN is set
# export SHIFT_TOKEN=your-shared-secret
# curl -s -X POST http://127.0.0.1:43158/api/shifts \
#   -H 'content-type: application/json' \
#   -H "X-Shift-Token: $SHIFT_TOKEN" \
#   -d '{"topic":"Explain what is going on with the Hormuz strait","platform":"youtube","cut":"one_time_short_episode","depth":"decade","script_lean":"centered_independent","tell":"Narrator-led global overview of the US and Iran","tone":"Grounded in the record"}'
```

### Tests

```bash
source .venv/bin/activate
PYTHONPATH=backend pytest backend/tests -q
```

Locks: required picks or no run; empty tell is 400; empty tone on news/doc is 400; documentary cut never invents a family even if tell says drama; fiction frame stays labeled; lean and tone do not restamp sources or collision URLs; Parallel down leaves collision `missing` (never `no`); a Hormuz doc URL hit stamps `collision=yes` on that beat; sourced footage preferred over Imagen; GET never spends; POST without token is 403; floor never posts.

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

Not a publisher. Not a clearance desk. Not legal advice. The floor does not post.
