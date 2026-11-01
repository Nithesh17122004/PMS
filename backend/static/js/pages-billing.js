window.ClinicFlow.registerRoute("billing", {
  async render(params) {
    const host = document.querySelector("#page-content");
    if (params && params.id) {
      const res = await window.ClinicFlow.apiGet("/api/invoices/" + params.id);
      const inv = res.invoice || {};
      host.innerHTML = `
        <div class="page-head">
          <div><div class="page-title">Invoice ${window.ClinicFlow.escapeHtml(inv.invoice_number || "")}</div><div class="page-sub">${window.ClinicFlow.escapeHtml(inv.patient ? inv.patient.full_name : "")}</div></div>
          <div class="row"><button class="btn" data-back>Back</button><a class="btn btn-primary" href="/api/invoices/${params.id}/pdf" target="_blank">Download PDF</a></div>
        </div>
        <div class="card"><div class="card-body">
          <div class="grid cols-3">
            <div><div class="muted small">Status</div><div>${window.ClinicFlow.statusBadge(inv.status)}</div></div>
            <div><div class="muted small">Total</div><b>${window.ClinicFlow.fmtMoney(inv.total)}</b></div>
            <div><div class="muted small">Balance</div><b>${window.ClinicFlow.fmtMoney(inv.balance)}</b></div>
          </div>
          <div class="divider"></div>
          <div class="muted small">Items</div>
          ${(inv.items || []).map((i) => `<div class="row between mb8"><span>${window.ClinicFlow.escapeHtml(i.description)}</span><span class="muted">${i.quantity} × ${window.ClinicFlow.fmtMoney(i.unit_price)}</span></div>`).join("") || '<div class="empty-state"><div class="empty-title">No items</div></div>'}
        </div></div>
      `;
      const back = host.querySelector("[data-back]");
      if (back) back.addEventListener("click", () => window.ClinicFlow.navigate("#/billing"));
      return;
    }
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const summary = await window.ClinicFlow.apiGet("/api/billing/summary");
    const invoices = await window.ClinicFlow.apiGet("/api/invoices");
    const rows = invoices || [];
    const sum = summary || {};
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Billing</div><div class="page-sub">Invoices, payments and refunds</div></div>
        <button class="btn btn-accent" id="invoice-new">${window.ClinicFlow.icon("plus", 16)} New invoice</button>
      </div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("billing", 20)}</span></div><div><div class="stat-value">${window.ClinicFlow.fmtMoney(sum.gross || 0)}</div><div class="stat-label">Gross · ${sum.range ? sum.range.start + " → " + sum.range.end : ""}</div></div></div>
        <div class="card stat-card"><div class="stat-icon teal"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("check", 20)}</span></div><div><div class="stat-value">${window.ClinicFlow.fmtMoney(sum.net || 0)}</div><div class="stat-label">Net revenue</div></div></div>
        <div class="card stat-card"><div class="stat-icon red"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("activity", 20)}</span></div><div><div class="stat-value">${window.ClinicFlow.fmtMoney(sum.outstanding || 0)}</div><div class="stat-label">Outstanding</div></div></div>
        <div class="card stat-card"><div class="stat-icon amber"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("billing", 20)}</span></div><div><div class="stat-value">${sum.payment_count ?? 0}</div><div class="stat-label">Payments</div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Invoices</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Number</th><th>Patient</th><th>Total</th><th>Balance</th><th>Status</th><th></th></tr></thead><tbody id="invoice-tbody"></tbody></table></div></div>
    `;
    const renderRows = (rows) => {
      const tbody = $("#invoice-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No invoices", "Create an invoice to start billing.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((inv) => `
        <tr>
          <td class="mono">${window.ClinicFlow.escapeHtml(inv.invoice_number)}</td>
          <td>${window.ClinicFlow.escapeHtml(inv.patient ? inv.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.fmtMoney(inv.total)}</td>
          <td>${window.ClinicFlow.fmtMoney(inv.balance)}</td>
          <td>${window.ClinicFlow.statusBadge(inv.status)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${inv.id}">Open</button></td>
        </tr>`).join("");
    };
    renderRows(rows);
    $("#invoice-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      const res = await window.ClinicFlow.apiGet("/api/invoices/" + id);
      const inv = res.invoice || {};
      const modal = window.ClinicFlow.openModal({ title: "Invoice " + window.ClinicFlow.escapeHtml(inv.invoice_number || ""), wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="grid cols-2">
          <div><div class="muted small">Patient</div><b>${window.ClinicFlow.escapeHtml(inv.patient ? inv.patient.full_name : "")}</b></div>
          <div><div class="muted small">Status</div><div>${window.ClinicFlow.statusBadge(inv.status)}</div></div>
          <div><div class="muted small">Subtotal</div><b>${window.ClinicFlow.fmtMoney(inv.subtotal)}</b></div>
          <div><div class="muted small">Tax</div><b>${window.ClinicFlow.fmtMoney(inv.tax_amount)}</b></div>
          <div><div class="muted small">Total</div><b>${window.ClinicFlow.fmtMoney(inv.total)}</b></div>
          <div><div class="muted small">Balance</div><b>${window.ClinicFlow.fmtMoney(inv.balance)}</b></div>
        </div>
        <div class="divider"></div>
        <div class="muted small">Items</div>
        ${(inv.items || []).map((i) => `<div class="row between mb8"><span>${window.ClinicFlow.escapeHtml(i.description)}</span><span class="muted">${i.quantity} × ${window.ClinicFlow.fmtMoney(i.unit_price)}</span></div>`).join("") || '<div class="empty-state"><div class="empty-title">No items</div></div>'}
        <div class="row mt16">
          <button class="btn" id="inv-pay">Record payment</button>
          <button class="btn" id="inv-refund">Refund</button>
          <a class="btn btn-primary" href="/api/invoices/" + id + "/pdf" target="_blank">PDF</a>
        </div>
      `;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Close</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      modal.querySelector("[data-modal-cancel]").addEventListener("click", () => window.ClinicFlow.closeModal());
      modal.querySelector("#inv-pay").addEventListener("click", async () => {
        const amount = window.prompt("Payment amount", String(inv.balance));
        if (!amount) return;
        await window.ClinicFlow.apiPost("/api/invoices/" + id + "/payments", { amount: Number(amount), method: "cash" });
        window.ClinicFlow.toast("Payment recorded", "ok");
        window.ClinicFlow.closeModal();
        window.ClinicFlow.navigate("#/billing");
      });
      modal.querySelector("#inv-refund").addEventListener("click", async () => {
        const paymentId = window.prompt("Payment ID to refund");
        if (!paymentId) return;
        const amount = window.prompt("Refund amount", "0");
        await window.ClinicFlow.apiPost("/api/invoices/" + id + "/refund", { payment_id: paymentId, amount: Number(amount), reason: "Customer request" });
        window.ClinicFlow.toast("Refund issued", "ok");
        window.ClinicFlow.closeModal();
        window.ClinicFlow.navigate("#/billing");
      });
    });
    if ($("#invoice-new")) {
      $("#invoice-new").addEventListener("click", async () => {
        const res = await window.ClinicFlow.apiGet("/api/patients");
        const patients = Array.isArray(res) ? res : [];
        const modal = window.ClinicFlow.openModal({ title: "New invoice", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field full"><span>Patient</span><select class="select" id="inv-patient">${patients.map((p) => `<option value="${p.id}">${window.ClinicFlow.escapeHtml(p.full_name)}</option>`).join("")}</select></label>
            <label class="field full"><span>Line items (one per line: description, quantity, unit_price)</span><textarea class="input" id="inv-items" placeholder='[{"description":"Consultation","quantity":1,"unit_price":500}]'></textarea></label>
            <label class="field"><span>Discount</span><input class="input" id="inv-discount" value="0"/></label>
            <label class="field"><span>Tax rate %</span><input class="input" id="inv-tax" value="0"/></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create invoice</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          let items = [];
          try { items = JSON.parse($("#inv-items").value || "[]"); } catch (e) { items = []; }
          const payload = {
            patient_id: $("#inv-patient").value,
            items: items.map((i) => ({ ...i, item_type: i.item_type || "service", unit_price: Number(i.unit_price || 0) })),
            discount_amount: Number($("#inv-discount").value || 0),
            tax_rate: Number($("#inv-tax").value || 0),
          };
          const res = await window.ClinicFlow.apiPost("/api/invoices", payload);
          window.ClinicFlow.toast("Invoice created", "ok");
          window.ClinicFlow.closeModal();
          await window.ClinicFlow.navigate("#/billing/" + res.invoice.id);
        });
      });
    }
  },
});
