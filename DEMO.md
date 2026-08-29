# One Crew — 3 minute demo

Record unedited. Show the timed VO and the cited sources. Do not post.

## 0:00–0:40 · Companion

Talk over the floor with `oc-hormuz-decade` already open.

> Topic is pick 1. Then platform, length, depth, lean, and tell (genre + vantage). You get a timed VO, cited sources, and a shot list cut from that VO.

## 0:40–1:20 · Six picks + timed VO

1. Point at **topic** first — Hormuz. Then **youtube · one_time_short_episode · decade · centered_independent · nonfiction · global_overview**. Seed stays a news short, not a feature. Same receipt can be told as short fiction (drama/one_family or thriller/one_ship) or as a `feature_film` with a fiction genre. Invented frame only on fiction genres, labeled `(frame)`. Documentary + thriller, or feature + nonfiction, is 400. Empty topic or tell = no run. Any missing pick = no run.
2. Point at the **timed VO** and the **shot list** together — act/scene blocks with running timecodes, citations like `[jcpoa-2018]`. One shot per beat, not a leftover stills collage. Point at the **collision list** next to the script: existing media with the same or near narration, so the creator sees a Content ID risk before they record. Match list only. We do not clear copyright.
3. Point at **grounded** jcpoa-2018 and **hormuz-share** (not independent, propaganda, still grounded).
4. Point at **mainstream** oil-panic — source lean `missing`. Then **producer-frame**.
5. Point at **fringe** secret-closure — still on the list. Centered ask did not hide it.
6. Causal link `missing`. Same receipt: a hit **and** a miss.

## 1:20–2:10 · Lean lock + floor

1. Script lean does not restamp sources. Unhinged voice still cannot invent a source.
2. The timed VO converted to a shot list. Boards are not optional. If Imagen is down, the shot list stays and images stay missing.
3. No publish button. The floor never posts. **live spend off**.

## 2:10–2:50 · Locks

```bash
PYTHONPATH=backend pytest backend/tests -q
curl -s http://127.0.0.1:43158/api/health
curl -s -X POST http://127.0.0.1:43158/api/shifts -d '{"topic":"Hormuz"}'
```

GET never spends. POST without token is 403. POST with token and any missing pick is 400.

## 2:50–3:00 · Close

Stay on the VO citation and the fringe row.

> The VO leaned. The stamps did not. The floor did not post.

Stop.

## Prep

- [ ] First-open shows six picks (topic first, tell last) + timed VO + shot list + mixed source list
- [ ] No pick defaults
- [ ] No publish control
- [ ] Tests green
