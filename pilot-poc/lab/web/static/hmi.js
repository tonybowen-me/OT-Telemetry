const WINDOW = 48;
const HINTS = {
  none: "",
  concealment_mitm: "Concealment MITM armed: SCADA now replays a frozen tank level. The HMI still looks normal \u2014 that is the point.",
  dos: "DoS armed: the tank-level sensor is dropped from the SCADA feed (missing data).",
};

let chart;

function fmt(v, unit = "", dp = 2) {
  if (v === null || v === undefined) return "\u2014";
  return (typeof v === "number" ? v.toFixed(dp) : v) + unit;
}

function initChart() {
  const ctx = document.getElementById("hmiChart");
  chart = new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [
      { label: "Tank level (SCADA)", data: [], borderColor: "#38bdf8", backgroundColor: "rgba(56,189,248,.12)", borderWidth: 2, tension: .25, pointRadius: 0, fill: true, spanGaps: false },
      { label: "Tank level (physical truth)", data: [], borderColor: "#f59e0b", borderDash: [5,4], borderWidth: 1.5, tension: .25, pointRadius: 0, hidden: true },
    ]},
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: { ticks: { color: "#8b98ae", maxTicksLimit: 6 }, grid: { color: "#1b2740" } },
        y: { min: 0, suggestedMax: 7, ticks: { color: "#8b98ae" }, grid: { color: "#1b2740" }, title: { display: true, text: "metres", color: "#8b98ae" } },
      },
      plugins: { legend: { labels: { color: "#c6d3e6", boxWidth: 12 } } },
    },
  });
}

function setActive(container, attr, value) {
  container.querySelectorAll("button").forEach((b) => {
    b.classList.toggle("active", b.dataset[attr] === value);
  });
}

async function post(url) {
  const r = await fetch(url, { method: "POST" });
  return r.json();
}

async function refresh() {
  let scada, truth;
  try {
    [scada, truth] = await Promise.all([
      fetch(`/api/scada?window=${WINDOW}`).then((r) => r.json()),
      fetch(`/api/truth?window=${WINDOW}`).then((r) => r.json()),
    ]);
  } catch (e) { return; }

  const frames = scada.frames;
  const cur = frames[frames.length - 1];
  const st = scada.status;

  // HMI gauges (SCADA-visible values)
  const lvl = cur.tank_level;
  document.getElementById("tankVal").textContent = fmt(lvl, " m");
  const pct = lvl === null ? 0 : Math.max(0, Math.min(100, (lvl / st.tank_max_level) * 100));
  document.getElementById("tankFill").style.height = pct + "%";
  const p1 = document.getElementById("pump1"), p2 = document.getElementById("pump2");
  p1.classList.toggle("on", cur.pump1_status === 1);
  p2.classList.toggle("on", cur.pump2_status === 1);
  document.getElementById("pump1v").textContent = cur.pump1_status === 1 ? "RUN" : "OFF";
  document.getElementById("pump2v").textContent = cur.pump2_status === 1 ? "RUN" : "OFF";
  document.getElementById("inflow").textContent = fmt(cur.tank_inflow, " m\u00b3/s", 3);
  document.getElementById("demand").textContent = fmt(cur.total_demand, " L/s", 1);
  document.getElementById("pJ39").textContent = fmt(cur.pressure_J39, " m", 1);
  document.getElementById("pJ156").textContent = fmt(cur.pressure_J156, " m", 1);

  // state + controls
  document.getElementById("stCond").textContent = st.condition === "surge" ? "demand surge" : "nominal";
  document.getElementById("stAtk").textContent = st.attack;
  setActive(document.getElementById("condBtns"), "cond", st.condition);
  setActive(document.getElementById("atkBtns"), "atk", st.attack);
  document.getElementById("hint").textContent = HINTS[st.attack] || "";
  document.getElementById("clock").textContent =
    `streaming \u00b7 step ${st.stream_index} \u00b7 ${st.step_seconds}s/step`;

  // chart
  chart.data.labels = frames.map((f) => "t" + f.iteration);
  chart.data.datasets[0].data = frames.map((f) => f.tank_level);
  chart.data.datasets[1].data = truth.frames.map((f) => f.tank_level);
  chart.data.datasets[1].hidden = !document.getElementById("revealTruth").checked;
  chart.update();
}

document.getElementById("condBtns").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  await post(`/api/condition/${b.dataset.cond}`); refresh();
});
document.getElementById("atkBtns").addEventListener("click", async (e) => {
  const b = e.target.closest("button"); if (!b) return;
  await post(`/api/attack/${b.dataset.atk}`); refresh();
});

initChart();
refresh();
setInterval(refresh, 1200);
