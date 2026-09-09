# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

Before you record: a cited script in the creator's voice, a collision list, and source stamps you can see. We do not clear copyright.

## Text description

One Crew is a research companion for a one-person / solo creator shop. You leave with a citable thesis plus a script, not a sketch. Before you record, you see (1) a timed VO with citations, (2) which lines already exist as someone else's media (collision yes / no / missing), and (3) which sources are house organs, propaganda, fringe, or unsourced. The research pack is always written — long-form prose plus bibliography, not a stamp list — and lists what was left out and why. The point is you can see the risk on the page. We do not clear copyright. We do not give legal advice. We do not license footage. A Parallel miss is not permission. Collision=missing means we did not get a search, not that you are in the clear. The floor never posts, so we also do not publish the thing that would get you a claim.

Required picks before any Parallel or Imagen spend, no defaults: topic (free text; empty or whitespace = no run), platform (tiktok, youtube, youtube_shorts, Instagram/Meta surfaces, podcast), length — same desk from shorts / YouTube Shorts through full_length_documentary and feature_film (tiktok-length, shorts, weekly_update, one_time_short_episode, full_length_documentary, feature_film), depth, script lean (voice only; fixed political list), tell (required free text; how the piece is told; examples on the floor, not a closed list), and tone (required free text on news/doc — the creator's voice so the script stays in that voice while remaining cite-faithful; examples only — News desk / Make the viewer think / Question the decisions / Personal take / On the cited print). Tone does not restamp sources. Same Parallel cites with a different tone yield a different VO stance (tone A/B); there is no A/B widget on the floor. Pairing is the cut: documentary / weekly_update are always host/reporter news (no invented people, even if tell says family thriller). feature_film may invent a frame labeled (frame) from whatever they typed and does not require tone. Empty tell, or empty tone on news/doc, is 400 and does not spend.

Cite-repair failsafe: if the VO or a room rewrite drifts from Parallel cites, re-query Parallel (up to 3 attempts); keep only supported beats or drop the rest. FAIL / HOLD (`cite-repair loop exhausted`) only after the loop exceeds 3. The discussant room may still run one extra Parallel research on `not_enough_information` (not a third); recut `other` is Vertex rewrite only. Cite-repair runs again after the room, before the board.

The researcher writes a timeline once and stamps each source. The floor writes a full recordable script (scene headings, action, host VO or screenplay dialogue — not one beat per receipt row), then searches Parallel for existing YouTube / docs / news / films whose narration matches, then cuts a frame-by-frame shot list. Hits stamp collision=yes with a sourced URL. A sourced miss is collision=no. Parallel down stays missing. Lean does not restamp. Nonfiction boards prefer archive tape for event shots; Imagen is only for maps, troop-movement animation, and infographics — never a photoreal fake of the event. Sourced is a cited link, not a rip. Fiction features may Imagen invented rooms. If Imagen or Vertex is down, the shot list stays and images stay missing.

## Features and functionality

- Before you record: timed VO, collision list, house-organ / propaganda / fringe / unsourced stamps
- Match list only — not a copyright clearance, not legal advice, not a license
- Required picks: topic, platform, length, depth, script lean, tell (free text), tone (free text on news/doc)
- Shot list cut from that VO; nonfiction uses archive tape for events; genAI is maps and infographics only; we do not license the tape
- Script lean does not restamp sources or collisions; tone is the creator's voice and also does not restamp
- Same cites + different tone change VO stance, not stamps (no A/B widget)
- Cite-repair: re-query Parallel if VO/board drift from cites; keep or drop; HOLD only after the loop exceeds 3 attempts
- Range: shorts / YouTube Shorts through full_length_documentary and feature_film
- Write-once Parallel timeline via Search + Extract + Task (pro). Search satisfies the track. Extract and Task make the pack a thesis. No Monitor create.
- GET never spends; POST is token-gated and pick-gated
- Floor never posts
- Gemini ADK crew on Vertex 2.5 Flash (`gemini-2.5-flash`)

## Technologies used

- Gemini 2.5 Flash (`gemini-2.5-flash`, Vertex AI)
- Google Agent Development Kit (ADK)
- Vertex Imagen
- Official Parallel Web Python SDK (`parallel-web`)
- Cloud Run, Cloud Firestore
- FastAPI
- Python 3.12

## Other data sources used

Seeded first-open packet `oc-recession-july-2026` in `sample_data/packet.json`. Leftover Hormuz (`oc-hormuz-decade`) is a named exclusion/negative case, not first-open. No creator accounts. No secrets.

## Google SDK used

Google ADK (`google-adk`) + Gemini / Imagen (`google-genai`). Firestore client. Parallel via `from parallel import Parallel`.

## Date started

29 August 2026

## Pre-existing / third-party code

Google ADK, google-genai, google-cloud-firestore, parallel-web, FastAPI. New repo.
