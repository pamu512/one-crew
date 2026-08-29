# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

Overnight researcher and board artist. Parallel timelines. Imagen shots. The floor never posts.

## Text description

One Crew is for a bedroom YouTube / TikTok creator who types a topic. The desk asks depth before any Parallel or Imagen spend — current, 2-3 years, 5 years, decade, few decades, or pre-1980. No depth chosen = no run. The researcher calls the official Parallel Web Python SDK and writes a timeline once. Each event is a row. Causal links are their own stamps: grounded only if Parallel sourced the link; otherwise the link is missing. Do not invent a 40-year chain.

Each event is stamped exactly one of grounded (Parallel URL on the row), mainstream (widely repeated, may be bias, not a source), or fringe (included and tagged, never sold as fact). The same receipt must show a Parallel hit and a Parallel miss. Boards come after the receipt if the creator wants frames. If Parallel, Vertex, or Imagen is down — or pre-1980 misses — the packet HOLDs. No invented source, no collage, no invented stamp, no invented chain.

GET is seeded (`oc-hormuz-decade`) and never spends Parallel or Imagen. POST that spends is 403 unless `X-Shift-Token` matches `SHIFT_TOKEN`. Depth is required on that POST. The floor has no publish control.

## Features and functionality

- Topic front door + required depth picker (no default)
- Write-once Parallel timeline
- Causal links: grounded only if Parallel sourced; else missing
- Stamps: grounded / mainstream / fringe
- Mainstream lean / interests / who_repeats: Parallel-sourced or missing
- Cited sources: independent yes/no/missing and vested_interest, Parallel-sourced or missing
- Hit and miss on the same receipt
- Four shot frames from script + Parallel refs, after the receipt
- Fail-closed HOLD when rails are down or pre-1980 misses
- GET never spends; POST spend is token-gated and depth-gated
- Floor never posts
- Gemini ADK crew on Vertex 3.5 Flash

## Technologies used

- Gemini 3.5 Flash (Vertex AI)
- Google Agent Development Kit (ADK)
- Vertex Imagen
- Official Parallel Web Python SDK (`parallel-web`)
- Cloud Run, Cloud Firestore
- FastAPI
- Python 3.12

## Other data sources used

Seeded first-open packet `oc-hormuz-decade` in `sample_data/packet.json`. No creator accounts. No secrets.

## Google SDK used

Google ADK (`google-adk`) + Gemini / Imagen (`google-genai`). Firestore client. Parallel via `from parallel import Parallel`.

## Date started

29 August 2026

## Pre-existing / third-party code

Google ADK, google-genai, google-cloud-firestore, parallel-web, FastAPI. New repo.
