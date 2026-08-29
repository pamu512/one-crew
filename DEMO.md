# One Crew — 3 minute demo

Record unedited. Show the receipt. Do not post.

## 0:00–0:40 · Companion

Talk over the floor with `oc-hormuz-decade` already open.

> One Crew is a research companion for a one-person shop. You pick the topic, how far back, and how long the piece is. The crew returns a write-once timeline. Missing stays missing.

## 0:40–1:20 · Front door + receipt

1. Point at **topic** Hormuz, **depth = decade**, **cut = one_time_short_episode**. No depth or cut is pre-selected on a new run. No depth = no run. No cut = no run. A TikTok packet is not a doc packet.
2. Point at **grounded** jcpoa-2018 — Parallel URL on the row. independent and propaganda are `missing`.
3. Point at **hormuz-share** — still grounded, the floor says **not independent** and **propaganda**, issuer OPEC.
4. Point at **mainstream** oil-panic — lean / interests are `missing`. Then **producer-frame** — those fields present, Parallel URL on each, lean is not the stamp.
5. Point at **fringe** secret-closure — Parallel miss, never sold as fact.
6. Point at the **causal link** jcpoa-to-houthi — stamp `missing`. Not invented.
7. Same receipt: a hit **and** a miss.

## 1:20–2:10 · Boards + floor

1. Boards are optional after the timeline. Seeded shots are sized to this cut — not a collage.
2. There is no publish button. The floor never posts.
3. Rail badges: Parallel / Vertex / Imagen missing on a local box. **live spend off**.

## 2:10–2:50 · Locks

```bash
PYTHONPATH=backend pytest backend/tests -q
curl -s http://127.0.0.1:43158/api/health
curl -s -X POST http://127.0.0.1:43158/api/shifts -d '{"topic":"Hormuz"}'
```

GET never spends. POST without `X-Shift-Token` is 403. POST with token and no depth or no cut is 400. If Parallel, Vertex, or Imagen is down: HOLD. pre-1980 still HOLDs if Parallel misses.

## 2:50–3:00 · Close

Stay on the missing causal link.

> The link is missing. The floor did not invent a chain. The floor did not post.

Stop.

## Prep

- [ ] First-open already shows `oc-hormuz-decade`
- [ ] Depth and cut pickers have no default
- [ ] No publish control on screen
- [ ] Tests green
