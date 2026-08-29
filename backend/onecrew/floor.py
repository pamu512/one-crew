from __future__ import annotations

# Bedroom-studio floor. No publish control. GET-only surface.

FLOOR_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>One Crew — floor</title>
  <style>
    :root {
      --bg: #16110d;
      --fg: #f3e6d4;
      --muted: #9a8470;
      --line: #3a2d24;
      --card: #1e1712;
      --grounded: #c8e6a0;
      --mainstream: #f0d48a;
      --fringe: #e8b4a0;
      --hold: #f0c27a;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; background: var(--bg); color: var(--fg); font-family: ui-sans-serif, system-ui, sans-serif; }
    header { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; padding: 18px 22px; border-bottom: 1px solid var(--line); }
    .brand { font-family: ui-monospace, monospace; letter-spacing: .22em; font-size: 12px; text-transform: uppercase; color: var(--hold); }
    .sub { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .badges { display: flex; flex-wrap: wrap; gap: 6px; }
    .badge { font-size: 11px; padding: 3px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); }
    .badge.ok { color: var(--grounded); border-color: #3d4a2e; }
    .badge.miss { color: var(--hold); border-color: #5a4630; }
    main { display: grid; grid-template-columns: 1fr; gap: 18px; padding: 22px; }
    @media (min-width: 960px) { main { grid-template-columns: 320px 1fr; } }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; }
    h1 { font-size: 22px; font-weight: 560; line-height: 1.25; margin: 8px 0 0; }
    .hook { color: var(--fg); }
    .script { color: var(--muted); font-size: 13px; line-height: 1.5; }
    .finding { border-top: 1px solid var(--line); padding: 12px 0; }
    .stamp { font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }
    .stamp.grounded { color: var(--grounded); }
    .stamp.mainstream { color: var(--mainstream); }
    .stamp.fringe { color: var(--fringe); }
    .url { font-size: 12px; color: #d8c4a8; word-break: break-all; }
    .note { font-size: 12px; color: var(--muted); }
    .frames { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .frame { background: #120e0b; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    .frame img { width: 100%; height: 140px; object-fit: cover; display: block; background: #0c0a08; }
    .frame p { font-size: 12px; color: var(--muted); margin: 8px 10px 10px; }
    .hold { color: var(--hold); }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="brand">One Crew</div>
      <div class="sub">Researcher + boarder. Floor never posts.</div>
    </div>
    <div class="badges" id="badges"></div>
  </header>
  <main>
    <section class="card">
      <div class="brand">First-open</div>
      <p class="script">Seeded packet. GET does not spend Parallel or Imagen. The floor never posts.</p>
      <p class="script" id="health"></p>
    </section>
    <section class="card" id="packet">Loading oc-pickle-debt…</section>
  </main>
  <script>
    async function load() {
      const health = await fetch("/api/health").then(r => r.json());
      const badges = document.getElementById("badges");
      badges.innerHTML = "";
      if (!health.shifts.enabled) {
        const b = document.createElement("span");
        b.className = "badge";
        b.textContent = "live spend off";
        badges.appendChild(b);
      }
      (health.rails.present || []).forEach(r => {
        const b = document.createElement("span");
        b.className = "badge ok";
        b.textContent = r + " present";
        badges.appendChild(b);
      });
      (health.rails.missing || []).forEach(r => {
        const b = document.createElement("span");
        b.className = "badge miss";
        b.textContent = r + " missing";
        badges.appendChild(b);
      });
      document.getElementById("health").textContent =
        "model " + health.model + " · store " + health.store + " · floor does not post";

      const body = await fetch("/api/packets").then(r => r.json());
      const packet = (body.packets || [])[0];
      const root = document.getElementById("packet");
      if (!packet) { root.textContent = "No packet."; return; }
      const rec = packet.receipt || {};
      const findings = (rec.findings || []).map(f => `
        <div class="finding">
          <div class="stamp ${f.stamp}">${f.stamp} · ${f.parallel_status}</div>
          <p>${f.claim}</p>
          ${f.parallel_url ? `<div class="url">${f.parallel_url}</div>` : ""}
          <div class="note">${f.note}</div>
          <div class="note">lean: ${f.lean || "missing"}${f.lean_url ? " · " + f.lean_url : ""}</div>
          <div class="note">interests: ${Array.isArray(f.interests) ? f.interests.join(", ") : (f.interests || "missing")}${f.interests_url ? " · " + f.interests_url : ""}</div>
          <div class="note">who_repeats: ${Array.isArray(f.who_repeats) ? f.who_repeats.join(", ") : (f.who_repeats || "missing")}${f.who_repeats_url ? " · " + f.who_repeats_url : ""}</div>
        </div>`).join("");
      const frames = (packet.frames || []).map(fr => `
        <div class="frame">
          <img src="${fr.image_href}" alt="${fr.shot}"/>
          <p>${fr.shot}</p>
        </div>`).join("");
      root.innerHTML = `
        <div class="brand">${packet.id}</div>
        <h1 class="hook">${packet.hook}</h1>
        <p class="script">${packet.script}</p>
        <p class="${rec.disposition === "HOLD" ? "hold" : "note"}">${rec.disposition || ""} ${rec.hold_reason || ""}</p>
        ${findings}
        <div class="brand" style="margin:16px 0 8px">Four shot frames</div>
        <div class="frames">${frames}</div>
      `;
    }
    load().catch(err => {
      document.getElementById("packet").textContent = "API unreachable. python -m onecrew";
      console.error(err);
    });
  </script>
</body>
</html>
"""
