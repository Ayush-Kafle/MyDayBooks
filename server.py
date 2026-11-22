#!/usr/bin/env python3
import json
import os
import re
import ssl
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from http.client import HTTPException
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATABASE = DATA_DIR / "daybook.sqlite3"
INITIAL_BACKUP = ROOT / "exports" / "daybook-backup-2026-11-21.json"
MAX_BODY_SIZE = 2 * 1024 * 1024
EVENT_SOURCES = (
    {
        "name": "Visit Cincy",
        "url": "https://www.visitcincy.com/events/",
        "host": "www.visitcincy.com",
        "kind": "visit-cincy",
    },
    {
        "name": "Cincinnati Zoo",
        "url": "https://cincinnatizoo.org/events/",
        "host": "cincinnatizoo.org",
        "kind": "zoo",
    },
)
EVENTS_REFRESH_INTERVAL = timedelta(days=7)
EVENTS_RETRY_INTERVAL = timedelta(days=1)
MAX_SOURCE_BYTES = 5 * 1024 * 1024


class EventCardParser(HTMLParser):
    def __init__(self, source_kind):
        super().__init__(convert_charrefs=True)
        self.source_kind = source_kind
        self.cards = []
        self.card = None
        self.title_depth = 0
        self.date_depth = 0
        self.venue_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        if tag == "article" and self.card is None:
            if self.source_kind == "visit-cincy" and any(
                item in classes for item in ("featured-slide", "stacked")
            ):
                self.card = {"title": "", "url": "", "texts": [], "dates": [], "venue": ""}
            elif self.source_kind == "zoo" and "archive-event" in classes:
                self.card = {"title": "", "url": "", "texts": [], "dates": [], "venue": ""}
        if self.card is None:
            return
        if tag in ("h2", "h3", "h4"):
            self.title_depth += 1
        if tag == "a":
            href = attributes.get("href", "")
            if self.source_kind == "visit-cincy" and "/event/" in urlparse(href).path:
                self.card["url"] = href
            elif self.source_kind == "zoo" and "/events/" in urlparse(href).path:
                self.card["url"] = href
        if tag in ("div", "li", "span") and any(
            "duration" in item or "date" in item for item in classes
        ):
            self.date_depth += 1
        if tag in ("div", "li") and any(
            "location" in item or "venue" in item for item in classes
        ):
            self.venue_depth += 1

    def handle_data(self, data):
        if self.card is None:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.card["texts"].append(text)
        if self.title_depth:
            self.card["title"] += f" {text}"
        if self.date_depth:
            self.card["dates"].append(text)
        if self.venue_depth:
            self.card["venue"] += f" {text}"

    def handle_endtag(self, tag):
        if self.card is None:
            return
        if tag in ("h2", "h3", "h4") and self.title_depth:
            self.title_depth -= 1
        if tag in ("div", "li", "span") and self.date_depth:
            self.date_depth -= 1
        if tag in ("div", "li") and self.venue_depth:
            self.venue_depth -= 1
        if tag == "article":
            self.card["title"] = " ".join(self.card["title"].split())
            self.card["venue"] = " ".join(self.card["venue"].split())
            self.cards.append(self.card)
            self.card = None
            self.title_depth = 0
            self.date_depth = 0
            self.venue_depth = 0


EVENT_DATE_PATTERN = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)


def parse_event_date(value):
    value = value.replace(",", "")
    for pattern in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def event_source_context():
    certificate_bundle = Path("/etc/ssl/cert.pem")
    if certificate_bundle.exists():
        return ssl.create_default_context(cafile=str(certificate_bundle))
    return ssl.create_default_context()


def fetch_source_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": "MyDaybook local event finder/1.0",
            "Accept": "text/html",
        },
    )
    with urlopen(request, context=event_source_context(), timeout=20) as response:
        body = response.read(MAX_SOURCE_BYTES + 1)
    if len(body) > MAX_SOURCE_BYTES:
        raise ValueError("Source response exceeded the 5 MB limit")
    return body.decode("utf-8", errors="replace")


def parse_source_events(source, html):
    parser = EventCardParser(source["kind"])
    parser.feed(html)
    events = []
    today = date.today()
    for card in parser.cards:
        title = card["title"].strip()
        if not title or not card["url"]:
            continue
        url = urljoin(source["url"], card["url"])
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or parsed_url.hostname != source["host"]:
            continue
        date_text = " ".join(card["dates"]) or " ".join(card["texts"])
        date_matches = [match.group(0) for match in EVENT_DATE_PATTERN.finditer(date_text)]
        if not date_matches:
            date_matches = [
                match.group(0)
                for match in EVENT_DATE_PATTERN.finditer(" ".join(card["texts"]))
            ]
        if not date_matches:
            continue
        start_date = parse_event_date(date_matches[0])
        end_date = parse_event_date(date_matches[1]) if len(date_matches) > 1 else start_date
        if start_date is None or end_date is None or end_date < today:
            continue
        label = date_matches[0]
        if len(date_matches) > 1 and date_matches[1] != date_matches[0]:
            label = f"{label} – {date_matches[1]}"
        category = "Local event"
        if source["kind"] == "zoo":
            category = next(
                (
                    value.replace("-", " ").title()
                    for value in ("family-friendly", "garden", "ticketed-event")
                    if value in " ".join(card["texts"]).lower()
                ),
                "Zoo event",
            )
        events.append(
            {
                "source": source["name"],
                "source_id": url,
                "title": title,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "date_label": label,
                "venue": card["venue"].strip(),
                "category": category,
                "url": url,
            }
        )
    if not events:
        raise ValueError("No current dated events could be extracted; saved results were kept")
    return events


def refresh_events():
    source_results = []
    for source in EVENT_SOURCES:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            html = fetch_source_html(source["url"])
            events = parse_source_events(source, html)
        except (OSError, ValueError, UnicodeError, HTTPException) as error:
            print(f"Event source {source['name']} failed: {error}", flush=True)
            source_results.append(
                {
                    "name": source["name"],
                    "ok": False,
                    "fetchedAt": None,
                    "eventCount": 0,
                    "error": str(error),
                }
            )
            continue
        with connect() as connection:
            connection.execute("DELETE FROM events WHERE source = ?", (source["name"],))
            connection.executemany(
                """
                INSERT INTO events
                    (source, source_id, title, start_date, end_date, date_label,
                     venue, category, url, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event["source"],
                        event["source_id"],
                        event["title"],
                        event["start_date"],
                        event["end_date"],
                        event["date_label"],
                        event["venue"],
                        event["category"],
                        event["url"],
                        fetched_at,
                    )
                    for event in events
                ],
            )
        source_results.append(
            {
                "name": source["name"],
                "ok": True,
                "fetchedAt": fetched_at,
                "eventCount": len(events),
                "error": None,
            }
        )
    attempted_at = datetime.now(timezone.utc).isoformat()
    successful = [result for result in source_results if result["ok"]]
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('events.source_status', ?)",
            (json.dumps(source_results, ensure_ascii=False),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('events.last_attempt_at', ?)",
            (json.dumps(attempted_at),),
        )
        if successful:
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('events.last_success_at', ?)",
                (json.dumps(attempted_at),),
            )
        events = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source, title, start_date, end_date, date_label, venue,
                       category, url, fetched_at
                FROM events
                WHERE end_date >= ?
                ORDER BY start_date, title
                """,
                (date.today().isoformat(),),
            )
        ]
    return {
        "ok": bool(successful),
        "partial": bool(successful) and len(successful) != len(source_results),
        "events": events,
        "sources": source_results,
        "lastRefreshAt": attempted_at,
    }


def get_events_payload():
    with connect() as connection:
        events = [
            dict(row)
            for row in connection.execute(
                """
                SELECT source, title, start_date, end_date, date_label, venue,
                       category, url, fetched_at
                FROM events
                WHERE end_date >= ?
                ORDER BY start_date, title
                """,
                (date.today().isoformat(),),
            )
        ]
        metadata = {
            row["key"]: json.loads(row["value"])
            for row in connection.execute(
                """
                SELECT key, value FROM metadata
                WHERE key IN ('events.source_status', 'events.last_attempt_at', 'events.last_success_at')
                """
            )
        }
    return {
        "events": events,
        "sources": metadata.get("events.source_status", []),
        "lastAttemptAt": metadata.get("events.last_attempt_at"),
        "lastRefreshAt": metadata.get("events.last_success_at"),
    }


def event_refresh_scheduler():
    while True:
        payload = get_events_payload()
        with connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'events.last_attempt_at'"
            ).fetchone()
        last_attempt = json.loads(row["value"]) if row else None
        sources = payload["sources"]
        has_source_failures = any(not source.get("ok") for source in sources)
        interval = EVENTS_RETRY_INTERVAL if has_source_failures else EVENTS_REFRESH_INTERVAL
        should_refresh = not last_attempt
        if last_attempt:
            attempted_at = datetime.fromisoformat(last_attempt.replace("Z", "+00:00"))
            should_refresh = datetime.now(timezone.utc) - attempted_at >= interval
        if should_refresh:
            refresh_events()
        time.sleep(3600)


def connect():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS archive_records (
                section TEXT NOT NULL,
                record_id TEXT NOT NULL,
                document_json TEXT NOT NULL,
                server_version TEXT,
                last_saved TEXT,
                PRIMARY KEY (section, record_id)
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                date_label TEXT NOT NULL,
                venue TEXT NOT NULL,
                category TEXT NOT NULL,
                url TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (source, source_id)
            );
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM archive_records").fetchone()[0]
        if count == 0 and INITIAL_BACKUP.exists():
            backup = json.loads(INITIAL_BACKUP.read_text(encoding="utf-8"))
            collections = backup.get("collections")
            if not isinstance(collections, dict):
                raise ValueError(f"Initial backup has no collections: {INITIAL_BACKUP}")
            expected = backup.get("backup", {}).get("documentCount")
            actual = sum(len(records) for records in collections.values())
            if expected is not None and int(expected) != actual:
                raise ValueError(f"Initial backup count mismatch: expected {expected}, found {actual}")
            document_meta = backup.get("documentMeta", {})
            for section, records in collections.items():
                for record_id, document in records.items():
                    meta = document_meta.get(section, {}).get(record_id, {})
                    connection.execute(
                        """
                        INSERT INTO archive_records
                            (section, record_id, document_json, server_version, last_saved)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            section,
                            str(record_id),
                            json.dumps(document, ensure_ascii=False, separators=(",", ":")),
                            str(meta.get("version")) if meta.get("version") is not None else None,
                            meta.get("updatedAt"),
                        ),
                    )
            for key, value in backup.get("backup", {}).items():
                connection.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    (f"backup.{key}", json.dumps(value, ensure_ascii=False)),
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("backup.sections", json.dumps(backup.get("sections", {}), ensure_ascii=False)),
            )
            print(f"Imported {actual} archived records from {INITIAL_BACKUP.name}", flush=True)


class DaybookHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            with connect() as connection:
                count = connection.execute("SELECT COUNT(*) FROM archive_records").fetchone()[0]
                state = connection.execute("SELECT updated_at FROM app_state WHERE id = 1").fetchone()
            return self.send_json({"ok": True, "archiveRecords": count, "stateSavedAt": state["updated_at"] if state else None})
        if path == "/api/state":
            with connect() as connection:
                row = connection.execute("SELECT state_json, updated_at FROM app_state WHERE id = 1").fetchone()
            if row is None:
                return self.send_json({"initialized": False, "state": {}})
            return self.send_json({"initialized": True, "state": json.loads(row["state_json"]), "updatedAt": row["updated_at"]})
        if path == "/api/events":
            return self.send_json(get_events_payload())
        if path == "/api/archive":
            with connect() as connection:
                rows = connection.execute(
                    "SELECT section, record_id, document_json, server_version, last_saved FROM archive_records ORDER BY section, record_id"
                ).fetchall()
                metadata = {
                    row["key"]: json.loads(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
                app_state_row = connection.execute("SELECT state_json FROM app_state WHERE id = 1").fetchone()
            collections = {}
            document_meta = {}
            for row in rows:
                collections.setdefault(row["section"], {})[row["record_id"]] = json.loads(row["document_json"])
                if row["server_version"] is not None or row["last_saved"] is not None:
                    document_meta.setdefault(row["section"], {})[row["record_id"]] = {
                        "version": row["server_version"],
                        "updatedAt": row["last_saved"],
                    }
            backup = {key.removeprefix("backup."): value for key, value in metadata.items() if key.startswith("backup.")}
            return self.send_json({
                "backup": backup,
                "sections": metadata.get("backup.sections", {}),
                "counts": {section: len(records) for section, records in collections.items()},
                "collections": collections,
                "documentMeta": document_meta,
                "currentAppState": json.loads(app_state_row["state_json"]) if app_state_row else {},
            })
        if path == "/api/backup.json":
            self.send_archive_json_download()
            return
        if path == "/api/database.sqlite3":
            with connect() as source, sqlite3.connect(":memory:") as snapshot:
                source.backup(snapshot)
                snapshot.commit()
                body = snapshot.serialize()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.sqlite3")
            self.send_header("Content-Disposition", 'attachment; filename="daybook.sqlite3"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def send_archive_json_download(self):
        with connect() as connection:
            rows = connection.execute(
                "SELECT section, record_id, document_json, server_version, last_saved FROM archive_records ORDER BY section, record_id"
            ).fetchall()
            metadata = {
                row["key"]: json.loads(row["value"])
                for row in connection.execute("SELECT key, value FROM metadata")
            }
            app_state_row = connection.execute("SELECT state_json FROM app_state WHERE id = 1").fetchone()
        collections = {}
        document_meta = {}
        for row in rows:
            collections.setdefault(row["section"], {})[row["record_id"]] = json.loads(row["document_json"])
            if row["server_version"] is not None or row["last_saved"] is not None:
                document_meta.setdefault(row["section"], {})[row["record_id"]] = {
                    "version": row["server_version"],
                    "updatedAt": row["last_saved"],
                }
        backup = {key.removeprefix("backup."): value for key, value in metadata.items() if key.startswith("backup.")}
        backup["exportedAt"] = datetime.now(timezone.utc).isoformat()
        backup["documentCount"] = len(rows)
        backup["databaseReportedCount"] = len(rows)
        payload = {
            "backup": backup,
            "sections": metadata.get("backup.sections", {}),
            "counts": {section: len(records) for section, records in collections.items()},
            "collections": collections,
            "documentMeta": document_meta,
            "currentAppState": json.loads(app_state_row["state_json"]) if app_state_row else {},
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="daybook-backup.json"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        if urlparse(self.path).path != "/api/state":
            return self.send_json({"error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_SIZE:
                return self.send_json({"error": "Request must contain valid JSON under 2 MB"}, 413)
            payload = json.loads(self.rfile.read(length))
            state = payload.get("state") if isinstance(payload, dict) else None
            if not isinstance(state, dict):
                return self.send_json({"error": "Expected a JSON object in the state field"}, 400)
            serialized = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
            with connect() as connection:
                connection.execute(
                    """
                    INSERT INTO app_state (id, state_json, updated_at)
                    VALUES (1, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (serialized,),
                )
                updated_at = connection.execute("SELECT updated_at FROM app_state WHERE id = 1").fetchone()[0]
            return self.send_json({"ok": True, "updatedAt": updated_at})
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return self.send_json({"error": f"Invalid JSON: {error}"}, 400)
        except sqlite3.Error as error:
            print(f"SQLite write failed: {error}", flush=True)
            return self.send_json({"error": "Could not save Daybook data to SQLite"}, 500)

    def do_POST(self):
        if urlparse(self.path).path != "/api/events/refresh":
            return self.send_json({"error": "Not found"}, 404)
        try:
            result = refresh_events()
            return self.send_json(result, 200 if result["ok"] else 502)
        except sqlite3.Error as error:
            print(f"SQLite event refresh failed: {error}", flush=True)
            return self.send_json({"error": "Could not save event suggestions to SQLite"}, 500)


if __name__ == "__main__":
    initialize_database()
    port = int(os.environ.get("DAYBOOK_PORT", "4173"))
    server = ThreadingHTTPServer(("127.0.0.1", port), DaybookHandler)
    print(f"Daybook SQLite server listening at http://127.0.0.1:{port}", flush=True)
    threading.Thread(target=event_refresh_scheduler, daemon=True).start()
    server.serve_forever()
