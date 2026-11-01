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
        <div class="row wrap">
          ${window.ClinicFlow.state.user.permissions.includes("doctors.manage") ? '<button class="btn btn-primary" id="doctor-edit">Edit details</button>' : ""}
          ${window.ClinicFlow.state.user.permissions.includes("doctors.manage") ? (d.user_id ? '<button class="btn" id="doctor-password">Reset login password</button>' : '<button class="btn" id="doctor-create-login">Create login</button>') : ""}
          ${window.ClinicFlow.state.user.permissions.includes("doctors.manage") ? '<button class="btn btn-danger" id="doctor-delete">Delete doctor profile</button>' : ""}
          <button class="btn" id="doctor-leave-new">Add leave</button>
          <button class="btn" id="doctor-schedule-new">Add schedule</button>
          <button class="btn" id="doctor-queue-link">Open queue</button>
        </div>
        <div class="muted small mt8">Login account: ${window.ClinicFlow.escapeHtml(d.email || "No login account linked")}</div>
      `;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Close</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      const canManageDoctor = window.ClinicFlow.state.user.permissions.includes("doctors.manage");
      if (canManageDoctor && modal.querySelector("#doctor-edit")) {
        modal.querySelector("#doctor-edit").addEventListener("click", async () => {
          const name = prompt("Doctor name:", d.full_name || "");
          if (name === null) return;
          const specialization = prompt("Specialization:", d.specialization || "");
          if (specialization === null) return;
          const room = prompt("Room number:", d.room_number || "");
          if (room === null) return;
          const fee = prompt("Consultation fee:", String(d.consultation_fee ?? 0));
          if (fee === null) return;
          const followUpFee = prompt("Follow-up fee:", String(d.follow_up_fee ?? 0));
          if (followUpFee === null) return;
          if (!name.trim() || !specialization.trim() || !Number.isFinite(Number(fee)) || Number(fee) < 0 || !Number.isFinite(Number(followUpFee)) || Number(followUpFee) < 0) {
            window.ClinicFlow.toast("Enter a doctor name, specialization and valid non-negative fees.", "error");
            return;
          }
          try {
            await window.ClinicFlow.apiPut("/api/doctors/" + id, {
              full_name: name.trim(), specialization: specialization.trim(),
              room_number: room.trim() || null,
              consultation_fee: Number(fee), follow_up_fee: Number(followUpFee),
            });
            window.ClinicFlow.toast("Doctor details updated.", "ok");
            window.ClinicFlow.closeModal(modal);
            await window.ClinicFlow.navigate("#/doctors");
          } catch (error) { window.ClinicFlow.toast(error.message || "Doctor details could not be saved.", "error"); }
        });
      }
      if (canManageDoctor && modal.querySelector("#doctor-create-login")) {
        modal.querySelector("#doctor-create-login").addEventListener("click", async () => {
          const email = prompt("Doctor login email:");
          if (!email) return;
          try {
            const result = await window.ClinicFlow.apiPost("/api/doctors/" + id + "/login", { email: email.trim() });
            if (result.temporary_password) window.prompt("Temporary doctor password (copy now):", result.temporary_password);
            window.ClinicFlow.toast("Doctor login created.", "ok");
            window.ClinicFlow.closeModal(modal);
            await window.ClinicFlow.navigate("#/doctors");
          } catch (error) { window.ClinicFlow.toast(error.message || "Doctor login could not be created.", "error"); }
        });
      }
      if (canManageDoctor && modal.querySelector("#doctor-password")) {
        modal.querySelector("#doctor-password").addEventListener("click", () => {
          window.ClinicFlow.confirmDialog("Generate a temporary password for this doctor? The current password will stop working.", async () => {
            const result = await window.ClinicFlow.apiPost("/api/doctors/" + id + "/reset-password", {});
            if (result.temporary_password) window.prompt("Temporary doctor password (copy now):", result.temporary_password);
            window.ClinicFlow.toast("Doctor password reset.", "ok");
          }, null, "Reset password");
        });
      }
      if (canManageDoctor && modal.querySelector("#doctor-delete")) {
        modal.querySelector("#doctor-delete").addEventListener("click", () => {
          window.ClinicFlow.confirmDialog("Permanently delete this doctor profile? Deletion is blocked when linked clinical records exist.", async () => {
            await window.ClinicFlow.apiDelete("/api/doctors/" + id);
            window.ClinicFlow.toast("Doctor profile deleted.", "ok");
            window.ClinicFlow.closeModal(modal);
            await window.ClinicFlow.navigate("#/doctors");
          }, null, "Delete doctor");
        });
      }

      modal.querySelector("#doctor-leave-new").addEventListener("click", () => {
        const modal2 = window.ClinicFlow.openModal({ title: "Add leave", wide: true });
        const body2 = document.createElement("div");
        body2.innerHTML = '<div class="form-grid"><label class="field"><span>Start</span><input class="input" type="date" id="dl-start" required/></label><label class="field"><span>End</span><input class="input" type="date" id="dl-end" required/></label><label class="field full"><span>Reason</span><input class="input" id="dl-reason"/></label></div><div data-form-error role="alert" aria-live="polite" hidden style="color:#b91c1c;margin-top:12px"></div>';
        modal2.querySelector(".modal-body").appendChild(body2);
        const footer2 = document.createElement("div");
        footer2.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Add leave</button>';
        modal2.querySelector(".modal-footer").appendChild(footer2);
        const confirm2 = modal2.querySelector("[data-modal-confirm]");
        let saving = false;
        const showError = (message) => {
          const target = modal2.querySelector("[data-form-error]");
          target.textContent = message;
          target.hidden = !message;
        };
        window.ClinicFlow.bindModalAction(confirm2, async () => {
          if (saving) return;
          const startDate = $("#dl-start").value;
          const endDate = $("#dl-end").value;
          if (!startDate || !endDate) return showError("Start and end dates are required.");
          if (endDate < startDate) return showError("Leave end date must be on or after the start date.");
          saving = true;
          confirm2.disabled = true;
          showError("");
          try {
            await window.ClinicFlow.apiPost("/api/doctors/" + id + "/leaves", {
              start_date: startDate,
              end_date: endDate,
              reason: $("#dl-reason").value.trim()
            });
            window.ClinicFlow.toast("Leave added", "ok");
            window.ClinicFlow.closeModal();
          } catch (error) {
            showError(error && error.message ? error.message : "Could not add leave. Please try again.");
          } finally {
            saving = false;
            if (modal2.isConnected) confirm2.disabled = false;
          }
        });
      });
      modal.querySelector("#doctor-schedule-new").addEventListener("click", () => {
        const modal2 = window.ClinicFlow.openModal({ title: "Add schedule", wide: true });
        const body2 = document.createElement("div");
        body2.innerHTML = '<div class="form-grid"><label class="field"><span>Weekday</span><select class="select" id="ds-weekday" required><option value="0">Monday</option><option value="1">Tuesday</option><option value="2">Wednesday</option><option value="3">Thursday</option><option value="4">Friday</option><option value="5">Saturday</option><option value="6">Sunday</option></select></label><label class="field"><span>Start time</span><input class="input" type="time" id="ds-start" required/></label><label class="field"><span>End time</span><input class="input" type="time" id="ds-end" required/></label><label class="field"><span>Slot minutes (5–240)</span><input class="input" type="number" id="ds-slot" min="5" max="240" step="1" value="15" required/></label></div><div data-form-error role="alert" aria-live="polite" hidden style="color:#b91c1c;margin-top:12px"></div>';
        modal2.querySelector(".modal-body").appendChild(body2);
        const footer2 = document.createElement("div");
        footer2.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Add schedule</button>';
        modal2.querySelector(".modal-footer").appendChild(footer2);
        const confirm2 = modal2.querySelector("[data-modal-confirm]");
        let saving = false;
        const showError = (message) => {
          const target = modal2.querySelector("[data-form-error]");
          target.textContent = message;
          target.hidden = !message;
        };
        window.ClinicFlow.bindModalAction(confirm2, async () => {
          if (saving) return;
          const weekday = Number($("#ds-weekday").value);
          const startTime = $("#ds-start").value;
          const endTime = $("#ds-end").value;
          const slotMinutes = Number($("#ds-slot").value);
          if (!Number.isInteger(weekday) || weekday < 0 || weekday > 6) return showError("Choose a weekday from Monday to Sunday.");
          if (!startTime) return showError("Start time is required.");
          if (!endTime) return showError("End time is required.");
          if (endTime <= startTime) return showError("End time must be after start time.");
          if (!Number.isInteger(slotMinutes) || slotMinutes < 5 || slotMinutes > 240) return showError("Slot duration must be a whole number between 5 and 240 minutes.");
          saving = true;
          confirm2.disabled = true;
          showError("");
          try {
            await window.ClinicFlow.apiPost("/api/doctors/" + id + "/schedules", {
              weekday,
              start_time: startTime,
              end_time: endTime,
              slot_minutes: slotMinutes
            });
            window.ClinicFlow.toast("Schedule added", "ok");
            window.ClinicFlow.closeModal();
          } catch (error) {
            showError(error && error.message ? error.message : "Could not add schedule. Please try again.");
          } finally {
            saving = false;
            if (modal2.isConnected) confirm2.disabled = false;
          }
        });
      });
      modal.querySelector("#doctor-queue-link").addEventListener("click", () => window.ClinicFlow.navigate("#/queue"));
    });
    if ($("#doctor-new")) {
      $("#doctor-new").addEventListener("click", async () => {
        const modal = window.ClinicFlow.openModal({ title: "Add doctor" });
        const body = document.createElement("div");
        body.innerHTML = '<div class="form-grid"><label class="field full"><span>Full name</span><input class="input" id="doc-name" required/></label><label class="field full"><span>Specialization</span><input class="input" id="doc-spec" required/></label><label class="field full"><span>Login email (optional)</span><input class="input" type="email" id="doc-email"/></label><label class="field full"><span>Password (leave blank for temporary password)</span><input class="input" type="password" id="doc-password"/></label></div><p class="muted small">Without a login email, this creates a doctor profile only. Add an email to create and link a doctor login account.</p><div data-form-error role="alert" aria-live="polite" hidden style="color:#b91c1c;margin-top:12px"></div>';
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Add doctor</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        const confirm = modal.querySelector("[data-modal-confirm]");
        let saving = false;
        window.ClinicFlow.bindModalAction(confirm, async () => {
          if (saving) return;
          const fullName = $("#doc-name").value.trim();
          const specialization = $("#doc-spec").value.trim();
          const email = $("#doc-email").value.trim();
          const password = $("#doc-password").value;
          const errorBox = modal.querySelector("[data-form-error]");
          if (!fullName || !specialization) {
            errorBox.textContent = "Doctor name and specialization are required.";
            errorBox.hidden = false;
            return;
          }
          if (password && !email) {
            errorBox.textContent = "A login email is required when setting a password.";
            errorBox.hidden = false;
            return;
          }
          if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
            errorBox.textContent = "Enter a valid doctor login email address.";
            errorBox.hidden = false;
            return;
          }
          if (password && (password.length < 10 || password.length > 72 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password))) {
            errorBox.textContent = "Password must be 10–72 characters and include uppercase, lowercase, a number, and a symbol.";
            errorBox.hidden = false;
            return;
          }
          errorBox.hidden = true;
          saving = true;
          confirm.disabled = true;
          try {
            const result = await window.ClinicFlow.apiPost("/api/doctors", {
              full_name: fullName,
              specialization,
              email: email || null,
              password: password || null
            });
            if (result.doctor && result.doctor.temporary_password) {
              window.prompt("Temporary doctor password (copy now):", result.doctor.temporary_password);
            }
            window.ClinicFlow.toast("Doctor added", "ok");
            window.ClinicFlow.closeModal();
            await window.ClinicFlow.navigate("#/doctors");
          } catch (error) {
            errorBox.textContent = error && error.message ? error.message : "Could not create doctor. Please try again.";
            errorBox.hidden = false;
          } finally {
            saving = false;
            if (modal.isConnected) confirm.disabled = false;
          }
        });
      });
    }
  },
});
