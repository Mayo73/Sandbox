/*
 * Page adapter for the Copilot bridge.
 *
 * Installs window.__copilotBridge with:
 *   read()      -> { url, strategy, messages: [{index, role, text, code[]}], composer }
 *   send(text)  -> { ok, method }
 *   probe()     -> diagnostics for tuning selectors
 *
 * Copilot's markup changes often. The chain is: configured selector ->
 * known selectors -> structural heuristic. probe() shows which one hit.
 */
(function () {
  var VERSION = 4;
  if (window.__copilotBridge && window.__copilotBridge.version === VERSION) {
    return "already-installed";
  }

  var MESSAGE_SELECTORS = [
    '[data-content="ai-message"], [data-content="user-message"]',
    "[data-message-author-role]",
    '[data-testid="chat-message"]',
    '[data-testid*="message"]:not([data-testid*="composer"])',
    "cib-message",
    '[class*="userMessage"], [class*="aiMessage"]',
    '[class*="chat-message"]',
    'main [role="listitem"]',
    '[role="log"] > *',
  ];

  var COMPOSER_SELECTORS =
    'textarea, [contenteditable="true"], [contenteditable=""], [role="textbox"]';

  var SEND_WORDS = [
    "send", "submit", "senden", "absenden", "abschicken", "nachricht senden",
  ];

  // ---------------------------------------------------------------- helpers
  function deepNodes(root, limit) {
    var out = [];
    var stack = [root];
    var cap = limit || 40000;
    while (stack.length && out.length < cap) {
      var node = stack.pop();
      if (!node) continue;
      out.push(node);
      if (node.shadowRoot) stack.push(node.shadowRoot);
      var kids = node.children;
      if (kids) {
        for (var i = kids.length - 1; i >= 0; i--) stack.push(kids[i]);
      }
    }
    return out;
  }

  function deepQueryAll(selector) {
    var light = [];
    try {
      light = Array.prototype.slice.call(document.querySelectorAll(selector));
    } catch (e) {
      return [];
    }
    if (light.length) return light;
    // Only pay for the full walk when the light DOM had nothing.
    return deepNodes(document.documentElement).filter(function (node) {
      try {
        return node.matches && node.matches(selector);
      } catch (e) {
        return false;
      }
    });
  }

  function isVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return false;
    var style = window.getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none" && style.opacity !== "0";
  }

  // innerText is what the user sees; jsdom and detached nodes only expose
  // textContent, so fall back to it instead of reading undefined.
  function rawText(el) {
    if (!el) return "";
    var text = el.innerText;
    if (text === undefined || text === null) text = el.textContent;
    return String(text || "").replace(/\u00a0/g, " ");
  }

  function textOf(el) {
    return rawText(el).trim();
  }

  function codeBlocksOf(el) {
    var blocks = [];
    var nodes = [];
    try {
      nodes = Array.prototype.slice.call(el.querySelectorAll("pre, code"));
    } catch (e) {
      nodes = [];
    }
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      // Skip <code> that sits inside a <pre> we already took.
      if (node.tagName === "CODE" && node.closest && node.closest("pre")) continue;
      var body = rawText(node);
      if (!body.trim()) continue;
      var lang = "";
      var probe = node.tagName === "PRE" ? node.querySelector("code") || node : node;
      var cls = (probe.className || "") + " " + (node.className || "");
      var match = /language-([\w+-]+)/.exec(cls);
      if (match) lang = match[1];
      if (!lang && node.dataset) lang = node.dataset.language || node.dataset.lang || "";
      blocks.push({ lang: String(lang).toLowerCase(), text: body });
    }
    return blocks;
  }

  function roleOf(el) {
    var attrs = [
      el.getAttribute && el.getAttribute("data-message-author-role"),
      el.getAttribute && el.getAttribute("data-content"),
      el.getAttribute && el.getAttribute("data-author"),
      el.getAttribute && el.getAttribute("data-role"),
      el.getAttribute && el.getAttribute("aria-label"),
      el.className && typeof el.className === "string" ? el.className : "",
      el.tagName || "",
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (/\b(user|human)\b|user-message|usermessage|you said|sie sagten|du sagtest/.test(attrs)) {
      return "user";
    }
    if (/\b(assistant|bot|ai|copilot)\b|ai-message|aimessage/.test(attrs)) {
      return "assistant";
    }
    // Avatar alt text is a decent second signal.
    var img = el.querySelector && el.querySelector("img[alt]");
    if (img) {
      var alt = (img.getAttribute("alt") || "").toLowerCase();
      if (/copilot|assistant|bing/.test(alt)) return "assistant";
      if (/you|user|profil|profile/.test(alt)) return "user";
    }
    return "unknown";
  }

  function collect(nodes, strategy) {
    var messages = [];
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var text = textOf(el);
      if (!text) continue;
      messages.push({
        index: messages.length,
        role: roleOf(el),
        text: text,
        code: codeBlocksOf(el),
      });
    }
    return { strategy: strategy, messages: messages };
  }

  // Last resort: find the container whose children look like a transcript.
  function heuristic() {
    var best = null;
    var nodes = deepNodes(document.body || document.documentElement, 20000);
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var kids = el.children;
      if (!kids || kids.length < 2) continue;
      var rich = 0;
      var longest = 0;
      for (var k = 0; k < kids.length; k++) {
        var len = textOf(kids[k]).length;
        if (len > 15) rich++;
        if (len > longest) longest = len;
      }
      if (rich < 2 || longest < 60) continue;
      var score = rich * 100 + Math.min(longest, 4000) / 100;
      if (!best || score > best.score) best = { el: el, score: score };
    }
    if (!best) return { strategy: "none", messages: [] };
    var turns = Array.prototype.slice.call(best.el.children).filter(function (child) {
      return textOf(child).length > 0;
    });
    return collect(turns, "heuristic");
  }

  function findMessages(customSelector) {
    var chain = customSelector ? [customSelector].concat(MESSAGE_SELECTORS) : MESSAGE_SELECTORS;
    for (var i = 0; i < chain.length; i++) {
      var nodes = deepQueryAll(chain[i]);
      if (nodes.length >= 1) {
        var picked = collect(nodes, "selector:" + chain[i]);
        if (picked.messages.length) return picked;
      }
    }
    return heuristic();
  }

  function findComposer() {
    var candidates = deepQueryAll(COMPOSER_SELECTORS).filter(isVisible);
    if (!candidates.length) return null;
    candidates.sort(function (a, b) {
      var ra = a.getBoundingClientRect();
      var rb = b.getBoundingClientRect();
      // Prefer wide boxes near the bottom of the viewport.
      return rb.width * 1.0 + rb.top * 0.5 - (ra.width * 1.0 + ra.top * 0.5);
    });
    return candidates[0];
  }

  function findSendButton() {
    var buttons = deepQueryAll('button, [role="button"]').filter(isVisible);
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      if (btn.disabled) continue;
      var label = [
        btn.getAttribute("aria-label") || "",
        btn.getAttribute("title") || "",
        btn.getAttribute("data-testid") || "",
        btn.id || "",
      ]
        .join(" ")
        .toLowerCase();
      for (var w = 0; w < SEND_WORDS.length; w++) {
        if (label.indexOf(SEND_WORDS[w]) !== -1) return btn;
      }
    }
    return null;
  }

  function setNativeValue(el, value) {
    var proto = Object.getPrototypeOf(el);
    var desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) {
      desc.set.call(el, value);
    } else {
      el.value = value;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function send(text, submit) {
    var el = findComposer();
    if (!el) return { ok: false, error: "no composer found" };
    try {
      if (el.scrollIntoView) el.scrollIntoView({ block: "center" });
    } catch (e) {
      /* not every host implements it; focusing is what actually matters */
    }
    el.focus();
    var method;

    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      setNativeValue(el, text);
      method = "native-value";
    } else {
      var inserted = false;
      try {
        document.execCommand("selectAll", false, null);
        inserted = document.execCommand("insertText", false, text);
      } catch (e) {
        inserted = false;
      }
      if (!inserted || !textOf(el)) {
        el.textContent = text;
        el.dispatchEvent(
          new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" })
        );
        method = "textContent";
      } else {
        method = "execCommand";
      }
    }

    var clicked = false;
    if (submit) {
      var btn = findSendButton();
      if (btn && !btn.disabled) {
        btn.click();
        clicked = true;
      }
    }
    return { ok: true, method: method, clicked: clicked, tag: el.tagName };
  }

  function read(customSelector) {
    var found = findMessages(customSelector || "");
    var composer = findComposer();
    return {
      url: location.href,
      title: document.title,
      strategy: found.strategy,
      messages: found.messages,
      composer: composer ? composer.tagName + (composer.id ? "#" + composer.id : "") : null,
    };
  }

  function probe(customSelector) {
    var counts = [];
    var chain = customSelector ? [customSelector].concat(MESSAGE_SELECTORS) : MESSAGE_SELECTORS;
    for (var i = 0; i < chain.length; i++) {
      counts.push({ selector: chain[i], hits: deepQueryAll(chain[i]).length });
    }
    var data = read(customSelector);
    var btn = findSendButton();
    return {
      url: data.url,
      title: data.title,
      strategy: data.strategy,
      selectorCounts: counts,
      composer: data.composer,
      sendButton: btn ? btn.getAttribute("aria-label") || btn.getAttribute("title") || btn.tagName : null,
      preview: data.messages.slice(-6).map(function (m) {
        return {
          index: m.index,
          role: m.role,
          codeBlocks: m.code.length,
          head: m.text.slice(0, 160),
        };
      }),
    };
  }

  window.__copilotBridge = { version: VERSION, read: read, send: send, probe: probe };
  return "installed";
})();
