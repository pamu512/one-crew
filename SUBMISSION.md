# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

Before you record: a timed VO, a collision list, and source stamps you can see. We do not clear copyright.

## Text description

One Crew is a research companion for a one-person shop. Before you record, you see (1) a timed VO with citations, (2) which lines already exist as someone else's media (collision yes / no / missing), and (3) which sources are house organs, propaganda, fringe, or unsourced. The point is you can see the risk on the page. We do not clear copyright. We do not give legal advice. We do not license footage. A Parallel miss is not permission. Collision=missing means we did not get a search, not that you are in the clear. The floor never posts, so we also do not publish the thing that would get you a claim.

Six picks are required before any Parallel or Imagen spend, no defaults: topic (free text; empty or whitespace = no run), platform (tiktok, youtube, youtube_shorts, Instagram/Meta surfaces, podcast), length (tiktok-length, shorts, weekly_update, one_time_short_episode, full_length_documentary, feature_film), depth, script lean (voice only), and tell (genre + vantage). nonfiction is news and documentaries. Fiction genres are features; frame invention is labeled (frame). Documentary/weekly_update require nonfiction; feature_film requires a fiction genre. Illegal pairs are 400 and do not spend.

The researcher writes a timeline once and stamps each source. The floor writes a full recordable script (scene headings, action, host VO or screenplay dialogue — not one beat per receipt row), then searches Parallel for existing YouTube / docs / news / films whose narration matches, then cuts a frame-by-frame shot list. Hits stamp collision=yes with a sourced URL. A sourced miss is collision=no. Parallel down stays missing. Lean does not restamp. TikTok/Shorts generate every beat; episode/doc/feature generate one key frame per scene (event cap, never 400 images). If Imagen or Vertex is down, the shot list stays and images stay missing.

## Features and functionality

- Before you record: timed VO, collision list, house-organ / propaganda / fringe / unsourced stamps
- Match list only — not a copyright clearance, not legal advice, not a license
- Six required picks: topic, platform, length, depth, script lean, tell (genre + vantage)
- Shot list cut from that VO; boards are not optional
- Script lean does not restamp sources or collisions
- Write-once Parallel timeline
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
