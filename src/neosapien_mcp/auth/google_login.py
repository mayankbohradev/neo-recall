"""Localhost Google sign-in helper — Firebase Auth popup → capture refresh token."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from neosapien_mcp import constants

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NeoRecall — Sign in</title>
  <style>
    :root { color-scheme: light; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center;
           background: #f6f4ef; color: #1a1a1a; }
    main { width: min(420px, 92vw); background: #fff; border: 1px solid #e5e0d6;
           border-radius: 12px; padding: 28px 24px; box-shadow: 0 8px 24px #0000000d; }
    h1 { font-size: 1.25rem; margin: 0 0 8px; }
    p { margin: 0 0 16px; line-height: 1.45; color: #444; font-size: 0.95rem; }
    button { width: 100%; border: 0; border-radius: 8px; padding: 12px 14px;
             background: #1a1a1a; color: #fff; font-size: 1rem; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: wait; }
    #status { margin-top: 14px; font-size: 0.9rem; min-height: 1.2em; }
    .ok { color: #0a7a3e; } .err { color: #b42318; }
  </style>
</head>
<body>
  <main>
    <h1>Sign in with Google</h1>
    <p>This connects <strong>NeoRecall</strong> to your Neo account.
       Read-only — it cannot delete your memories. Your token stays on this computer.</p>
    <button id="btn" type="button">Continue with Google</button>
    <p id="status"></p>
  </main>
  <script type="module">
    import { initializeApp } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
    import {
      getAuth, GoogleAuthProvider, signInWithPopup
    } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

    const firebaseConfig = __FIREBASE_CONFIG__;
    const app = initializeApp(firebaseConfig);
    const auth = getAuth(app);
    const status = document.getElementById("status");
    const btn = document.getElementById("btn");

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      status.className = "";
      status.textContent = "Opening Google sign-in…";
      try {
        const provider = new GoogleAuthProvider();
        provider.setCustomParameters({ prompt: "select_account" });
        const result = await signInWithPopup(auth, provider);
        const user = result.user;
        const payload = {
          refresh_token: user.refreshToken,
          uid: user.uid,
          email: user.email || "",
          firebase_api_key: firebaseConfig.apiKey,
        };
        status.textContent = "Saving credentials…";
        const resp = await fetch("/capture", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) throw new Error(await resp.text());
        status.className = "ok";
        status.textContent = "Done. You can close this tab and return to the terminal.";
        btn.textContent = "Signed in";
      } catch (err) {
        status.className = "err";
        status.textContent = (err && err.message) ? err.message : String(err);
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def _firebase_config_json() -> str:
    return json.dumps(
        {
            "apiKey": constants.FIREBASE_API_KEY,
            "authDomain": constants.FIREBASE_AUTH_DOMAIN,
            "projectId": constants.FIREBASE_PROJECT_ID,
            "storageBucket": constants.FIREBASE_STORAGE_BUCKET,
            "messagingSenderId": constants.FIREBASE_MESSAGING_SENDER_ID,
            "appId": constants.FIREBASE_APP_ID,
        }
    )


class _CaptureState:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.payload: dict[str, Any] | None = None
        self.error: str | None = None


def run_google_login(*, timeout_sec: int = 180) -> dict[str, Any]:
    """
    Open a browser to a localhost page, wait for Google Firebase sign-in,
    return {refresh_token, uid, email, firebase_api_key}.
    """
    state = _CaptureState()
    html = LOGIN_HTML.replace("__FIREBASE_CONFIG__", _firebase_config_json())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return  # keep tokens/out of console noise

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/login"):
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urllib.parse.urlparse(self.path).path
            if path != "/capture":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
                rt = (data.get("refresh_token") or "").strip()
                uid = (data.get("uid") or "").strip()
                if not rt or not uid:
                    raise ValueError("missing refresh_token or uid")
                state.payload = {
                    "refresh_token": rt,
                    "uid": uid,
                    "email": (data.get("email") or "").strip(),
                    "firebase_api_key": (
                        data.get("firebase_api_key") or constants.FIREBASE_API_KEY
                    ),
                }
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                state.event.set()
            except Exception as exc:  # noqa: BLE001
                state.error = str(exc)
                msg = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
                state.event.set()

    server = ThreadingHTTPServer((constants.AUTH_HELPER_HOST, constants.AUTH_HELPER_PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{constants.AUTH_HELPER_HOST}:{constants.AUTH_HELPER_PORT}/"
    print(f"\nOpening browser: {url}")
    print("Sign in with the Google account you use for NeoSapien.\n")
    webbrowser.open(url)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if state.event.wait(timeout=0.5):
            break
    server.shutdown()
    server.server_close()

    if state.error:
        raise RuntimeError(f"Sign-in failed: {state.error}")
    if not state.payload:
        raise RuntimeError(
            f"Timed out after {timeout_sec}s waiting for Google sign-in. "
            "Re-run: neo-recall-auth --google"
        )
    return state.payload
