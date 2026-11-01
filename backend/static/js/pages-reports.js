window.ClinicFlow.registerRoute("reports", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    let types = {};
    try {
      types = (await window.ClinicFlow.apiGet("/api/reports/types")) || {};
    } catch (e) {
      window.ClinicFlow.toast(e.message, "error");
    }
    const groups = (types && types.groups) || {};
    const typeList = (types && types.types) || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Reports</div><div class="page-sub">Operational and financial reporting</div></div>
      </div>
      ${Object.keys(groups).map((g) => `
        <div class="card mb16"><div class="card-header"><div class="card-title">${window.ClinicFlow.escapeHtml(g)}</div></div><div class="card-body row wrap">${typeList.filter((t) => groups[g] && groups[g].includes(t.key)).map((t) => `<button class="btn" data-report="${t.key}">${window.ClinicFlow.escapeHtml(t.title)}</button>`).join("")}</div></div>`).join("")}
      <div class="card"><div class="card-header"><div class="card-title">Preview</div></div><div class="card-body" id="report-preview"></div></div>
    `;
    host.querySelectorAll("[data-report]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const key = btn.getAttribute("data-report");
        const preview = $("#report-preview");
        if (!preview) return;
        preview.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
        try {
          const data = await window.ClinicFlow.apiGet("/api/reports/" + key);
          const report = data.report || {};
          preview.innerHTML = `<div class="card-title mb16">${window.ClinicFlow.escapeHtml(report.title || key)}</div>
            <div class="muted small mb8">${report.date_label || ""}</div>
            <div class="table-wrap"><table class="table"><thead><tr>${(report.columns || []).map((c) => `<th>${window.ClinicFlow.escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>${(report.rows || []).slice(0, 20).map((r) => `<tr>${r.map((c) => `<td>${window.ClinicFlow.escapeHtml(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
          preview.dataset.reportKey = key;
        } catch (e) {
          preview.innerHTML = '<div class="empty-state"><div class="empty-title">Failed to load report</div><div class="empty-sub">' + window.ClinicFlow.escapeHtml(e.message) + '</div></div>';
        }
      });
    });
  },
});
