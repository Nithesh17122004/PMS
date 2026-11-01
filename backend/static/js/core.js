/* ClinicFlow SPA core: API client, router, shell, UI primitives, charts. */
window.ClinicFlow = window.ClinicFlow || {};
window.ClinicFlow.App = {
  user: null,
  clinic: null,
  permissions: [],
  page: "dashboard",
  routeParams: {},
  doctorScope: null,
  queueDoctorId: null,
  initialized: false,
};

(function () {
  const state = window.ClinicFlow.App;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function toast(message, type) {
    type = type || "info";
    let host = document.querySelector(".toast-container");
    if (!host) {
      host = document.createElement("div");
      host.className = "toast-container";
      document.body.appendChild(host);
    }
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.innerHTML = '<div class="row">' + '<div class="grow">' + escapeHtml(message) + '</div>' +
      '<button class="icon-btn" style="border:0;background:transparent;color:#cbd5e1" data-toast-close>&times;</button>' +
      '</div>';
    el.querySelector("[data-toast-close]").addEventListener("click", () => el.remove());
    host.appendChild(el);
    setTimeout(() => el.remove(), 5200);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function hideLoading() { const l = document.querySelector(".loading-overlay"); if (l) l.remove(); }
  function showLoading() { if (document.querySelector(".loading-overlay")) return; const d = document.createElement("div"); d.className = "loading-overlay"; d.innerHTML = '<div class="spinner"></div>'; document.body.appendChild(d); }
  function emptyState(title, sub, icon) {
    const host = document.querySelector(".empty") || document.body;
    const wrap = document.createElement("div");
    wrap.className = "empty-state";
    wrap.innerHTML = '<div>' + (icon || '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M20 13H8l-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z"/><polyline points="2 13 7 13 12 3 17 13"/><line x1="16" y1="17" x2="22" y2="17"/></svg>') + '</div><div class="empty-title">' + escapeHtml(title) + '</div>' +
      (sub ? '<div class="empty-sub">' + escapeHtml(sub) + '</div>' : '');
    return wrap.outerHTML;
  }
  function closeModal(modalOrHost) {
    let host = null;
    if (modalOrHost && typeof modalOrHost.closest === "function") {
      host = modalOrHost.matches && modalOrHost.matches(".modal-backdrop")
        ? modalOrHost
        : modalOrHost.closest(".modal-backdrop");
    }
    if (!host) {
      const stack = document.querySelectorAll(".modal-backdrop");
      host = stack.length ? stack[stack.length - 1] : null;
    }
    if (host) host.remove();
    return Boolean(host);
  }

  function bindModalDismissal(host) {
    host.addEventListener("click", function (event) {
      if (event.target === host) {
        closeModal(host);
        return;
      }
      const dismiss = event.target.closest
        ? event.target.closest("[data-modal-close], [data-modal-cancel]")
        : null;
      if (dismiss && host.contains(dismiss)) {
        event.preventDefault();
        closeModal(host);
      }
    });
  }

  function confirmDialog(message, onConfirm, onCancel, confirmText) {
    const host = document.createElement("div");
    host.className = "modal-backdrop";
    const modal = document.createElement("div");
    modal.className = "modal";
    modal.innerHTML = '<div class="modal-header"><h3></h3><button class="icon-btn" data-modal-close>&times;</button></div><div class="modal-body"><p class="muted"></p></div><div class="modal-footer"><button class="btn" data-modal-cancel>Cancel</button><button class="btn btn-danger" data-modal-confirm></button></div>';
    modal.querySelector("h3").textContent = message || "";
    modal.querySelector(".modal-body p").textContent = message || "";
    modal.querySelector("[data-modal-confirm]").textContent = confirmText || "Confirm";
    host.appendChild(modal);
    document.body.appendChild(host);

    let settled = false;
    const finish = (callback) => {
      if (settled) return;
      settled = true;
      host.remove();
      if (typeof callback === "function") {
        try {
          const result = callback();
          if (result && typeof result.catch === "function") {
            result.catch((error) => toast(error && error.message ? error.message : "The action could not be completed.", "error"));
          }
        } catch (error) {
          toast(error && error.message ? error.message : "The action could not be completed.", "error");
        }
      }
    };
    modal.querySelector("[data-modal-confirm]").addEventListener("click", () => finish(onConfirm));
    host.addEventListener("click", (event) => {
      if (event.target === host) {
        finish(onCancel);
        return;
      }
      const dismiss = event.target.closest
        ? event.target.closest("[data-modal-close], [data-modal-cancel]")
        : null;
      if (dismiss && host.contains(dismiss)) finish(onCancel);
    });
  }

  function bindModalAction(button, action, onError) {
    if (!button || typeof action !== "function") return;
    let busy = false;
    button.addEventListener("click", async (event) => {
      if (busy) {
        event.preventDefault();
        return;
      }
      busy = true;
      button.disabled = true;
      try {
        await action(event);
      } catch (error) {
        if (typeof onError === "function") {
          onError(error);
        } else {
          toast(error && error.message ? error.message : "The action could not be completed. Please try again.", "error");
        }
      } finally {
        busy = false;
        if (button.isConnected) button.disabled = false;
      }
    });
  }

  function openModal({ title, body, footer, wide } = {}) {
    const host = document.createElement("div");
    host.className = "modal-backdrop";
    const modal = document.createElement("div");
    modal.className = "modal" + (wide ? " wide" : "");
    modal.innerHTML = '<div class="modal-header"><h3></h3><button class="icon-btn" data-modal-close>&times;</button></div><div class="modal-body"></div><div class="modal-footer"></div>';
    modal.querySelector("h3").textContent = title || "";
    modal.querySelector(".modal-body").appendChild(body || document.createElement("div"));
    modal.querySelector(".modal-footer").appendChild(footer || document.createElement("div"));
    host.appendChild(modal);
    document.body.appendChild(host);
    bindModalDismissal(host);
    return modal;
  }

  async function api(method, url, body) {
    const options = { method, headers: { "Content-Type": "application/json" } };
    const token = document.querySelector('meta[name="csrf-token"]');
    if (token && token.content) options.headers["X-CSRF-Token"] = token.content;
    if (body !== undefined) options.body = JSON.stringify(body);
    const res = await fetch(url, { ...options, credentials: "same-origin" });
    let payload = null;
    try { payload = await res.json(); } catch (e) { payload = null; }
    if (res.status === 429) { toast(payload && payload.error && payload.error.message ? payload.error.message : "Too many requests. Please wait.", "info"); }
    if (res.status >= 400) {
      if (res.status === 401 && !location.pathname.startsWith("/login") && !location.pathname.startsWith("/reset")) {
        window.location.hash = "#/dashboard";
      }
      throw Object.assign(new Error((payload && payload.error && payload.error.message) || "Request failed"), { status: res.status, code: payload && payload.error ? payload.error.code : "error", data: payload });
    }
    return payload ? payload.data : null;
  }

  async function apiPost(url, body) { return api("POST", url, body); }
  async function apiPut(url, body) { return api("PUT", url, body); }
  async function apiDelete(url) { return api("DELETE", url); }
  async function apiGet(url) { return api("GET", url); }

  function currentDoctorId() {
    const me = state.user;
    if (me && me.doctor_id) return me.doctor_id;
    const q = location.hash.split("?")[0];
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const doctorId = params.get("doctor_id");
    if (doctorId) return doctorId;
    if (me && me.doctor_id) return me.doctor_id;
    if (me && me.is_super_admin) return null;
    if (me && (me.permissions || []).includes("tokens.manage_all")) return null;
    return me && me.doctor_id ? me.doctor_id : null;
  }

  function doctorQuery() {
    if (state.doctorScope) {
      const url = new URLSearchParams(location.hash.split("?")[1] || "");
      if (state.doctorScope) url.set("doctor_id", state.doctorScope);
      return url.toString();
    }
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    const doctorId = params.get("doctor_id");
    if (doctorId) return "doctor_id=" + encodeURIComponent(doctorId);
    return "";
  }

  function fmtMoney(value, currency) {
    const amount = Number(value || 0);
    const code = (state.clinic && state.clinic.settings && state.clinic.settings.currency) || "INR";
    const symbols = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED" };
    const symbol = symbols[code] || code + " ";
    return symbol + amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  }
  function fmtDateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
  }
  function timeAgo(value) {
    if (!value) return "";
    const then = new Date(value).getTime();
    if (isNaN(then)) return "";
    const diff = Date.now() - then;
    const mins = Math.round(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    const hours = Math.round(mins / 60);
    if (hours < 24) return hours + "h ago";
    const days = Math.round(hours / 24);
    if (days < 30) return days + "d ago";
    return fmtDate(value);
  }

  function initials(name) {
    const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
    const out = parts.slice(0, 2).map((p) => p[0] && p[0].toUpperCase()).join("");
    return out || "U";
  }

  function statusBadge(status) {
    const map = {
      waiting: "info", called: "amber", in_consultation: "violet", completed: "ok",
      skipped: "warn", cancelled: "danger", no_show: "danger", recalled: "teal",
      scheduled: "info", confirmed: "teal", rescheduled: "violet", completed_: "ok", cancelled_: "danger",
      paid: "ok", partial: "amber", unpaid: "danger", draft: "warn", refunded: "violet",
      active: "ok", inactive: "danger", cancelled_: "danger",
    };
    const key = status == null ? "" : String(status);
    const cls = map[key] || "info";
    return '<span class="badge ' + cls + '"><span class="dot"></span>' + escapeHtml(key.replace(/_/g, " ")) + "</span>";
  }

  function can(code) { return (state.permissions || []).includes(code); }

  function svgIcon(name, size) {
    const icons = {
      dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
      patients: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
      appointments: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
      queue: '<line x1="19" y1="5" x2="5" y2="5"/><line x1="19" y1="12" x2="5" y2="12"/><line x1="19" y1="19" x2="5" y2="19"/><circle cx="7" cy="5" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="7" cy="19" r="2"/>',
      consultations: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
      followups: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
      prescriptions: '<path d="M11 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><polyline points="7 4 7 4 7 7"/><path d="M11 4 7 4 7 7"/><path d="M15 21 15 21 15 18"/><path d="M11 21 11 18 11 21"/>',
      billing: '<rect x="2" y="4" width="20" height="16" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/>',
      pharmacy: '<path d="m7.5 4 9 5-9 5V4z"/><path d="m7.5 15 9 5-9 5V15z"/>',
      lab: '<path d="M9 3h6v18H9z"/><path d="M9 3 7.5 8M9 3l1.5 5M15 3l1.5 5M15 3 13.5 8"/><path d="M12 18v-6"/>',
      reports: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
      notifications: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
      doctors: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>',
      settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
      admin: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/><path d="M12 14v7"/>',
      logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
      logo: '<path d="M3 12l9-9 9 9v7H3z"/><path d="M12 22V12"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
      search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
      plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
      download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
      x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
      check: '<polyline points="20 6 9 17 4 12"/>',
      clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
      calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
      eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
      edit: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
      trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
      refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
      flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
      box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6 12 12.01 20.73 6"/><line x1="12" y1="22" x2="12" y2="12"/>',
      file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
      star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
      shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
      activity: '<polyline points="22 12 18 12 15 21 9 21 6 12 2 12 9 3 15 3 18 12 22 12"/>',
      history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    };
    const paths = icons[name] || icons.file;
    const sizeAttr = size || 18;
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:' + sizeAttr + 'px;height:' + sizeAttr + 'px">' + paths + '</svg>';
  }

  function setIcon(html, name, size) { return html; }

  function statusTone(status) {
    const value = String(status || "").toLowerCase();
    const tones = {
      waiting: "info", called: "amber", in_consultation: "violet", completed: "ok", skipped: "warn",
      cancelled: "danger", no_show: "danger", recalled: "teal", scheduled: "info", confirmed: "ok",
      paid: "ok", partial: "amber", unpaid: "danger", draft: "warn", refunded: "violet",
      active: "ok", inactive: "danger", pending: "warn", sent: "ok", failed: "danger", skipped_n: "warn",
    };
    return tones[value] || "info";
  }

  function toneClass(value) { return statusTone(value); }

  /* Charts (dependency free SVG) */
  function lineChart(container, points, options) {
    options = options || {};
    if (!container) return;
    const w = 560, h = 180, pad = 26;
    const data = points.data || points;
    if (!data || !data.length) return;
    const max = Math.max(1, ...data.map((d) => Number(d.value || 0)));
    const stepX = (w - pad * 2) / Math.max(1, data.length - 1);
    const coords = data.map((d, i) => [pad + i * stepX, h - pad - (Number(d.value || 0) / max) * (h - pad * 2)]);
    const path = coords.map((c, i) => (i ? "L" : "M") + c[0].toFixed(1) + " " + c[1].toFixed(1)).join(" ");
    const area = path + ` L${coords[coords.length - 1][0].toFixed(1)} ${h - pad} L${coords[0][0].toFixed(1)} ${h - pad} Z`;
    const gridLines = [0, 0.5, 1].map((f) => ({ y: h - pad - f * (h - pad * 2), v: max * f }));
    container.innerHTML = "";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("class", "chart-box");
    svg.innerHTML = gridLines.map((g) => `<line x1="${pad}" y1="${g.y}" x2="${w - pad}" y2="${g.y}" stroke="#e2e8f0" stroke-width="1"/>`).join("");
    svg.innerHTML += `<path d="${area}" fill="rgba(14,99,178,0.12)"/><path d="${path}" fill="none" stroke="#0e63b2" stroke-width="2.5" stroke-linecap="round"/>`;
    data.forEach((d, i) => {
      const c = coords[i];
      svg.innerHTML += `<circle cx="${c[0]}" cy="${c[1]}" r="3.2" fill="#fff" stroke="#0e63b2" stroke-width="2"/>`;
      if (i % Math.ceil(data.length / 7) === 0 || i === data.length - 1) {
        svg.innerHTML += `<text x="${c[0]}" y="${h - 8}" text-anchor="middle" font-size="10" fill="#64748b">${d.date || d.label || ""}</text>`;
      }
    });
    container.appendChild(svg);
    if (options.legend) {
      const legend = document.createElement("div");
      legend.className = "chart-legend mt8";
      legend.innerHTML = options.legend.map((l) => `<span class="key"><span class="swatch" style="background:${l.color}"></span>${l.label}</span>`).join("");
      container.appendChild(legend);
    }
  }
  function barChart(container, items, options) {
    options = options || {};
    if (!container) return;
    const w = 560, h = 180, pad = 26;
    const data = items.data || items;
    if (!data || !data.length) return;
    const max = Math.max(1, ...data.map((d) => Number(d.value || 0)));
    const bw = Math.min(42, ((w - pad * 2) / data.length) * 0.62);
    const step = (w - pad * 2) / data.length;
    let html = `<line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#e2e8f0"/><line x1="${pad}" y1="${pad / 2}" x2="${w - pad}" y2="${pad / 2}" stroke="#eef2f7"/>`;
    data.forEach((d, i) => {
      const bh = (Number(d.value || 0) / max) * (h - pad * 2);
      const x = pad + i * step + (step - bw) / 2;
      const y = h - pad - bh;
      html += `<rect x="${x}" y="${y}" width="${bw}" height="${Math.max(1, bh)}" rx="4" fill="${d.color || "#0e63b2"}"/>`;
      html += `<text x="${x + bw / 2}" y="${y - 5}" text-anchor="middle" font-size="10" fill="#475569">${Number(d.value || 0)}</text>`;
      html += `<text x="${x + bw / 2}" y="${h - 8}" text-anchor="middle" font-size="10" fill="#64748b">${String(d.date || d.label || "").slice(5)}</text>`;
    });
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("class", "chart-box");
    svg.innerHTML = html;
    container.innerHTML = "";
    container.appendChild(svg);
  }
  function donutChart(container, items) {
    if (!container) return;
    const data = items.data || items || [];
    const colors = ["#0e63b2", "#0d9488", "#b45309", "#6d28d9", "#dc2626", "#0369a1"];
    const total = data.reduce((s, d) => s + Number(d.value || 0), 0) || 1;
    const r = 60, cx = 70, cy = 70, circ = 2 * Math.PI * r;
    let offset = 0;
    let html = "";
    data.forEach((d, i) => {
      const frac = Number(d.value || 0) / total;
      const dash = frac * circ;
      html += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${colors[i % colors.length]}" stroke-width="16" stroke-dasharray="${dash} ${circ - dash}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
      offset += dash;
    });
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 150 150");
    svg.innerHTML = `<circle cx="75" cy="75" r="58" fill="none" stroke="#eef2f7" stroke-width="16"/><g>${html}</g><text x="75" y="71" text-anchor="middle" font-size="20" font-weight="700" fill="#0f172a">${total}</text><text x="75" y="88" text-anchor="middle" font-size="10" fill="#64748b">total</text></svg>`;
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function fmtTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  /* Router */
  const routes = {};
  function registerRoute(name, handler) { routes[name] = handler; }

  function currentPath() {
    const hash = location.hash || "#/dashboard";
    const clean = hash.replace(/^#/, "") || "/dashboard";
    const [path, query] = clean.split("?");
    const parts = path.split("/").filter(Boolean);
    const key = parts[0] || "dashboard";
    return { key, parts, query: new URLSearchParams(query || "") };
  }

  let lastNavHash = null;

  async function navigate(path, params) {
    path = String(path || "").replace(/^#+/, "");
    if (!path.startsWith("/")) path = "/" + path;
    if (params) {
      const url = new URLSearchParams(location.hash.split("?")[1] || "");
      Object.entries(params).forEach(([k, v]) => url.set(k, v));
      location.hash = "#" + path + (url.toString() ? "?" + url.toString() : "");
    } else {
      location.hash = "#" + path;
    }
    lastNavHash = location.hash;
    await routeChange();
  }

  let navToken = 0;

  async function routeChange() {
    const { key, parts } = currentPath();
    state.page = key;
    const titleEl = document.querySelector("#page-title");
    const subEl = document.querySelector("#page-sub");
    if (titleEl) titleEl.textContent = titleFor(key);
    if (subEl) subEl.textContent = subtitleFor(key);
    // Update sidebar active state
    document.querySelectorAll("[data-nav]").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-nav") === key);
    });
    const myToken = ++navToken;
    const host = document.querySelector("#page-content");
    if (!host) return;
    host.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
    try {
      if (routes[key]) {
        state.routeParams = Object.fromEntries(parts.slice(1).map((p, i) => [parts[i - 1] || "id", p]));
        await routes[key].render(state.routeParams);
      } else if (key === "prescriptions") {
        await routes["consultations"].render(state.routeParams);
      } else {
        host.innerHTML = '<div class="empty-state"><div class="empty-title">Page not found</div><div class="empty-sub">The requested page does not exist.</div></div>';
      }
    } catch (e) {
      if (myToken !== navToken) return;
      const msg = (e && e.message) ? e.message : "Please try again.";
      host.innerHTML = '<div class="empty-state"><div class="empty-title">Something went wrong</div><div class="empty-sub">' + escapeHtml(msg) + '</div><button class="btn mt16" onclick="window.ClinicFlow.navigate(window.location.hash || \'#/dashboard\')">Retry</button></div>';
    }
    const overlay = host.querySelector(".loading-overlay");
    if (overlay) overlay.remove();
  }

  function subscribeRouting() {
    window.addEventListener("hashchange", () => {
      if (lastNavHash && location.hash === lastNavHash) {
        lastNavHash = null;
        return;
      }
      lastNavHash = null;
      routeChange();
    });
  }

  /* Shell rendering */
  function sidebarGroups() {
    const user = state.user;
    const groups = [];
    if ((user.permissions || []).includes("platform.view")) {
      groups.push({ label: "Platform", items: [["admin", "Clinics", "admin"]] });
    }
    groups.push(
      { label: "Overview", items: [["dashboard", "Dashboard", "dashboard"]] },
      { label: "Patients", items: [["patients", "Patients", "patients"]] },
      { label: "Queue", items: [["appointments", "Appointments", "calendar"], ["queue", "Token Queue", "queue"]] },
      {
        label: "Clinical",
        items: [
          ["consultations", "Consultations", "consultations"],
          ["followups", "Follow-ups", "followups"],
          ["prescriptions", "Prescriptions", "prescriptions"],
        ],
      },
      {
        label: "Financial",
        items: [["billing", "Billing", "billing"], ["pharmacy", "Pharmacy", "pharmacy"], ["lab", "Laboratory", "lab"], ["reports", "Reports", "reports"]],
      },
      { label: "Operations", items: [["doctors", "Doctors", "doctors"], ["notifications", "Notifications", "notifications"], ["settings", "Settings", "settings"]] },
    );
    return groups;
  }

  function shell() {
    const host = $("#app-root");
    if (!host) return;
    host.innerHTML = '<div class="app-shell">' +
      '<aside class="sidebar">' +
        '<div class="brand"><div class="brand-mark">CF</div><div><div class="brand-name">ClinicFlow</div><div class="brand-sub">Clinic Suite</div></div></div>' +
        '<div id="clinicflow-nav"></div>' +
        '<div class="sidebar-footer"><button class="nav-item" id="shell-logout"><span class="label">Sign out</span>' + window.ClinicFlow.icon("logout", 18) + '</button></div>' +
      '</aside>' +
      '<div class="main">' +
        '<header class="topbar">' +
          '<div class="grow"><h1 id="page-title">Dashboard</h1><div class="muted small" id="page-sub">Clinic workspace</div></div>' +
          '<button class="icon-btn bell-btn" id="shell-bell" title="Notifications">' + window.ClinicFlow.icon("bell", 17) + '<span class="bell-count hidden" id="bell-count">0</span></button>' +
          '<div class="row"><div class="avatar lg" id="top-avatar">U</div><div><div id="top-name" style="font-weight:700;font-size:13px">User</div><div class="muted small" id="top-role">Clinic</div></div></div>' +
        '</header>' +
        '<main class="content" id="page-content"><div class="loading-overlay"><div class="spinner"></div></div></main>' +
      '</div>' +
      '</div>';
    const navHost = $("#clinicflow-nav");
    const groups = sidebarGroups();
    navHost.innerHTML = groups.map((g) => {
      const items = g.items.map((i) => {
        const active = state.page === i[0] ? " nav-item active" : " nav-item";
        const label = g.label === "Overview" && i[0] === "dashboard" ? "Dashboard" : i[1];
        const iconName = i[2];
        return '<button class="nav-item' + (state.page === i[0] ? " active" : "") + '" data-nav="' + i[0] + '">' + window.ClinicFlow.icon(iconName, 18) + '<span class="label">' + label + '</span></button>';
      }).join("");
      const label = g.label === "Overview" ? "" : '<div class="nav-group-label">' + g.label + '</div>';
      return label + '<div class="nav-group">' + items + '</div>';
    }).join("");
    navHost.querySelectorAll("[data-nav]").forEach((el) => {
      el.addEventListener("click", () => navigate("#/" + el.getAttribute("data-nav")));
    });
    $("#shell-logout").addEventListener("click", async () => {
      try { await api("POST", "/api/auth/logout"); } catch (e) {}
      sessionStorage.clear();
      window.location.hash = "#/dashboard";
      window.location.href = "/login";
    });
    $("#shell-bell").addEventListener("click", async () => {
      await navigate("#/notifications");
    });
    if (state.user) {
      $("#top-avatar").textContent = state.user.initials || "U";
      $("#top-name").textContent = state.user.full_name || "User";
      $("#top-role").textContent = state.user.role ? state.user.role.name : "Clinic";
    }
  }

  async function refreshShell() {
    shell();
    $("#page-title").textContent = titleFor(state.page);
    $("#page-sub").textContent = subtitleFor(state.page);
  }
  function titleFor(page) {
    const map = {
      dashboard: "Dashboard", patients: "Patients", appointments: "Appointments", queue: "Token Queue",
      followups: "Follow-ups", consultations: "Consultations", prescriptions: "Prescriptions", billing: "Billing",
      pharmacy: "Pharmacy", lab: "Laboratory", reports: "Reports", notifications: "Notifications",
      doctors: "Doctors", settings: "Settings", admin: "Clinics",
    };
    return map[page] || "ClinicFlow";
  }
  function subtitleFor(page) {
    const map = {
      dashboard: "Today at a glance", patients: "Registered patients", appointments: "Appointments",
      queue: "Live waiting room", followups: "Follow-up care", consultations: "Clinical consultations",
      prescriptions: "Medication records", billing: "Invoices, payments and refunds",
      pharmacy: "Medicines and stock", lab: "Laboratory workflow", reports: "Operational reports",
      notifications: "Inbox and delivery", doctors: "Clinical staff", settings: "Clinic configuration", admin: "Platform clinics",
    };
    return map[page] || "";
  }

  async function init() {
    const me = await apiGet("/api/auth/me");
    state.user = me.user;
    state.clinic = me.user.clinic;
    state.permissions = me.user.permissions || [];
    state.initialized = true;
    shell();
    $("#page-title").textContent = titleFor(state.page);
    $("#page-sub").textContent = subtitleFor(state.page);
    await routeChange();
    setInterval(async () => { try { const unread = await apiGet("/api/notifications/unread-count"); const el = $("#bell-count"); if (el) { el.textContent = String(unread.count || 0); el.classList.toggle("hidden", !(unread.count || 0)); } } catch (e) {} }, 30000);
  }

  async function boot() {
    subscribeRouting();
    if (location.pathname === "/login" || location.pathname === "/forgot-password" || location.pathname === "/reset-password" || location.pathname === "/setup") {
      return;
    }
    await init();
  }

  window.ClinicFlow = window.ClinicFlow || {};
  window.ClinicFlow.App = window.ClinicFlow.App || {};
  window.ClinicFlow.App.boot = boot;
  window.ClinicFlow.api = api;
  window.ClinicFlow.navigate = navigate;
  window.ClinicFlow.state = state;
  window.ClinicFlow.registerRoute = registerRoute;
  window.ClinicFlow.toast = toast;
  window.ClinicFlow.closeModal = closeModal;
  window.ClinicFlow.openModal = openModal;
  window.ClinicFlow.confirmDialog = confirmDialog;
  window.ClinicFlow.bindModalAction = bindModalAction;
  window.ClinicFlow.showLoading = showLoading;
  window.ClinicFlow.hideLoading = hideLoading;
  window.ClinicFlow.emptyState = emptyState;
  window.ClinicFlow.fmtMoney = fmtMoney;
  window.ClinicFlow.fmtDate = fmtDate;
  window.ClinicFlow.fmtDateTime = fmtDateTime;
  window.ClinicFlow.timeAgo = timeAgo;
  window.ClinicFlow.initials = initials;
  window.ClinicFlow.can = can;
  window.ClinicFlow.statusTone = statusTone;
  window.ClinicFlow.toneClass = toneClass;
  window.ClinicFlow.statusBadge = statusBadge;
  window.ClinicFlow.fmtTime = fmtTime;
  window.ClinicFlow.currentDoctorId = currentDoctorId;
  window.ClinicFlow.doctorQuery = doctorQuery;
  window.ClinicFlow.lineChart = lineChart;
  window.ClinicFlow.barChart = barChart;
  window.ClinicFlow.donutChart = donutChart;
  window.ClinicFlow.refreshShell = refreshShell;
  window.ClinicFlow.titleFor = titleFor;
  window.ClinicFlow.subtitleFor = subtitleFor;
  window.ClinicFlow.escapeHtml = escapeHtml;
  window.ClinicFlow.apiPost = apiPost;
  window.ClinicFlow.apiPut = apiPut;
  window.ClinicFlow.apiDelete = apiDelete;
  window.ClinicFlow.apiGet = apiGet;

  // Expose the DOM query shorthand used by page modules (vanilla JS, not jQuery).
  window.$ = $;
  window.ClinicFlow.$ = $;

  function icon(name, size) {
    const icons = {
      dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
      patients: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
      calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
      queue: '<line x1="19" y1="5" x2="5" y2="5"/><line x1="19" y1="12" x2="5" y2="12"/><line x1="19" y1="19" x2="5" y2="19"/><circle cx="7" cy="5" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="7" cy="19" r="2"/>',
      consultations: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
      followups: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
      prescriptions: '<path d="M11 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><polyline points="7 4 7 4 7 7"/><path d="M11 4 7 4 7 7"/><path d="M15 21 15 21 15 18"/><path d="M11 21 11 18 11 21"/>',
      billing: '<rect x="2" y="4" width="20" height="16" rx="2"/><line x1="2" y1="9" x2="22" y2="9"/>',
      pharmacy: '<path d="m7.5 4 9 5-9 5V4z"/><path d="m7.5 15 9 5-9 5V15z"/>',
      lab: '<path d="M9 3h6v18H9z"/><path d="M9 3 7.5 8M9 3l1.5 5M15 3l1.5 5M15 3 13.5 8"/><path d="M12 18v-6"/>',
      reports: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
      notifications: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
      doctors: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>',
      settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
      admin: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/><path d="M12 14v7"/>',
      logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
      bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
      search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
      plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
      download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
      x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
      check: '<polyline points="20 6 9 17 4 12"/>',
      clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
      eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
      edit: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
      trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
      refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
      shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
      activity: '<polyline points="22 12 18 12 15 21 9 21 6 12 2 12 9 3 15 3 18 12 22 12"/>',
      history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
      flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/>',
      box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6 12 12.01 20.73 6"/><line x1="12" y1="22" x2="12" y2="12"/>',
      file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
      star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
      user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
      phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
      mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
      map: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
      heart: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z"/>',
      warning: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
      info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
      success: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
      block: '<circle cx="12" cy="12" r="10"/><line x1="4.97" y1="4.97" x2="9.88" y2="9.88"/><line x1="14.12" y1="14.12" x2="19.03" y2="19.03"/><line x1="14.12" y1="9.88" x2="19.03" y2="4.97"/><line x1="9.88" y1="14.12" x2="4.97" y2="19.03"/>',
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:' + (size || 18) + 'px;height:' + (size || 18) + 'px">' + (icons[name] || icons.file) + '</svg>';
  }
  window.ClinicFlow.icon = icon;

  window.ClinicFlow.renderShell = refreshShell;
})();

window.ClinicFlow.boot = async function () {
  const path = window.location.pathname;
  const isAuthPage = ["/login", "/forgot-password", "/reset-password", "/setup"].some((p) => path.startsWith(p));
  if (isAuthPage) {
    return;
  }
  await window.ClinicFlow.App.boot();
};
