document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("#reset-form");
  const errorBox = document.querySelector("#reset-error");
  const token = document.querySelector("#reset-token");
  const newPassword = document.querySelector("#reset-new-password");
  const confirm = document.querySelector("#reset-confirm");
  if (!form) return;
  if (token) token.value = new URLSearchParams(window.location.search).get("token") || "";
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.textContent = "";
    const tokenValue = token ? token.value.trim() : "";
    const password = newPassword ? newPassword.value : "";
    if (!tokenValue) { errorBox.textContent = "Reset token is missing. Open the link from your email."; return; }
    if (password !== (confirm ? confirm.value : password)) { errorBox.textContent = "Passwords do not match."; return; }
    try {
      const res = await window.ClinicFlow.apiPost("/api/auth/reset-password", { token: tokenValue, new_password: password });
      window.ClinicFlow.toast(res.message || "Password reset successfully.", "ok");
      setTimeout(() => { window.location.href = "/login"; }, 900);
    } catch (err) { errorBox.textContent = err.message || "Reset failed."; }
  });
});
