/* eslint-disable no-console */
const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const pythonCandidates = [
  process.env.LOCALWHISPER_PYTHON,
  process.env.LOCALAPPDATA
    ? path.join(process.env.LOCALAPPDATA, "LocalWhisper", "venv", "Scripts", "python.exe")
    : null,
  path.join(repoRoot, ".venv", "Scripts", "python.exe"),
].filter(Boolean);
const python = pythonCandidates.find((candidate) => fs.existsSync(candidate));
if (!python) {
  throw new Error(`LocalWhisper Python runtime not found. Checked: ${pythonCandidates.join(", ")}`);
}

function existingBrowser() {
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) {
    throw new Error("Chrome/Edge executable not found.");
  }
  return found;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return response.json();
}

async function waitForDevToolsPort(profileDir) {
  const activePortPath = path.join(profileDir, "DevToolsActivePort");
  for (let i = 0; i < 80; i += 1) {
    if (fs.existsSync(activePortPath)) {
      const [port] = fs.readFileSync(activePortPath, "utf8").split(/\r?\n/);
      if (port) {
        return Number(port);
      }
    }
    await sleep(250);
  }
  throw new Error("Chrome DevToolsActivePort was not created.");
}

async function waitForTab(port, title) {
  for (let i = 0; i < 80; i += 1) {
    try {
      const tabs = await getJson(`http://127.0.0.1:${port}/json`);
      const tab = tabs.find((item) => (item.title || "").includes(title))
        || tabs.find((item) => (item.url || "").startsWith("data:text/html"));
      if (tab && tab.webSocketDebuggerUrl) {
        return tab;
      }
    } catch {
      // Browser is still starting.
    }
    await sleep(250);
  }
  throw new Error("CDP tab not found.");
}

async function cleanupBrowser(proc, profile) {
  try {
    proc.kill();
  } catch {
    // Already closed.
  }
  for (let i = 0; i < 8; i += 1) {
    try {
      fs.rmSync(profile, { recursive: true, force: true });
      return;
    } catch {
      await sleep(250);
    }
  }
}

function connectCdp(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let nextId = 0;
    const pending = new Map();

    ws.onopen = () => {
      resolve({
        send(method, params = {}) {
          const id = ++nextId;
          ws.send(JSON.stringify({ id, method, params }));
          return new Promise((res, rej) => pending.set(id, { res, rej, method }));
        },
        close() {
          ws.close();
        },
      });
    };
    ws.onerror = (event) => reject(event.error || event);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (!msg.id || !pending.has(msg.id)) {
        return;
      }
      const request = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) {
        request.rej(new Error(`${request.method}: ${JSON.stringify(msg.error)}`));
      } else {
        request.res(msg.result);
      }
    };
  });
}

const injectPython = String.raw`
import json
import sys
import time

import uiautomation as auto
from PySide6.QtWidgets import QApplication

from localwhisper.app import App
from localwhisper.focus import activate_window, get_focus_info
from localwhisper.injector import current_clipboard_text

title = sys.argv[1]
text = sys.argv[2]

qapp = QApplication.instance() or QApplication([])

win = None
for _ in range(50):
    for child in auto.GetRootControl().GetChildren():
        if title in ((getattr(child, "Name", "") or "")):
            win = child
            break
    if win:
        break
    time.sleep(0.1)

if win:
    activate_window(int(getattr(win, "NativeWindowHandle", 0) or 0), 0)
    win.SetActive()
    rect = win.BoundingRectangle
    auto.Click(rect.left + 120, rect.top + 12)
    time.sleep(0.25)

info = get_focus_info()
if title not in (info.get("title") or ""):
    raise RuntimeError(f"Expected foreground title containing {title!r}, got {info!r}")
stub = App.__new__(App)
stub._last_text_injected = False
stub._clipboard_restore_snapshot = None
stub._clipboard_restore_pending = False
stub._clipboard_restore_generation = 0
stub._enter_pending = False
stub._quit_pending = False

ok = App._inject_text_into(
    stub,
    text,
    int(info.get("hwnd") or 0),
    int(info.get("focus_hwnd") or info.get("caret_hwnd") or 0),
    info.get("process") or None,
    info.get("title") or None,
)

deadline = time.time() + 1.2
while time.time() < deadline:
    qapp.processEvents()
    time.sleep(0.03)

print(json.dumps({"ok": ok, "focus": info, "clipboard": current_clipboard_text()}))
`;

const notepadPython = String.raw`
import ctypes
import json
import pathlib
import subprocess
import tempfile
import time
import uuid

import uiautomation as auto
from PySide6.QtWidgets import QApplication

from localwhisper.app import App
from localwhisper.focus import activate_window, get_focus_info
from localwhisper.injector import current_clipboard_text

user32 = ctypes.WinDLL("user32", use_last_error=True)
WM_GETTEXTLENGTH = 0x000E
WM_GETTEXT = 0x000D

def get_text(hwnd):
    n = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(int(n) + 4096)
    user32.SendMessageW(hwnd, WM_GETTEXT, len(buf), ctypes.byref(buf))
    return buf.value

name = "lw_verify_" + uuid.uuid4().hex[:8] + ".txt"
path = pathlib.Path(tempfile.gettempdir()) / name
path.write_text("", encoding="utf-8")
text = "NOTEPAD_DIRECT_\u00e7\u00e3\u00e9"
qapp = QApplication.instance() or QApplication([])

subprocess.Popen(["notepad.exe", str(path)])
win = None
for _ in range(60):
    candidate = auto.WindowControl(searchDepth=1, Name=f"{name} - Notepad")
    if candidate.Exists(0.2):
        win = candidate
        break
    time.sleep(0.2)

if not win:
    raise RuntimeError("Notepad window was not found.")

activate_window(int(getattr(win, "NativeWindowHandle", 0) or 0), 0)
win.SetActive()
rect = win.BoundingRectangle
auto.Click(rect.left + 160, rect.top + 180)
time.sleep(0.3)
info = get_focus_info()
if (info.get("process") or "").lower() != "notepad.exe":
    raise RuntimeError(f"Expected Notepad foreground, got {info!r}")

stub = App.__new__(App)
stub._last_text_injected = False
stub._clipboard_restore_snapshot = None
stub._clipboard_restore_pending = False
stub._clipboard_restore_generation = 0
stub._enter_pending = False
stub._quit_pending = False

ok = App._inject_text_into(
    stub,
    text,
    int(info.get("hwnd") or 0),
    int(info.get("focus_hwnd") or info.get("caret_hwnd") or 0),
    info.get("process") or None,
    info.get("title") or None,
)

deadline = time.time() + 1.2
while time.time() < deadline:
    qapp.processEvents()
    time.sleep(0.03)

after = get_focus_info()
focus_hwnd = int(after.get("focus_hwnd") or after.get("caret_hwnd") or info.get("focus_hwnd") or 0)
value = get_text(focus_hwnd)
auto.SendKeys("{Ctrl}s")
time.sleep(0.2)
try:
    win.GetWindowPattern().Close()
except Exception:
    pass

print(json.dumps({"ok": ok, "focus": info, "value": value, "clipboard": current_clipboard_text()}))
`;

const prepareClipboardPython = String.raw`
import pickle
import sys

from localwhisper.injector import set_clipboard_text_protected, snapshot_clipboard

with open(sys.argv[1], "wb") as f:
    pickle.dump(snapshot_clipboard(), f)
set_clipboard_text_protected("LW_ORIGINAL_CLIPBOARD")
print("{}")
`;

const restoreClipboardPython = String.raw`
import os
import pickle
import sys

from localwhisper.injector import restore_clipboard

path = sys.argv[1]
if os.path.exists(path):
    with open(path, "rb") as f:
        snapshot = pickle.load(f)
    restore_clipboard(snapshot)
    try:
        os.remove(path)
    except OSError:
        pass
print("{}")
`;

function runPython(code, args = []) {
  const output = cp.execFileSync(python, ["-c", code, ...args], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  return JSON.parse(output.trim());
}

async function verifyBrowserTargets() {
  const title = `LW CDP Verify ${Date.now()}`;
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><style>body{font-family:sans-serif;padding:24px}input,textarea,[contenteditable]{display:block;width:640px;min-height:32px;margin:12px;padding:8px;border:1px solid #777}</style></head><body><label>Plain<input id="plain" aria-label="PlainInput"></label><label>Area<textarea id="area" aria-label="AreaBox"></textarea></label><div id="edit" contenteditable="true" role="textbox" aria-label="EditableBox"></div><div id="modern" class="cm-content" contenteditable="true" role="textbox" aria-label="ModernEditor"></div><input id="search" type="search" aria-label="SearchBox"></body></html>`;
  const url = `data:text/html;base64,${Buffer.from(html, "utf8").toString("base64")}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "lw_cdp_profile_"));
  const browser = existingBrowser();
  const proc = cp.spawn(browser, [
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--disable-sync",
    "--force-renderer-accessibility",
    "--remote-debugging-port=0",
    "--new-window",
    url,
  ], { stdio: "ignore" });

  try {
    const port = await waitForDevToolsPort(profile);
    const tab = await waitForTab(port, title);
    const cdp = await connectCdp(tab.webSocketDebuggerUrl);
    await cdp.send("Runtime.enable");
    await cdp.send("Page.enable");
    await cdp.send("Page.bringToFront");

    const targets = [
      { name: "chromium-input", selector: "#plain", text: "CHROME_INPUT_\u00e7\u00e3\u00e9", read: "el.value" },
      { name: "chromium-textarea", selector: "#area", text: "CHROME_TEXTAREA_\u00e7\u00e3\u00e9", read: "el.value" },
      { name: "chromium-contenteditable", selector: "#edit", text: "CHROME_EDITABLE_\u00e7\u00e3\u00e9", read: "el.innerText" },
      { name: "chromium-modern-editor", selector: "#modern", text: "CHROME_MODERN_EDITOR_\u00e7\u00e3\u00e9", read: "el.innerText" },
      { name: "chromium-search", selector: "#search", text: "CHROME_SEARCH_\u00e7\u00e3\u00e9", read: "el.value" },
    ];

    const results = [];
    for (const target of targets) {
      const selector = JSON.stringify(target.selector);
      await cdp.send("Runtime.evaluate", {
        expression: `(() => { const el = document.querySelector(${selector}); if ("value" in el) el.value = ""; else el.innerText = ""; el.focus(); return document.activeElement.id; })()`,
        returnByValue: true,
      });
      const injected = runPython(injectPython, [title, target.text]);
      const valueResult = await cdp.send("Runtime.evaluate", {
        expression: `(() => { const el = document.querySelector(${selector}); return ${target.read}; })()`,
        returnByValue: true,
      });
      results.push({
        name: target.name,
        expected: target.text,
        value: valueResult.result.value,
        injected,
        pass: injected.ok && valueResult.result.value === target.text && injected.clipboard === "LW_ORIGINAL_CLIPBOARD",
      });
    }
    cdp.close();
    return results;
  } finally {
    await cleanupBrowser(proc, profile);
  }
}

(async () => {
  const clipboardSnapshotPath = path.join(os.tmpdir(), `lw_clipboard_${process.pid}.pickle`);
  runPython(prepareClipboardPython, [clipboardSnapshotPath]);
  try {
    const notepad = runPython(notepadPython);
    const browserTargets = await verifyBrowserTargets();
    const results = [
      {
        name: "notepad",
        expected: "NOTEPAD_DIRECT_\u00e7\u00e3\u00e9",
        value: notepad.value,
        injected: notepad,
        pass: notepad.ok && notepad.value === "NOTEPAD_DIRECT_\u00e7\u00e3\u00e9" && notepad.clipboard === "LW_ORIGINAL_CLIPBOARD",
      },
      ...browserTargets,
    ];
    console.log(JSON.stringify({ pass: results.every((item) => item.pass), results }, null, 2));
    process.exitCode = results.every((item) => item.pass) ? 0 : 1;
  } finally {
    runPython(restoreClipboardPython, [clipboardSnapshotPath]);
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
