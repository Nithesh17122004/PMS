document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#setup-form");
  const errorBox = document.querySelector("#setup-error");
  const submit = document.querySelector("#setup-submit");
  const toggle = document.querySelector("#setup-toggle-password");
  const password = document.querySelector("#setup-password");
  if (toggle && password) {
    toggle.addEventListener("click", () => {
      const isPwd = password.type === "password";
      password.type = isPwd ? "text" : "password";
      toggle.textContent = isPwd ? "Hide" : "Show";
    });
  }
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.textContent = "";
    const clinicName = document.querySelector("#setup-clinic-name").value.trim();
    const clinicEmail = document.querySelector("#setup-clinic-email").value.trim();
    const adminName = document.querySelector("#setup-admin-name").value.trim();
    const adminEmail = document.querySelector("#setup-admin-email").value.trim();
    const pwd = password.value;
    const confirm = document.querySelector("#setup-confirm").value;
    if (!clinicName || !clinicEmail || !adminName || !adminEmail || !pwd || !confirm) {
      errorBox.textContent = "All required fields must be filled in.";
      return;
    }
    if (pwd !== confirm) {
      errorBox.textContent = "Passwords do not match.";
      return;
    }
    submit.disabled = true;
    submit.textContent = "Creating…";
    try {
      const res = await window.ClinicFlow.apiPost("/api/setup", {
        clinic_name: clinicName,
        clinic_email: clinicEmail,
        clinic_phone: document.querySelector("#setup-clinic-phone").value.trim() || null,
        clinic_address: document.querySelector("#setup-clinic-address").value.trim() || null,
        admin_name: adminName,
        admin_email: adminEmail,
        password: pwd,
        confirm_password: confirm,
      });
      window.ClinicFlow.toast("Clinic created. Welcome!", "ok");
      window.location.href = (res && res.redirect) || "/app";
    } catch (err) {
      errorBox.textContent = err.message || "Setup failed.";
      if (err.status === 409) {
        setTimeout(() => { window.location.href = "/login"; }, 1200);
      }
    } finally {
      submit.disabled = false;
      submit.textContent = "Create clinic and administrator";
    }
  });
});
