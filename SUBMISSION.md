# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

A research companion for a one-person shop. You pick the window and the cut. The floor never posts.

## Text description

One Crew is a research companion for a one-person shop. You type a topic, then choose how far back and how long the piece is. Depth is required (1y / 2-3y / 5y / decade / few decades / pre-1980 pre-internet). Cut is required (tiktok, youtube_shorts, weekly_update, one_time_short_episode, full_length_documentary). No depth or no cut = no run. The receipt and any boards are sized to that cut. A TikTok packet is not a doc packet. A documentary depth+cut can be a long timeline.

The researcher calls the official Parallel Web Python SDK and writes a timeline once. Each event is stamped grounded, mainstream, or fringe, plus lean, interests, source independence, vested interest, and propaganda — Parallel-sourced or missing. Causal links are grounded only if Parallel sourced the link; otherwise missing. Missing stays missing.

Boards stay optional after the timeline, from the script/timeline plus Parallel refs — never a collage. If Parallel, Vertex, or Imagen is down — or pre-1980 misses — the packet HOLDs. GET is seeded (`oc-hormuz-decade`) and never spends. POST that spends is token-gated. The floor never posts.

## Features and functionality

- Research companion front door: topic + required depth + required cut (no defaults)
- Receipt and boards sized to the cut; TikTok is not a doc packet
- Write-once Parallel timeline
- Causal links: grounded only if Parallel sourced; else missing
- Stamps: grounded / mainstream / fringe
- Mainstream lean / interests / who_repeats: Parallel-sourced or missing
- Cited sources: independent yes/no/missing and vested_interest, Parallel-sourced or missing
- Propaganda yes/no/missing: Parallel-sourced named issuer or missing; not Gemini tone
- Hit and miss on the same receipt
- Optional boards after the timeline, never a collage
- Fail-closed HOLD when rails are down or pre-1980 misses
- GET never spends; POST spend is token-gated, depth-gated, and cut-gated
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
