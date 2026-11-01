window.ClinicFlow.registerRoute("settings", {
  async render() {
    const host = document.querySelector("#page-content");
    const canManageStaff = window.ClinicFlow.can("staff.manage");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const clinic = await window.ClinicFlow.apiGet("/api/clinic").catch(() => null);
    const c = (clinic && (clinic.clinic || clinic)) || {};
    const staff = await window.ClinicFlow.apiGet("/api/clinic/staff").catch(() => []);
    const roles = await window.ClinicFlow.apiGet("/api/clinic/roles").catch(() => []);
    const perms = await window.ClinicFlow.apiGet("/api/clinic/permissions").catch(() => ({ groups: {}, permissions: [] }));
    const audit = await window.ClinicFlow.apiGet("/api/clinic/audit-logs").catch(() => []);
    const roleList = roles || [];
    const staffRoles = roleList.filter((role) => role.slug !== "doctor");
    const permGroups = (perms && perms.groups) || {};
    const allPerms = (perms && perms.permissions) || [];
    host.innerHTML = `
      <div class="page-head"><div><div class="page-title">Settings</div><div class="page-sub">Clinic, staff, roles and audit</div></div>
        <div class="row"><button class="btn" id="change-my-password">Change my password</button>${canManageStaff ? '<button class="btn btn-accent" id="staff-new">' + window.ClinicFlow.icon("plus", 16) + " Add staff</button>" : ""}</div>
      </div>
      <div class="card mb16"><div class="card-header"><div class="card-title">Clinic</div></div><div class="card-body grid cols-2">
        <div><div class="muted small">Name</div><b>${window.ClinicFlow.escapeHtml(c.name || "")}</b></div>
        <div><div class="muted small">Timezone</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.timezone : "")}</b></div>
        <div><div class="muted small">Currency</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.currency : "")}</b></div>
        <div><div class="muted small">Token mode</div><b>${window.ClinicFlow.escapeHtml(c.settings ? c.settings.token_mode : "")}</b></div>
      </div></div>
      <div class="card mb16">
        <div class="card-header"><div class="card-title">Staff</div>
          <div class="row"><input class="input" id="staff-search" placeholder="Search name, email, role" style="min-width:200px"/><select class="select" id="staff-status"><option value="all">All</option><option value="active">Active</option><option value="inactive">Inactive</option></select></div>
        </div>
        <div class="table-wrap"><table class="table"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody id="staff-tbody"></tbody></table></div>
      </div>
      <div class="card mb16"><div class="card-header"><div class="card-title">Roles &amp; permissions</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Role</th><th>Permissions</th><th>Users</th><th></th></tr></thead><tbody id="roles-tbody"></tbody></table></div></div>
      <div class="card"><div class="card-header"><div class="card-title">Audit log</div></div><div class="table-wrap"><table class="table"><thead><tr><th>Actor</th><th>Action</th><th>Entity</th><th>When</th></tr></thead><tbody id="audit-tbody"></tbody></table></div></div>
    `;

    const changeMyPassword = document.querySelector("#change-my-password");
    if (changeMyPassword) {
      changeMyPassword.addEventListener("click", () => {
        const modal = window.ClinicFlow.openModal({ title: "Change my password", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <label class="field"><span>Current password</span><input class="input" id="my-current-password" type="password" autocomplete="current-password"/></label>
          <label class="field"><span>New password</span><input class="input" id="my-new-password" type="password" maxlength="72" autocomplete="new-password"/></label>
          <label class="field"><span>Confirm new password</span><input class="input" id="my-confirm-password" type="password" maxlength="72" autocomplete="new-password"/></label>
          <p class="muted small">Use at least 10 characters with uppercase, lowercase, a number and a symbol.</p>
          <div data-form-error role="alert" style="color:#b91c1c"></div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Update password</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        const errorBox = modal.querySelector("[data-form-error]");
        window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
          const currentPassword = modal.querySelector("#my-current-password").value;
          const nextPassword = modal.querySelector("#my-new-password").value;
          const confirmPassword = modal.querySelector("#my-confirm-password").value;
          if (nextPassword !== confirmPassword) { errorBox.textContent = "The new passwords do not match."; return; }
          if (nextPassword.length < 10 || nextPassword.length > 72 || !/[A-Z]/.test(nextPassword) || !/[a-z]/.test(nextPassword) || !/[0-9]/.test(nextPassword) || !/[^A-Za-z0-9]/.test(nextPassword)) {
            errorBox.textContent = "Use 10–72 characters with uppercase, lowercase, a number and a symbol.";
            return;
          }
          await window.ClinicFlow.apiPost("/api/auth/change-password", {
            current_password: currentPassword,
            new_password: nextPassword,
          });
          window.ClinicFlow.toast("Your password has been changed.", "ok");
          window.ClinicFlow.closeModal();
        }, (error) => { errorBox.textContent = error.message || "Password could not be updated."; });
      });
    }

    let staffRows = staff || [];
    const renderStaff = (rows) => {
      staffRows = rows || [];
      const tbody = document.querySelector("#staff-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="5">${window.ClinicFlow.emptyState("No staff", "Invite staff members.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((u) => `
        <tr>
          <td><div class="row"><span class="avatar" style="background:${u.avatar_color || "#0e63b2"}">${window.ClinicFlow.initials(u.full_name)}</span><div><b>${window.ClinicFlow.escapeHtml(u.full_name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(u.designation || "")}</div></div></div></td>
          <td>${window.ClinicFlow.escapeHtml(u.email)}</td>
          <td>${window.ClinicFlow.escapeHtml(u.role ? u.role.name : "")}</td>
          <td>${window.ClinicFlow.statusBadge(u.is_active ? "active" : "inactive")}</td>
          <td class="right nowrap">
            ${canManageStaff ? '<button class="btn btn-sm" data-edit="' + u.id + '">Edit</button>' : ""}
            ${canManageStaff && u.id !== window.ClinicFlow.state.user.id ? `
              <button class="btn btn-sm" data-reset="${u.id}">Reset pwd</button>
              <button class="btn btn-sm" data-set-password="${u.id}">Set password</button>
              <button class="btn btn-sm ${u.is_active ? "btn-danger" : ""}" data-toggle="${u.id}" data-active="${u.is_active}">${u.is_active ? "Deactivate" : "Activate"}</button>
            ` : '<span class="muted small">Current account</span>'}
          </td>
        </tr>`).join("");
    };
    renderStaff(staff || []);

    const renderRoles = (rows) => {
      const tbody = document.querySelector("#roles-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="4">${window.ClinicFlow.emptyState("No roles", "")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((r) => `
        <tr>
          <td><b>${window.ClinicFlow.escapeHtml(r.name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(r.slug)}</div></td>
          <td class="muted small">${(r.permissions || []).length} permissions</td>
          <td>${r.user_count ?? 0}</td>
          <td class="right">${canManageStaff ? '<button class="btn btn-sm" data-perms="' + r.id + '">Manage permissions</button>' : ""}</td>
        </tr>`).join("");
    };
    renderRoles(roleList || []);

    const auditList = audit || [];
    document.querySelector("#audit-tbody").innerHTML = auditList.slice(0, 30).map((l) => `
      <tr>
        <td>${window.ClinicFlow.escapeHtml(l.user ? l.user.full_name : "System")}</td>
        <td class="mono">${window.ClinicFlow.escapeHtml(l.action)}</td>
        <td>${window.ClinicFlow.escapeHtml(l.entity_type || "")}</td>
        <td class="muted nowrap">${window.ClinicFlow.fmtDateTime(l.created_at)}</td>
      </tr>`).join("");

    // Search/filter
    const reloadStaff = async () => {
      const q = document.querySelector("#staff-search").value.trim();
      const status = document.querySelector("#staff-status").value;
      try {
        const data = await window.ClinicFlow.apiGet("/api/clinic/staff?status=" + encodeURIComponent(status) + (q ? "&q=" + encodeURIComponent(q) : ""));
        renderStaff(data || []);
      } catch (error) {
        window.ClinicFlow.toast(error && error.message ? error.message : "Could not refresh staff.", "error");
      }
    };
    document.querySelector("#staff-search").addEventListener("input", () => { clearTimeout(window._st); window._st = setTimeout(reloadStaff, 250); });
    document.querySelector("#staff-status").addEventListener("change", reloadStaff);

    // Create non-doctor staff accounts. Doctor logins and profiles are created together in Doctors.
    document.querySelector("#staff-new")?.addEventListener("click", () => {
      const modal = window.ClinicFlow.openModal({ title: "Add staff", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="form-grid">
          <label class="field"><span>Full name</span><input class="input" id="st-name" required/></label>
          <label class="field"><span>Email</span><input class="input" id="st-email" type="email" maxlength="190" required/></label>
          <label class="field"><span>Role</span><select class="select" id="st-role" required><option value="">Choose a role</option>${staffRoles.map((r) => `<option value="${r.id}">${window.ClinicFlow.escapeHtml(r.name)}</option>`).join("")}</select></label>
          <label class="field"><span>Phone</span><input class="input" id="st-phone"/></label>
          <label class="field"><span>Designation</span><input class="input" id="st-designation"/></label>
          <label class="field"><span>Password (leave blank for temporary password)</span><input class="input" id="st-password" type="password" maxlength="72"/></label>
        </div>
        <p class="muted small">Doctor accounts must be created in the Doctors module so the login is linked to a clinical profile.</p>
        <button class="btn btn-sm" type="button" data-open-doctors>Open Doctors</button>
        <div data-form-error role="alert" aria-live="polite" hidden style="color:#b91c1c;margin-top:12px"></div>`;
      modal.querySelector(".modal-body").appendChild(body);
      body.querySelector("[data-open-doctors]").addEventListener("click", async () => {
        window.ClinicFlow.closeModal();
        await window.ClinicFlow.navigate("#/doctors");
      });
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Create</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      const confirm = modal.querySelector("[data-modal-confirm]");
      let creating = false;
      const showError = (message) => {
        const target = modal.querySelector("[data-form-error]");
        target.textContent = message;
        target.hidden = !message;
      };
      window.ClinicFlow.bindModalAction(confirm, async () => {
        if (creating) return;
        const payload = {
          full_name: modal.querySelector("#st-name").value.trim(),
          email: modal.querySelector("#st-email").value.trim(),
          role_id: modal.querySelector("#st-role").value,
          phone: modal.querySelector("#st-phone").value.trim() || null,
          designation: modal.querySelector("#st-designation").value.trim() || null,
          password: modal.querySelector("#st-password").value || null,
        };
        if (!payload.full_name) return showError("Full name is required.");
        if (!payload.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(payload.email)) return showError("Enter a valid email address.");
        if (!payload.role_id) return showError("Choose a staff role.");
        if (payload.password && (payload.password.length < 10 || payload.password.length > 72 || !/[A-Z]/.test(payload.password) || !/[a-z]/.test(payload.password) || !/[0-9]/.test(payload.password) || !/[^A-Za-z0-9]/.test(payload.password))) {
          return showError("Password must be 10–72 characters and include uppercase, lowercase, a number, and a symbol.");
        }
        creating = true;
        confirm.disabled = true;
        showError("");
        try {
          const res = await window.ClinicFlow.apiPost("/api/clinic/staff", payload);
          if (res.staff && res.staff.temporary_password) {
            window.prompt("Temporary password (copy now):", res.staff.temporary_password);
          }
          window.ClinicFlow.toast("Staff created", "ok");
          window.ClinicFlow.closeModal();
          await reloadStaff();
        } catch (error) {
          showError(error && error.message ? error.message : "Could not create staff account. Please try again.");
        } finally {
          creating = false;
          if (modal.isConnected) confirm.disabled = false;
        }
      });
    });

    // Table actions
    document.querySelector("#staff-tbody").addEventListener("click", async (e) => {
      const editBtn = e.target.closest("[data-edit]");
      const resetBtn = e.target.closest("[data-reset]");
      const setPasswordBtn = e.target.closest("[data-set-password]");
      const toggleBtn = e.target.closest("[data-toggle]");
      if (editBtn) {
        const id = editBtn.getAttribute("data-edit");
        const u = staffRows.find((x) => x.id === id);
        if (!u) return;
        const modal = window.ClinicFlow.openModal({ title: "Edit staff", wide: true });
        const editableRoles = roleList.filter((r) => r.slug !== "doctor" || (u.role && u.role.slug === "doctor"));
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field"><span>Full name</span><input class="input" id="ed-name" value="${window.ClinicFlow.escapeHtml(u.full_name)}"/></label>
            <label class="field"><span>Phone</span><input class="input" id="ed-phone" value="${window.ClinicFlow.escapeHtml(u.phone || "")}"/></label>
            <label class="field"><span>Designation</span><input class="input" id="ed-designation" value="${window.ClinicFlow.escapeHtml(u.designation || "")}"/></label>
            <label class="field"><span>Role</span><select class="select" id="ed-role">${editableRoles.map((r) => `<option value="${r.id}" ${r.id === (u.role && u.role.id) ? "selected" : ""}>${window.ClinicFlow.escapeHtml(r.name)}</option>`).join("")}</select></label>
            <label class="checkbox-row"><input type="checkbox" id="ed-active" ${u.is_active ? "checked" : ""}/> Active</label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Save</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        const confirm = modal.querySelector("[data-modal-confirm]");
        let saving = false;
        const errorBox = document.createElement("div");
        errorBox.setAttribute("data-form-error", "");
        errorBox.setAttribute("role", "alert");
        errorBox.style.cssText = "color:#b91c1c;margin-top:12px";
        modal.querySelector(".modal-body").appendChild(errorBox);
        window.ClinicFlow.bindModalAction(confirm, async () => {
          if (saving) return;
          const fullName = modal.querySelector("#ed-name").value.trim();
          if (!fullName) {
            errorBox.textContent = "Full name is required.";
            return;
          }
          saving = true;
          confirm.disabled = true;
          errorBox.textContent = "";
          try {
            await window.ClinicFlow.apiPut("/api/clinic/staff/" + id, {
              full_name: fullName,
              phone: modal.querySelector("#ed-phone").value.trim() || null,
              designation: modal.querySelector("#ed-designation").value.trim() || null,
              role_id: modal.querySelector("#ed-role").value,
              is_active: modal.querySelector("#ed-active").checked,
            });
            window.ClinicFlow.toast("Staff updated", "ok");
            window.ClinicFlow.closeModal();
            await reloadStaff();
          } catch (error) {
            errorBox.textContent = error && error.message ? error.message : "Could not update staff.";
          } finally {
            saving = false;
            if (modal.isConnected) confirm.disabled = false;
          }
        });
      }
      if (setPasswordBtn) {
        const id = setPasswordBtn.getAttribute("data-set-password");
        const member = staffRows.find((x) => x.id === id);
        if (!member) return;
        const modal = window.ClinicFlow.openModal({ title: "Set password · " + member.full_name, wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <label class="field"><span>New password</span><input class="input" id="set-staff-password" type="password" maxlength="72" autocomplete="new-password"/></label>
          <label class="field"><span>Confirm password</span><input class="input" id="set-staff-password-confirm" type="password" maxlength="72" autocomplete="new-password"/></label>
          <label class="checkbox-row"><input type="checkbox" id="set-staff-force-change" checked/> Require this user to change it at next sign-in</label>
          <div data-form-error role="alert" aria-live="polite" style="color:#b91c1c;margin-top:12px"></div>
          <p class="muted small">The password is stored securely as a hash and is never displayed again. Do not send it over an insecure channel.</p>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" type="button" data-modal-cancel>Cancel</button><button class="btn btn-primary" type="button" data-modal-confirm>Save password</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        const confirm = modal.querySelector("[data-modal-confirm]");
        const errorBox = modal.querySelector("[data-form-error]");
        window.ClinicFlow.bindModalAction(confirm, async () => {
          const password = modal.querySelector("#set-staff-password").value;
          const repeated = modal.querySelector("#set-staff-password-confirm").value;
          if (password !== repeated) {
            errorBox.textContent = "The passwords do not match.";
            return;
          }
          if (password.length < 10 || password.length > 72 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
            errorBox.textContent = "Use 10–72 characters with uppercase, lowercase, a number and a symbol.";
            return;
          }
          errorBox.textContent = "";
          await window.ClinicFlow.apiPost("/api/clinic/staff/" + id + "/set-password", {
            password,
            require_change: modal.querySelector("#set-staff-force-change").checked,
          });
          window.ClinicFlow.toast("Password updated for " + member.full_name, "ok");
          window.ClinicFlow.closeModal();
          await reloadStaff();
        }, (error) => { errorBox.textContent = error.message || "Could not update the password."; });
      }
      if (resetBtn) {
        const id = resetBtn.getAttribute("data-reset");
        window.ClinicFlow.confirmDialog("Reset this staff member's password?", async () => {
          try {
            const res = await window.ClinicFlow.apiPost("/api/clinic/staff/" + id + "/reset-password");
            window.prompt("Temporary password (copy now):", res.temporary_password);
            window.ClinicFlow.toast("Password reset", "ok");
            await reloadStaff();
          } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
        });
      }
      if (toggleBtn) {
        const id = toggleBtn.getAttribute("data-toggle");
        const currentlyActive = toggleBtn.getAttribute("data-active") === "true";
        try {
          await window.ClinicFlow.apiPut("/api/clinic/staff/" + id, { is_active: !currentlyActive });
          window.ClinicFlow.toast("Status updated", "ok");
          await reloadStaff();
        } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
      }
    });

    // Permission matrix
    document.querySelector("#roles-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-perms]");
      if (!btn) return;
      const roleId = btn.getAttribute("data-perms");
      const role = (roleList || []).find((r) => r.id === roleId);
      if (!role) return;
      const current = new Set(role.permissions || []);
      const modal = window.ClinicFlow.openModal({ title: "Permissions: " + role.name, wide: true });
      const body = document.createElement("div");
      body.innerHTML = Object.keys(permGroups).map((g) => `
        <div class="mb16">
          <div style="font-weight:700;margin-bottom:6px">${window.ClinicFlow.escapeHtml(g)}</div>
          <div class="grid cols-2">
            ${(permGroups[g] || []).map((p) => `
              <label class="checkbox-row"><input type="checkbox" data-perm="${p.code}" ${current.has(p.code) ? "checked" : ""}/> ${window.ClinicFlow.escapeHtml(p.name)}</label>
            `).join("")}
          </div>
        </div>`).join("");
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Save permissions</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
        const codes = Array.from(body.querySelectorAll("[data-perm]"))
          .filter((cb) => cb.checked)
          .map((cb) => cb.getAttribute("data-perm"));
        try {
          await window.ClinicFlow.apiPut("/api/clinic/roles/" + roleId, { permissions: codes });
          window.ClinicFlow.toast("Permissions updated", "ok");
          window.ClinicFlow.closeModal();
          await window.ClinicFlow.navigate("#/settings");
        } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
      });
    });
  },
});
