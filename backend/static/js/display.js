window.ClinicFlow.display = {
  clinic: null,
  key: null,
  data: null,
  async load() {
    const el = document.querySelector("#display-root");
    const key = (el && el.getAttribute("data-key")) || this.key;
    if (!key) return;
    this.key = key;
    const host = document.querySelector("#display-root");
    if (host) host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const data = await window.ClinicFlow.apiGet("/api/public/display/" + key);
    this.data = data || {};
    const d = this.data;
    const clinic = d.clinic || {};
    const now = d.now_serving || [];
    const overall = d.overall || {};
    const queues = d.queues || [];
    const current = now[0] || null;
    document.querySelector("#display-clinic").textContent = clinic.name || "Clinic";
    document.querySelector("#display-message").textContent = d.display_message || "Please wait for your token.";
    const numberEl = document.querySelector("#display-number");
    if (current) {
      numberEl.textContent = current.display_number;
      numberEl.classList.remove("big");
    } else {
      numberEl.textContent = "--";
      numberEl.classList.add("big");
    }
    const servingEl = document.querySelector("#display-serving");
    if (current) {
      servingEl.innerHTML = `<div class="display-row"><div><div class="display-sub">Now serving</div><div>${window.ClinicFlow.escapeHtml(current.doctor || "")} · ${window.ClinicFlow.escapeHtml(current.room_number || "")}</div></div><div class="display-number" style="font-size:42px">${window.ClinicFlow.escapeHtml(current.display_number)}</div></div>`;
    } else {
      servingEl.innerHTML = '<div class="display-row"><div class="display-sub">Now serving</div><div class="display-number" style="font-size:42px">--</div></div>';
    }
    const waitingEl = document.querySelector("#display-waiting");
    waitingEl.innerHTML = (queues || []).map((q) => {
      const count = q.waiting ? q.waiting.length : 0;
      return `<div class="display-row"><div><div class="display-sub">${window.ClinicFlow.escapeHtml(q.doctor || "")}</div><div class="muted small">${q.specialization || ""}${q.room_number ? " · Room " + window.ClinicFlow.escapeHtml(q.room_number) : ""}</div></div><div><div style="font-size:26px;font-weight:800">${count}</div><div class="muted small">waiting</div></div></div>`;
    }).join("");
    const countsEl = document.querySelector("#display-counts");
    countsEl.innerHTML = Object.entries(overall || {}).map(([k, v]) => `<span class="badge" style="background:rgba(255,255,255,0.12);color:#eaf2fc">${k.replace(/_/g, "")}: ${v}</span>`).join("");
  },
  async start() {
    await this.load();
    setInterval(() => { this.load(); }, 15000);
  },
};
document.addEventListener("DOMContentLoaded", () => {
  if (window.ClinicFlow && window.ClinicFlow.display) window.ClinicFlow.display.start();
});
