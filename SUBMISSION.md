# Submission copy

Do not file until the owner says so. Repo: https://github.com/pamu512/one-crew

## Project name

One Crew

## Tagline

Pick topic, then platform, length, depth, lean, and how to tell it. You get a timed VO, cited sources, and a shot list cut from that VO.

## Text description

One Crew is a research companion that returns a timed VO plus cited sources. Before any Parallel or Imagen spend you pick, in order: topic (free text, required; empty or whitespace = no run), then platform (tiktok, youtube, youtube_shorts, Instagram/Meta: instagram_reels, instagram_stories, instagram_feed, facebook_reels, facebook_feed, threads, plus podcast), length (tiktok-length, shorts, weekly_update, one_time_short_episode, full_length_documentary, feature_film), depth (1y, 2-3y, 5y, decade, few_decades, pre-1980_pre-internet), script lean (centered_independent, left, right, far_right, far_left, unhinged_fringe), and tell (genre: nonfiction, horror, war, historical, musical, drama, thriller; vantage: global_overview, one_family, one_ship). nonfiction is documentaries and news: host/reporter VO from the receipt, no invented family or ship. Fiction genres are feature films; frame invention is allowed only there and must be labeled (frame). full_length_documentary and weekly_update require nonfiction. feature_film requires a fiction genre. Illegal pairs are 400 and do not spend. Receipt stamps stay non-fiction. No defaults. Any missing pick = no run.

The researcher writes a timeline once and stamps each source. The floor writes a timed VO in the requested lean, sized to platform and length, with beats, timecodes, and citations pointing at those rows. After the VO exists, Parallel searches for existing YouTube videos, documentaries, news packages, and films whose script or narration is the same or substantially the same, so the creator sees collisions before they record. That is a match list, not a copyright clearance. Then a shot list is cut from that VO. TikTok/Shorts generate every beat. Episode/doc/feature generate one Imagen key frame per scene (capped at the event cap, never 400 images). Not a receipt-join. If Imagen or Vertex is down, the shot list stays and images stay missing. Script lean does not restamp sources or collisions. The floor never posts.

## Features and functionality

- Six required picks: topic, platform, length, depth, script lean, tell (genre + vantage)
- Timed VO plus cited sources plus a collision list plus a shot list cut from that VO
- Collision search after VO: match list of existing media with the same script; not a copyright clearance
- Boards are not optional; Imagen/Vertex down keeps the shot list and leaves images missing
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
