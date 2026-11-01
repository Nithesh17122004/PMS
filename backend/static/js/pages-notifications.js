window.ClinicFlow.registerRoute("notifications", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const items = await window.ClinicFlow.apiGet("/api/notifications");
    const list = items || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Notifications</div><div class="page-sub">Inbox and delivery</div></div>
        <button class="btn" id="notif-refresh">Refresh</button>
      </div>
      <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>Type</th><th>Subject</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody id="notif-tbody"></tbody></table></div></div>
    `;
    const renderRows = (rows) => {
      const tbody = $("#notif-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="5">${window.ClinicFlow.emptyState("No notifications", "You're all caught up.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((n) => `
        <tr>
          <td><span class="badge info">${window.ClinicFlow.escapeHtml(n.notification_type || "")}</span></td>
          <td>${window.ClinicFlow.escapeHtml(n.subject || "")}</td>
          <td>${window.ClinicFlow.statusBadge(n.status)}</td>
          <td class="muted nowrap">${window.ClinicFlow.fmtDateTime(n.created_at)}</td>
          <td class="right"><button class="btn btn-sm" data-read="${n.id}">Mark read</button></td>
        </tr>`).join("");
    };
    renderRows(list);
    $("#notif-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-read]");
      if (!btn) return;
      const id = btn.getAttribute("data-read");
      await window.ClinicFlow.apiPost("/api/notifications/" + id + "/read");
      window.ClinicFlow.navigate("#/notifications");
    });
  },
});
