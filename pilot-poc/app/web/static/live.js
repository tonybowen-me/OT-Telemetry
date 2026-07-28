"use strict";

let levelChart = null;
const POLL_MS = 1200;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}
function el(id) { return document.getElementById(id); }
function setStatus(node, text, cls) { node.textContent = text; node.className = "status " + cls; }

function lineChart(canvasId, existing, labels, datasets, yTitle) {
  if (existing) { existing.data.labels = labels; existing.data.datasets.forEach((d, i) => { d.data = datasets[i].data; }); existing.update("none"); return existing; }
  return new Chart(el(canvasId), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true, animation: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#e6edf3" } } },
      scales: {
        x: { title: { display: true, text: "live stream (5-min steps)", color: "#8b949e" }, ticks: { color: "#8b949e", maxTicksLimit: 10 }, grid: { color: "#21262d" } },
        y: { title: { display: true, text: yTitle, color: "#8b949e" }, min: 0, suggestedMax: 7, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}
function ds(label, data, color, dashed) {
  return { label, data, borderColor: color, backgroundColor: color, borderDash: dashed ? [6, 4] : [], pointRadius: 0, borderWidth: 2, tension: 0.15, spanGaps: false };
}
function statusTag(s) {
  const map = { pass: "tag-pass", fail: "tag-fail", not_applicable: "tag-na", warn: "tag-warn" };
  return `<span class="${map[s] || ""}">${s.replace("_", " ")}</span>`;
}
function fillTable(sel, rows) {
  const tb = document.querySelector(sel + " tbody");
  tb.innerHTML = "";
  rows.forEach((cells) => {
    const tr = document.createElement("tr");
    cells.forEach((c) => { const td = document.createElement("td"); td.innerHTML = c; tr.appendChild(td); });
    tb.appendChild(tr);
  });
}
function list(id, items, emptyText) {
  const ul = el(id); ul.innerHTML = "";
  if (!items.length) { const li = document.createElement("li"); li.textContent = emptyText; li.style.color = "#8b949e"; ul.appendChild(li); return; }
  items.forEach((t) => { const li = document.createElement("li"); li.innerHTML = t; ul.appendChild(li); });
}

async function updateLabBanner() {
  try {
    const s = await getJSON("/api/lab-status");
    if (s.connected) {
      el("connDot").className = "conn ok";
      el("connText").textContent = `connected to utility @ ${s.lab_url}`;
      el("labCond").textContent = s.status.condition === "surge" ? "demand surge" : "nominal";
      el("labAtk").textContent = s.status.attack;
    } else {
      el("connDot").className = "conn bad";
      el("connText").textContent = `utility offline (${s.lab_url}) — start the lab service`;
    }
  } catch (e) {
    el("connDot").className = "conn bad";
    el("connText").textContent = "utility offline";
  }
}

async function tick() {
  await updateLabBanner();
  let r;
  try {
    r = await getJSON("/api/live");
  } catch (e) { return; }

  setStatus(el("pilot-status"), r.pilot_status.toUpperCase(), r.pilot_status);
  el("pilot-sub").textContent = r.layer3.triggered && r.layer3.top_hypothesis
    ? "root cause: " + r.layer3.candidates[0].label
    : (r.pilot_status === "valid" ? "telemetry physically self-consistent" : "");

  const sigCls = r.sigma.alert ? "alert" : "quiet";
  setStatus(el("sigma-status"), r.sigma.alert ? (r.sigma.highest_level || "alert").toUpperCase() : "NO ALERT", sigCls);
  el("sigma-sub").textContent = r.sigma.alert ? `${r.sigma.triggered_rules.length} rule(s) matched` : "no threshold rule matched";

  el("comparison").textContent = r.comparison;

  const ev = r.evidence;
  levelChart = lineChart("levelChart", levelChart, ev.iterations, [
    ds("reported (SCADA — PILOT input)", ev.reported_tank_level, "#f85149", true),
    ds("actual (physical truth)", ev.actual_tank_level, "#2ea043", false),
  ], "tank level (m)");

  list("explanations", r.explanations.map((e) => `<span>${e}</span>`), "—");
  list("findings", r.operational_findings, "None.");

  const rc = el("rootcause");
  if (r.layer3.triggered && r.layer3.candidates.length) {
    const top = r.layer3.candidates[0];
    rc.innerHTML = `<div class="rc-title">${top.label} — ${(top.confidence * 100).toFixed(0)}%</div>` +
      top.evidence.map((e) => `<div class="rc-ev">• ${e}</div>`).join("");
  } else {
    rc.innerHTML = `<span style="color:#8b949e">Layer 3 not engaged — no inconsistency to explain.</span>`;
  }

  fillTable("#invariants", r.layer1.invariants.map((i) => [`<code>${i.rule_id}</code>`, statusTag(i.status), i.observed]));
  fillTable("#trust", r.layer2.sensors.map((s) => [s.name, statusTag(s.verdict), `min trust ${s.min_trust}`]));
  list("sigma-rules", r.sigma.triggered_rules.map((h) =>
    `<code>${h.name}</code> (${h.level}) — <code>${h.expression}</code>, ${h.hit_count}× from iter ${h.first_iteration}`), "None.");
}

tick();
setInterval(tick, POLL_MS);
