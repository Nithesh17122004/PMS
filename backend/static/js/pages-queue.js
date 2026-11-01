window.ClinicFlow.registerRoute("queue", {
  async render() {
    const host = document.querySelector("#page-content");
    const state = window.ClinicFlow.state;
    const me = state.user;
    const isDoctor = me.role && me.role.slug === "doctor";
    const doctorId = isDoctor ? (me.doctor_id || window.ClinicFlow.currentDoctorId()) : window.ClinicFlow.currentDoctorId();
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Token Queue</div><div class="page-sub">Live waiting room · ${state.clinic ? state.clinic.name : ""}</div></div>
        <div class="row"><input type="date" id="queue-date" class="input" style="width:auto"/><button class="btn" id="queue-refresh">Refresh</button></div>
      </div>
      <div class="grid" style="grid-template-columns: 340px 1fr; align-items:start;">
        <div class="card"><div class="card-header"><div class="card-title">Now serving</div></div><div class="card-body" id="queue-current"></div></div>
        <div class="card"><div class="card-header"><div class="card-title">Waiting list</div><div class="card-body" id="queue-waiting"></div></div></div>
      </div>
      <div class="card mt16"><div class="card-header"><div class="card-title">Queue actions</div><div class="card-body" id="queue-actions"></div></div></div>
    `;
    const load = async () => {
      try {
        const q = new URLSearchParams(window.ClinicFlow.doctorQuery());
        const res = await window.ClinicFlow.apiGet("/api/tokens/queue?" + q.toString());
        return res || {};
      } catch (e) { window.ClinicFlow.toast(e.message, "error"); return {}; }
    };
    const renderAll = async () => {
      const data = await load();
      const counts = data.counts || {};
      const current = data.current || null;
      const next = data.next || null;
      const waitingList = data.waiting || [];
      const currentBox = $("#queue-current");
      if (!current) {
        currentBox.innerHTML = '<div class="empty-state"><div class="empty-title">Nothing being seen</div><div class="empty-sub">Call the next token when the patient arrives.</div></div>';
      } else {
        const patient = current.patient || {};
        currentBox.innerHTML = `
          <div class="token-card current">
            <div class="row between">
              <div>
                <div class="muted small">Now serving</div>
                <div class="token-number">${window.ClinicFlow.escapeHtml(current.display_number)}</div>
                <div class="muted small">${window.ClinicFlow.escapeHtml((data.doctor && data.doctor.full_name) || "")} · ${window.ClinicFlow.escapeHtml(current.visit_type || "")}</div>
              </div>
              <div class="right">${window.ClinicFlow.statusBadge(current.status)}</div>
            </div>
            <div class="divider"></div>
            <div class="row between">
              <div><div class="muted small">Patient</div><b>${window.ClinicFlow.escapeHtml(patient.full_name || patient.first_name || "Patient")}</b></div>
              <div class="muted small">Waiting ${current.waiting_minutes ?? 0} min</div>
            </div>
          </div>`;
      }
      const waitingBox = $("#queue-waiting");
      if (!waitingList.length) {
        waitingBox.innerHTML = '<div class="empty-state"><div class="empty-title">Queue is clear</div><div class="empty-sub">No tokens waiting.</div></div>';
      } else {
        waitingBox.innerHTML = waitingList.map((t) => `
          <div class="token-card ${t.id === (current || {}).id ? "current" : ""}" style="margin-bottom:10px;">
            <div class="row between">
              <b style="font-size:18px;color:${window.ClinicFlow.statusColor(t.status)}">${window.ClinicFlow.escapeHtml(t.display_number)}</b>
              <span class="muted small">${window.ClinicFlow.statusBadge(t.status)}</span>
            </div>
            <div class="muted small">${window.ClinicFlow.escapeHtml(t.patient ? t.patient.full_name : "Patient")} · ${window.ClinicFlow.escapeHtml(t.doctor ? t.doctor.full_name : "")}</div>
            <div class="muted small">Waiting ${t.waiting_minutes ?? 0} min</div>
          </div>`).join("");
      }
      const actionsBox = $("#queue-actions");
      const actionButtons = [];
      const add = (label, method, path, confirmText) => {
        const b = document.createElement("button");
        b.className = "btn btn-sm";
        b.textContent = label;
        b.addEventListener("click", async () => {
          if (confirmText) {
            window.ClinicFlow.confirmDialog(confirmText, async () => {
              try {
                const res = await window.ClinicFlow.api(method, path);
                window.ClinicFlow.toast("Token updated", "ok");
                await renderAll();
              } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
            }, null, "Confirm");
            return;
          }
          try {
            const res = await window.ClinicFlow.api(method, path);
            window.ClinicFlow.toast("Token updated", "ok");
            await renderAll();
          } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
        });
        return b;
      };
      const currentId = current ? current.id : null;
      if (currentId) {
        actionButtons.push(add("Recall", "POST", "/api/tokens/" + currentId + "/recall"));
        actionButtons.push(add("Skip", "POST", "/api/tokens/" + currentId + "/skip", "Skip this token?"));
        actionButtons.push(add("No-show", "POST", "/api/tokens/" + currentId + "/no-show", "Mark this token as a no-show?"));
      }
      if (next) actionButtons.push(add("Call next", "POST", "/api/tokens/" + next.id + "/call"));
      actionsBox.innerHTML = "";
      actionButtons.forEach((b) => actionsBox.appendChild(b));
    };
    const refresh = async () => { await renderAll(); };
    $("#queue-refresh").addEventListener("click", refresh);
    const dateInputEl = $("#queue-date");
    if (dateInputEl) dateInputEl.addEventListener("change", () => window.ClinicFlow.navigate("#/queue"));
    await renderAll();
  },
});
