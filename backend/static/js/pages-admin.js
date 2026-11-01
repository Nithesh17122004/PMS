window.ClinicFlow.registerRoute("admin", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const data = await window.ClinicFlow.apiGet("/api/admin/dashboard");
    const d = data || {};
    host.innerHTML = `
      <div class="page-head"><div><div class="page-title">Platform</div><div class="page-sub">Clinics and operations</div></div></div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("admin", 20)}</span></div><div><div class="stat-value">${d.stats ? d.stats.clinics : 0}</div><div class="stat-label">Clinics</div></div></div>
        <div class="card stat-card"><div class="stat-icon teal"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("patients", 20)}</span></div><div><div class="stat-value">${d.stats ? d.stats.patients : 0}</div><div class="stat-label">Patients</div></div></div>
        <div class="card stat-card"><div class="stat-icon amber"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("activity", 20)}</span></div><div><div class="stat-value">${d.stats ? d.stats.consultations : 0}</div><div class="stat-label">Consultations</div></div></div>
        <div class="card stat-card"><div class="stat-icon red"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("billing", 20)}</span></div><div><div class="stat-value">${window.ClinicFlow.fmtMoney(d.stats ? d.stats.revenue : 0)}</div><div class="stat-label">Revenue</div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Clinics</div><div class="card-body table-wrap"><table class="table"><thead><tr><th>Name</th><th>Slug</th><th>Plan</th><th>Status</th><th></th></tr></thead><tbody id="admin-clinic-tbody"></tbody></table></div></div></div>
    `;
    const clinics = (d.clinics || []);
    $("#admin-clinic-tbody").innerHTML = clinics.map((cl) => `
      <tr>
        <td><b>${window.ClinicFlow.escapeHtml(cl.name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(cl.city || "")}</div></td>
        <td class="mono">${window.ClinicFlow.escapeHtml(cl.slug)}</td>
        <td>${window.ClinicFlow.escapeHtml(cl.plan || "")}</td>
        <td>${window.ClinicFlow.statusBadge(cl.is_active ? "active" : "inactive")}</td>
        <td class="right"><button class="btn btn-sm" data-view="${cl.id}">Manage</button></td>
      </tr>`).join("");
    $("#admin-clinic-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      const res = await window.ClinicFlow.apiGet("/api/admin/clinics/" + id);
      const cl = res.clinic || {};
      window.ClinicFlow.toast(cl.name || "Clinic", "info");
    });
  },
});
