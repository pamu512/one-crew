from __future__ import annotations

# Bedroom-studio floor. Topic + required depth. No publish control. GET-only until POST /shift.

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
    .script { color: var(--muted); font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
    .finding { border-top: 1px solid var(--line); padding: 12px 0; }
    .stamp { font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }
    .stamp.grounded { color: var(--grounded); }
    .stamp.mainstream { color: var(--mainstream); }
    .stamp.fringe { color: var(--fringe); }
    .stamp.missing { color: var(--hold); }
    .url { font-size: 12px; color: #d8c4a8; word-break: break-all; }
    .note { font-size: 12px; color: var(--muted); }
    .frames { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .frame { background: #120e0b; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    .frame img { width: 100%; height: 140px; object-fit: cover; display: block; background: #0c0a08; }
    .frame p { font-size: 12px; color: var(--muted); margin: 8px 10px 10px; }
    .hold { color: var(--hold); }
    label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 6px; }
    textarea, input[type="password"] {
      width: 100%; background: #120e0b; color: var(--fg); border: 1px solid var(--line);
      border-radius: 8px; padding: 8px; font: inherit;
    }
    .depths { display: flex; flex-direction: column; gap: 6px; margin: 8px 0 12px; }
    .depths label { display: flex; gap: 8px; align-items: center; margin: 0; color: var(--fg); font-size: 13px; }
    button {
      background: #2a2118; color: var(--fg); border: 1px solid var(--line);
      border-radius: 8px; padding: 8px 12px; font: inherit; cursor: pointer;
    }
    button:disabled { opacity: .45; cursor: not-allowed; }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="brand">One Crew</div>
      <div class="sub">Research companion. Timed VO, cited sources, collision list. Floor never posts.</div>
    </div>
    <div class="badges" id="badges"></div>
  </header>
  <main>
    <section class="card">
      <div class="brand">Desk</div>
      <p class="script">Topic first, then platform, length, depth, script lean, tell, tone. Any missing pick = no run. GET does not spend. The floor never posts.</p>
      <label for="topic">Topic — pick 1, required</label>
      <textarea id="topic" rows="3" placeholder="Are we near recession?"></textarea>
      <label>Platform — required</label>
      <div class="depths" id="platforms"></div>
      <label>Length / cut — required</label>
      <div class="depths" id="cuts"></div>
      <label>Depth — required</label>
      <div class="depths" id="depths"></div>
      <label>Script lean — required (does not restamp sources)</label>
      <div class="depths" id="leans"></div>
      <label for="tell">Tell — pick 6, required free text</label>
      <textarea id="tell" rows="3" placeholder="Host-only desk read of the last year of US recession prints"></textarea>
      <p class="note">Examples only — not the only allowed values:</p>
      <p class="note">Host-only desk read of the last year of US recession prints</p>
      <p class="note">No guest. No panel. Just the cited prints.</p>
      <p class="note">Walk USREC, then payrolls, then GDP — host only</p>
      <p class="note">One family in Bandar Abbas, kitchen radio on</p>
      <p class="note">Thriller on a tanker crossing Hormuz that might get hit</p>
      <p class="note">Weekly news desk, host only</p>
      <p class="note">Historical drama through one port family</p>
      <p class="note">Leftover tell (not first-open): Narrator-led global overview of the US and Iran</p>
      <p class="note">Documentary / weekly_update stay news: host VO, no invented people, even if you type a family thriller. Feature invents a frame from whatever you typed.</p>
      <label for="tone">Tone — required on news/doc (not on feature_film)</label>
      <textarea id="tone" rows="2" placeholder="On the cited print"></textarea>
      <p class="note">Examples only — not the only allowed values:</p>
      <p class="note">News desk</p>
      <p class="note">Make the viewer think</p>
      <p class="note">Question the decisions</p>
      <p class="note">Personal take</p>
      <p class="note">On the cited print</p>
      <p class="note">Tone is a voice. It does not restamp source rows. It is not a clearance.</p>
      <label for="token">Shift token (spend only)</label>
      <input id="token" type="password" autocomplete="off"/>
      <button id="research" type="button" disabled>Write script</button>
      <p class="script" id="desk-msg">Any missing pick = no run.</p>
      <p class="script" id="health"></p>
    </section>
    <section class="card" id="packet">Loading oc-recession-july-2026…</section>
  </main>
  <script>
    const PLATFORMS = [
      {id:"tiktok", label:"tiktok"},
      {id:"youtube", label:"youtube"},
      {id:"youtube_shorts", label:"youtube_shorts"},
      {id:"instagram_reels", label:"instagram_reels"},
      {id:"instagram_stories", label:"instagram_stories"},
      {id:"instagram_feed", label:"instagram_feed"},
      {id:"facebook_reels", label:"facebook_reels"},
      {id:"facebook_feed", label:"facebook_feed"},
      {id:"threads", label:"threads"},
      {id:"podcast", label:"podcast"}
    ];
    const CUTS = [
      {id:"tiktok-length", label:"tiktok-length"},
      {id:"shorts", label:"shorts"},
      {id:"weekly_update", label:"weekly_update"},
      {id:"one_time_short_episode", label:"one_time_short_episode"},
      {id:"full_length_documentary", label:"full_length_documentary"},
      {id:"feature_film", label:"feature_film"}
    ];
    const DEPTHS = [
      {id:"1y", label:"1y"},
      {id:"2-3y", label:"2-3y"},
      {id:"5y", label:"5y"},
      {id:"decade", label:"decade"},
      {id:"few_decades", label:"few_decades"},
      {id:"pre-1980_pre-internet", label:"pre-1980_pre-internet"}
    ];
    const LEANS = [
      {id:"centered_independent", label:"centered_independent"},
      {id:"left", label:"left"},
      {id:"right", label:"right"},
      {id:"far_right", label:"far_right"},
      {id:"far_left", label:"far_left"},
      {id:"unhinged_fringe", label:"unhinged_fringe"}
    ];
    function chosenRadio(name) {
      const el = document.querySelector('input[name="' + name + '"]:checked');
      return el ? el.value : "";
    }

    function syncDesk() {
      const topic = document.getElementById("topic").value.trim();
      const platform = chosenRadio("platform");
      const cut = chosenRadio("cut");
      const depth = chosenRadio("depth");
      const lean = chosenRadio("script_lean");
      const tell = document.getElementById("tell").value.trim();
      const tone = document.getElementById("tone").value.trim();
      const needTone = cut !== "feature_film";
      const btn = document.getElementById("research");
      const live = window.__shiftsOn === true;
      btn.disabled = !topic || !platform || !cut || !depth || !lean || !tell || (needTone && !tone) || !live;
      const msg = document.getElementById("desk-msg");
      if (!topic) { msg.textContent = "No topic chosen = no run."; return; }
      if (!platform) { msg.textContent = "No platform chosen = no run."; return; }
      if (!cut) { msg.textContent = "No cut chosen = no run."; return; }
      if (!depth) { msg.textContent = "No depth chosen = no run."; return; }
      if (!lean) { msg.textContent = "No script lean chosen = no run."; return; }
      if (!tell) { msg.textContent = "No tell chosen = no run."; return; }
      if (needTone && !tone) { msg.textContent = "No tone chosen = no run."; return; }
      msg.textContent = live
        ? "Picks locked. Research spends Parallel only after this."
        : "Live spend off. Token-gate still on spend.";
    }

    function renderRadios(rootId, name, rows) {
      const root = document.getElementById(rootId);
      root.innerHTML = "";
      rows.forEach(d => {
        const lab = document.createElement("label");
        const inp = document.createElement("input");
        inp.type = "radio";
        inp.name = name;
        inp.value = d.id;
        inp.addEventListener("change", syncDesk);
        lab.appendChild(inp);
        lab.appendChild(document.createTextNode(d.label));
        root.appendChild(lab);
      });
    }

    function findingHtml(f) {
      return `
        <div class="finding">
          <div class="stamp ${f.stamp}">${f.stamp} · ${f.parallel_status}${f.when ? " · " + f.when : ""}</div>
          ${f.independent === "no" ? `<div class="stamp fringe">not independent</div>` : ""}
          ${f.propaganda === "yes" ? `<div class="stamp fringe">propaganda</div>` : ""}
          <p>${f.claim}</p>
          ${f.parallel_url ? `<div class="url">${f.parallel_url}</div>` : ""}
          <div class="note">${f.note}</div>
          <div class="note">lean: ${f.lean || "missing"}${f.lean_url ? " · " + f.lean_url : ""}</div>
          <div class="note">interests: ${Array.isArray(f.interests) ? f.interests.join(", ") : (f.interests || "missing")}${f.interests_url ? " · " + f.interests_url : ""}</div>
          <div class="note">who_repeats: ${Array.isArray(f.who_repeats) ? f.who_repeats.join(", ") : (f.who_repeats || "missing")}${f.who_repeats_url ? " · " + f.who_repeats_url : ""}</div>
          <div class="note">independent: ${f.independent || "missing"}${f.independent_url ? " · " + f.independent_url : ""}</div>
          <div class="note">vested_interest: ${Array.isArray(f.vested_interest) ? f.vested_interest.join(", ") : (f.vested_interest || "missing")}${f.vested_interest_url ? " · " + f.vested_interest_url : ""}</div>
          <div class="note">propaganda: ${f.propaganda || "missing"}${f.propaganda_issuer && f.propaganda_issuer !== "missing" ? " · " + f.propaganda_issuer : ""}${f.propaganda_url ? " · " + f.propaganda_url : ""}</div>
        </div>`;
    }

    function linkHtml(l) {
      return `
        <div class="finding">
          <div class="stamp ${l.stamp}">link · ${l.stamp}</div>
          <p>${l.claim}</p>
          <div class="note">${l.from_id} → ${l.to_id}</div>
          ${l.parallel_url ? `<div class="url">${l.parallel_url}</div>` : `<div class="note">causal link missing — not invented</div>`}
        </div>`;
    }

    function renderPacket(packet) {
      const rec = packet.receipt || {};
      const findings = (rec.findings || []).map(findingHtml).join("");
      const links = (rec.causal_links || []).map(linkHtml).join("");
      const frames = (packet.frames || []).map(fr => `
        <div class="frame">
          ${fr.image_href ? `<img src="${fr.image_href}" alt="${fr.shot}"/>` : `<p class="note">Image missing. Shot list kept. Not invented.</p>`}
          <p>${fr.shot_no ? "#" + fr.shot_no + " · " : ""}${fr.camera ? fr.camera + " · " : ""}${fr.shot}</p>
          <p class="note">footage · ${fr.footage || "missing"}${fr.kind ? " · " + fr.kind : ""}${fr.footage === "sourced" ? " · someone else's footage, not ours. We do not license it." : ""}${fr.footage === "imagen" && (fr.kind === "motion_graphic" || fr.kind === "infographic") ? " · graphic, not archive" : ""}</p>
          ${fr.footage_url ? `<div class="url">${fr.footage_url}${fr.footage_title && fr.footage_title !== "missing" ? " · " + fr.footage_title : ""}</div>` : ""}
          ${fr.line ? `<p class="note">${fr.line}</p>` : ""}
        </div>`).join("");
      document.getElementById("packet").innerHTML = `
        <div class="brand">${packet.id}</div>
        <h1 class="hook">${packet.topic || packet.hook}</h1>
        <p class="script">platform: ${packet.platform || "none"} · cut: ${packet.cut || "none"} · depth: ${packet.depth || "none"} · script lean: ${packet.script_lean || "none"} · tell: ${packet.tell || "none"} · tone: ${packet.tone || "none"}</p>
        <div class="brand" style="margin:16px 0 8px">Timed VO</div>
        <p class="script">${packet.script || ""}</p>
        <div class="brand" style="margin:16px 0 8px">Existing media · collision</div>
        <p class="note">Match list of videos/docs/films with the same or near script. Not a copyright clearance. The floor does not post.</p>
        ${(packet.beats || []).map(b => `
          <div class="finding">
            <div class="stamp ${b.collision === "yes" ? "fringe" : "missing"}">collision · ${b.collision || "missing"}${b.collision_kind && b.collision_kind !== "missing" ? " · " + b.collision_kind : ""}</div>
            <p>${b.id}</p>
            ${b.collision_url ? `<div class="url">${b.collision_url}</div>` : ""}
            ${b.collision_title && b.collision_title !== "missing" ? `<div class="note">${b.collision_title}</div>` : ""}
          </div>`).join("")}
        <p class="${packet.collision_disposition === "HOLD" ? "hold" : "note"}">${packet.collision_disposition || "HOLD"} ${packet.collision_hold_reason || ""}</p>
        <p class="${rec.disposition === "HOLD" ? "hold" : "note"}">${rec.disposition || ""} ${rec.hold_reason || ""}</p>
        <div class="brand" style="margin:16px 0 8px">Research pack (always written · floor does not post it)</div>
        <p class="script">${packet.research_pack || "Research pack missing."}</p>
        <div class="brand" style="margin:16px 0 8px">Cited sources</div>
        ${findings}
        <div class="brand" style="margin:16px 0 8px">Causal links</div>
        ${links || `<p class="note">No Parallel-sourced link. Missing, not invented.</p>`}
        <div class="brand" style="margin:16px 0 8px">Shot list (from that VO)</div>
        <div class="frames">${frames}</div>
      `;
      if (packet.topic && !document.getElementById("topic").value) {
        document.getElementById("topic").value = packet.topic;
      }
    }

    async function load() {
      renderRadios("platforms", "platform", PLATFORMS);
      renderRadios("cuts", "cut", CUTS);
      renderRadios("depths", "depth", DEPTHS);
      renderRadios("leans", "script_lean", LEANS);
      const health = await fetch("/api/health").then(r => r.json());
      window.__shiftsOn = !!(health.shifts && health.shifts.enabled);
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
      syncDesk();

      const body = await fetch("/api/packets").then(r => r.json());
      const packet = (body.packets || [])[0];
      if (!packet) { document.getElementById("packet").textContent = "No packet."; return; }
      renderPacket(packet);
      syncDesk();
    }

    document.getElementById("topic").addEventListener("input", syncDesk);
    document.getElementById("tell").addEventListener("input", syncDesk);
    document.getElementById("tone").addEventListener("input", syncDesk);
    document.getElementById("research").addEventListener("click", async () => {
      const platform = chosenRadio("platform");
      const cut = chosenRadio("cut");
      const depth = chosenRadio("depth");
      const script_lean = chosenRadio("script_lean");
      const topic = document.getElementById("topic").value.trim();
      const tell = document.getElementById("tell").value.trim();
      const tone = document.getElementById("tone").value.trim();
      if (!topic || !platform || !cut || !depth || !script_lean || !tell || (cut !== "feature_film" && !tone)) {
        document.getElementById("desk-msg").textContent = "Any missing pick = no run.";
        return;
      }
      const token = document.getElementById("token").value.trim();
      const res = await fetch("/api/shifts", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(token ? {"X-Shift-Token": token} : {})
        },
        body: JSON.stringify({topic, platform, cut, depth, script_lean, tell, tone, goal: topic || "Research the topic. Do not post."})
      });
      const text = await res.text();
      document.getElementById("desk-msg").textContent = res.ok ? "Timeline written." : (res.status + " " + text);
      if (res.ok) load();
    });

    load().catch(err => {
      document.getElementById("packet").textContent = "API unreachable. python -m onecrew";
      console.error(err);
    });
  </script>
</body>
</html>
"""
