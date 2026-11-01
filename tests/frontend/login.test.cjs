const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const loginSource = fs.readFileSync(
  path.join(__dirname, "../../backend/static/js/login.js"),
  "utf8"
);

test("login submits the password field value, not the input element", async () => {
  const dom = new JSDOM(
    `<!doctype html><html><body>
      <form id="login-form">
        <input id="login-email" type="email"/>
        <input id="login-password" type="password"/>
        <div id="login-error"></div>
        <button type="submit">Sign in</button>
      </form>
    </body></html>`,
    { runScripts: "outside-only", url: "https://clinicflow.test/login" }
  );

  const { window } = dom;
  let submitted = null;
  window.ClinicFlow = {
    state: {},
    apiPost: async (url, payload) => {
      assert.equal(url, "/api/auth/login");
      submitted = payload;
      return {
        user: {
          full_name: "Test User",
          clinic: { id: "clinic-1" },
          permissions: ["dashboard.view"]
        }
      };
    },
    toast: () => {},
    navigate: async () => {}
  };

  window.document.querySelector("#login-email").value = "user@example.test";
  window.document.querySelector("#login-password").value = "Correct@Test123";

  const domReady = new Promise((resolve) => {
    window.document.addEventListener("DOMContentLoaded", resolve, { once: true });
  });
  window.eval(loginSource);
  await domReady;

  const form = window.document.querySelector("#login-form");
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(
    { email: submitted.email, password: submitted.password },
    { email: "user@example.test", password: "Correct@Test123" }
  );
  assert.equal(typeof submitted.password, "string");
  dom.window.close();
});
