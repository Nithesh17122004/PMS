window.ClinicFlow.registerRoute("doctors", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const list = await window.ClinicFlow.apiGet("/api/doctors").catch(() => []);
    const rows = Array.isArray(list) ? list : [];
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Doctors</div><div class="page-sub">Clinical staff and schedules</div></div>
        <button class="btn btn-accent" id="doctor-new">${window.ClinicFlow.icon("plus", 16)} Add doctor</button>
      </div>
      <div class="card"><div class="table-wrap"><table class="table"><thead><tr><th>Doctor</th><th>Specialty</th><th>Room</th><th>Fee</th><th>Today</th><th></th></tr></thead><tbody id="doctor-tbody"></tbody></table></div></div>
    `;
    const renderRows = (items) => {
      const tbody = $("#doctor-tbody");
      if (!items || !items.length) { tbody.innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No doctors", "Add a doctor profile.")}</td></tr>`; return; }
      tbody.innerHTML = items.map((d) => `
        <tr>
          <td><div class="row"><span class="avatar" style="background:${d.avatar_color || "#0e63b2"}">${window.ClinicFlow.initials(d.full_name)}</span><div><b>${window.ClinicFlow.escapeHtml(d.full_name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(d.doctor_code || "")}</div></div></div></td>
          <td>${window.ClinicFlow.escapeHtml(d.specialization)}</td>
          <td>${window.ClinicFlow.escapeHtml(d.room_number || "—")}</td>
          <td>${window.ClinicFlow.fmtMoney(d.consultation_fee)}</td>
          <td>${window.ClinicFlow.statusBadge(d.today_counts && d.today_counts.completed ? "completed" : d.today_counts && Object.keys(d.today_counts || {}).length ? "waiting" : "waiting")}</td>
          <td class="right"><button class="btn btn-sm" data-view="${d.id}">Manage</button></td>
        </tr>`).join("");
    };
    renderRows(rows);
    $("#doctor-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      const res = await window.ClinicFlow.apiGet("/api/doctors/" + id);
      const d = res.doctor || {};
      const modal = window.ClinicFlow.openModal({ title: "Doctor " + window.ClinicFlow.escapeHtml(d.full_name || ""), wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="grid cols-2">
          <div><div class="muted small">Specialty</div><b>${window.ClinicFlow.escapeHtml(d.specialization)}</b></div>
          <div><div class="muted small">Room</div><b>${window.ClinicFlow.escapeHtml(d.room_number || "—")}</b></div>
          <div><div class="muted small">Consultation fee</div><b>${window.ClinicFlow.fmtMoney(d.consultation_fee)}</b></div>
          <div><div class="muted small">Follow-up fee</div><b>${window.ClinicFlow.fmtMoney(d.follow_up_fee)}</b></div>
          <div><div class="muted small">Experience</div><b>${d.experience_years ?? 0} yrs</b></div>
          <div><div class="muted small">Available</div><b>${d.is_available ? "Yes" : "No"}</b></div>
        </div>
        <div class="divider"></div>
        <div class="row"><button class="btn" id="doctor-leave-new">Add leave</button><button class="btn" id="doctor-schedule-new">Add schedule</button><button class="btn" id="doctor-queue-link">Open queue</button></div>
      `;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Close</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      modal.querySelector("[data-modal-cancel]").addEventListener("click", () => window.ClinicFlow.closeModal());
      modal.querySelector("#doctor-leave-new").addEventListener("click", async () => {
        const modal2 = window.ClinicFlow.openModal({ title: "Add leave", wide: true });
        const body2 = document.createElement("div");
        body2.innerHTML = '<div class="form-grid"><label class="field"><span>Start</span><input class="input" type="date" id="dl-start"/></label><label class="field"><span>End</span><input class="input" type="date" id="dl-end"/></label><label class="field full"><span>Reason</span><input class="input" id="dl-reason"/></label></div>';
        modal2.querySelector(".modal-body").appendChild(body2);
        const footer2 = document.createElement("div");
        footer2.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Add leave</button>';
        modal2.querySelector(".modal-footer").appendChild(footer2);
        modal2.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          await window.ClinicFlow.apiPost("/api/doctors/" + id + "/leaves", { start_date: $("#dl-start").value, end_date: $("#dl-end").value, reason: $("#dl-reason").value });
          window.ClinicFlow.toast("Leave added", "ok");
          window.ClinicFlow.closeModal();
        });
      });
      modal.querySelector("#doctor-schedule-new").addEventListener("click", async () => {
        const modal2 = window.ClinicFlow.openModal({ title: "Add schedule", wide: true });
        const body2 = document.createElement("div");
        body2.innerHTML = '<div class="form-grid"><label class="field"><span>Weekday (0=Mon)</span><input class="input" type="number" id="ds-weekday" value="1"/></label><label class="field"><span>Start time</span><input class="input" type="time" id="ds-start"/></label><label class="field"><span>End time</span><input class="input" type="time" id="ds-end"/></label><label class="field"><span>Slot minutes</span><input class="input" type="number" id="ds-slot" value="15"/></label></div>';
        modal2.querySelector(".modal-body").appendChild(body2);
        const footer2 = document.createElement("div");
        footer2.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Add schedule</button>';
        modal2.querySelector(".modal-footer").appendChild(footer2);
        modal2.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          await window.ClinicFlow.apiPost("/api/doctors/" + id + "/schedules", { weekday: Number($("#ds-weekday").value), start_time: $("#ds-start").value, end_time: $("#ds-end").value, slot_minutes: Number($("#ds-slot").value) });
          window.ClinicFlow.toast("Schedule added", "ok");
          window.ClinicFlow.closeModal();
        });
      });
      modal.querySelector("#doctor-queue-link").addEventListener("click", () => window.ClinicFlow.navigate("#/queue"));
    });
    if ($("#doctor-new")) {
      $("#doctor-new").addEventListener("click", async () => {
        const modal = window.ClinicFlow.openModal({ title: "Add doctor" });
        const body = document.createElement("div");
        body.innerHTML = '<div class="form-grid"><label class="field full"><span>Full name</span><input class="input" id="doc-name"/></label><label class="field full"><span>Specialization</span><input class="input" id="doc-spec"/></label></div>';
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Add doctor</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          await window.ClinicFlow.apiPost("/api/doctors", { full_name: $("#doc-name").value, specialization: $("#doc-spec").value });
          window.ClinicFlow.toast("Doctor added", "ok");
          window.ClinicFlow.closeModal();
          window.ClinicFlow.navigate("#/doctors");
        });
      });
    }
  },
});
