window.ClinicFlow.registerRoute("pharmacy", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const alerts = await window.ClinicFlow.apiGet("/api/pharmacy/alerts");
    const meds = await window.ClinicFlow.apiGet("/api/pharmacy/medications");
    const alertData = alerts || {};
    const medList = meds || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Pharmacy</div><div class="page-sub">Medicines, stock and dispensing</div></div>
        <button class="btn btn-accent" id="pharm-dispense">${window.ClinicFlow.icon("plus", 16)} Dispense</button>
      </div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("pharmacy", 20)}</span></div><div><div class="stat-value">${medList.length}</div><div class="stat-label">Medications</div></div></div>
        <div class="card stat-card"><div class="stat-icon red"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("warning", 20)}</span></div><div><div class="stat-value">${alertData.counts ? alertData.counts.low_stock : 0}</div><div class="stat-label">Low stock</div></div></div>
        <div class="card stat-card"><div class="stat-icon amber"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("clock", 20)}</span></div><div><div class="stat-value">${alertData.counts ? alertData.counts.expiring : 0}</div><div class="stat-label">Expiring ≤ 90 days</div></div></div>
        <div class="card stat-card"><div class="stat-icon violet"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("box", 20)}</span></div><div><div class="stat-value">${alertData.counts ? alertData.counts.expired : 0}</div><div class="stat-label">Expired</div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Medications</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Name</th><th>SKU</th><th>Stock</th><th>Unit price</th><th>Status</th></tr></thead><tbody id="pharm-tbody"></tbody></table></div></div>
    `;
    const renderRows = (rows) => {
      const tbody = $("#pharm-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="5">${window.ClinicFlow.emptyState("No medications", "Add medicines to the catalogue.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((m) => `
        <tr>
          <td><b>${window.ClinicFlow.escapeHtml(m.name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(m.generic_name || "")}</div></td>
          <td class="mono">${window.ClinicFlow.escapeHtml(m.sku)}</td>
          <td>${m.stock ?? 0}</td>
          <td>${window.ClinicFlow.fmtMoney(m.unit_price)}</td>
          <td>${m.low_stock ? `<span class="badge warn">${window.ClinicFlow.icon("warning", 12)} Low</span>` : window.ClinicFlow.statusBadge(m.is_active ? "active" : "inactive")}</td>
        </tr>`).join("");
    };
    renderRows(medList);
    if ($("#pharm-dispense")) {
      $("#pharm-dispense").addEventListener("click", async () => {
        const res = await window.ClinicFlow.apiGet("/api/prescriptions");
        const prescriptions = Array.isArray(res) ? res : [];
        const modal = window.ClinicFlow.openModal({ title: "Dispense medicine", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field full"><span>Patient</span><input class="input" id="ph-patient" placeholder="Search patient or select prescription"/></label>
            <label class="field full"><span>Prescription</span><select class="select" id="ph-rx">${prescriptions.map((r) => `<option value="${r.id}">${window.ClinicFlow.escapeHtml(r.prescription_code)} · ${window.ClinicFlow.escapeHtml(r.patient ? r.patient.full_name : "")}</option>`).join("")}</select></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Dispense</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          const items = [{ medication_id: window.prompt("Medication ID to dispense", ""), quantity: Number(window.prompt("Quantity", "1")) }];
          const payload = {
            prescription_id: $("#ph-rx").value || null,
            patient_id: $("#ph-patient").value.trim() || null,
            items,
          };
          const res = await window.ClinicFlow.apiPost("/api/pharmacy/dispense", payload);
          window.ClinicFlow.toast("Dispensed", "ok");
          window.ClinicFlow.closeModal();
        });
      });
    }
  },
});
