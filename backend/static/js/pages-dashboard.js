window.ClinicFlow.registerRoute("dashboard", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const data = await window.ClinicFlow.apiGet("/api/dashboard").catch(() => ({}));
    const d = data || {};
    const stats = d.stats || {};
    const charts = d.charts || {};
    const user = window.ClinicFlow.state.user;
    const clinic = window.ClinicFlow.state.clinic;
    const content = `
      <div class="page-head">
        <div><div class="page-title">Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, ${user ? user.full_name.split(" ")[0] : ""}</div>
        <div class="page-sub">Here is what is happening at ${clinic ? clinic.name : "your clinic"} today.</div></div>
        <button class="btn btn-primary" id="dash-today-tokens">Today's tokens</button>
      </div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("activity", 20)}</span></div><div><div class="stat-value">${stats.total_patients ?? 0}</div><div class="stat-label">Total patients</div><div class="stat-foot">${stats.new_patients_today ?? 0} new today</div></div></div>
        <div class="card stat-card"><div class="stat-icon teal"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("queue", 20)}</span></div><div><div class="stat-value">${stats.waiting ?? 0}</div><div class="stat-label">Waiting</div><div class="stat-foot">${stats.in_consultation ?? 0} in consultation</div></div></div>
        <div class="card stat-card"><div class="stat-icon amber"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("calendar", 20)}</span></div><div><div class="stat-value">${stats.todays_appointments ?? 0}</div><div class="stat-label">Appointments</div><div class="stat-foot">${stats.followups_today ?? 0} follow-ups due</div></div></div>
        <div class="card stat-card"><div class="stat-icon red"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("billing", 20)}</span></div><div><div class="stat-value">${window.ClinicFlow.fmtMoney(stats.daily_revenue ?? 0, clinic && clinic.settings ? clinic.settings.currency : "INR")}</div><div class="stat-label">Today's revenue</div><div class="stat-foot">${window.ClinicFlow.fmtMoney(stats.pending_payments ?? 0, "INR")} pending</div></div></div>
      </div>
      <div class="grid" style="grid-template-columns: 2fr 1fr; margin-top:16px;">
        <div class="card"><div class="card-header"><div class="card-title">Visits · last 14 days</div></div><div class="card-body"><div id="dash-visits-chart"></div></div></div>
        <div class="card"><div class="card-header"><div class="card-title">Queue mix</div></div><div class="card-body"><div id="dash-queue-chart"></div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Daily revenue</div></div><div class="card-body"><div id="dash-revenue-chart"></div></div></div>
    `;
    host.innerHTML = content;
    const visitsEl = $("#dash-visits-chart");
    if (visitsEl) window.ClinicFlow.lineChart(visitsEl, { data: charts.daily_visits }, { xKey: "date" });
    const queueEl = $("#dash-queue-chart");
    const queueItems = (charts.token_queue || []).map((s) => ({ label: String(s.status).replace(/_/g, " "), value: s.count, color: statusColor(s.status) }));
    if (queueEl) window.ClinicFlow.donutChart(queueEl, { data: queueItems });
    const revenueEl = $("#dash-revenue-chart");
    if (revenueEl) window.ClinicFlow.barChart(revenueEl, { data: charts.daily_revenue });
    const btn = $("#dash-today-tokens");
    if (btn) btn.addEventListener("click", () => window.ClinicFlow.navigate("#/queue"));
  }
});

function statusColor(status) {
  const map = {
    waiting: "#0284c7", called: "#d97706", in_consultation: "#6d28d9", completed: "#047857",
    skipped: "#b45309", cancelled: "#dc2626", no_show: "#dc2626", recalled: "#0d9488",
    scheduled: "#0284c7", confirmed: "#0d9488", paid: "#047857", partial: "#b45309",
    unpaid: "#dc2626", draft: "#b45309", refunded: "#6d28d9", active: "#047857", inactive: "#dc2626",
  };
  const key = String(status || "").toLowerCase();
  const val = map[key];
  if (val) return val;
  const hue = [...key].reduce((s, c) => s + c.charCodeAt(0), 0) % 360;
  return "hsl(" + Math.round(hue) + ", 55%, 45%)";
}
