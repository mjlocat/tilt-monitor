"use strict";

// Tilt color name -> CSS color for card accents / chart lines.
const COLOR_HEX = {
  Red: "#e0524a", Green: "#3fa34d", Black: "#888", Purple: "#9b59b6",
  Orange: "#e08a2a", Blue: "#3a86ff", Yellow: "#e0c020", Pink: "#e06aa8",
};

let chart = null;
let calibration = {}; // color -> {temp_correction, sg_correction}

async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}

async function putJSON(url, body) {
  const r = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

function fmtAge(ts) {
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

async function refreshCalibration() {
  const list = await getJSON("/api/calibration");
  calibration = {};
  for (const c of list) {
    calibration[c.color] = {
      temp_correction: c.temp_correction,
      sg_correction: c.sg_correction,
    };
  }
}

function cardHTML(r) {
  const cal = calibration[r.color] || { temp_correction: 0, sg_correction: 0 };
  const hex = COLOR_HEX[r.color] || "#f0a020";
  const battery = r.battery_weeks == null ? "—" : `${r.battery_weeks} wk`;
  return `
    <div class="card" style="--color:${hex}">
      <div class="color-name">${r.color}</div>
      <div class="big">${r.sg.toFixed(3)}</div>
      <div class="sub">SG &middot; ${r.temperature.toFixed(1)}&deg;F</div>
      <div class="sub">Battery age: ${battery} &middot; RSSI ${r.rssi} &middot; ${fmtAge(r.ts)}</div>
      <div class="cal">
        <label>Temp correction
          <input type="number" step="0.1" value="${cal.temp_correction}" data-color="${r.color}" data-field="temp"></label>
        <label>SG correction
          <input type="number" step="0.001" value="${cal.sg_correction}" data-color="${r.color}" data-field="sg"></label>
        <button class="secondary" data-save="${r.color}">Save calibration</button>
      </div>
    </div>`;
}

async function refreshCurrent() {
  const readings = await getJSON("/api/current");
  const container = document.getElementById("cards");
  if (!readings.length) {
    container.innerHTML = '<p class="muted">Waiting for a Tilt reading…</p>';
    return;
  }
  container.innerHTML = readings.map(cardHTML).join("");

  container.querySelectorAll("button[data-save]").forEach((btn) => {
    btn.addEventListener("click", () => saveCalibration(btn.dataset.save));
  });

  // Populate history color selector with seen colors.
  const sel = document.getElementById("history-color");
  const existing = new Set([...sel.options].map((o) => o.value));
  for (const r of readings) {
    if (!existing.has(r.color)) {
      const opt = document.createElement("option");
      opt.value = opt.textContent = r.color;
      sel.appendChild(opt);
    }
  }
  if (!sel.value && readings.length) sel.value = readings[0].color;
}

async function saveCalibration(color) {
  const t = document.querySelector(`input[data-color="${color}"][data-field="temp"]`).value;
  const s = document.querySelector(`input[data-color="${color}"][data-field="sg"]`).value;
  await putJSON("/api/calibration", {
    color,
    temp_correction: parseFloat(t) || 0,
    sg_correction: parseFloat(s) || 0,
  });
  await refreshCalibration();
  await refreshCurrent();
  await refreshChart();
}

async function refreshChart() {
  const color = document.getElementById("history-color").value;
  const hours = document.getElementById("history-hours").value;
  if (!color) return;
  const data = await getJSON(`/api/history?color=${color}&hours=${hours}`);
  const hex = COLOR_HEX[color] || "#f0a020";
  const points = data.map((d) => ({ x: d.ts * 1000, sg: d.sg, temp: d.temperature }));

  const cfg = {
    type: "line",
    data: {
      datasets: [
        {
          label: "Gravity",
          yAxisID: "y",
          borderColor: hex,
          backgroundColor: hex,
          data: points.map((p) => ({ x: p.x, y: p.sg })),
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "Temp (°F)",
          yAxisID: "y1",
          borderColor: "#8a8f99",
          backgroundColor: "#8a8f99",
          data: points.map((p) => ({ x: p.x, y: p.temp })),
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    },
    options: {
      animation: false,
      scales: {
        x: { type: "time", ticks: { color: "#8a8f99" }, grid: { color: "#333" } },
        y: { position: "left", title: { display: true, text: "SG", color: "#8a8f99" }, ticks: { color: "#8a8f99" }, grid: { color: "#333" } },
        y1: { position: "right", title: { display: true, text: "°F", color: "#8a8f99" }, ticks: { color: "#8a8f99" }, grid: { drawOnChartArea: false } },
      },
      plugins: { legend: { labels: { color: "#e6e6e6" } } },
    },
  };

  if (chart) {
    chart.data = cfg.data;
    chart.update();
  } else {
    chart = new Chart(document.getElementById("chart"), cfg);
  }
}

async function refreshSettings() {
  const s = await getJSON("/api/settings");
  document.getElementById("bf-enabled").checked = s.bf_enabled;
  document.getElementById("bf-interval").textContent = Math.round(s.upload_interval_seconds / 60);
  document.getElementById("bf-api-key").placeholder = s.bf_api_key_set ? "•••••• (set)" : "API key";
}

function wireEvents() {
  document.getElementById("bf-enabled").addEventListener("change", async (e) => {
    await putJSON("/api/settings", { bf_enabled: e.target.checked });
    setStatus(e.target.checked ? "Uploads enabled." : "Uploads disabled.");
  });
  document.getElementById("bf-save").addEventListener("click", async () => {
    const key = document.getElementById("bf-api-key").value;
    if (!key) return setStatus("Enter an API key first.");
    await putJSON("/api/settings", { bf_api_key: key });
    document.getElementById("bf-api-key").value = "";
    await refreshSettings();
    setStatus("API key saved.");
  });
  document.getElementById("bf-test").addEventListener("click", async () => {
    setStatus("Sending…");
    await fetch("/api/brewersfriend/test", { method: "POST" });
    setStatus("Upload attempted — check server logs / Brewer's Friend.");
  });
  document.getElementById("history-color").addEventListener("change", refreshChart);
  document.getElementById("history-hours").addEventListener("change", refreshChart);
}

function setStatus(msg) {
  document.getElementById("bf-status").textContent = msg;
}

async function init() {
  wireEvents();
  await refreshCalibration();
  await refreshSettings();
  await refreshCurrent();
  await refreshChart();
  setInterval(async () => {
    await refreshCurrent();
    await refreshChart();
  }, 5000);
}

init();
