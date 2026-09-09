# One Crew — 2–3 minute demo

Record unedited. Product spine, not a floor-UI walk. Do not post.

Live default is Gemini 2.5 Flash (`gemini-2.5-flash`) + ADK + Vertex Imagen.

## 0:00–0:25 · Problem

Talk over first-open (seed example `oc-recession-july-2026`). GET never spends.

> One Crew is a research companion for a one-person / solo creator shop. Before you record you see collisions, dirty sources, and holes. You leave with a citable thesis plus a full recordable script, not a 6-beat sketch. We do not clear copyright, do not give legal advice, and do not license tape. Collision=missing is not a clearance. The floor never posts.

## 0:25–1:15 · Solution — cites, script, board, tone

1. Required picks, no defaults: topic, platform, length, depth, script lean, **tell** (required free text — how the piece is told), **tone** (required free text on news/doc). Empty tell, or empty tone on news/doc, is 400 and does not spend. `feature_film` does not require tone.
2. **Tone** is the creator's voice: the script stays in that voice while remaining cite-faithful. Tone does not restamp sources. A questioning tone still cannot invent a source or hide fringe.
3. Point at the **cited pack**, the **full script** (scenes, action, host VO — not six pasted claims), and the **frame-by-frame shot list**. Nonfiction uses archive tape for events; Imagen is maps and infographics only. We do not license the tape.
4. Seed collisions stay `missing` because GET does not spend. Lean does not restamp.

## 1:15–1:40 · Failsafe — cite-repair

> If the VO or a room rewrite drifts from Parallel cites, we re-query Parallel. Keep only supported beats or drop the rest. FAIL / HOLD only after the cite-repair loop exceeds 3 attempts (`cite-repair loop exhausted`). The room may still run one extra Parallel research on `not_enough_information`, then cite-repair runs again before the board. We do not invent a URL.

## 1:40–2:00 · Range

Stay on the length picks. Same desk covers **shorts / YouTube Shorts** through **`full_length_documentary`** and **`feature_film`**. Pairing is the cut: documentary / weekly_update stay host/reporter news (no invented people); feature may invent a `(frame)`.

## 2:00–2:20 · Shield

No publish button. The floor never posts. GET never spends. POST needs `SHIFT_TOKEN` + `X-Shift-Token` and every required pick. Unset token → 403. Missing pick → 400. **live spend off** on first-open.

## 2:20–2:40 · Optional — tone A/B, same cites

Same Parallel cites, two tone strings (e.g. **News desk** vs **Question the decisions**): VO stance changes; stamps do not. There is no A/B widget on the floor — that is two runs with the same picks and a different tone.

## 2:40–3:00 · Close

Stay on a collision row and a fringe row.

> You can see the risk. The script stayed in the creator's voice and on the cites. We did not clear it. The floor did not post.

Stop.

## Locks

```bash
PYTHONPATH=backend pytest backend/tests -q
curl -s http://127.0.0.1:43158/api/health
curl -s -X POST http://127.0.0.1:43158/api/shifts \
  -H 'content-type: application/json' \
  -H "X-Shift-Token: $SHIFT_TOKEN" \
  -d '{"topic":"Are we near recession?","platform":"youtube","cut":"one_time_short_episode","depth":"2-3y","script_lean":"centered_independent","tell":"Host-only desk read of the last year of US recession prints","tone":"On the cited print"}'
```

GET never spends. POST without token is 403. POST with token and any missing pick is 400. Cite-repair HOLDs only after the loop exceeds 3 attempts. Live POST mints a new snapshot id. Seed `oc-recession-july-2026` stays first-open. Leftover `oc-hormuz-decade` is not GET.

## Prep

- [ ] First-open shows required picks + script + collision list (`missing`) + mixed source list + shot list
- [ ] Tell and tone are free-text fields (tone skipped on `feature_film`)
- [ ] No pick defaults
- [ ] No publish control
- [ ] Live default `gemini-2.5-flash`
- [ ] Tests green
