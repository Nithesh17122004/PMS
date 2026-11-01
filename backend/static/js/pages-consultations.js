window.ClinicFlow.registerRoute("consultations", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    let list = [];
    try { list = await window.ClinicFlow.apiGet("/api/consultations"); } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
    const rows = list || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Consultations</div><div class="page-sub">Clinical encounters</div></div>
        <button class="btn btn-accent" id="consult-new">${window.ClinicFlow.icon("plus", 16)} New consultation</button>
      </div>
      <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>Code</th><th>Patient</th><th>Doctor</th><th>Status</th><th>Started</th><th></th></tr></thead><tbody id="consult-tbody"></tbody></table></div></div>
    `;
    const renderRows = (items) => {
      const tbody = $("#consult-tbody");
      if (!items || !items.length) { tbody.innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No consultations", "Encounter records will appear here.")}</td></tr>`; return; }
      tbody.innerHTML = items.map((c) => `
        <tr>
          <td class="mono">${window.ClinicFlow.escapeHtml(c.consultation_code)}</td>
          <td>${window.ClinicFlow.escapeHtml(c.patient ? c.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.escapeHtml(c.doctor ? c.doctor.full_name : "")}</td>
          <td>${window.ClinicFlow.statusBadge(c.status)}</td>
          <td class="muted nowrap">${window.ClinicFlow.fmtDateTime(c.started_at)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${c.id}">Open</button></td>
        </tr>`).join("");
    };
    renderRows(rows);
    $("#consult-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      await window.ClinicFlow.navigate("#/consultations/" + btn.getAttribute("data-view"));
    });
    if ($("#consult-new")) {
      $("#consult-new").addEventListener("click", async () => {
        const doctorsRes = await window.ClinicFlow.apiGet("/api/doctors").catch(() => []);
        const doctors = Array.isArray(doctorsRes) ? doctorsRes : (doctorsRes.doctors || []);
        const modal = window.ClinicFlow.openModal({ title: "New consultation", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field full"><span>Patient</span><input class="input" id="cn-patient" placeholder="Search patient"/></label>
            <label class="field"><span>Doctor</span><select class="select" id="cn-doctor">${doctors.map((d) => `<option value="${d.id}">${window.ClinicFlow.escapeHtml(d.full_name)}</option>`).join("")}</select></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create draft</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          const patientTerm = $("#cn-patient").value.trim();
          let patientId = null;
          if (patientTerm) {
            const searchRes = await window.ClinicFlow.apiPost("/api/patients/search", { query: patientTerm, limit: 5 });
            const found = searchRes.patients && searchRes.patients[0];
            if (found) patientId = found.id;
          }
          if (!patientId) { window.ClinicFlow.toast("Select a valid patient.", "error"); return; }
          await window.ClinicFlow.apiPost("/api/consultations", { patient_id: patientId, doctor_id: $("#cn-doctor").value });
          window.ClinicFlow.closeModal();
          window.ClinicFlow.toast("Consultation draft created", "ok");
        });
      });
    }
  },
});

window.ClinicFlow.registerRoute("consultation", {
  async render(params) {
    const host = document.querySelector("#page-content");
    const id = params.id;
    const data = await window.ClinicFlow.apiGet("/api/consultations/" + id);
    const c = data.consultation || {};
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Consultation ${window.ClinicFlow.escapeHtml(c.consultation_code || "")}</div><div class="page-sub">${window.ClinicFlow.escapeHtml(c.patient ? c.patient.full_name : "")} · ${window.ClinicFlow.statusBadge(c.status)}</div></div>
        <div class="row"><button class="btn" data-back>Back</button><button class="btn btn-accent" id="consult-complete">Complete</button><button class="btn" id="consult-invoice">Invoice</button></div>
      </div>
      <div class="card"><div class="card-body"><div id="consult-form"></div></div></div>
    `;
    if (host.querySelector("[data-back]")) host.querySelector("[data-back]").addEventListener("click", () => window.ClinicFlow.navigate("#/consultations"));
    const form = $("#consult-form");
    form.innerHTML = `
      <div class="form-grid">
        <label class="field full"><span>Symptoms</span><textarea class="input" id="cf-symptoms">${window.ClinicFlow.escapeHtml(c.symptoms || "")}</textarea></label>
        <label class="field"><span>Vitals (blood_pressure, pulse, temperature, weight_kg, height_cm, spo2, respiratory_rate)</span><textarea class="input" id="cf-vitals" placeholder='{"blood_pressure":"120/80"}'></textarea></label>
        <label class="field"><span>Diagnosis summary</span><input class="input" id="cf-diagnosis"/></label>
        <label class="field full"><span>Treatment plan</span><textarea class="input" id="cf-treatment"></textarea></label>
        <label class="field full"><span>Doctor notes</span><textarea class="input" id="cf-notes"></textarea></label>
        <label class="checkbox-row"><input type="checkbox" id="cf-followup" ${c.follow_up_required ? "checked" : ""}/> Follow-up required</label>
        <label class="field"><span>Follow-up date</span><input class="input" type="date" id="cf-followup-date"/></label>
        <label class="field"><span>Follow-up priority</span><select class="select" id="cf-followup-priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
        <label class="field full"><span>Diagnoses (ICD codes)</span><textarea class="input" id="cf-icd" placeholder='[{"icd_code":"J06.9","description":"Acute URI","diagnosis_type":"primary"}]'></textarea></label>
      </div>
      <div class="row mt16">
        <button class="btn" id="consult-save">Save draft</button>
        <button class="btn btn-primary" id="consult-complete-btn">Complete</button>
      </div>
    `;
    const save = async () => {
      const payload = {
        symptoms: $("#cf-symptoms").value,
        diagnosis_summary: $("#cf-diagnosis").value,
        treatment_plan: $("#cf-treatment").value,
        doctor_notes: $("#cf-notes").value,
        follow_up_required: $("#cf-followup").checked,
        follow_up_date: $("#cf-followup-date").value,
        follow_up_instructions: $("#cf-treatment").value,
        follow_up_priority: $("#cf-followup-priority").value,
      };
      let diagnoses = [];
      try { diagnoses = JSON.parse($("#cf-icd").value || "[]"); } catch (e) { diagnoses = []; }
      payload.diagnoses = diagnoses;
      const vitals = {};
      try { const parsed = JSON.parse($("#cf-vitals").value || "{}"); Object.assign(vitals, parsed); } catch (e) {}
      if (Object.keys(vitals).length) payload.vitals = vitals;
      await window.ClinicFlow.apiPut("/api/consultations/" + id, payload);
      window.ClinicFlow.toast("Draft saved", "ok");
      window.ClinicFlow.closeModal();
    };
    if (host.querySelector("#consult-save")) host.querySelector("#consult-save").addEventListener("click", save);
    if (host.querySelector("#consult-complete-btn")) host.querySelector("#consult-complete-btn").addEventListener("click", async () => {
      const payload = {
        diagnosis_summary: $("#cf-diagnosis").value,
        treatment_plan: $("#cf-treatment").value,
        follow_up_required: $("#cf-followup").checked,
        follow_up_date: $("#cf-followup-date").value,
        follow_up_instructions: $("#cf-treatment").value,
        follow_up_priority: $("#cf-followup-priority").value,
      };
      const res = await window.ClinicFlow.apiPost("/api/consultations/" + id + "/complete", payload);
      window.ClinicFlow.toast("Consultation completed", "ok");
      await window.ClinicFlow.navigate("#/consultations/" + res.consultation.id);
    });
    if (host.querySelector("#consult-invoice")) host.querySelector("#consult-invoice").addEventListener("click", async () => {
      const res = await window.ClinicFlow.apiPost("/api/consultations/" + id + "/invoice");
      window.ClinicFlow.toast("Invoice created", "ok");
    });
  },
});

window.ClinicFlow.registerRoute("prescriptions", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const list = await window.ClinicFlow.apiGet("/api/prescriptions");
    const rows = list || [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Prescriptions</div><div class="page-sub">Medication records</div></div>
      </div>
      <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>Code</th><th>Patient</th><th>Doctor</th><th>Items</th><th>Status</th><th></th></tr></thead><tbody id="rx-tbody"></tbody></table></div></div>
    `;
    const renderRows = (items) => {
      const tbody = $("#rx-tbody");
      if (!items || !items.length) { tbody.innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No prescriptions", "Issue prescriptions from completed consultations.")}</td></tr>`; return; }
      tbody.innerHTML = items.map((r) => `
        <tr>
          <td class="mono">${window.ClinicFlow.escapeHtml(r.prescription_code)}</td>
          <td>${window.ClinicFlow.escapeHtml(r.patient ? r.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.escapeHtml(r.doctor ? r.doctor.full_name : "")}</td>
          <td>${r.item_count ?? 0}</td>
          <td>${window.ClinicFlow.statusBadge(r.status)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${r.id}">Open</button></td>
        </tr>`).join("");
    };
    renderRows(rows);
    $("#rx-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      const res = await window.ClinicFlow.apiGet("/api/prescriptions/" + id);
      const r = res.prescription || {};
      const modal = window.ClinicFlow.openModal({ title: "Prescription " + window.ClinicFlow.escapeHtml(r.prescription_code || ""), wide: true });
      const body = document.createElement("div");
      const items = r.items || [];
      body.innerHTML = items.length ? items.map((i) => `<div class="row mb8"><div class="grow"><b>${window.ClinicFlow.escapeHtml(i.medicine_name)}</b> ${window.ClinicFlow.escapeHtml(i.strength || "")} ${window.ClinicFlow.escapeHtml(i.form || "")}</div><div class="muted small">${window.ClinicFlow.escapeHtml(i.dosage)} · ${window.ClinicFlow.escapeHtml(i.frequency)} · ${i.duration_days ? i.duration_days + " days" : ""}</div></div>`).join("") : '<div class="empty-state"><div class="empty-title">No items</div></div>';
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><a class="btn btn-primary" href="/api/prescriptions/' + id + '/pdf" target="_blank">Download PDF</a>';
      modal.querySelector(".modal-footer").appendChild(footer);
      modal.querySelector("[data-modal-cancel]").addEventListener("click", () => window.ClinicFlow.closeModal());
    });
  },
});
