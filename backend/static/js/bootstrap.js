document.addEventListener("DOMContentLoaded", () => {
  const check = () => {
    if (document.querySelector("#app-root")) {
      window.ClinicFlow.boot();
    }
  };
  check();
});
