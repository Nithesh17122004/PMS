document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("#login-form");
  const errorBox = document.querySelector("#login-error");
  const email = document.querySelector("#login-email");
  const password = document.querySelector("#login-password");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.textContent = "";
    if (!email.value || !password.value) { errorBox.textContent = "Enter your email and password."; return; }
    try {
      const res = await window.ClinicFlow.apiPost("/api/auth/login", { email: email.value.trim(), password: password.value });
      const user = res.user;
      window.ClinicFlow.state.user = user;
      window.ClinicFlow.state.clinic = user.clinic;
      window.ClinicFlow.state.permissions = user.permissions || [];
      window.ClinicFlow.toast("Welcome back, " + (user.full_name || "user"), "ok");
      window.location.hash = "#/dashboard";
      await window.ClinicFlow.navigate("#/dashboard");
    } catch (err) {
      errorBox.textContent = err.message || "Sign in failed.";
      const attempts = err.data && err.data.error && err.data.error.details ? err.data.error.details.attempts : null;
      if (attempts) { errorBox.textContent = "Too many failed attempts. Account temporarily locked."; }
    }
  });
});
