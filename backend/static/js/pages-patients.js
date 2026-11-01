function hashCode(s) { let h = 0; for (let i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) | 0; } return Math.abs(h); }
function avatarColor(name) { const colors = ["#0e63b2", "#0d9488", "#6d28d9", "#b45309", "#0369a1"]; return colors[hashCode(String(name || "")) % colors.length]; }

window.ClinicFlow.registerRoute("patients", {
  async render(params) {
    const host = document.querySelector("#page-content");
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const state = window.ClinicFlow.state;
    const me = state.user;
    const canEdit = me.permissions.includes("patients.edit");
    const canCreate = me.permissions.includes("patients.create");
    const canExport = me.permissions.includes("patients.export");
    host.innerHTML = `
      <div class="page-head">
        <div><div class="page-title">Patients</div><div class="page-sub">Registered patient records</div></div>
        <div class="row">
          ${canExport ? '<button class="btn" id="patient-export">Export</button>' : ""}
          ${canCreate ? '<button class="btn btn-accent" id="patient-new">' + window.ClinicFlow.icon("plus", 16) + ' Register patient</button>' : ""}
        </div>
      </div>
      <div class="card">
        <div class="toolbar">
          <div class="search"><span class="icon-btn" style="border:0;background:transparent;position:absolute;left:8px;top:50%;transform:translateY(-50%)">${window.ClinicFlow.icon("search", 15)}</span><input class="input" id="patient-search-input" placeholder="Search name, code or phone"/></div>
          <select class="select" id="patient-status"><option value="active">Active</option><option value="inactive">Inactive</option><option value="merged">Merged</option></select>
          <select class="select" id="patient-sort"><option value="recent">Recently registered</option><option value="name">Name A-Z</option><option value="code">Patient code</option></select>
          <button class="btn" id="patient-search-btn">Search</button>
        </div>
        <div class="table-wrap"><table class="table"><thead><tr><th>Patient</th><th>Code</th><th>Age</th><th>Phone</th><th>Registered</th><th></th></tr></thead><tbody id="patient-tbody"></tbody></table></div>
      </div>
    `;
    const renderEmpty = () => {
      $("#patient-tbody").innerHTML = `<tr><td colspan="6">${window.ClinicFlow.emptyState("No patients found", "Try a different search term.")}</td></tr>`;
    };
    const renderRows = (patients) => {
      const tbody = $("#patient-tbody");
      if (!patients || !patients.length) { renderEmpty(); return; }
      tbody.innerHTML = patients.map((p) => `
        <tr>
          <td><div class="row"><span class="avatar" style="background:${avatarColor(p.full_name)}">${window.ClinicFlow.initials(p.full_name)}</span><div><div style="font-weight:700">${window.ClinicFlow.escapeHtml(p.full_name)}</div><div class="muted small">${window.ClinicFlow.escapeHtml(p.gender || "")}${p.blood_group ? " · " + window.ClinicFlow.escapeHtml(p.blood_group) : ""}</div></div></div></td>
          <td class="mono">${window.ClinicFlow.escapeHtml(p.patient_code)}</td>
          <td>${p.age ?? ""}</td>
          <td>${window.ClinicFlow.escapeHtml(p.phone_masked || p.phone || "")}</td>
          <td class="muted nowrap">${window.ClinicFlow.fmtDate(p.created_at)}</td>
          <td class="right"><button class="btn btn-sm" data-view="${p.id}">View</button></td>
        </tr>`).join("");
    };
    const load = async () => {
      const search = $("#patient-search-input");
      const status = $("#patient-status");
      const sort = $("#patient-sort");
      const term = search ? search.value.trim() : "";
      if (term) {
        const res = await window.ClinicFlow.apiPost("/api/patients/search", { query: term, limit: 50 });
        return res.patients || [];
      }
      const res = await window.ClinicFlow.apiGet("/api/patients?status=" + encodeURIComponent(status.value) + "&sort=" + sort.value);
      return res || [];
    };
    const runSearch = async () => {
      try { renderRows(await load()); } catch (e) { window.ClinicFlow.toast(e.message, "error"); }
    };
    const searchInput = $("#patient-search-input");
    const searchBtn = $("#patient-search-btn");
    const statusSel = $("#patient-status");
    const sortSel = $("#patient-sort");
    if (searchInput) searchInput.addEventListener("input", (e) => { if (e.target.value.trim().length > 2) runSearch(); });
    if (searchBtn) searchBtn.addEventListener("click", runSearch);
    if (statusSel) statusSel.addEventListener("change", runSearch);
    if (sortSel) sortSel.addEventListener("change", runSearch);
    const first = await load();
    renderRows(first);

    if ($("#patient-new")) {
      $("#patient-new").addEventListener("click", async () => {
        const modal = window.ClinicFlow.openModal({ title: "Register patient", wide: true });
        const body = document.createElement("div");
        body.innerHTML = '<div class="form-grid">' +
          '<label class="field"><span>First name</span><input class="input" id="pf-first"/></label>' +
          '<label class="field"><span>Last name</span><input class="input" id="pf-last"/></label>' +
          '<label class="field"><span>Gender</span><select class="select" id="pf-gender"><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option><option value="prefer_not_to_say">Prefer not to say</option></select></label>' +
          '<label class="field"><span>Date of birth</span><input class="input" type="date" id="pf-dob"/></label>' +
          '<label class="field"><span>Age (optional)</span><input class="input" type="number" id="pf-age"/></label>' +
          '<label class="field"><span>Phone</span><input class="input" id="pf-phone"/></label>' +
          '<label class="field"><span>Email</span><input class="input" id="pf-email"/></label>' +
          '<label class="field"><span>Blood group</span><input class="input" id="pf-blood"/></label>' +
          '</div>';
        modal.querySelector(".modal-body").appendChild(body);
        const footer = document.createElement("div");
        footer.className = "row";
        footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Save patient</button>';
        modal.querySelector(".modal-footer").appendChild(footer);
        window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
          const payload = {
            first_name: $("#pf-first").value.trim(), last_name: $("#pf-last").value.trim(),
            gender: $("#pf-gender").value, date_of_birth: $("#pf-dob").value || null,
            age_years: $("#pf-age").value || null, phone: $("#pf-phone").value.trim(),
            email: $("#pf-email").value.trim() || null, blood_group: $("#pf-blood").value.trim() || null,
          };
          await window.ClinicFlow.apiPost("/api/patients", payload);
          window.ClinicFlow.toast("Patient registered", "ok");
          window.ClinicFlow.closeModal();
          await runSearch();
        });
      });
    }
    if ($("#patient-export")) {
      $("#patient-export").addEventListener("click", async () => {
        const res = await window.ClinicFlow.apiGet("/api/reports/patients/export.csv");
        const blob = new Blob([res.content || ""], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "patients.csv";
        a.click();
        URL.revokeObjectURL(url);
      });
    }
    $("#patient-tbody").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-view]");
      if (!btn) return;
      const id = btn.getAttribute("data-view");
      await window.ClinicFlow.navigate("#/patient/" + id);
    });
  },
});

window.ClinicFlow.registerRoute("patient", {
  async render(params) {
    const host = document.querySelector("#page-content");
    const id = params.id;
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    const data = await window.ClinicFlow.apiGet("/api/patients/" + id);
    const p = data.patient || {};
    host.innerHTML = `
      <div class="page-head">
        <div class="row">
          <span class="avatar lg" style="background:${avatarColor(p.full_name)}">${window.ClinicFlow.initials(p.full_name)}</span>
          <div><div class="page-title">${window.ClinicFlow.escapeHtml(p.full_name)}</div><div class="page-sub mono">${window.ClinicFlow.escapeHtml(p.patient_code)}</div></div>
        </div>
        <div class="row">
          <button class="btn" data-back>Back</button>
          <button class="btn" id="patient-edit">Edit</button>
          <button class="btn" id="patient-timeline">Timeline</button>
        </div>
      </div>
      <div class="grid cols-3">
        <div class="card"><div class="card-header"><div class="card-title">Contact</div></div><div class="card-body">
          <dl class="kv">
            <dt>Phone</dt><dd>${window.ClinicFlow.escapeHtml(p.phone || p.phone_masked || "—")}</dd>
            <dt>Email</dt><dd>${window.ClinicFlow.escapeHtml(p.email ? p.email : "—")}</dd>
            <dt>Address</dt><dd>${[p.address_line1, p.address_line2, p.city, p.state, p.postal_code, p.country].filter(Boolean).join(", ") || "—"}</dd>
            <dt>Emergency</dt><dd>${[p.emergency_contact_name, p.emergency_contact_relation, p.emergency_contact_phone].filter(Boolean).join(" · ") || "—"}</dd>
          </dl>
        </div></div>
        <div class="card"><div class="card-header"><div class="card-title">Clinical</div></div><div class="card-body">
          <dl class="kv">
            <dt>Gender</dt><dd>${p.gender || "—"}</dd>
            <dt>Date of birth</dt><dd>${window.ClinicFlow.fmtDate(p.date_of_birth)}</dd>
            <dt>Blood group</dt><dd>${p.blood_group || "—"}</dd>
            <dt>Allergies</dt><dd>${window.ClinicFlow.escapeHtml(p.allergies || "—")}</dd>
            <dt>Medical history</dt><dd style="white-space:pre-wrap">${window.ClinicFlow.escapeHtml(p.medical_history || "—")}</dd>
            <dt>Patient notes</dt><dd style="white-space:pre-wrap">${window.ClinicFlow.escapeHtml(p.notes || "—")}</dd>
            <dt>Alternate phone</dt><dd>${window.ClinicFlow.escapeHtml(p.alternate_phone || "—")}</dd>
            <dt>Preferred contact</dt><dd>${window.ClinicFlow.escapeHtml(p.preferred_contact || "—")}</dd>
            <dt>Email consent</dt><dd>${p.consent_email ? "Yes" : "No"}</dd>
            <dt>SMS consent</dt><dd>${p.consent_sms ? "Yes" : "No"}</dd>
            <dt>WhatsApp consent</dt><dd>${p.consent_whatsapp ? "Yes" : "No"}</dd>
            <dt>Registered</dt><dd>${window.ClinicFlow.fmtDateTime(p.created_at)}</dd>
            <dt>Last updated</dt><dd>${window.ClinicFlow.fmtDateTime(p.updated_at)}</dd>
          </dl>
        </div></div>
        <div class="card"><div class="card-header"><div class="card-title">Activity</div></div><div class="card-body">
          <dl class="kv">${Object.entries(p.stats || {}).map(([k, v]) => `<dt>${k.replace(/_/g, " ")}</dt><dd>${v}</dd>`).join("")}</dl>
        </div></div>
      </div>
    `;
    const backBtn = host.querySelector("[data-back]");
    if (backBtn) backBtn.addEventListener("click", () => window.ClinicFlow.navigate("#/patients"));
    const editBtn = host.querySelector("#patient-edit");
    if (editBtn) editBtn.addEventListener("click", async () => {
      const modal = window.ClinicFlow.openModal({ title: "Edit patient", wide: true });
      const body = document.createElement("div");
      body.innerHTML = `
        <div class="form-grid">
          <label class="field"><span>First name</span><input class="input" id="pe-first" value="${window.ClinicFlow.escapeHtml(p.first_name || "")}" required/></label>
          <label class="field"><span>Last name</span><input class="input" id="pe-last" value="${window.ClinicFlow.escapeHtml(p.last_name || "")}" required/></label>
          <label class="field"><span>Gender</span><select class="select" id="pe-gender">
            <option value="female" ${p.gender === "female" ? "selected" : ""}>Female</option>
            <option value="male" ${p.gender === "male" ? "selected" : ""}>Male</option>
            <option value="other" ${p.gender === "other" ? "selected" : ""}>Other</option>
            <option value="prefer_not_to_say" ${p.gender === "prefer_not_to_say" ? "selected" : ""}>Prefer not to say</option>
          </select></label>
          <label class="field"><span>Date of birth</span><input class="input" type="date" id="pe-dob" value="${p.date_of_birth || ""}"/></label>
          <label class="field"><span>Phone</span><input class="input" id="pe-phone" value="${window.ClinicFlow.escapeHtml(p.phone || "")}"/></label>
          <label class="field"><span>Email</span><input class="input" id="pe-email" value="${window.ClinicFlow.escapeHtml(p.email || "")}"/></label>
        </div>
        <div data-form-error role="alert" aria-live="polite" hidden style="color:#b91c1c;margin-top:12px"></div>`;
      modal.querySelector(".modal-body").appendChild(body);
      const footer = document.createElement("div");
      footer.innerHTML = '<button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-primary" data-modal-confirm>Save changes</button>';
      modal.querySelector(".modal-footer").appendChild(footer);
      window.ClinicFlow.bindModalAction(modal.querySelector("[data-modal-confirm]"), async () => {
        const payload = {
          first_name: $("#pe-first").value.trim(), last_name: $("#pe-last").value.trim(),
          gender: $("#pe-gender").value, date_of_birth: $("#pe-dob").value || null,
          phone: $("#pe-phone").value.trim(), email: $("#pe-email").value.trim() || null,
        };
        await window.ClinicFlow.apiPut("/api/patients/" + id, payload);
        window.ClinicFlow.toast("Patient updated", "ok");
        window.ClinicFlow.closeModal();
        await window.ClinicFlow.navigate("#/patients/" + id);
      });
    });
    const timelineBtn = host.querySelector("#patient-timeline");
    if (timelineBtn) timelineBtn.addEventListener("click", async () => {
      const events = await window.ClinicFlow.apiGet("/api/patients/" + id + "/timeline");
      const modal = window.ClinicFlow.openModal({ title: "Patient timeline", wide: true });
      const body = document.createElement("div");
      const items = (events || []).slice(0, 30);
      body.innerHTML = items.length ? items.map((e) => `<div class="row mb8"><span class="badge info">${window.ClinicFlow.escapeHtml(e.type)}</span><div class="grow"><b>${window.ClinicFlow.escapeHtml(e.title)}</b><div class="muted small">${window.ClinicFlow.escapeHtml(e.detail || "")}</div></div><span class="muted small">${window.ClinicFlow.fmtDateTime(e.at)}</span></div>`).join("") : '<div class="empty-state"><div class="empty-title">No timeline events yet</div></div>';
      modal.querySelector(".modal-body").appendChild(body);
    });
  },
});
