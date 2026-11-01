const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const coreSource = fs.readFileSync(
  path.join(__dirname, "../../backend/static/js/core.js"),
  "utf8"
);

function createClinicFlow() {
  const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", {
    runScripts: "outside-only",
    url: "https://clinicflow.test/"
  });
  dom.window.eval(coreSource);
  return { dom, api: dom.window.ClinicFlow };
}

test("dynamically appended Cancel button closes its modal", () => {
  const { dom, api } = createClinicFlow();
  const modal = api.openModal({ title: "Dynamic footer" });
  const footer = modal.querySelector(".modal-footer");
  footer.innerHTML = '<button type="button" data-modal-cancel>Cancel</button>';
  footer.querySelector("[data-modal-cancel]").click();
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 0);
  dom.window.close();
});

test("close icon closes the top modal", () => {
  const { dom, api } = createClinicFlow();
  const modal = api.openModal({ title: "Close icon" });
  modal.querySelector("[data-modal-close]").click();
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 0);
  dom.window.close();
});

test("backdrop click closes only the clicked modal", () => {
  const { dom, api } = createClinicFlow();
  const parent = api.openModal({ title: "Parent" });
  const child = api.openModal({ title: "Child" });
  const childHost = child.closest(".modal-backdrop");
  childHost.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 1);
  assert.equal(parent.isConnected, true);
  dom.window.close();
});

test("nested modal Cancel returns to the parent modal", () => {
  const { dom, api } = createClinicFlow();
  const parent = api.openModal({ title: "Doctor details" });
  const child = api.openModal({ title: "Doctor schedule" });
  const footer = child.querySelector(".modal-footer");
  footer.innerHTML = '<button type="button" data-modal-cancel>Cancel</button>';
  footer.querySelector("[data-modal-cancel]").click();
  assert.equal(parent.isConnected, true);
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 1);
  api.closeModal();
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 0);
  dom.window.close();
});

test("Confirm does not close a normal modal before async work succeeds", async () => {
  const { dom, api } = createClinicFlow();
  const modal = api.openModal({ title: "Save" });
  const footer = modal.querySelector(".modal-footer");
  footer.innerHTML = '<button type="button" data-modal-confirm>Save</button>';
  const button = footer.querySelector("[data-modal-confirm]");
  button.addEventListener("click", async () => {
    try {
      await Promise.reject(new Error("simulated request failure"));
    } catch (_) {
      // The page reports the error and intentionally keeps the modal open.
    }
  });
  button.click();
  await Promise.resolve();
  assert.equal(modal.isConnected, true);
  dom.window.close();
});

test("confirmation dialog invokes its confirm callback only once", () => {
  const { dom, api } = createClinicFlow();
  let calls = 0;
  api.confirmDialog("Confirm once?", () => { calls += 1; });
  const button = dom.window.document.querySelector(".modal-backdrop [data-modal-confirm]");
  button.click();
  button.click();
  assert.equal(calls, 1);
  dom.window.close();
});


test("confirmation dialog stays open after a failed async action and can retry", async () => {
  const { dom, api } = createClinicFlow();
  let attempts = 0;
  api.confirmDialog("Run action?", async () => {
    attempts += 1;
    if (attempts === 1) throw new Error("Temporary failure");
  });
  const host = dom.window.document.querySelector(".modal-backdrop");
  const button = host.querySelector("[data-modal-confirm]");
  button.click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(host.isConnected, true);
  assert.equal(host.querySelector("[data-confirm-error]").textContent, "Temporary failure");
  assert.equal(button.disabled, false);
  button.click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(attempts, 2);
  assert.equal(dom.window.document.querySelectorAll(".modal-backdrop").length, 0);
  dom.window.close();
});

test("bindModalAction blocks duplicate submissions and reports rejection", async () => {
  const { dom, api } = createClinicFlow();
  const modal = api.openModal({ title: "Guarded action" });
  const footer = modal.querySelector(".modal-footer");
  footer.innerHTML = '<button type="button" data-modal-confirm>Save</button><div data-error></div>';
  const button = footer.querySelector("[data-modal-confirm]");
  const error = footer.querySelector("[data-error]");
  let calls = 0;
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  api.bindModalAction(button, async () => {
    calls += 1;
    await pending;
    throw new Error("Save failed");
  }, (reason) => { error.textContent = reason.message; });
  button.click();
  button.click();
  assert.equal(calls, 1);
  assert.equal(button.disabled, true);
  release();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(error.textContent, "Save failed");
  assert.equal(button.disabled, false);
  assert.equal(modal.isConnected, true);
  dom.window.close();
});
