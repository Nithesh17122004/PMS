window.ClinicFlow.registerRoute("appointments", {
  async render(params) {
    const host = document.querySelector("#page-content");
    const state = window.ClinicFlow.state;
    const me = state.user;
    const canEdit = me.permissions.includes("appointments.edit");
    const canCancel = me.permissions.includes("appointments.cancel");
    const canCreate = me.permissions.includes("appointments.create");
    const canOverride = me.permissions.includes("appointments.override");
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Appointments</div><div class="page-sub">Scheduling and visits</div></div>
        ${canCreate ? '<button class="btn btn-accent" id="appt-new">' + window.ClinicFlow.icon("plus", 16) + " Book appointment</button>" : ""}
      </div>
      <div class="card">
        <div class="toolbar">
          <input class="input" type="date" id="appt-date" style="width:auto" />
          <select class="select" id="appt-doctor"><option value="">All doctors</option></select>
          <select class="select" id="appt-status"><option value="">All statuses</option><option value="scheduled">Scheduled</option><option value="confirmed">Confirmed</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select>
          <button class="btn" id="appt-refresh">Refresh</button>
        </div>
        <div class="table-wrap"><table class="table"><thead><tr><th>Code</th><th>Patient</th><th>Doctor</th><th>Date</th><th>Time</th><th>Status</th><th></th></tr></thead><tbody id="appt-tbody"></tbody></table></div>
      </div>
    `;
    const load = async () => {
      try {
        const q = new URLSearchParams(window.ClinicFlow.doctorQuery());
        const res = await window.ClinicFlow.apiGet("/api/appointments?" + q.toString());
        return res || [];
      } catch (e) { window.ClinicFlow.toast(e.message, "error"); return []; }
    };
    const renderRows = (rows) => {
      const tbody = $("#appt-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="7">${window.ClinicFlow.emptyState("No appointments found", "Adjust the filters.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((a) => `
        <tr>
          <td class="mono">${window.ClinicFlow.escapeHtml(a.appointment_code)}</td>
          <td>${window.ClinicFlow.escapeHtml(a.patient ? a.patient.full_name : "")}</td>
          <td>${window.ClinicFlow.escapeHtml(a.doctor ? a.doctor.full_name : "")}</td>
          <td>${window.ClinicFlow.fmtDate(a.appointment_date)}</td>
          <td class="nowrap">${window.ClinicFlow.fmtTime(a.start_time)} – ${window.ClinicFlow.fmtTime(a.end_time)}</td>
          <td>${window.ClinicFlow.statusBadge(a.status)}</td>
          <td class="right nowrap">
            ${a.token ? `<button class="btn btn-sm" data-token="${a.token.id}">Token ${a.token.display_number}</button>` : ""}
            ${canEdit ? `<button class="btn btn-sm" data-resched="${a.id}">Reschedule</button>` : ""}
            ${canEdit ? `<button class="btn btn-sm" data-checkin="${a.id}">Check in</button>` : ""}
            ${canCancel ? `<button class="btn btn-sm btn-danger" data-cancel="${a.id}">Cancel</button>` : ""}
          </td>
        </tr>`).join("");
    };
    const run = async () => {
      const rows = await load();
      renderRows(rows);
    };
    const doctorSelect = $("#appt-doctor");
    const statusSelect = $("#appt-status");
    const dateInputEl = $("#appt-date");
    if (doctorSelect) doctorSelect.addEventListener("change", run);
    if (statusSelect) statusSelect.addEventListener("change", run);
    if (dateInputEl) dateInputEl.addEventListener("change", run);
    $("#appt-refresh").addEventListener("click", run);
    await run();
    let doctors = [];
    try { doctors = await window.ClinicFlow.apiGet("/api/doctors"); } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
    const doctorList = Array.isArray(doctors) ? doctors : (doctors.doctors || []);
    doctorSelect.innerHTML = '<option value="">All doctors</option>' + doctorList.map((d) => `<option value="${d.id}">${window.ClinicFlow.escapeHtml(d.full_name)}</option>`).join("");
    await run();

    $("#appt-new").addEventListener("click", async () => {
      const doctorsRes = await window.ClinicFlow.apiGet("/api/doctors");
      const doctorList = (Array.isArray(doctorsRes) ? doctorsRes : (doctorsRes.doctors || [])).filter((d) => d.is_active);
      const modal = window.ClinicFlow.openModal({ title: "Book appointment", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="form-grid">
          <label class="field full"><span>Patient</span><input class="input" id="appt-patient" placeholder="Search and select a patient"/></label>
          <div id="appt-patient-results" class="field full"></div>
          <label class="field full"><span>Doctor</span><select class="select" id="appt-doctor-sel">${doctorList.map((d) => `<option value="${d.id}">${window.ClinicFlow.escapeHtml(d.full_name)}</option>`).join("")}</select></label>
          <label class="field"><span>Date</span><input class="input" type="date" id="appt-date-sel"/></label>
          <label class="field"><span>Start time</span><input class="input" type="time" id="appt-start-sel"/></label>
        </div>`;
      modal.querySelector(".modal-body").appendChild(body);
      window.ClinicFlow.bindPatientCodePicker(body.querySelector("#appt-patient"), body.querySelector("#appt-patient-results"));
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Book</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
        const patientId = modal.querySelector("#appt-patient").dataset.patientId;
        if (!patientId) { window.ClinicFlow.toast("Search and select a patient by code or name before booking.", "error"); return; }
        const payload = {
          patient_id: patientId,
          doctor_id: $("#appt-doctor-sel").value,
          appointment_date: $("#appt-date-sel").value,
          start_time: $("#appt-start-sel").value,
          visit_type: "consultation",
        };
        const res = await window.ClinicFlow.apiPost("/api/appointments", payload);
        window.ClinicFlow.toast("Appointment booked", "ok");
        window.ClinicFlow.closeModal();
        await run();
      });
    });
    $("#appt-tbody").addEventListener("click", async (e) => {
      const resched = e.target.closest("[data-resched]");
      const checkin = e.target.closest("[data-checkin]");
      const cancel = e.target.closest("[data-cancel]");
      const tokenBtn = e.target.closest("[data-token]");
      if (cancel) {
        const id = cancel.getAttribute("data-cancel");
        window.ClinicFlow.confirmDialog("Cancel this appointment?", async () => {
          const res = await window.ClinicFlow.apiPost("/api/appointments/" + id + "/cancel", { reason: "Cancelled from console" });
          window.ClinicFlow.toast("Appointment cancelled", "ok");
          await run();
        });
        return;
      }
      if (checkin) {
        const id = checkin.getAttribute("data-checkin");
        const res = await window.ClinicFlow.apiPost("/api/appointments/" + id + "/check-in");
        window.ClinicFlow.toast("Checked in — token generated", "ok");
        await run();
        return;
      }
      if (resched) {
        const id = resched.getAttribute("data-resched");
        const res = await window.ClinicFlow.apiGet("/api/appointments/" + id);
        const appt = res.appointment;
        const modal = window.ClinicFlow.openModal({ title: "Reschedule appointment", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field"><span>New date</span><input class="input" type="date" id="appt-new-date" value="${appt.appointment_date || ""}"/></label>
            <label class="field"><span>New start time</span><input class="input" type="time" id="appt-new-start" value="${(appt.start_time || "").slice(0, 5)}"/></label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Reschedule</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
          await window.ClinicFlow.apiPost("/api/appointments/" + id + "/reschedule", {
            appointment_date: $("#appt-new-date").value,
            start_time: $("#appt-new-start").value,
          });
          window.ClinicFlow.closeModal();
          await run();
        });
      }
      if (tokenBtn) {
        const id = tokenBtn.getAttribute("data-token");
        window.ClinicFlow.navigate("#/queue");
      }
    });
  },
});
