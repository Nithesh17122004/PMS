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
        ${window.ClinicFlow.state.user.doctor_id && (window.ClinicFlow.state.user.permissions || []).includes("consultations.create") ? '<button class="btn btn-accent" id="consult-new">' + window.ClinicFlow.icon("plus", 16) + ' New consultation</button>' : ""}
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
      await window.ClinicFlow.navigate("#/consultation/" + btn.getAttribute("data-view"));
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
            <div id="cn-patient-results" class="field full"></div>
            <label class="field"><span>Doctor</span><select class="select" id="cn-doctor">${doctors.map((d) => `<option value="${d.id}">${window.ClinicFlow.escapeHtml(d.full_name)}</option>`).join("")}</select></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        window.ClinicFlow.bindPatientCodePicker(body.querySelector("#cn-patient"), body.querySelector("#cn-patient-results"));
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create draft</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
          const patientId = modal.querySelector("#cn-patient").dataset.patientId;
          if (!patientId) { window.ClinicFlow.toast("Search and select a patient by code or name.", "error"); return; }
          const result = await window.ClinicFlow.apiPost("/api/consultations", { patient_id: patientId, doctor_id: $("#cn-doctor").value });
          window.ClinicFlow.closeModal();
          // Keep the user on the consultation editor after saving.
          window.ClinicFlow.toast("Consultation draft created", "ok");
          await window.ClinicFlow.navigate("#/consultation/" + result.consultation.id);
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
    const currentUser = window.ClinicFlow.state.user || {};
    const canEdit = c.status === "draft" && !!currentUser.doctor_id && c.doctor && currentUser.doctor_id === c.doctor.id;
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Consultation ${window.ClinicFlow.escapeHtml(c.consultation_code || "")}</div><div class="page-sub">${window.ClinicFlow.escapeHtml(c.patient ? c.patient.full_name : "")} · ${window.ClinicFlow.statusBadge(c.status)}</div></div>
        <div class="row"><button class="btn" data-back>Back</button>${(window.ClinicFlow.state.user.permissions || []).includes("billing.create") ? '<button class="btn" id="consult-invoice">Invoice</button>' : ""}</div>
      </div>
      <div class="card"><div class="card-body"><div id="consult-form"></div></div></div>
    `;
    if (host.querySelector("[data-back]")) host.querySelector("[data-back]").addEventListener("click", () => window.ClinicFlow.navigate("#/consultations"));
    const form = $("#consult-form");
    form.innerHTML = `
      <div class="form-grid">
        <label class="field full"><span>Symptoms</span><textarea class="input" id="cf-symptoms">${window.ClinicFlow.escapeHtml(c.symptoms || "")}</textarea></label>
        <label class="field full"><span>Observations / examination</span><textarea class="input" id="cf-observations">${window.ClinicFlow.escapeHtml(c.observations || "")}</textarea></label>
        <label class="field"><span>Vitals (blood_pressure, pulse, temperature, weight_kg, height_cm, spo2, respiratory_rate)</span><textarea class="input" id="cf-vitals" placeholder='{"blood_pressure":"120/80"}'>${window.ClinicFlow.escapeHtml(JSON.stringify(c.vitals || {}, null, 2))}</textarea></label>
        <label class="field"><span>Diagnosis summary</span><textarea class="input" id="cf-diagnosis">${window.ClinicFlow.escapeHtml(c.diagnosis_summary || "")}</textarea></label>
        <label class="field full"><span>Treatment plan</span><textarea class="input" id="cf-treatment">${window.ClinicFlow.escapeHtml(c.treatment_plan || "")}</textarea></label>
        <label class="field full"><span>Doctor notes</span><textarea class="input" id="cf-notes">${window.ClinicFlow.escapeHtml(c.doctor_notes || "")}</textarea></label>
        <label class="checkbox-row"><input type="checkbox" id="cf-followup" ${c.follow_up_required ? "checked" : ""}/> Follow-up required</label>
        <label class="field"><span>Follow-up date</span><input class="input" type="date" id="cf-followup-date"/></label>
        <label class="field"><span>Follow-up priority</span><select class="select" id="cf-followup-priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
        <label class="field full"><span>Diagnoses (ICD codes)</span><textarea class="input" id="cf-icd" placeholder='[{"icd_code":"J06.9","description":"Acute URI","diagnosis_type":"primary"}]'>${window.ClinicFlow.escapeHtml(JSON.stringify(c.diagnoses || [], null, 2))}</textarea></label>
      </div>
      ${canEdit ? '<div class="row mt16"><button class="btn" id="consult-save">Save draft</button><button class="btn btn-primary" id="consult-complete-btn">Complete</button></div>' : '<div class="muted small mt16">This consultation is read-only because it is completed or belongs to another doctor.</div>'}
    `;
    if (!canEdit) form.querySelectorAll("textarea, input, select").forEach((field) => { field.disabled = true; });
    const previousConsultations = (data.consultation.previous_consultations || []);
    if (previousConsultations.length) {
      const previousPanel = document.createElement("div");
      previousPanel.className = "card mt16";
      previousPanel.innerHTML = '<div class="card-header"><div class="card-title">Previous consultations</div></div><div class="card-body">' +
        previousConsultations.map((item) => '<div class="row between mb8"><div><b>' + window.ClinicFlow.escapeHtml(item.consultation_code) +
        '</b><div class="muted small">' + window.ClinicFlow.fmtDateTime(item.completed_at) + ' · ' +
        window.ClinicFlow.escapeHtml(item.diagnosis_summary || "No diagnosis recorded") + '</div></div>' +
        window.ClinicFlow.statusBadge(item.status) + '</div>').join("") + '</div>';
      host.appendChild(previousPanel);
    }
    const collectPayload = () => {
      let diagnoses;
      let vitals;
      try { diagnoses = JSON.parse($("#cf-icd").value || "[]"); }
      catch (error) { throw new Error("Diagnoses must be valid JSON."); }
      if (!Array.isArray(diagnoses)) throw new Error("Diagnoses must be a JSON list.");
      try { vitals = JSON.parse($("#cf-vitals").value || "{}"); }
      catch (error) { throw new Error("Vitals must be valid JSON."); }
      if (!vitals || typeof vitals !== "object" || Array.isArray(vitals)) throw new Error("Vitals must be a JSON object.");
      const followUp = $("#cf-followup").checked;
      const followUpDate = $("#cf-followup-date").value;
      return {
        symptoms: $("#cf-symptoms").value,
        observations: $("#cf-observations").value,
        vitals,
        diagnosis_summary: $("#cf-diagnosis").value,
        treatment_plan: $("#cf-treatment").value,
        doctor_notes: $("#cf-notes").value,
        diagnoses,
        follow_up_required: followUp,
        follow_up_date: followUpDate,
        follow_up_instructions: $("#cf-treatment").value,
        follow_up_priority: $("#cf-followup-priority").value,
      };
    };
    const save = async () => {
      try {
        await window.ClinicFlow.apiPut("/api/consultations/" + id, collectPayload());
        window.ClinicFlow.toast("Draft saved.", "ok");
      } catch (error) {
        window.ClinicFlow.toast(error.message || "Draft could not be saved.", "error");
      }
    };
    if (canEdit && host.querySelector("#consult-save")) host.querySelector("#consult-save").addEventListener("click", save);
    if (canEdit && host.querySelector("#consult-complete-btn")) host.querySelector("#consult-complete-btn").addEventListener("click", async () => {
      const button = host.querySelector("#consult-complete-btn");
      button.disabled = true;
      try {
        if ($("#cf-followup").checked && !$("#cf-followup-date").value) throw new Error("Select a follow-up date before completing.");
        const result = await window.ClinicFlow.apiPost("/api/consultations/" + id + "/complete", collectPayload());
        window.ClinicFlow.toast("Consultation completed.", "ok");
        await window.ClinicFlow.navigate("#/consultation/" + result.consultation.id);
      } catch (error) {
        window.ClinicFlow.toast(error.message || "Consultation could not be completed.", "error");
      } finally { if (button.isConnected) button.disabled = false; }
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

    });
  },
});
