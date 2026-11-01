window.ClinicFlow.registerRoute("settings", {
  async render() {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const clinic = await window.ClinicFlow.apiGet("/api/clinic");
    const c = clinic.clinic || clinic || {};
    const staff = await window.ClinicFlow.apiGet("/api/clinic/staff");
    const roles = await window.ClinicFlow.apiGet("/api/clinic/roles");
    const perms = await window.ClinicFlow.apiGet("/api/clinic/permissions");
    const audit = await window.ClinicFlow.apiGet("/api/clinic/audit-logs");
    const roleList = roles || [];
    const permGroups = (perms && perms.groups) || {};
    const allPerms = (perms && perms.permissions) || [];
    host.innerHTML = `
      <div class="page-head"><div><div class="page-title">Settings</div><div class="page-sub">Clinic, staff, roles and audit</div></div>
        <button class="btn btn-accent" id="staff-new">${window.ClinicFlow.icon("plus", 16)} Add staff</button>
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

    const renderStaff = (rows) => {
      const tbody = document.querySelector("#staff-tbody");
      if (!rows || !rows.length) { tbody.innerHTML = `<tr><td colspan="5">${window.ClinicFlow.emptyState("No staff", "Invite staff members.")}</td></tr>`; return; }
      tbody.innerHTML = rows.map((u) => `
        <tr>
          <td><div class="row"><span class="avatar" style="background:${u.avatar_color || "#0e63b2"}">${window.ClinicFlow.initials(u.full_name)}</span><div><b>${window.ClinicFlow.escapeHtml(u.full_name)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(u.designation || "")}</div></div></div></td>
          <td>${window.ClinicFlow.escapeHtml(u.email)}</td>
          <td>${window.ClinicFlow.escapeHtml(u.role ? u.role.name : "")}</td>
          <td>${window.ClinicFlow.statusBadge(u.is_active ? "active" : "inactive")}</td>
          <td class="right nowrap">
            <button class="btn btn-sm" data-edit="${u.id}">Edit</button>
            <button class="btn btn-sm" data-reset="${u.id}">Reset pwd</button>
            <button class="btn btn-sm ${u.is_active ? "btn-danger" : ""}" data-toggle="${u.id}" data-active="${u.is_active}">${u.is_active ? "Deactivate" : "Activate"}</button>
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
          <td class="right"><button class="btn btn-sm" data-perms="${r.id}">Manage permissions</button></td>
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
      const data = await window.ClinicFlow.apiGet("/api/clinic/staff?status=" + encodeURIComponent(status) + (q ? "&q=" + encodeURIComponent(q) : ""));
      renderStaff(data || []);
    };
    document.querySelector("#staff-search").addEventListener("input", () => { clearTimeout(window._st); window._st = setTimeout(reloadStaff, 250); });
    document.querySelector("#staff-status").addEventListener("change", reloadStaff);

    // Create staff
    document.querySelector("#staff-new").addEventListener("click", () => {
      const modal = window.ClinicFlow.openModal({ title: "Add staff", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="form-grid">
          <label class="field"><span>Full name</span><input class="input" id="st-name"/></label>
          <label class="field"><span>Email</span><input class="input" id="st-email" type="email"/></label>
          <label class="field"><span>Role</span><select class="select" id="st-role">${roleList.map((r) => `<option value="${r.id}">${window.ClinicFlow.escapeHtml(r.name)}</option>`).join("")}</select></label>
          <label class="field"><span>Phone</span><input class="input" id="st-phone"/></label>
          <label class="field"><span>Designation</span><input class="input" id="st-designation"/></label>
          <label class="field"><span>Password (leave blank for temp)</span><input class="input" id="st-password" type="password"/></label>
        </div>`;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Create</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
        try {
          const payload = {
            full_name: document.querySelector("#st-name").value.trim(),
            email: document.querySelector("#st-email").value.trim(),
            role_id: document.querySelector("#st-role").value,
            phone: document.querySelector("#st-phone").value.trim() || null,
            designation: document.querySelector("#st-designation").value.trim() || null,
            password: document.querySelector("#st-password").value || null,
          };
          const res = await window.ClinicFlow.apiPost("/api/clinic/staff", payload);
          if (res.staff && res.staff.temporary_password) {
            window.prompt("Temporary password (copy now):", res.staff.temporary_password);
          }
          window.ClinicFlow.toast("Staff created", "ok");
          window.ClinicFlow.closeModal();
          await reloadStaff();
        } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
      });
    });

    // Table actions
    document.querySelector("#staff-tbody").addEventListener("click", async (e) => {
      const editBtn = e.target.closest("[data-edit]");
      const resetBtn = e.target.closest("[data-reset]");
      const toggleBtn = e.target.closest("[data-toggle]");
      if (editBtn) {
        const id = editBtn.getAttribute("data-edit");
        const u = (staff || []).find((x) => x.id === id);
        if (!u) return;
        const modal = window.ClinicFlow.openModal({ title: "Edit staff", wide: true });
        const body = document.createElement("div");
        body.innerHTML = `
          <div class="form-grid">
            <label class="field"><span>Full name</span><input class="input" id="ed-name" value="${window.ClinicFlow.escapeHtml(u.full_name)}"/></label>
            <label class="field"><span>Phone</span><input class="input" id="ed-phone" value="${window.ClinicFlow.escapeHtml(u.phone || "")}"/></label>
            <label class="field"><span>Designation</span><input class="input" id="ed-designation" value="${window.ClinicFlow.escapeHtml(u.designation || "")}"/></label>
            <label class="field"><span>Role</span><select class="select" id="ed-role">${roleList.map((r) => `<option value="${r.id}" ${r.id === (u.role && u.role.id) ? "selected" : ""}>${window.ClinicFlow.escapeHtml(r.name)}</option>`).join("")}</select></label>
            <label class="checkbox-row"><input type="checkbox" id="ed-active" ${u.is_active ? "checked" : ""}/> Active</label>
          </div>`;
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Save</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
          try {
            await window.ClinicFlow.apiPut("/api/clinic/staff/" + id, {
              full_name: document.querySelector("#ed-name").value.trim(),
              phone: document.querySelector("#ed-phone").value.trim() || null,
              designation: document.querySelector("#ed-designation").value.trim() || null,
              role_id: document.querySelector("#ed-role").value,
              is_active: document.querySelector("#ed-active").checked,
            });
            window.ClinicFlow.toast("Staff updated", "ok");
            window.ClinicFlow.closeModal();
            await reloadStaff();
          } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
        });
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
      modal.querySelector("[data-modal-confirm]").addEventListener("click", async () => {
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
