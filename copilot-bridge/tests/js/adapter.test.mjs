/*
 * Exercises copilot_bridge/profiles/default.js against a fake chat DOM.
 *
 *   npm install jsdom
 *   node tests/js/adapter.test.mjs
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url));
const ADAPTER = readFileSync(join(here, "..", "..", "copilot_bridge", "profiles", "default.js"), "utf8");

let passed = 0;
function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  ok   ${name}`);
  } catch (err) {
    console.error(`  FAIL ${name}\n       ${err.message}`);
    process.exitCode = 1;
  }
}

/** jsdom gives every element a 0x0 rect, which would make isVisible() false. */
function makeVisible(win) {
  win.Element.prototype.getBoundingClientRect = function () {
    const tag = this.tagName;
    const wide = tag === "TEXTAREA" || this.getAttribute("contenteditable") !== null;
    return { width: wide ? 600 : 40, height: wide ? 60 : 30, top: wide ? 700 : 100, left: 0, right: 0, bottom: 0 };
  };
}

function build(bodyHtml, { composer = "contenteditable" } = {}) {
  const composerHtml =
    composer === "textarea"
      ? '<textarea id="composer"></textarea>'
      : '<div id="composer" contenteditable="true"></div>';
  const dom = new JSDOM(
    `<!doctype html><html><body><main>${bodyHtml}</main>
     <footer>${composerHtml}<button aria-label="Nachricht senden" id="send">go</button></footer>
     </body></html>`,
    { runScripts: "outside-only", url: "https://copilot.microsoft.com/chats/1" }
  );
  makeVisible(dom.window);
  dom.window.eval(ADAPTER);
  return dom.window;
}

const TRANSCRIPT = `
  <div data-content="user-message">Liste bitte meinen Desktop auf</div>
  <div data-content="ai-message">
    <p>Klar, hier der Aufruf:</p>
    <pre><code class="language-json">{"bridge": 1, "tool": "fs.list", "args": {"path": "%USERPROFILE%\\\\Desktop"}, "id": "c1"}</code></pre>
  </div>`;

test("installs and reports a version", () => {
  const win = build(TRANSCRIPT);
  assert.equal(typeof win.__copilotBridge, "object");
  assert.ok(win.__copilotBridge.version >= 4);
});

test("read() finds both turns with roles", () => {
  const win = build(TRANSCRIPT);
  const data = win.__copilotBridge.read("");
  assert.equal(data.strategy, 'selector:[data-content="ai-message"], [data-content="user-message"]');
  assert.equal(data.messages.length, 2);
  assert.equal(data.messages[0].role, "user");
  assert.equal(data.messages[1].role, "assistant");
  assert.match(data.messages[1].text, /Klar, hier der Aufruf/);
});

test("read() extracts the code block with its language", () => {
  const win = build(TRANSCRIPT);
  const assistant = win.__copilotBridge.read("").messages[1];
  assert.equal(assistant.code.length, 1);
  assert.equal(assistant.code[0].lang, "json");
  const payload = JSON.parse(assistant.code[0].text);
  assert.equal(payload.tool, "fs.list");
  assert.equal(payload.id, "c1");
});

test("a <code> inside a <pre> is not counted twice", () => {
  const win = build(TRANSCRIPT);
  const assistant = win.__copilotBridge.read("").messages[1];
  assert.equal(assistant.code.length, 1);
});

test("pierces shadow DOM", () => {
  const win = build('<div id="host"></div>');
  const host = win.document.getElementById("host");
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = '<div data-content="ai-message">versteckte Antwort</div>';
  makeVisible(win);
  const data = win.__copilotBridge.read("");
  assert.equal(data.messages.length, 1);
  assert.match(data.messages[0].text, /versteckte Antwort/);
});

test("falls back to the structural heuristic", () => {
  const win = build(`
    <div class="thread">
      <div class="x">Eine Frage von mir, lang genug um als echter Turn zu zaehlen.</div>
      <div class="x">Eine Antwort, ebenfalls lang genug fuer die Heuristik an dieser Stelle.</div>
    </div>`);
  const data = win.__copilotBridge.read("");
  assert.equal(data.strategy, "heuristic");
  assert.equal(data.messages.length, 2);
});

test("the heuristic stays quiet on a page with only short text", () => {
  const win = build('<div class="thread"><div>ja</div><div>nein</div></div>');
  const data = win.__copilotBridge.read("");
  assert.equal(data.strategy, "none");
  assert.equal(data.messages.length, 0);
});

test("a custom selector wins over the built-in chain", () => {
  const win = build('<article class="turn">Antwort per eigenem Selektor</article>' + TRANSCRIPT);
  const data = win.__copilotBridge.read(".turn");
  assert.equal(data.strategy, "selector:.turn");
  assert.equal(data.messages.length, 1);
});

test("send() fills a contenteditable composer and clicks send", () => {
  const win = build(TRANSCRIPT);
  let clicked = false;
  win.document.getElementById("send").addEventListener("click", () => (clicked = true));
  const result = win.__copilotBridge.send("Ergebnis: ok", true);
  assert.equal(result.ok, true);
  assert.equal(result.clicked, true);
  assert.equal(clicked, true);
  assert.equal(win.document.getElementById("composer").textContent, "Ergebnis: ok");
});

test("send() uses the native value setter for a textarea", () => {
  const win = build(TRANSCRIPT, { composer: "textarea" });
  let inputEvents = 0;
  win.document.getElementById("composer").addEventListener("input", () => (inputEvents += 1));
  const result = win.__copilotBridge.send("hallo", false);
  assert.equal(result.method, "native-value");
  assert.equal(win.document.getElementById("composer").value, "hallo");
  assert.equal(inputEvents, 1);
  assert.equal(result.clicked, false);
});

test("send() reports when there is no composer", () => {
  const dom = new JSDOM("<!doctype html><html><body><p>leer</p></body></html>", {
    runScripts: "outside-only",
    url: "https://copilot.microsoft.com/",
  });
  makeVisible(dom.window);
  dom.window.eval(ADAPTER);
  const result = dom.window.__copilotBridge.send("x", true);
  assert.equal(result.ok, false);
  assert.match(result.error, /no composer/);
});

test("probe() reports selector hit counts and the send button", () => {
  const win = build(TRANSCRIPT);
  const info = win.__copilotBridge.probe("");
  assert.equal(info.sendButton, "Nachricht senden");
  assert.ok(info.selectorCounts.some((c) => c.hits === 2));
  assert.equal(info.preview.at(-1).codeBlocks, 1);
});

test("re-running the adapter does not reinstall", () => {
  const win = build(TRANSCRIPT);
  assert.equal(win.eval(ADAPTER), "already-installed");
});

console.log(`\n${passed} passed`);
