window.ClinicFlow.registerRoute("queue", {
  async render() {
    const host = document.querySelector("#page-content");
    const state = window.ClinicFlow.state;
    const me = state.user || {};
    const permissions = new Set(me.permissions || []);
    const can = (code) => permissions.has(code);
    const isDoctor = !!(me.role && me.role.slug === "doctor");
    const today = new Date();
    const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Token Queue</div><div class="page-sub">Register patients, call the next token and track each doctor's waiting room.</div></div>
        <div class="row">
          <input type="date" id="queue-date" class="input" style="width:auto" value="${localToday}"/>
          ${can("tokens.create") ? '<button class="btn btn-accent" id="queue-new">Generate token</button>' : ""}
          <button class="btn" id="queue-refresh">Refresh</button>
        </div>
      </div>
      <div class="grid cols-3 mb16" id="queue-summary"></div>
      <div id="queue-board"><div class="loading-overlay"><div class="spinner"></div></div></div>
    `;

    const dateInput = $("#queue-date");
    const summary = $("#queue-summary");
    const board = $("#queue-board");

    const load = async () => {
      const params = new URLSearchParams(window.ClinicFlow.doctorQuery());
      if (dateInput.value) params.set("date", dateInput.value);
      return await window.ClinicFlow.apiGet("/api/tokens/queue?" + params.toString());
    };

    const post = async (path, body) => {
      await window.ClinicFlow.apiPost(path, body);
      window.ClinicFlow.toast("Queue updated.", "ok");
      await renderBoard();
    };

    const actionButton = (label, path, style) => {
      const button = document.createElement("button");
      button.className = "btn btn-sm " + (style || "");
      button.textContent = label;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try { await post(path); }
        catch (error) { window.ClinicFlow.toast(error.message || "Queue action failed.", "error"); }
        finally { if (button.isConnected) button.disabled = false; }
      });
      return button;
    };

    const patientLine = (token) => {
      const p = token.patient || {};
      return `<div><b>${window.ClinicFlow.escapeHtml(token.display_number || "—")}</b> · ${window.ClinicFlow.escapeHtml(p.patient_code || "")} · ${window.ClinicFlow.escapeHtml(p.full_name || "Patient")}</div>
        <div class="muted small">${window.ClinicFlow.escapeHtml(token.visit_type || "walk_in").replace(/_/g, " ")} · ${window.ClinicFlow.escapeHtml(token.status || "")}</div>`;
    };

    const renderQueueCard = (queue) => {
      const doctor = queue.doctor || {};
      const current = queue.current || null;
      const waiting = queue.waiting || [];
      const next = queue.next || waiting[0] || null;
      const card = document.createElement("section");
      card.className = "card mb16";
      const counts = queue.counts || {};
      card.innerHTML = `
        <div class="card-header row between">
          <div><div class="card-title">${window.ClinicFlow.escapeHtml(doctor.full_name || "Doctor queue")}</div><div class="muted small">${window.ClinicFlow.escapeHtml(doctor.doctor_code || "")} ${doctor.specialization ? "· " + window.ClinicFlow.escapeHtml(doctor.specialization) : ""}</div></div>
          <div class="right"><b>${queue.total || 0}</b><div class="muted small">tokens today</div></div>
        </div>
        <div class="card-body">
          <div class="grid cols-3 mb16">
            <div><div class="muted small">Waiting</div><b>${counts.waiting || 0}</b></div>
            <div><div class="muted small">In progress</div><b>${(counts.called || 0) + (counts.recalled || 0) + (counts.in_consultation || 0)}</b></div>
            <div><div class="muted small">Completed</div><b>${counts.completed || 0}</b></div>
          </div>
          <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px">
            <div class="token-card current">
              <div class="muted small">Now serving</div>
              ${current ? patientLine(current) : '<div class="muted">No patient is being seen.</div>'}
              <div data-current-actions class="row mt12"></div>
            </div>
            <div class="token-card">
              <div class="muted small">Next patient</div>
              ${next ? patientLine(next) : '<div class="muted">No patients are waiting.</div>'}
              <div data-next-actions class="row mt12"></div>
            </div>
          </div>
          <div class="mt16"><div class="card-title">Waiting list</div><div data-waiting-list class="mt8"></div></div>
        </div>`;
      const currentActions = card.querySelector("[data-current-actions]");
      const nextActions = card.querySelector("[data-next-actions]");
      const list = card.querySelector("[data-waiting-list]");
      if (current) {
        if (can("tokens.recall")) currentActions.appendChild(actionButton("Recall", "/api/tokens/" + current.id + "/recall"));
        if (can("tokens.skip")) currentActions.appendChild(actionButton("Skip", "/api/tokens/" + current.id + "/skip"));
        if (can("tokens.skip")) currentActions.appendChild(actionButton("No-show", "/api/tokens/" + current.id + "/no-show"));
        if (current.status !== "in_consultation" && can("consultations.create")) {
          currentActions.appendChild(actionButton("Start consultation", "/api/tokens/" + current.id + "/start", "btn-primary"));
        }
        if (current.status === "in_consultation" && can("consultations.complete")) {
          currentActions.appendChild(actionButton("Close token", "/api/tokens/" + current.id + "/complete"));
        }
      }
      if (next && !current && can("tokens.call")) {
        nextActions.appendChild(actionButton("Call next", "/api/tokens/" + next.id + "/call", "btn-primary"));
      } else if (next && current) {
        nextActions.innerHTML = '<span class="muted small">Finish or skip the current patient before calling the next.</span>';
      }
      const rows = waiting.length ? waiting.map((token) => `
        <div class="row between" style="padding:8px 0;border-bottom:1px solid #e5e7eb">
          <div>${patientLine(token)}</div><span class="muted small">${token.waiting_minutes || 0} min</span>
        </div>`).join("") : '<div class="muted small">The waiting list is empty.</div>';
      list.innerHTML = rows;
      return card;
    };

    const renderBoard = async () => {
      board.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
      let data;
      try {
        data = await load();
      } catch (error) {
        board.innerHTML = '<div class="empty-state"><div class="empty-title">Queue could not be loaded</div><div class="empty-sub">' + window.ClinicFlow.escapeHtml(error.message || "Please try again.") + '</div></div>';
        summary.innerHTML = "";
        return;
      }
      const queues = Array.isArray(data.queues) ? data.queues : (data.doctor ? [data] : []);
      const overall = data.overall || data;
      const total = overall.total || 0;
      const counts = overall.counts || {};
      summary.innerHTML = [
        ["Total tokens", total],
        ["Waiting", counts.waiting || 0],
        ["Completed", counts.completed || 0],
      ].map(([label, value]) => `<div class="card stat-card"><div><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div></div>`).join("");
      board.innerHTML = "";
      if (!queues.length) {
        board.innerHTML = '<div class="card"><div class="card-body"><div class="empty-state"><div class="empty-title">No active doctor queues</div><div class="empty-sub">Generate a token to create today’s first queue entry.</div></div></div></div>';
        return;
      }
      queues.forEach((queue) => board.appendChild(renderQueueCard(queue)));
    };

    const openGenerateModal = async () => {
      let doctors = [];
      try {
        const response = await window.ClinicFlow.apiGet("/api/doctors?status=active");
        doctors = Array.isArray(response) ? response : (response.doctors || []);
      } catch (error) {
        window.ClinicFlow.toast(error.message || "Doctors could not be loaded.", "error");
        return;
      }
      if (isDoctor) doctors = doctors.filter((doctor) => doctor.id === me.doctor_id);
      const modal = window.ClinicFlow.openModal({ title: "Generate patient token", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <p class="muted small">Search by patient code (for example P000123) or name, then select the exact patient record.</p>
        <label class="field"><span>Patient code / name</span><input class="input" id="token-patient-search" placeholder="Enter patient code or name" autocomplete="off"/></label>
        <div id="token-patient-results" class="mb16"></div>
        <label class="field"><span>Doctor</span><select class="select" id="token-doctor">${doctors.map((doctor) => '<option value="' + window.ClinicFlow.escapeHtml(doctor.id) + '">' + window.ClinicFlow.escapeHtml(doctor.full_name) + '</option>').join("")}</select></label>
        <label class="field"><span>Visit type</span><select class="select" id="token-visit-type">
          <option value="walk_in">Walk-in</option><option value="appointment">Appointment check-in</option><option value="follow_up">Follow-up</option><option value="priority">Priority</option>${["clinic_admin","doctor","nurse"].includes(me.role && me.role.slug) ? '<option value="emergency">Emergency</option>' : ""}
        </select></label>
        <label class="field"><span>Notes / reason (required for emergency)</span><textarea class="input" id="token-notes" rows="2"></textarea></label>
        <div id="token-form-error" role="alert" aria-live="polite" style="color:#b91c1c"></div>`;
      modal.querySelector(".modal-body").appendChild(body);
      window.ClinicFlow.bindPatientCodePicker(body.querySelector("#token-patient-search"), body.querySelector("#token-patient-results"));
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Generate token</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      const confirm = modal.querySelector("[data-modal-confirm]");
      const errorBox = modal.querySelector("#token-form-error");
      if (!doctors.length) {
        errorBox.textContent = "No active doctor is available. Add or activate a doctor first.";
        confirm.disabled = true;
      }
      window.ClinicFlow.bindModalAction(confirm, async () => {
        const patientInput = modal.querySelector("#token-patient-search");
        const patientId = patientInput.dataset.patientId;
        const doctorId = modal.querySelector("#token-doctor").value;
        if (!patientId) { errorBox.textContent = "Search and select a patient record. Typing alone is not enough."; return; }
        if (!doctorId) { errorBox.textContent = "Select an active doctor."; return; }
        const payload = {
          patient_id: patientId,
          doctor_id: doctorId,
          visit_type: modal.querySelector("#token-visit-type").value,
          notes: modal.querySelector("#token-notes").value.trim() || null,
        };
        const result = await window.ClinicFlow.apiPost("/api/tokens", payload);
        const token = result.token;
        window.ClinicFlow.toast("Token " + token.display_number + " generated for " + (token.patient.patient_code || token.patient.full_name), "ok");
        window.ClinicFlow.closeModal();
        await renderBoard();
      }, (error) => { errorBox.textContent = error.message || "Token could not be generated."; });
    };

    if (can("tokens.create")) $("#queue-new").addEventListener("click", openGenerateModal);
    $("#queue-refresh").addEventListener("click", renderBoard);
    dateInput.addEventListener("change", renderBoard);
    await renderBoard();
  },
});
