#!/usr/bin/env python3
"""Kleiner HTTP-Server mit grundlegender Bot-Erkennung."""

from __future__ import annotations

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

        suspicious_reasons = self._analyse_request()
        if suspicious_reasons:
            logging.warning("Verdächtige Anfrage von %s: %s", client_id, suspicious_reasons)
            self.suspicion_store.bulk_flag(client_id, suspicious_reasons)
            self._deny_request(client_id, suspicious_reasons)
            return

        stored = self.suspicion_store.get(client_id)
        if stored:
            self._deny_request(client_id, stored["reasons"])
            return

        super().do_GET()

    def do_POST(self) -> None:  # type: ignore[override]
        client_id = self.client_address[0]
        if self.path != "/report-bot":
            self.send_error(HTTPStatus.NOT_FOUND, "Unbekannte Ressource")
            return

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

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "received"}).encode("utf-8"))

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

    def _deny_request(self, client_id: str, reasons: List[str]) -> None:
        body = textwrap.dedent(
            """
            <html lang='de'>
              <head>
                <meta charset='utf-8' />
                <title>Zugriff blockiert</title>
                <style>
                  body {
                    font-family: Arial, sans-serif;
                    background: #0f172a;
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                  }
                  main {
                    background: rgba(15, 23, 42, 0.85);
                    padding: 2.5rem;
                    border-radius: 20px;
                    max-width: 640px;
                    box-shadow: 0 24px 64px rgba(15, 23, 42, 0.5);
                  }
                  h1 {
                    margin-top: 0;
                    color: #f97316;
                  }
                  li {
                    margin-bottom: 0.5rem;
                  }
                  code {
                    background: rgba(15, 23, 42, 0.6);
                    padding: 0.1rem 0.4rem;
                    border-radius: 6px;
                  }
                </style>
              </head>
              <body>
                <main>
                  <h1>Zugriff verweigert</h1>
                  <p>Die Anfrage wurde als potenzieller Bot identifiziert. Gründe:</p>
                  <ul>
            """
        ).strip()
        body += "".join(f"<li>{reason}</li>\n" for reason in reasons)
        body += textwrap.dedent(
            """
                  </ul>
                  <p>Bitte kontaktiere den Support, wenn du glaubst, dass dies ein Fehler ist.</p>
                  <p><code>/bot-status</code> liefert detaillierte Informationen.</p>
                </main>
              </body>
            </html>
            """
        )
        cookie = SimpleCookie()
        cookie["bot_flagged"] = "1"
        cookie["bot_flagged"]["path"] = "/"
        encoded_body = body.encode("utf-8")
        self.send_response(HTTPStatus.FORBIDDEN)
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
