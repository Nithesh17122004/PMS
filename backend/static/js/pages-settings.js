window.ClinicFlow.registerRoute("settings", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const clinic = await window.ClinicFlow.apiGet("/api/clinic");
    const c = clinic.clinic || clinic || {};
    const staff = await window.ClinicFlow.apiGet("/api/clinic/staff");
    host.innerHTML = `
      <div class="page-head"><div><div class="page-title">Settings</div><div class="page-sub">Clinic, staff, roles and audit</div></div></div>
      <div class="card mb16"><div class="card-header"><div class="card-title">Clinic</div></div><div class="card-body grid cols-2">
        <div><div class="muted small">Name</div><b>${window.ClinicFlow.escapeHtml(c.name || "")}</b></div>
        <div><div class="muted small">Timezone</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.timezone : "")}</b></div>
        <div><div class="muted small">Currency</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.currency : "")}</b></div>
        <div><div class="muted small">Token mode</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.token_mode : "")}</b></div>
      </div></div>
      <div class="card mb16"><div class="card-header"><div class="card-title">Staff</div><div class="card-body table-wrap"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead><tbody id="staff-tbody"></tbody></table></div></div></div>
      <div class="card mb16"><div class="card-header"><div class="card-title">Audit log</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Actor</th><th>Action</th><th>Entity</th><th>When</th></tr></thead><tbody id="audit-tbody"></tbody></table></div></div>
    `;
    const staffList = staff || [];
    $("#staff-tbody").innerHTML = staffList.map((u) => `
      <tr>
        <td><div class="row"><span class="avatar" style="background:${u.avatar_color || "#0e63b2"}">${window.ClinicFlow.initials(u.full_name)}</span><div><b>${window.ClinicFlow.escapeHtml(u.full_name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(u.designation || "")}</div></div></div></td>
        <td>${window.ClinicFlow.escapeHtml(u.email)}</td>
        <td>${window.ClinicFlow.escapeHtml(u.role ? u.role.name : "")}</td>
        <td>${window.ClinicFlow.statusBadge(u.is_active ? "active" : "inactive")}</td>
      </tr>`).join("") || '<tr><td colspan="4">${window.ClinicFlow.emptyState("No staff", "Invite staff members.")}</td></tr>';
    const audit = await window.ClinicFlow.apiGet("/api/clinic/audit-logs");
    const auditList = audit || [];
    $("#audit-tbody").innerHTML = auditList.slice(0, 30).map((l) => `
      <tr>
        <td>${window.ClinicFlow.escapeHtml(l.user ? l.user.full_name : "System")}</td>
        <td class="mono">${window.ClinicFlow.escapeHtml(l.action)}</td>
        <td>${window.ClinicFlow.escapeHtml(l.entity_type || "")}</td>
        <td class="muted nowrap">${window.ClinicFlow.fmtDateTime(l.created_at)}</td>
      </tr>`).join("");
  },
});
