document.addEventListener("DOMContentLoaded", async () => {
  const form = document.querySelector("#forgot-form");
  const email = document.querySelector("#forgot-email");
  const message = document.querySelector("#forgot-message");
  const demoUrl = document.querySelector("#forgot-demo-url");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    message.textContent = "";
    if (!email || !email.value) { message.textContent = "Enter your account email."; return; }
    try {
      const res = await window.ClinicFlow.apiPost("/api/auth/forgot-password", { email: email.value.trim() });
      message.textContent = res.message || "If an account exists, a reset link was sent.";
      if (demoUrl && res.demo_reset_url) demoUrl.value = res.demo_reset_url;
    } catch (err) { message.textContent = err.message || "Reset request failed."; }
  });
});
