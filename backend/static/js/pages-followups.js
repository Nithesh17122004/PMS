window.ClinicFlow.registerRoute("followups", {
  async render() {
    const host = document.querySelector("#page-content");
    const state = window.ClinicFlow.state;
    const me = state.user || {};
    const permissions = new Set(me.permissions || []);
    const can = (code) => permissions.has(code);
    const mayManage = can("followups.manage");
    const canArrive = mayManage || can("tokens.create");
    const localDate = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Follow-ups</div><div class="page-sub">Plan reviews, contact patients and register their arrival.</div></div>
        ${mayManage ? '<button class="btn btn-accent" id="followup-new">New follow-up</button>' : ""}
      </div>
      <div class="grid cols-4" id="followup-stats"></div>
      <div class="card mt16">
        <div class="toolbar">
          <input class="input" id="followup-search" placeholder="Search patient name or code"/>
          <select class="select" id="followup-filter"><option value="all">All follow-ups</option><option value="due">Due today / overdue</option><option value="overdue">Overdue</option><option value="upcoming">Upcoming</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option><option value="missed">Missed</option></select>
          <button class="btn" id="followup-refresh">Refresh</button>
        </div>
        <div class="table-wrap"><table class="table"><thead><tr><th>Patient / code</th><th>Doctor</th><th>Due date</th><th>Status</th><th></th></tr></thead><tbody id="followup-tbody"></tbody></table></div>
      </div>`;
    const stats = $("#followup-stats");
    const tbody = $("#followup-tbody");
    const search = $("#followup-search");
    const filter = $("#followup-filter");
    const cards = [
      ["today", "Due today"], ["upcoming", "Upcoming"], ["overdue", "Overdue"], ["completed", "Completed"],
    ];
    const loadStats = async () => {
      try {
        const data = await window.ClinicFlow.apiGet("/api/followups/dashboard");
        const counts = data.counts || {};
        stats.innerHTML = cards.map(([key, label]) => `<div class="card stat-card"><div><div class="stat-value">${counts[key] || 0}</div><div class="stat-label">${label}</div></div></div>`).join("");
      } catch (error) {
        stats.innerHTML = "";
        window.ClinicFlow.toast(error.message || "Follow-up summary could not be loaded.", "error");
      }
    };
    const loadRows = async () => {
      const params = new URLSearchParams();
      params.set("status", filter.value);
      if (search.value.trim()) params.set("q", search.value.trim());
      const response = await window.ClinicFlow.apiGet("/api/followups?" + params.toString());
      const rows = Array.isArray(response) ? response : (response.followups || []);
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5">' + window.ClinicFlow.emptyState("No follow-ups found", "Change the filter or create a follow-up plan.") + '</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((item) => `
        <tr>
          <td><b>${window.ClinicFlow.escapeHtml(item.patient ? item.patient.full_name : "Unknown patient")}</b><div class="muted small mono">${window.ClinicFlow.escapeHtml(item.patient ? item.patient.patient_code : "")}</div></td>
          <td>${window.ClinicFlow.escapeHtml(item.doctor ? item.doctor.full_name : "")}</td>
          <td class="nowrap">${window.ClinicFlow.fmtDate(item.due_date)}</td>
          <td>${window.ClinicFlow.statusBadge(item.status)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${item.id}">Manage</button></td>
        </tr>`).join("");
    };
    const refresh = async () => {
      try { await Promise.all([loadStats(), loadRows()]); }
      catch (error) { window.ClinicFlow.toast(error.message || "Follow-ups could not be loaded.", "error"); }
    };
    $("#followup-refresh").addEventListener("click", refresh);
    filter.addEventListener("change", loadRows);
    let searchTimer = null;
    search.addEventListener("input", () => {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadRows().catch((error) => window.ClinicFlow.toast(error.message, "error")), 220);
    });
    tbody.addEventListener("click", (event) => {
      const button = event.target.closest("[data-view]");
      if (button) window.ClinicFlow.navigate("#/followups/" + button.getAttribute("data-view"));
    });
    await refresh();

    if (mayManage && $("#followup-new")) {
      $("#followup-new").addEventListener("click", async () => {
        let doctors = [];
        try {
          const response = await window.ClinicFlow.apiGet("/api/doctors?status=active");
          doctors = Array.isArray(response) ? response : (response.doctors || []);
        } catch (error) {
          window.ClinicFlow.toast(error.message || "Doctors could not be loaded.", "error");
          return;
        }
        if (me.role && me.role.slug === "doctor") doctors = doctors.filter((doctor) => doctor.id === me.doctor_id);
        const modal = window.ClinicFlow.openModal({ title: "Create follow-up plan", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <p class="muted small">Search by patient code or name and select the exact patient record.</p>
          <label class="field"><span>Patient code / name</span><input class="input" id="fu-patient-search" placeholder="For example P000123" autocomplete="off"/></label>
          <div id="fu-patient-results" class="mb16"></div>
          <label class="field"><span>Doctor</span><select class="select" id="fu-doctor">${doctors.map((doctor) => '<option value="' + window.ClinicFlow.escapeHtml(doctor.id) + '">' + window.ClinicFlow.escapeHtml(doctor.full_name) + '</option>').join("")}</select></label>
          <label class="field"><span>Follow-up date</span><input class="input" type="date" id="fu-due" min="${localDate}" value="${localDate}"/></label>
          <label class="field"><span>Instructions</span><textarea class="input" id="fu-instructions" rows="3" maxlength="4000" placeholder="Review symptoms, investigations or treatment progress"></textarea></label>
          <label class="field"><span>Priority</span><select class="select" id="fu-priority"><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
          <div data-form-error role="alert" style="color:#b91c1c"></div>`;
        modal.querySelector(".modal-body").appendChild(body);
        window.ClinicFlow.bindPatientCodePicker(body.querySelector("#fu-patient-search"), body.querySelector("#fu-patient-results"));
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Create follow-up</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        const confirm = modal.querySelector("[data-modal-confirm]");
        const errorBox = modal.querySelector("[data-form-error]");
        if (!doctors.length) {
          errorBox.textContent = "No active doctor is available.";
          confirm.disabled = true;
        }
        window.ClinicFlow.bindModalAction(confirm, async () => {
          const patientId = modal.querySelector("#fu-patient-search").dataset.patientId;
          if (!patientId) { errorBox.textContent = "Search and select a patient. Typing a name or code alone does not select a record."; return; }
          const doctorId = modal.querySelector("#fu-doctor").value;
          const dueDate = modal.querySelector("#fu-due").value;
          if (!doctorId) { errorBox.textContent = "Select an active doctor."; return; }
          if (!dueDate || dueDate < localDate) { errorBox.textContent = "Choose today or a future date."; return; }
          await window.ClinicFlow.apiPost("/api/followups", {
            patient_id: patientId,
            doctor_id: doctorId,
            due_date: dueDate,
            instructions: modal.querySelector("#fu-instructions").value.trim(),
            priority: modal.querySelector("#fu-priority").value,
          });
          window.ClinicFlow.toast("Follow-up created.", "ok");
          window.ClinicFlow.closeModal();
          await refresh();
        }, (error) => { errorBox.textContent = error.message || "Follow-up could not be created."; });
      });
    }
  },
});

window.ClinicFlow.registerRoute("followup", {
  async render(params) {
    const host = document.querySelector("#page-content");
    const id = params.id;
    const me = window.ClinicFlow.state.user || {};
    const permissions = new Set(me.permissions || []);
    const can = (code) => permissions.has(code);
    const mayManage = can("followups.manage");
    const canArrive = mayManage || can("tokens.create");
    const response = await window.ClinicFlow.apiGet("/api/followups/" + encodeURIComponent(id));
    const f = response.followup || {};
    const p = f.patient || {};
    const doctor = f.doctor || {};
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Follow-up · ${window.ClinicFlow.escapeHtml(p.patient_code || "")}</div><div class="page-sub">${window.ClinicFlow.escapeHtml(p.full_name || "")} · Due ${window.ClinicFlow.fmtDate(f.due_date)}</div></div>
        <div class="row"><button class="btn" data-back>Back</button></div>
      </div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px">
        <div class="card"><div class="card-body">
          <div class="muted small">Patient</div><h3>${window.ClinicFlow.escapeHtml(p.full_name || "—")}</h3><div class="mono">${window.ClinicFlow.escapeHtml(p.patient_code || "")}</div>
          <div class="muted small mt8">${window.ClinicFlow.escapeHtml(p.phone_masked || "")}</div>
        </div></div>
        <div class="card"><div class="card-body">
          <div class="muted small">Doctor</div><h3>${window.ClinicFlow.escapeHtml(doctor.full_name || "—")}</h3>
          <div class="muted small">${window.ClinicFlow.escapeHtml(doctor.specialization || "")}</div>
        </div></div>
      </div>
      <div class="card mt16"><div class="card-body">
        <div class="row between"><b>Follow-up details</b>${window.ClinicFlow.statusBadge(f.status)}</div>
        <dl class="kv"><dt>Due date</dt><dd>${window.ClinicFlow.fmtDate(f.due_date)}</dd><dt>Original date</dt><dd>${window.ClinicFlow.fmtDate(f.original_due_date)}</dd><dt>Priority</dt><dd>${window.ClinicFlow.escapeHtml(f.priority || "normal")}</dd><dt>Instructions</dt><dd>${window.ClinicFlow.escapeHtml(f.instructions || "—")}</dd><dt>Linked appointment</dt><dd>${f.appointment_id ? "Yes — reschedule the appointment in Appointments." : "No"}</dd><dt>Token</dt><dd>${window.ClinicFlow.escapeHtml(f.token ? f.token.display_number : "Not arrived yet")}</dd></dl>
        <div id="fu-detail-error" role="alert" style="color:#b91c1c;margin-top:10px"></div>
        <div class="row wrap mt16" id="fu-detail-actions"></div>
      </div></div>`;
    const actions = $("#fu-detail-actions");
    const errorBox = $("#fu-detail-error");
    const addAction = (label, handler, css) => {
      const button = document.createElement("button");
      button.className = "btn " + (css || "");
      button.textContent = label;
      button.addEventListener("click", async () => {
        button.disabled = true;
        errorBox.textContent = "";
        try { await handler(); }
        catch (error) { errorBox.textContent = error.message || "Action could not be completed."; }
        finally { if (button.isConnected) button.disabled = false; }
      });
      actions.appendChild(button);
    };
    const refreshDetail = () => window.ClinicFlow.navigate("#/followups/" + id);
    $("#page-content [data-back]").addEventListener("click", () => window.ClinicFlow.navigate("#/followups"));
    if (mayManage && ["upcoming", "missed"].includes(f.status)) {
      addAction("Confirm", async () => {
        await window.ClinicFlow.apiPost("/api/followups/" + id + "/confirm", {});
        window.ClinicFlow.toast("Follow-up confirmed.", "ok");
        await refreshDetail();
      }, "btn-primary");
    }
    if (mayManage && !["completed", "cancelled"].includes(f.status)) {
      addAction("Reschedule", async () => {
        const proposed = prompt("Enter new follow-up date (YYYY-MM-DD):", f.due_date || "");
        if (!proposed) return;
        const reason = prompt("Reason for rescheduling (optional):", "") || "";
        await window.ClinicFlow.apiPost("/api/followups/" + id + "/reschedule", { due_date: proposed, reason });
        window.ClinicFlow.toast("Follow-up rescheduled.", "ok");
        await refreshDetail();
      });
      addAction("Cancel follow-up", async () => {
        const reason = prompt("Why is this follow-up being cancelled?");
        if (!reason || reason.trim().length < 3) return;
        await window.ClinicFlow.apiPost("/api/followups/" + id + "/cancel", { reason });
        window.ClinicFlow.toast("Follow-up cancelled.", "ok");
        await refreshDetail();
      }, "btn-danger");
      addAction("Send reminder", async () => {
        const channel = prompt("Reminder channel: email, sms or whatsapp", "sms");
        if (!channel) return;
        const result = await window.ClinicFlow.apiPost("/api/followups/" + id + "/remind", { channel: channel.trim().toLowerCase() });
        window.ClinicFlow.toast("Reminder status: " + ((result.reminder || {}).status || "queued"), "ok");
        await refreshDetail();
      });
    }
    if (canArrive && !["completed", "cancelled"].includes(f.status) && (!f.token || ["cancelled", "completed", "skipped", "no_show"].includes(f.token.status))) {
      addAction("Patient arrived · generate token", async () => {
        const result = await window.ClinicFlow.apiPost("/api/followups/" + id + "/arrive", {});
        window.ClinicFlow.toast("Token " + result.token.display_number + " generated.", "ok");
        await window.ClinicFlow.navigate("#/queue");
      }, "btn-primary");
    }
    if (can("followups.complete") && f.status !== "completed" && f.status !== "cancelled") {
      addAction("Mark completed", async () => {
        await window.ClinicFlow.apiPost("/api/followups/" + id + "/complete", {});
        window.ClinicFlow.toast("Follow-up completed.", "ok");
        await refreshDetail();
      });
    }
    if (!actions.children.length) {
      actions.innerHTML = '<span class="muted small">No actions are available for your role or this follow-up status.</span>';
    }
    if (Array.isArray(response.followup && response.followup.reminders) && response.followup.reminders.length) {
      const history = document.createElement("div");
      history.className = "card mt16";
      history.innerHTML = '<div class="card-body"><b>Reminder history</b>' + response.followup.reminders.map((item) =>
        '<div class="row between" style="padding:8px 0;border-bottom:1px solid #e5e7eb"><span>' + window.ClinicFlow.escapeHtml(item.channel + " · " + item.reminder_type) + '</span><span>' + window.ClinicFlow.statusBadge(item.status) + '</span></div>'
      ).join("") + '</div>';
      host.appendChild(history);
    }
  },
});
