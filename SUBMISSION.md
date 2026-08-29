# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

Pick platform, length, depth, then how you want it to lean. You get a script and cited sources.

## Text description

One Crew is a research companion that returns a script plus cited sources. Before any Parallel or Imagen spend you pick, in order: platform (tiktok, youtube, youtube_shorts, instagram, podcast), length (tiktok-length, shorts, weekly_update, one_time_short_episode, full_length_documentary), depth (1y, 2-3y, 5y, decade, few_decades, pre-1980_pre-internet), and script lean (centered_independent, left, right, far_right, far_left, unhinged_fringe). No defaults. Any missing pick = no run.

The researcher writes a timeline once and stamps each source. The floor writes the script in the requested lean, sized to platform and length, with citations pointing at those rows. Script lean does not restamp sources. Unhinged voice cannot invent sources or mark propaganda as grounded. Centered_independent still shows missing when Parallel missed. Boards stay optional after the script. The floor never posts.

## Features and functionality

- Four required picks: platform, length, depth, script lean
- Script plus cited sources, sized to platform + length
- Script lean does not restamp sources
- Write-once Parallel timeline
- Stamps: grounded / mainstream / fringe, source lean, interests, independent, vested_interest, propaganda
- Causal links grounded only if Parallel sourced
- GET never spends; POST is token-gated and pick-gated
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
