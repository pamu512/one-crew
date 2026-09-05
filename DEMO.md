# One Crew — 3 minute demo

Record unedited. Show the timed VO, the collision list, and the source stamps. Do not post.

## 0:00–0:40 · What you see before you record

Talk over the floor with `oc-recession-july-2026` already open. First paint is the recession 8-beat: smash USREC=0 into payrolls −23k.

> One Crew is a research companion for a one-person shop. Before you record you see collisions, dirty sources, and holes. You leave with a citable thesis plus a full recordable script, not a 6-beat sketch. Tell and tone are free text. Nonfiction uses archive tape; Imagen is maps and infographics only. We do not clear copyright, do not give legal advice, and do not license tape. Collision=missing is not a clearance. The floor never posts.

## 0:40–1:20 · VO, collisions, stamps

1. Point at **topic** first — `Are we near recession?` Then **youtube · one_time_short_episode · 1y · centered_independent**, tell **Host-only desk read of the last year of US recession prints**, and tone **On the cited print** (free text; the listed lines are examples, not the only values). Seed stays a news short, not a feature. Seed collisions are `missing` because GET does not spend.
2. Point at the **full script** (scenes, action, host VO — not six pasted claims) and the **collision list** next to it. Then the **frame-by-frame shot list**. First paint: USREC=0 smashed into payrolls −23k. Citations like `[usrec-july-2026]`.
3. Point at **grounded** usrec-july-2026 and payrolls-july-2026 (official series, Parallel hit).
4. Point at **mainstream** already-in — source lean `missing`. The scare stays on the list.
5. Point at **fringe** lei-july-2026 — still on the list. Centered ask did not hide it. LEI and ISM stay off the VO unless a beat cites them.
6. No leftover Hormuz causal on first-open. Same receipt: a hit **and** a miss.

## 1:20–2:10 · Lean lock + floor

1. Script lean does not restamp sources or collision URLs. Unhinged voice still cannot invent a source.
2. The timed VO converted to a shot list. Nonfiction uses archive tape for events; Imagen is maps and infographics only. Fiction may Imagen invented rooms. We do not license the tape. Boards are not optional. If Imagen is down, the shot list stays and images stay missing.
3. No publish button. The floor never posts. **live spend off**.

## 2:10–2:50 · Locks

```bash
PYTHONPATH=backend pytest backend/tests -q
curl -s http://127.0.0.1:43158/api/health
curl -s -X POST http://127.0.0.1:43158/api/shifts \
  -H 'content-type: application/json' \
  -H "X-Shift-Token: $SHIFT_TOKEN" \
  -d '{"topic":"Are we near recession?","platform":"youtube","cut":"one_time_short_episode","depth":"2-3y","script_lean":"centered_independent","tell":"Host-only desk read of the last year of US recession prints","tone":"On the cited print"}'
```

GET never spends. POST without token is 403. POST with token and any missing pick is 400. Live POST mints a new snapshot id. Seed `oc-recession-july-2026` stays first-open. Leftover `oc-hormuz-decade` is not GET.

## 2:50–3:00 · Close

Stay on a collision row and a fringe row.

> You can see the risk. We did not clear it. The floor did not post.

Stop.

## Prep

- [ ] First-open shows required picks + timed VO + collision list (`missing`) + mixed source list + shot list
- [ ] No pick defaults
- [ ] No publish control
- [ ] Tests green
