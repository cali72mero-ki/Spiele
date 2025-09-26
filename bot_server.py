#!/usr/bin/env python3
"""Kleiner HTTP-Server mit grundlegender Bot-Erkennung."""

from __future__ import annotations

import html
import json
import logging
import textwrap
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
)


class SuspicionStore:
    """Speichert Verdachtsfälle in Memory."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, List[str]]] = {}

    def flag(self, client_id: str, reason: str) -> None:
        bucket = self._store.setdefault(client_id, {"reasons": [], "ts": time.time()})
        if reason not in bucket["reasons"]:
            bucket["reasons"].append(reason)
            bucket["ts"] = time.time()

    def bulk_flag(self, client_id: str, reasons: List[str]) -> None:
        for reason in reasons:
            self.flag(client_id, reason)

    def get(self, client_id: str) -> Dict[str, List[str]] | None:
        entry = self._store.get(client_id)
        if entry and time.time() - entry.get("ts", 0) > 3600:
            # nach einer Stunde löschen
            self._store.pop(client_id, None)
            return None
        return entry

    def clear(self, client_id: str) -> None:
        self._store.pop(client_id, None)


SUSPICIOUS_TOKENS = ("bot", "spider", "crawler", "scrapy", "curl", "python")
HEADLESS_HINTS = ("headless", "phantomjs", "selenium")


class BotShieldHandler(SimpleHTTPRequestHandler):
    suspicion_store = SuspicionStore()

    def translate_path(self, path: str) -> str:
        """Sicherstellen, dass nur Dateien aus dem Web-Ordner bedient werden."""
        clean_path = unquote(path.split("?", 1)[0].split("#", 1)[0])
        target = (WEB_DIR / clean_path.lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        try:
            target.relative_to(WEB_DIR)
        except ValueError:
            return str(WEB_DIR / "index.html")
        if not target.exists():
            return str(WEB_DIR / "index.html")
        return str(target)

    # pylint: disable=missing-docstring
    def log_message(self, format: str, *args):  # type: ignore[override]
        logging.info("%s - %s", self.client_address[0], format % args)

    def end_headers(self):  # type: ignore[override]
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:  # type: ignore[override]
        client_id = self.client_address[0]
        if self.path == "/bot-status":
            self._handle_status(client_id)
            return
        if self.path == "/human-verified":
            self._handle_clear(client_id)
            return

        suspicious_reasons = self._analyse_request()
        flagged_reasons: List[str] = []
        if suspicious_reasons:
            logging.warning("Verdächtige Anfrage von %s: %s", client_id, suspicious_reasons)
            self.suspicion_store.bulk_flag(client_id, suspicious_reasons)
            flagged_reasons.extend(suspicious_reasons)

        stored = self.suspicion_store.get(client_id)
        if stored:
            for reason in stored["reasons"]:
                if reason not in flagged_reasons:
                    flagged_reasons.append(reason)

        if flagged_reasons:
            self._serve_with_challenge(flagged_reasons)
            return

        super().do_GET()

    def do_POST(self) -> None:  # type: ignore[override]
        client_id = self.client_address[0]
        if self.path == "/report-bot":
            self._handle_report(client_id)
            return
        if self.path == "/human-verified":
            self._handle_clear(client_id)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Unbekannte Ressource")

    # Hilfsfunktionen -----------------------------------------------------

    def _analyse_request(self) -> List[str]:
        reasons: List[str] = []
        user_agent = (self.headers.get("User-Agent") or "").lower()
        if not user_agent:
            reasons.append("Kein User-Agent")
        else:
            if any(token in user_agent for token in SUSPICIOUS_TOKENS):
                reasons.append("User-Agent enthält Bot-Tokens")
            if any(token in user_agent for token in HEADLESS_HINTS):
                reasons.append("Headless-Indiz im User-Agent")
        if not self.headers.get("Accept-Language"):
            reasons.append("Keine Accept-Language gesetzt")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site == "none":
            reasons.append("Fehlender Kontext (Sec-Fetch-Site: none)")
        if self.headers.get("X-Forwarded-For"):
            reasons.append("Proxy/Forwarded Header gesetzt")
        return reasons

    def _serve_with_challenge(self, reasons: List[str]) -> None:
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = path / "index.html"
        if not path.exists():
            path = WEB_DIR / "index.html"

        try:
            html_content = path.read_text("utf-8")
        except OSError as exc:
            logging.error("Konnte Datei %s nicht lesen: %s", path, exc)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Datei konnte nicht gelesen werden")
            return

        injected = self._inject_challenge(html_content, reasons)
        encoded_body = injected.encode("utf-8")
        cookie = SimpleCookie()
        cookie["bot_flagged"] = "1"
        cookie["bot_flagged"]["path"] = "/"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded_body)))
        for morsel in cookie.values():
            self.send_header("Set-Cookie", morsel.OutputString())
        self.end_headers()
        self.wfile.write(encoded_body)

    def _handle_status(self, client_id: str) -> None:
        stored = self.suspicion_store.get(client_id)
        payload = {"flagged": False, "reasons": []}
        if stored:
            payload["flagged"] = True
            payload["reasons"] = stored["reasons"]
        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            if cookie.get("bot_flagged"):
                payload.setdefault("cookies", {})
                payload["cookies"]["bot_flagged"] = cookie["bot_flagged"].value

        response = json.dumps(payload)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))

    def _handle_report(self, client_id: str) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Ungültiges JSON")
            return

        reasons = data.get("reasons") or []
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, str) and reason.strip():
                    self.suspicion_store.flag(client_id, reason.strip())
        logging.warning("Client %s meldete verdächtiges Verhalten: %s", client_id, reasons)

        self._write_json({"status": "received"})

    def _handle_clear(self, client_id: str) -> None:
        self.suspicion_store.clear(client_id)
        cookie = SimpleCookie()
        cookie["bot_flagged"] = "0"
        cookie["bot_flagged"]["path"] = "/"
        cookie["bot_flagged"]["max-age"] = "0"
        payload = {"status": "cleared"}
        encoded = json.dumps(payload)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        for morsel in cookie.values():
            self.send_header("Set-Cookie", morsel.OutputString())
        self.end_headers()
        self.wfile.write(encoded.encode("utf-8"))

    def _write_json(self, payload: Dict[str, object]) -> None:
        encoded = json.dumps(payload)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded.encode("utf-8"))

    def _inject_challenge(self, html_content: str, reasons: List[str]) -> str:
        reasons_json = json.dumps(reasons, ensure_ascii=False)
        reasons_html = "".join(
            f"<li>{html.escape(reason)}</li>" for reason in reasons
        )
        snippet = textwrap.dedent(
            f"""
            <div id="bot-challenge-overlay" class="bot-challenge-overlay" role="dialog" aria-modal="true">
              <div class="bot-challenge-card">
                <h1>Verdachtsprüfung</h1>
                <p>Unser System hat Auffälligkeiten entdeckt. Bitte beantworte die Frage, um fortzufahren.</p>
                <div class="bot-reasons">
                  <strong>Gründe:</strong>
                  <ul>
                    {reasons_html}
                  </ul>
                </div>
                <form class="bot-challenge-form">
                  <label for="bot-answer">Frage:</label>
                  <div class="bot-question" data-role="question"></div>
                  <input id="bot-answer" name="answer" type="text" placeholder="Antwort eingeben" autocomplete="off" required />
                  <button type="submit">Bestätigen</button>
                  <p class="bot-feedback" data-role="feedback" aria-live="polite"></p>
                </form>
              </div>
            </div>
            <style>
              .bot-challenge-overlay {{
                position: fixed;
                inset: 0;
                background: rgba(15, 23, 42, 0.92);
                display: grid;
                place-items: center;
                z-index: 2147483000;
                backdrop-filter: blur(4px);
              }}
              .bot-challenge-card {{
                width: min(560px, 90vw);
                background: linear-gradient(165deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98));
                padding: 2.5rem;
                border-radius: 24px;
                box-shadow: 0 30px 90px rgba(8, 47, 73, 0.6);
                color: #e2e8f0;
                display: grid;
                gap: 1.4rem;
              }}
              .bot-challenge-card h1 {{
                margin: 0;
                font-size: clamp(2rem, 4vw, 2.5rem);
              }}
              .bot-reasons ul {{
                padding-left: 1.25rem;
                margin: 0.75rem 0 0;
              }}
              .bot-challenge-form {{
                display: grid;
                gap: 0.75rem;
              }}
              .bot-challenge-form input {{
                padding: 0.75rem 1rem;
                border-radius: 12px;
                border: 1px solid rgba(148, 163, 184, 0.4);
                background: rgba(15, 23, 42, 0.6);
                color: inherit;
                font-size: 1rem;
              }}
              .bot-challenge-form button {{
                padding: 0.75rem 1.2rem;
                border-radius: 12px;
                border: none;
                background: linear-gradient(135deg, #38bdf8, #2563eb);
                color: white;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
              }}
              .bot-challenge-form button:hover,
              .bot-challenge-form button:focus {{
                transform: translateY(-1px);
                box-shadow: 0 20px 45px rgba(37, 99, 235, 0.35);
              }}
              .bot-feedback {{
                min-height: 1.25rem;
                color: #f97316;
                font-weight: 600;
              }}
            </style>
            <script id="bot-challenge-script" data-reasons='{reasons_json}'>
              (() => {{
                const script = document.getElementById('bot-challenge-script');
                const overlay = document.getElementById('bot-challenge-overlay');
                if (!script || !overlay) return;

                const questionBox = overlay.querySelector('[data-role="question"]');
                const feedback = overlay.querySelector('[data-role="feedback"]');
                const form = overlay.querySelector('.bot-challenge-form');
                const input = overlay.querySelector('#bot-answer');

                const questions = [
                  {{ q: 'Wie viele Buchstaben hat das Wort "Mensch"?', a: '6' }},
                  {{ q: 'Was ergibt 7 + 5?', a: '12' }},
                  {{ q: 'Welcher Wochentag folgt auf Montag?', a: 'dienstag' }},
                  {{ q: 'Schreibe das Wort "Sonne" rückwärts.', a: 'ennos' }},
                  {{ q: 'Wie heißt die Hauptstadt von Deutschland?', a: 'berlin' }}
                ];

                const current = questions[Math.floor(Math.random() * questions.length)];
                if (questionBox) {{
                  questionBox.textContent = current.q;
                }}

                const markSolved = async () => {{
                  try {{
                    await fetch('/human-verified', {{
                      method: 'POST',
                      headers: {{ 'Content-Type': 'application/json' }},
                      body: JSON.stringify({{ cleared: true, question: current.q }})
                    }});
                  }} catch (err) {{
                    console.warn('Konnte Status nicht senden', err);
                  }}
                }};

                form?.addEventListener('submit', async (event) => {{
                  event.preventDefault();
                  const value = (input?.value || '').trim().toLowerCase();
                  if (!value) {{
                    feedback.textContent = 'Bitte gib eine Antwort ein.';
                    return;
                  }}
                  if (value === current.a) {{
                    feedback.textContent = 'Danke! Der Verdacht wurde aufgehoben.';
                    await markSolved();
                    setTimeout(() => overlay.remove(), 600);
                  }} else {{
                    feedback.textContent = 'Das war leider falsch. Versuche es erneut.';
                    input?.focus();
                  }}
                }});

                input?.focus();
              }})();
            </script>
            """
        )

        if "</body>" in html_content:
            return html_content.replace("</body>", snippet + "</body>")
        return html_content + snippet


def run(server_class=HTTPServer, handler_class=BotShieldHandler) -> None:
    server_address = ("0.0.0.0", 8080)
    httpd = server_class(server_address, handler_class)
    logging.info("BotShield-Server läuft auf http://%s:%s", *server_address)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Server wird beendet ...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
