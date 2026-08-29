# One Crew — 3 minute demo

Record unedited. Show the timed VO, the collision list, and the source stamps. Do not post.

## 0:00–0:40 · What you see before you record

Talk over the floor with `oc-hormuz-decade` already open.

> One Crew is a research companion for a one-person shop. Before you record you see a timed VO with citations, which lines already exist as someone else's media (collision yes / no / missing), and which sources are house organs, propaganda, fringe, or unsourced. You can see the risk on the page. We do not clear copyright. We do not give legal advice. A Parallel miss is not permission. Collision=missing means we did not get a search. The floor never posts.

## 0:40–1:20 · VO, collisions, stamps

1. Point at **topic** first — Hormuz. Then **youtube · one_time_short_episode · decade · centered_independent · nonfiction · global_overview**. Seed stays a news short, not a feature. Seed collisions are `missing` because GET does not spend.
2. Point at the **timed VO** and the **collision list** next to it. Then the **shot list** — one shot per beat, not a leftover stills collage. Citations like `[jcpoa-2018]`.
3. Point at **grounded** jcpoa-2018 and **hormuz-share** (not independent, propaganda, still grounded).
4. Point at **mainstream** oil-panic — source lean `missing`. Then **producer-frame**.
5. Point at **fringe** secret-closure — still on the list. Centered ask did not hide it.
6. Causal link `missing`. Same receipt: a hit **and** a miss.

## 1:20–2:10 · Lean lock + floor

1. Script lean does not restamp sources or collision URLs. Unhinged voice still cannot invent a source.
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

Stay on a collision row and a fringe row.

> You can see the risk. We did not clear it. The floor did not post.

Stop.

## Prep

- [ ] First-open shows six picks + timed VO + collision list (`missing`) + mixed source list + shot list
- [ ] No pick defaults
- [ ] No publish control
- [ ] Tests green
