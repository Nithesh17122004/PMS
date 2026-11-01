window.ClinicFlow.registerRoute("lab", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const tests = await window.ClinicFlow.apiGet("/api/lab/tests").catch(() => []);
    const orders = await window.ClinicFlow.apiGet("/api/lab/orders").catch(() => []);
    const testList = tests || [];
    const orderList = orders || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Laboratory</div><div class="page-sub">Orders, samples and results</div></div>
        <button class="btn btn-accent" id="lab-new">${window.ClinicFlow.icon("plus", 16)} New lab order</button>
      </div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("lab", 20)}</span></div><div><div class="stat-value">${testList.length}</div><div class="stat-label">Tests</div></div></div>
        <div class="card stat-card"><div class="stat-icon teal"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("file", 20)}</span></div><div><div class="stat-value">${orderList.length}</div><div class="stat-label">Orders</div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Lab orders</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Order</th><th>Patient</th><th>Doctor</th><th>Status</th><th>Total</th><th></th></tr></thead><tbody id="lab-tbody"></tbody></table></div></div>
    `;
    const renderRows = (rows) => {
      const tbody = $("#lab-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No lab orders", "Create a lab order.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((o) => `
        <tr>
          <td class="mono">${window.ClinicFlow.escapeHtml(o.order_number)}</td>
          <td>${window.ClinicFlow.escapeHtml(o.patient ? o.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.escapeHtml(o.doctor ? o.doctor.full_name : "")}</td>
          <td>${window.ClinicFlow.statusBadge(o.status)}</td>
          <td>${window.ClinicFlow.fmtMoney(o.total_amount)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${o.id}">Open</button></td>
        </tr>`).join("");
    };
    renderRows(orderList);
    $("#lab-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      const res = await window.ClinicFlow.apiGet("/api/lab/orders/" + id);
      const o = res.order || {};
      const modal = window.ClinicFlow.openModal({ title: "Lab order " + window.ClinicFlow.escapeHtml(o.order_number || ""), wide: true });
      const body = document.createElement("div");
      body.innerHTML = (o.items || []).map((i) => `
        <div class="row between mb8">
          <div><b>${window.ClinicFlow.escapeHtml(i.test ? i.test.name : "")}</b><div class="muted small">${window.ClinicFlow.escapeHtml(i.test ? i.test.code : "")} · ${window.ClinicFlow.escapeHtml(i.test ? i.test.reference_range : "")}</div></div>
          <div class="right">${window.ClinicFlow.statusBadge(i.status)}</div>
        </div>`).join("") || '<div class="empty-state"><div class="empty-title">No items</div></div>';
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Close</button><a class="btn btn-primary" href="/api/lab/orders/" + id + "/pdf" target="_blank">Report PDF</a>';
      modal.querySelector(".modal-footer").appendChild(footer);

    });
    if ($("#lab-new")) {
      $("#lab-new").addEventListener("click", async () => {
        const modal = window.ClinicFlow.openModal({ title: "New lab order", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field full"><span>Patient</span><input class="input" id="lab-patient" placeholder="Search patient"/></label>
            <label class="field full"><span>Test selection (IDs)</span><input class="input" id="lab-tests" placeholder="test-id-1,test-id-2"/></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create order</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          const ids = ($("#lab-tests").value || "").split(",").map((s) => s.trim()).filter(Boolean);
          const res = await window.ClinicFlow.apiPost("/api/lab/orders", { patient_id: $("#lab-patient").value.trim(), test_ids: ids });
          window.ClinicFlow.toast("Lab order created", "ok");
          window.ClinicFlow.closeModal();
        });
      });
    }
  },
});
