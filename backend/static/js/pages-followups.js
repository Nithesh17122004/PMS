window.ClinicFlow.registerRoute("followups", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    let data = {};
    try { data = await window.ClinicFlow.apiGet("/api/followups/dashboard"); } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
    const d = data || {};
    const counts = d.counts || {};
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Follow-ups</div><div class="page-sub">Care plans and reminders</div></div>
        <button class="btn btn-accent" id="followup-new">${window.ClinicFlow.icon("plus", 16)} New follow-up</button>
      </div>
      <div class="grid cols-4">
        <div class="card stat-card"><div class="stat-icon"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("followups", 20)}</span></div><div><div class="stat-value">${counts.today || 0}</div><div class="stat-label">Due today</div></div></div>
        <div class="card stat-card"><div class="stat-icon teal"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("activity", 20)}</span></div><div><div class="stat-value">${counts.upcoming || 0}</div><div class="stat-label">Upcoming</div></div></div>
        <div class="card stat-card"><div class="stat-icon red"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("clock", 20)}</span></div><div><div class="stat-value">${counts.overdue || 0}</div><div class="stat-label">Overdue</div></div></div>
        <div class="card stat-card"><div class="stat-icon violet"><span class="icon-btn" style="border:0;background:transparent">${window.ClinicFlow.icon("check", 20)}</span></div><div><div class="stat-value">${counts.completed || 0}</div><div class="stat-label">Completed</div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Follow-up plans</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Patient</th><th>Doctor</th><th>Due</th><th>Status</th><th></th></tr></thead><tbody id="followup-tbody"></tbody></table></div></div>
    `;
    const load = async () => {
      try {
        const res = await window.ClinicFlow.apiGet("/api/followups");
        return res || [];
      } catch (e) { window.ClinicFlow.toast(e.message, "error"); return []; }
    };
    const renderRows = (rows) => {
      const tbody = $("#followup-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="5">${window.ClinicFlow.emptyState("No follow-ups", "Create a follow-up plan.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((f) => `
        <tr>
          <td>${window.ClinicFlow.escapeHtml(f.patient ? f.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.escapeHtml(f.doctor ? f.doctor.full_name : "")}</td>
          <td class="nowrap">${window.ClinicFlow.fmtDate(f.due_date)}</td>
          <td>${window.ClinicFlow.statusBadge(f.status)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${f.id}">Manage</button></td>
        </tr>`).join("");
    };
    const run = async () => renderRows(await load());
    await run();
    $("#followup-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      await window.ClinicFlow.navigate("#/followups/" + id);
    });
    $("#followup-new").addEventListener("click", async () => {
      const res = await window.ClinicFlow.apiGet("/api/doctors").catch(() => []);
      const doctors = Array.isArray(res) ? res : (res.doctors || []);
      const modal = window.ClinicFlow.openModal({ title: "New follow-up", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="form-grid">
          <label class="field full"><span>Patient</span><input class="input" id="fu-patient" placeholder="Search patient"/></label>
          <label class="field"><span>Doctor</span><select class="select" id="fu-doctor">${doctors.map((d) => `<option value="${d.id}">${window.ClinicFlow.escapeHtml(d.full_name)}</option>`).join("")}</select></label>
          <label class="field"><span>Due date</span><input class="input" type="date" id="fu-due"/></label>
          <label class="field full"><span>Instructions</span><textarea class="input" id="fu-instructions"></textarea></label>
        </div>`;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
        const patientTerm = $("#fu-patient").value.trim();
        let patientId = null;
        if (patientTerm) {
          const searchRes = await window.ClinicFlow.apiPost("/api/patients/search", { query: patientTerm, limit: 5 });
          const found = searchRes.patients && searchRes.patients[0];
          if (found) patientId = found.id;
        }
        if (!patientId) { window.ClinicFlow.toast("Select a valid patient.", "error"); return; }
        const payload = {
          patient_id: patientId, doctor_id: $("#fu-doctor").value, due_date: $("#fu-due").value,
          instructions: $("#fu-instructions").value, priority: "normal",
        };
        await window.ClinicFlow.apiPost("/api/followups", payload);
        window.ClinicFlow.closeModal();
        await run();
      });
    });
  },
});

window.ClinicFlow.registerRoute("followup", {
  async render(params) {
    const host = document.querySelector("#page-content");
    const id = params.id;
    const data = await window.ClinicFlow.apiGet("/api/followups/" + id);
    const f = data.followup || {};
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Follow-up ${window.ClinicFlow.escapeHtml(f.id || "")}</div><div class="page-sub">${window.ClinicFlow.escapeHtml(f.patient ? f.patient.full_name : "")} · due ${window.ClinicFlow.fmtDate(f.due_date)}</div></div>
        <div class="row">
          <button class="btn" data-back>Back</button>
          <button class="btn" id="fu-arrive">Patient arrived</button>
          <button class="btn" id="fu-complete">Complete</button>
        </div>
      </div>
      <div class="card"><div class="card-body"><dl class="kv"><dt>Status</dt><dd>${window.ClinicFlow.statusBadge(f.status)}</dd><dt>Instructions</dt><dd>${window.ClinicFlow.escapeHtml(f.instructions || "—")}</dd></dl></div></div>
    `;
    if (host.querySelector("[data-back]")) host.querySelector("[data-back]").addEventListener("click", () => window.ClinicFlow.navigate("#/followups"));
    if (host.querySelector("#fu-arrive")) host.querySelector("#fu-arrive").addEventListener("click", async () => {
      const res = await window.ClinicFlow.apiPost("/api/followups/" + id + "/arrive");
      window.ClinicFlow.toast("Follow-up arrived — token generated", "ok");
      window.ClinicFlow.navigate("#/queue");
    });
    if (host.querySelector("#fu-complete")) host.querySelector("#fu-complete").addEventListener("click", async () => {
      await window.ClinicFlow.apiPost("/api/followups/" + id + "/complete");
      window.ClinicFlow.toast("Follow-up completed", "ok");
      await window.ClinicFlow.navigate("#/followups");
    });
  },
});
