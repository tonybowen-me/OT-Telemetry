"use strict";

let levelChart = null;
let pressureChart = null;

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

function el(id) { return document.getElementById(id); }

function setStatus(node, text, cls) {
  node.textContent = text;
  node.className = "status " + cls;
}

function lineChart(canvasId, existing, labels, datasets, yTitle) {
  if (existing) existing.destroy();
  return new Chart(el(canvasId), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#e6edf3" } } },
      scales: {
        x: { title: { display: true, text: "iteration (5-min steps)", color: "#8b949e" },
             ticks: { color: "#8b949e", maxTicksLimit: 12 }, grid: { color: "#21262d" } },
        y: { title: { display: true, text: yTitle, color: "#8b949e" },
             ticks: { color: "#8b949e" }, grid: { color: "#21262d" } }
      }
    }
  });
}

function ds(label, data, color, dashed) {
  return {
    label, data, borderColor: color, backgroundColor: color,
    borderDash: dashed ? [6, 4] : [], pointRadius: 0, borderWidth: 2, tension: 0.15,
    spanGaps: false,
  };
}

async function loadScenarios() {
  const scenarios = await getJSON("/api/scenarios");
  const sel = el("scenario");
  sel.innerHTML = "";
  scenarios.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => render(sel.value));
  if (scenarios.length) render(scenarios[0].id);
}

function fillTable(tbodySel, rows) {
  const tb = document.querySelector(tbodySel + " tbody");
  tb.innerHTML = "";
  rows.forEach((cells) => {
    const tr = document.createElement("tr");
    cells.forEach((c) => {
      const td = document.createElement("td");
      td.innerHTML = c;
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
}

function statusTag(s) {
  const map = { pass: "tag-pass", fail: "tag-fail", not_applicable: "tag-na", warn: "tag-warn" };
  return `<span class="${map[s] || ""}">${s.replace("_", " ")}</span>`;
}

async function render(id) {
  const r = await getJSON(`/api/scenario/${id}`);
  const meta = await getJSON(`/api/scenario/${id}/meta`);

  el("scenario-class").textContent = r.scenario_class.replace(/_/g, " ");
  el("scenario-desc").textContent = meta.description + "  " + meta.narrative;

  setStatus(el("pilot-status"), r.pilot_status.toUpperCase(), r.pilot_status);
  el("pilot-sub").textContent = r.layer3.triggered && r.layer3.top_hypothesis
    ? "root cause: " + r.layer3.candidates[0].label
    : (r.pilot_status === "valid" ? "telemetry physically self-consistent" : "");

  const sigCls = r.sigma.alert ? "alert" : "quiet";
  setStatus(el("sigma-status"), r.sigma.alert ? (r.sigma.highest_level || "alert").toUpperCase() : "NO ALERT", sigCls);
  el("sigma-sub").textContent = r.sigma.alert
    ? `${r.sigma.triggered_rules.length} rule(s) matched`
    : "no threshold rule matched";

  el("comparison").textContent = r.comparison;

  const ev = r.evidence;
  levelChart = lineChart("levelChart", levelChart, ev.iterations, [
    ds("actual (physical truth)", ev.actual_tank_level, "#2ea043", false),
    ds("reported (SCADA)", ev.reported_tank_level, "#f85149", true),
  ], "tank level (m)");
  pressureChart = lineChart("pressureChart", pressureChart, ev.iterations, [
    ds("actual J39", ev.pressure_J39_actual, "#2ea043", false),
    ds("reported J39", ev.pressure_J39_reported, "#f85149", true),
  ], "pressure (m)");

  const expUl = el("explanations");
  expUl.innerHTML = "";
  r.explanations.forEach((e) => {
    const li = document.createElement("li"); li.textContent = e; expUl.appendChild(li);
  });
  const fUl = el("findings");
  fUl.innerHTML = "";
  if (!r.operational_findings.length) {
    const li = document.createElement("li"); li.textContent = "None."; li.style.color = "#8b949e"; fUl.appendChild(li);
  }
  r.operational_findings.forEach((f) => {
    const li = document.createElement("li"); li.textContent = f; fUl.appendChild(li);
  });

  const rc = el("rootcause");
  if (r.layer3.triggered && r.layer3.candidates.length) {
    const top = r.layer3.candidates[0];
    rc.innerHTML = `<div class="rc-title">${top.label} — ${(top.confidence * 100).toFixed(0)}%</div>` +
      top.evidence.map((e) => `<div class="rc-ev">• ${e}</div>`).join("");
  } else {
    rc.innerHTML = `<span style="color:#8b949e">Layer 3 not engaged — no inconsistency to explain.</span>`;
  }

  fillTable("#invariants", r.layer1.invariants.map((i) => [
    `<code>${i.rule_id}</code>`, statusTag(i.status), i.observed,
  ]));
  fillTable("#trust", r.layer2.sensors.map((s) => [
    s.name, statusTag(s.verdict), `min trust ${s.min_trust}`,
  ]));

  const sr = el("sigma-rules");
  sr.innerHTML = "";
  if (!r.sigma.triggered_rules.length) {
    const li = document.createElement("li"); li.textContent = "None."; li.style.color = "#8b949e"; sr.appendChild(li);
  }
  r.sigma.triggered_rules.forEach((h) => {
    const li = document.createElement("li");
    li.innerHTML = `<code>${h.name}</code> (${h.level}) — <code>${h.expression}</code>, ${h.hit_count}× from iter ${h.first_iteration}`;
    sr.appendChild(li);
  });
}

loadScenarios().catch((e) => {
  document.querySelector("main").insertAdjacentHTML("afterbegin",
    `<p style="color:#f85149">Failed to load: ${e.message}</p>`);
});
