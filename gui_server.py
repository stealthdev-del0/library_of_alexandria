from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from system import Book, Library, StorageError


def _split_genres(value: str) -> list[str]:
    items = []
    for part in str(value or "").split(","):
        token = " ".join(part.strip().split())
        if token:
            items.append(token)
    return items


def _parse_tags(value: str | list[str] | tuple[str, ...] | set[str]) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = str(value or "").split(",")
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        token = " ".join(part.strip().split()).lower()
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def book_to_api_dict(book: Book) -> dict[str, Any]:
    payload = book.to_dict()
    payload["progress_label"] = book.progress_label()
    payload["display_creator"] = book.composer or book.author
    payload["genres"] = _split_genres(book.genre)
    payload["id"] = book.book_id
    return payload


def filter_books(
    books: list[Book],
    *,
    query: str = "",
    item_type: str = "",
    read: str = "all",
    language: str = "",
    genre: str = "",
    tag: str = "",
    location: str = "",
) -> list[Book]:
    query_key = query.strip().casefold()
    item_type_key = item_type.strip().casefold()
    read_key = read.strip().lower()
    language_key = language.strip().casefold()
    genre_key = genre.strip().casefold()
    tag_key = tag.strip().casefold()
    location_key = location.strip().casefold()

    def matches(book: Book) -> bool:
        if item_type_key and book.item_type.casefold() != item_type_key:
            return False
        if read_key == "read" and not book.read:
            return False
        if read_key == "unread" and book.read:
            return False
        if language_key and book.language.casefold() != language_key:
            return False
        if location_key and book.location.casefold() != location_key:
            return False
        if genre_key and genre_key not in (book.genre or "").casefold():
            return False
        if tag_key and tag_key not in {item.casefold() for item in book.tags}:
            return False
        if query_key:
            haystack = " ".join(
                [
                    book.book_id or "",
                    book.title,
                    book.author,
                    book.composer or "",
                    book.isbn,
                    book.genre,
                    " ".join(book.tags),
                    book.notes,
                    book.language,
                    book.location,
                ]
            ).casefold()
            if query_key not in haystack:
                return False
        return True

    result = [book for book in books if matches(book)]
    result.sort(key=lambda item: (item.title.casefold(), item.author.casefold()))
    return result


def build_graph_payload(books: list[Book]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()

    def ensure_node(node_id: str, label: str, kind: str) -> None:
        if node_id in nodes:
            return
        color = {
            "item": "#58a6ff",
            "creator": "#7ee787",
            "genre": "#f2cc60",
            "tag": "#ff7b72",
            "language": "#c297ff",
            "location": "#6e7681",
        }.get(kind, "#8b949e")
        nodes[node_id] = {
            "id": node_id,
            "label": label,
            "kind": kind,
            "color": color,
        }

    for book in books:
        if not book.book_id:
            continue
        item_id = f"item:{book.book_id}"
        item_label = f"{book.title} ({book.book_id})"
        ensure_node(item_id, item_label, "item")

        creator = (book.composer or book.author).strip()
        if creator:
            creator_id = f"creator:{creator.casefold()}"
            ensure_node(creator_id, creator, "creator")
            edges.add((item_id, creator_id, "created_by"))

        for genre_name in _split_genres(book.genre):
            genre_id = f"genre:{genre_name.casefold()}"
            ensure_node(genre_id, genre_name, "genre")
            edges.add((item_id, genre_id, "in_genre"))

        for tag_name in book.tags[:24]:
            tag_id = f"tag:{tag_name.casefold()}"
            ensure_node(tag_id, tag_name, "tag")
            edges.add((item_id, tag_id, "has_tag"))

        language_id = f"language:{book.language.casefold()}"
        ensure_node(language_id, book.language, "language")
        edges.add((item_id, language_id, "in_language"))

        location_id = f"location:{book.location.casefold()}"
        ensure_node(location_id, book.location, "location")
        edges.add((item_id, location_id, "stored_at"))

    edge_payload = [
        {"source": source, "target": target, "kind": kind}
        for source, target, kind in sorted(edges)
    ]
    return {"nodes": list(nodes.values()), "edges": edge_payload}


def lookup_book_by_isbn(isbn: str) -> dict[str, Any] | None:
    normalized = re.sub(r"[^0-9Xx]", "", str(isbn or ""))
    if not normalized:
        return None

    encoded = quote(normalized)
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{encoded}&format=json&jscmd=data"
    request = Request(
        url,
        headers={
            "User-Agent": "LibraryOfAlexandriaGUI/1.0 (+https://github.com/stealthdev-del0/library_of_alexandria)"
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    entry = payload.get(f"ISBN:{normalized}")
    if not isinstance(entry, dict):
        return None

    title = str(entry.get("title", "")).strip()
    authors = entry.get("authors", [])
    author = ""
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, dict):
            author = str(first.get("name", "")).strip()
    pages = entry.get("number_of_pages")
    if not isinstance(pages, int) or pages <= 0:
        pages = None

    year = None
    publish_date = str(entry.get("publish_date", "")).strip()
    year_match = re.search(r"(1[0-9]{3}|20[0-9]{2}|21[0-9]{2})", publish_date)
    if year_match:
        year = int(year_match.group(1))

    subjects = entry.get("subjects", [])
    subject_names: list[str] = []
    if isinstance(subjects, list):
        for raw in subjects[:8]:
            if isinstance(raw, dict):
                name = str(raw.get("name", "")).strip()
            else:
                name = str(raw).strip()
            if name:
                subject_names.append(name)

    genre = ", ".join(subject_names[:2]) if subject_names else ""
    tags = _parse_tags(subject_names[:6])

    return {
        "isbn": normalized,
        "title": title,
        "author": author,
        "year": year,
        "pages": pages,
        "genre": genre,
        "tags": tags,
        "language": "English",
        "cover": "Softcover",
    }


@dataclass
class SharedRuntime:
    library: Library
    data_file: Path


class _AlexandriaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class AlexandriaGUIServer:
    def __init__(self, runtime: SharedRuntime, host: str = "127.0.0.1", port: int = 8765):
        self.runtime = runtime
        self.host = host
        self.port = port
        self._lock = threading.RLock()
        self._server: _AlexandriaHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _current_library(self) -> Library:
        return self.runtime.library

    def _set_runtime(self, library: Library, data_file: Path) -> None:
        with self._lock:
            self.runtime.library = library
            self.runtime.data_file = data_file

    def update_runtime(self, library: Library, data_file: Path) -> None:
        self._set_runtime(library, data_file)

    def start(self) -> tuple[str, int]:
        handler = self._build_handler()
        self._server = _AlexandriaHTTPServer((self.host, self.port), handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, name="alexandria-gui", daemon=True)
        self._thread.start()
        return self.host, self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _build_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AlexandriaGUI/1.0"

            def _send_json(self, payload: dict[str, Any] | list[Any], status: int = 200) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str, status: int = 200) -> None:
                body = html.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    return {}
                raw = self.rfile.read(length).decode("utf-8", errors="replace")
                if not raw.strip():
                    return {}
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return {}
                if isinstance(parsed, dict):
                    return parsed
                return {}

            def _library(self) -> Library:
                return outer._current_library()

            def _book_from_reference(self, reference: str) -> Book | None:
                return self._library().get_by_reference(reference)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)

                if path == "/" or path == "/index.html":
                    self._send_html(self._render_app_html())
                    return

                if path == "/api/status":
                    lib = self._library()
                    payload = {
                        "host": outer.host,
                        "port": outer.port,
                        "data_file": str(outer.runtime.data_file),
                        "stats": lib.stats(),
                    }
                    self._send_json(payload)
                    return

                if path == "/api/books":
                    lib = self._library()
                    filtered = filter_books(
                        lib.books[:],
                        query=(query.get("query") or [""])[0],
                        item_type=(query.get("item_type") or [""])[0],
                        read=(query.get("read") or ["all"])[0],
                        language=(query.get("language") or [""])[0],
                        genre=(query.get("genre") or [""])[0],
                        tag=(query.get("tag") or [""])[0],
                        location=(query.get("location") or [""])[0],
                    )
                    self._send_json({"items": [book_to_api_dict(item) for item in filtered]})
                    return

                if path.startswith("/api/books/"):
                    reference = path.split("/api/books/", 1)[1]
                    if not reference:
                        self._send_json({"error": "Missing reference"}, status=400)
                        return
                    book = self._book_from_reference(reference)
                    if not book:
                        self._send_json({"error": "Book not found"}, status=404)
                        return
                    self._send_json({"item": book_to_api_dict(book)})
                    return

                if path == "/api/graph":
                    lib = self._library()
                    filtered = filter_books(
                        lib.books[:],
                        query=(query.get("query") or [""])[0],
                        item_type=(query.get("item_type") or [""])[0],
                        read=(query.get("read") or ["all"])[0],
                        language=(query.get("language") or [""])[0],
                        genre=(query.get("genre") or [""])[0],
                        tag=(query.get("tag") or [""])[0],
                        location=(query.get("location") or [""])[0],
                    )
                    payload = build_graph_payload(filtered)
                    self._send_json(payload)
                    return

                if path == "/api/dedup":
                    threshold_raw = (query.get("threshold") or ["0.88"])[0]
                    try:
                        threshold = float(threshold_raw)
                    except ValueError:
                        threshold = 0.88
                    findings = self._library().find_potential_duplicates(threshold=threshold)
                    self._send_json({"findings": findings})
                    return

                if path == "/api/doctor":
                    fix = (query.get("fix") or ["0"])[0] in {"1", "true", "yes"}
                    report = self._library().doctor_data(fix=fix)
                    self._send_json({"report": report, "fix": fix})
                    return

                if path == "/api/recommend":
                    count_raw = (query.get("count") or ["10"])[0]
                    try:
                        count = int(count_raw)
                    except ValueError:
                        count = 10
                    recommendations = self._library().recommend_books_with_reasons(limit=max(1, count))
                    payload = [
                        {
                            "item": book_to_api_dict(entry["book"]),
                            "score": entry["score"],
                            "reasons": entry["reasons"],
                        }
                        for entry in recommendations
                    ]
                    self._send_json({"recommendations": payload})
                    return

                if path == "/api/reading-plan":
                    minutes_raw = (query.get("minutes") or ["120"])[0]
                    weeks_raw = (query.get("weeks") or ["4"])[0]
                    try:
                        minutes = int(minutes_raw)
                        weeks = int(weeks_raw)
                        plan = self._library().create_reading_plan(minutes, weeks=weeks)
                    except (ValueError, TypeError) as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return
                    self._send_json({"plan": plan})
                    return

                if path == "/api/series-next":
                    name = (query.get("name") or [""])[0]
                    items = self._library().next_in_series(name or None)
                    self._send_json({"items": [book_to_api_dict(item) for item in items]})
                    return

                self._send_json({"error": "Not found"}, status=404)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                payload = self._read_json()
                lib = self._library()

                if path == "/api/books":
                    try:
                        book = Book(
                            title=str(payload.get("title", "")).strip(),
                            author=str(payload.get("author", "")).strip(),
                            year=payload.get("year"),
                            isbn=str(payload.get("isbn", "")).strip(),
                            genre=str(payload.get("genre", "")).strip(),
                            pages=payload.get("pages"),
                            read=bool(payload.get("read", False)),
                            notes=str(payload.get("notes", "")).strip(),
                            rating=payload.get("rating"),
                            progress_pages=payload.get("progress_pages"),
                            language=str(payload.get("language", "English")).strip() or "English",
                            location=str(payload.get("location", "Zuhause")).strip() or "Zuhause",
                            cover=str(payload.get("cover", "Softcover")).strip() or "Softcover",
                            tags=_parse_tags(payload.get("tags", [])),
                            item_type=str(payload.get("item_type", "Book")).strip() or "Book",
                            composer=str(payload.get("composer", "")).strip(),
                            instrumentation=str(payload.get("instrumentation", "")).strip(),
                            catalog_number=str(payload.get("catalog_number", "")).strip(),
                            key_signature=str(payload.get("key_signature", "")).strip(),
                            era_style=str(payload.get("era_style", "")).strip(),
                            difficulty=str(payload.get("difficulty", "")).strip(),
                            duration_minutes=payload.get("duration_minutes"),
                            publisher=str(payload.get("publisher", "")).strip(),
                            practice_status=str(payload.get("practice_status", "")).strip(),
                        )
                    except ValueError as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return
                    if not book.title or not book.author:
                        self._send_json({"error": "title and author are required"}, status=400)
                        return
                    try:
                        changed = lib.add_book(book)
                    except StorageError as exc:
                        self._send_json({"error": str(exc)}, status=500)
                        return
                    if not changed:
                        self._send_json({"error": "duplicate item"}, status=409)
                        return
                    self._send_json({"item": book_to_api_dict(book)}, status=201)
                    return

                if path == "/api/books/isbn-autofill":
                    isbn = str(payload.get("isbn", "")).strip()
                    metadata = lookup_book_by_isbn(isbn)
                    if not metadata:
                        self._send_json({"error": "No metadata found for this ISBN"}, status=404)
                        return
                    self._send_json({"metadata": metadata})
                    return

                if path.startswith("/api/books/") and path.endswith("/read"):
                    reference = path[len("/api/books/") : -len("/read")]
                    if not reference:
                        self._send_json({"error": "Missing reference"}, status=400)
                        return
                    read_flag = bool(payload.get("read", True))
                    try:
                        changed = lib.set_read(reference, read_flag)
                    except StorageError as exc:
                        self._send_json({"error": str(exc)}, status=500)
                        return
                    if not changed:
                        self._send_json({"error": "No change"}, status=409)
                        return
                    book = self._book_from_reference(reference)
                    self._send_json({"item": book_to_api_dict(book)} if book else {"ok": True})
                    return

                if path.startswith("/api/books/") and path.endswith("/reading-list"):
                    reference = path[len("/api/books/") : -len("/reading-list")]
                    action = str(payload.get("action", "add")).strip().lower()
                    try:
                        if action == "remove":
                            changed = lib.remove_from_reading_list(reference)
                        else:
                            changed = lib.add_to_reading_list(reference)
                    except StorageError as exc:
                        self._send_json({"error": str(exc)}, status=500)
                        return
                    if not changed:
                        self._send_json({"error": "No change"}, status=409)
                        return
                    self._send_json({"ok": True})
                    return

                if path == "/api/dedup/merge":
                    primary = str(payload.get("primary", "")).strip()
                    duplicate = str(payload.get("duplicate", "")).strip()
                    if not primary or not duplicate:
                        self._send_json({"error": "primary and duplicate are required"}, status=400)
                        return
                    try:
                        changed = lib.merge_items(primary, duplicate)
                    except (StorageError, ValueError) as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return
                    if not changed:
                        self._send_json({"error": "Merge failed"}, status=409)
                        return
                    self._send_json({"ok": True})
                    return

                self._send_json({"error": "Not found"}, status=404)

            def do_PUT(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                payload = self._read_json()
                lib = self._library()
                if path.startswith("/api/books/"):
                    reference = path.split("/api/books/", 1)[1]
                    if not reference:
                        self._send_json({"error": "Missing reference"}, status=400)
                        return
                    updates: dict[str, Any] = {}
                    allowed_fields = {
                        "title",
                        "author",
                        "year",
                        "isbn",
                        "genre",
                        "pages",
                        "read",
                        "notes",
                        "rating",
                        "progress_pages",
                        "language",
                        "location",
                        "cover",
                        "tags",
                        "item_type",
                        "composer",
                        "instrumentation",
                        "catalog_number",
                        "key_signature",
                        "era_style",
                        "difficulty",
                        "duration_minutes",
                        "publisher",
                        "practice_status",
                        "last_practiced",
                        "series_name",
                        "series_index",
                        "ai_summary",
                        "ai_author_note",
                        "ai_tags",
                        "tempo_target_bpm",
                        "practice_minutes_total",
                    }
                    for key in allowed_fields:
                        if key in payload:
                            updates[key] = payload[key]
                    if "tags" in updates:
                        updates["tags"] = _parse_tags(updates["tags"])
                    if "ai_tags" in updates:
                        updates["ai_tags"] = _parse_tags(updates["ai_tags"])
                    try:
                        changed = lib.edit_book(reference, **updates)
                    except (StorageError, ValueError) as exc:
                        self._send_json({"error": str(exc)}, status=400)
                        return
                    if not changed:
                        self._send_json({"error": "No change"}, status=409)
                        return
                    item = self._book_from_reference(reference)
                    if not item and "isbn" in updates:
                        item = self._book_from_reference(str(updates["isbn"]))
                    if not item:
                        self._send_json({"ok": True})
                        return
                    self._send_json({"item": book_to_api_dict(item)})
                    return
                self._send_json({"error": "Not found"}, status=404)

            def do_DELETE(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path
                lib = self._library()
                if path.startswith("/api/books/"):
                    reference = path.split("/api/books/", 1)[1]
                    if not reference:
                        self._send_json({"error": "Missing reference"}, status=400)
                        return
                    try:
                        changed = lib.remove_book(reference)
                    except StorageError as exc:
                        self._send_json({"error": str(exc)}, status=500)
                        return
                    if not changed:
                        self._send_json({"error": "Book not found"}, status=404)
                        return
                    self._send_json({"ok": True})
                    return
                self._send_json({"error": "Not found"}, status=404)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def _render_app_html(self) -> str:
                return GUI_HTML

        return Handler


GUI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Alexandria GUI</title>
  <style>
    :root{
      --bg:#0a1020;
      --bg2:#121a34;
      --panel:#131e3b;
      --line:#24365f;
      --text:#eaf0ff;
      --muted:#9aaedc;
      --accent:#58a6ff;
      --ok:#39d98a;
      --warn:#f2cc60;
      --err:#ff7b72;
      --shadow:0 20px 44px rgba(0,0,0,.24);
      --radius:14px;
      --ease:cubic-bezier(.22,1,.36,1);
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0;
      font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;
      background:
        radial-gradient(1200px 760px at 20% -18%,#26408a4f,transparent),
        radial-gradient(980px 740px at 112% 16%,#39d98a17,transparent),
        var(--bg);
      color:var(--text);
    }
    .app{
      min-height:100vh;
      display:grid;
      grid-template-columns:320px 1fr;
    }
    .sidebar{
      border-right:1px solid var(--line);
      background:linear-gradient(180deg,#0e1630 0%,#0a1020 100%);
      padding:16px;
      display:flex;
      flex-direction:column;
      gap:12px;
      position:sticky;
      top:0;
      height:100vh;
    }
    .brand{display:grid;gap:4px}
    .title{font-size:20px;font-weight:760;letter-spacing:.2px}
    .sub{font-size:12px;color:var(--muted)}
    .tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
    .tabs button{
      padding:10px 8px;
      border-radius:11px;
      border:1px solid var(--line);
      background:#111b37;
      color:var(--text);
      cursor:pointer;
      transition:transform .18s var(--ease),border-color .18s var(--ease),background .18s var(--ease);
    }
    .tabs button:hover{transform:translateY(-1px)}
    .tabs button.active{
      border-color:var(--accent);
      background:linear-gradient(180deg,#173267,#132955);
      box-shadow:0 0 0 1px #58a6ff55 inset;
    }
    input,select,textarea,button{font:inherit}
    input,select,textarea{
      background:#0c1532;
      border:1px solid var(--line);
      color:var(--text);
      border-radius:11px;
      padding:10px;
      transition:border-color .18s var(--ease),box-shadow .18s var(--ease),background .18s var(--ease);
    }
    input:focus,select:focus,textarea:focus{
      outline:none;
      border-color:var(--accent);
      box-shadow:0 0 0 2px #58a6ff33;
      background:#101c40;
    }
    textarea{min-height:84px;resize:vertical}
    button{
      background:#1a2c58;
      border:1px solid #355286;
      color:var(--text);
      border-radius:11px;
      padding:10px 12px;
      cursor:pointer;
      transition:transform .16s var(--ease),filter .16s var(--ease),background .16s var(--ease),border-color .16s var(--ease);
    }
    button:hover{transform:translateY(-1px);filter:brightness(1.04)}
    button:active{transform:translateY(0)}
    button.primary{background:linear-gradient(180deg,#2e67c9,#2351a5);border-color:#4478d8}
    button.ok{background:#1f513f;border-color:#2f785f}
    button.warn{background:#5c4a21;border-color:#7c6331}
    button.err{background:#5c2727;border-color:#824141}
    button.ghost{background:#121d3c}
    .status{font-size:12px;color:var(--muted)}
    .status.ok{color:var(--ok)}
    .status.warn{color:var(--warn)}
    .status.err{color:var(--err)}
    .content{
      padding:16px;
      display:grid;
      grid-template-rows:auto 1fr;
      gap:12px;
    }
    .topbar{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      position:sticky;
      top:8px;
      z-index:8;
      background:linear-gradient(180deg,rgba(10,16,32,.96),rgba(10,16,32,.74));
      backdrop-filter:blur(6px);
      border:1px solid #1b2a4d;
      border-radius:13px;
      padding:10px 12px;
      box-shadow:var(--shadow);
    }
    .chip{
      padding:6px 10px;
      border:1px solid var(--line);
      border-radius:999px;
      background:#0f1735;
      color:var(--muted);
      font-size:12px;
      white-space:nowrap;
    }
    .toolbar{display:flex;flex-wrap:wrap;gap:8px}
    .panel{
      background:linear-gradient(180deg,#121b36,#0f1731);
      border:1px solid var(--line);
      border-radius:var(--radius);
      overflow:hidden;
      box-shadow:var(--shadow);
      animation:fadeIn .22s var(--ease);
    }
    @keyframes fadeIn{
      from{opacity:.55;transform:translateY(6px)}
      to{opacity:1;transform:translateY(0)}
    }
    .panel h3{
      margin:0;
      padding:12px 14px;
      border-bottom:1px solid var(--line);
      font-size:14px;
      letter-spacing:.2px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:8px;
    }
    .panel-body{padding:12px 14px}
    .grid{display:grid;grid-template-columns:1.15fr .85fr;gap:12px;height:calc(100vh - 110px)}
    .scroll{overflow:auto;max-height:100%}
    table{width:100%;border-collapse:collapse}
    th,td{
      padding:9px 8px;
      border-bottom:1px solid #1f2c4f;
      font-size:13px;
      text-align:left;
      white-space:nowrap;
    }
    th{position:sticky;top:0;background:#111a36;z-index:2}
    td.clip{
      max-width:260px;
      overflow:hidden;
      text-overflow:ellipsis;
    }
    tbody tr{cursor:pointer;transition:background .16s var(--ease)}
    tbody tr:hover{background:#1a2750}
    tbody tr.active{background:#223764}
    .details dl{
      display:grid;
      grid-template-columns:132px 1fr;
      gap:6px 10px;
      margin:0;
    }
    .details dt{color:var(--muted)}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
    .form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
    .form-grid .full{grid-column:1/-1}
    .split{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
    .hidden{display:none}
    .graph-controls{
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:8px;
      margin-bottom:10px;
    }
    .toggles{
      display:flex;
      flex-wrap:wrap;
      gap:8px 14px;
      margin:10px 0;
      color:var(--muted);
      font-size:12px;
    }
    .toggles label{
      display:flex;
      align-items:center;
      gap:6px;
      user-select:none;
      cursor:pointer;
    }
    .graph-wrap{
      position:relative;
      background:#0b1126;
      border:1px solid var(--line);
      border-radius:12px;
      overflow:hidden;
    }
    #graphCanvas{
      width:100%;
      height:560px;
      display:block;
      cursor:grab;
      background:radial-gradient(800px 520px at 10% -12%,#21408933,transparent),#0b1126;
    }
    #graphCanvas.dragging{cursor:grabbing}
    .graph-tip{
      position:absolute;
      bottom:8px;
      right:10px;
      background:#09102acc;
      border:1px solid #20345c;
      border-radius:8px;
      padding:6px 8px;
      font-size:11px;
      color:var(--muted);
      pointer-events:none;
    }
    .spinner{
      width:16px;
      height:16px;
      border:2px solid #5078bd;
      border-top-color:transparent;
      border-radius:50%;
      animation:spin .7s linear infinite;
      display:inline-block;
      vertical-align:middle;
      margin-left:6px;
    }
    @keyframes spin{to{transform:rotate(360deg)}}
    .console-shell{
      position:fixed;
      left:320px;
      right:0;
      bottom:0;
      background:linear-gradient(180deg,#0d162f,#0a1125);
      border-top:1px solid var(--line);
      box-shadow:0 -16px 40px rgba(0,0,0,.35);
      transform:translateY(calc(100% - 40px));
      transition:transform .22s var(--ease);
      z-index:40;
    }
    .console-shell.open{transform:translateY(0)}
    .console-head{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:8px;
      padding:8px 12px;
      border-bottom:1px solid #1e2e55;
      cursor:pointer;
      user-select:none;
    }
    .console-title{font-size:12px;color:var(--muted)}
    .console-body{
      padding:10px 12px;
      display:grid;
      gap:8px;
      max-height:46vh;
    }
    .console-log{
      background:#081026;
      border:1px solid #1f3158;
      border-radius:10px;
      padding:10px;
      min-height:120px;
      max-height:30vh;
      overflow:auto;
      font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;
      font-size:12px;
      line-height:1.5;
      white-space:pre-wrap;
    }
    .console-line.ok{color:#9ef8c9}
    .console-line.err{color:#ffaca7}
    .console-line.muted{color:#94a6d6}
    .console-input{
      display:grid;
      grid-template-columns:1fr auto auto;
      gap:8px;
    }
    .prompt{color:#9dc4ff;font-size:12px}
    .k{color:#9eb7ec}
    .legend{
      display:flex;
      flex-wrap:wrap;
      gap:8px 12px;
      color:var(--muted);
      font-size:12px;
    }
    .dot{
      width:10px;
      height:10px;
      border-radius:999px;
      display:inline-block;
      vertical-align:middle;
      margin-right:5px;
    }
    .search-box{display:grid;grid-template-columns:1fr auto;gap:8px}
    .tiny{font-size:11px;color:var(--muted)}
    @media (max-width: 1100px){
      .app{grid-template-columns:1fr}
      .sidebar{
        position:relative;
        height:auto;
        border-right:none;
        border-bottom:1px solid var(--line);
      }
      .grid{grid-template-columns:1fr;height:auto}
      #graphCanvas{height:420px}
      .graph-controls{grid-template-columns:repeat(2,minmax(0,1fr))}
      .console-shell{left:0}
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="title">Library Of Alexandria</div>
        <div class="sub">GUI + CLI style workflow on one dataset</div>
      </div>
      <div class="tabs">
        <button id="tabLibrary" class="active">Library</button>
        <button id="tabGraph">Graph</button>
        <button id="tabTools">Tools</button>
      </div>
      <div class="search-box">
        <input id="searchInput" placeholder="Search title, author, isbn..." />
        <button id="searchBtn">Go</button>
      </div>
      <div class="split">
        <select id="quickRead">
          <option value="all">All</option>
          <option value="read">Read</option>
          <option value="unread">Unread</option>
        </select>
        <select id="quickType">
          <option value="">Type</option>
          <option value="Book">Book</option>
          <option value="SheetMusic">SheetMusic</option>
        </select>
        <select id="quickLang">
          <option value="">Language</option>
          <option value="German">German</option>
          <option value="English">English</option>
          <option value="French">French</option>
          <option value="Japanese">Japanese</option>
        </select>
      </div>
      <button id="toggleConsoleBtn" class="ghost">Toggle Console</button>
      <div class="status" id="statusLine">Ready.</div>
      <div class="status" id="serverLine">Loading...</div>
      <div class="tiny">Tip: Ctrl + ` opens the console.</div>
    </aside>

    <main class="content">
      <div class="topbar">
        <div class="chip" id="statsChip">0 items</div>
        <div class="toolbar">
          <button id="refreshBtn">Refresh</button>
          <button id="markReadBtn" class="ok">Mark Read</button>
          <button id="markUnreadBtn">Mark Unread</button>
          <button id="readingAddBtn">Reading +</button>
          <button id="readingRemoveBtn">Reading -</button>
          <button id="deleteBtn" class="err">Delete</button>
          <button id="openConsoleBtn" class="ghost">Console</button>
        </div>
      </div>

      <section id="libraryView" class="grid">
        <div class="panel scroll">
          <h3>Items</h3>
          <div class="panel-body">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Title</th>
                  <th>Creator</th>
                  <th>Lang</th>
                  <th>Read</th>
                </tr>
              </thead>
              <tbody id="booksBody"></tbody>
            </table>
          </div>
        </div>
        <div class="panel scroll">
          <h3>
            <span>Details & Edit</span>
            <span id="busyBadge" class="tiny"></span>
          </h3>
          <div class="panel-body">
            <div class="details">
              <dl id="detailsList"></dl>
            </div>
            <hr style="border-color:#22315a;border-style:solid;border-width:1px 0 0;margin:12px 0" />
            <div class="form-grid">
              <input id="fTitle" placeholder="Title" class="full" />
              <input id="fAuthor" placeholder="Author" />
              <select id="fType">
                <option value="Book">Book</option>
                <option value="SheetMusic">SheetMusic</option>
              </select>
              <input id="fIsbn" placeholder="ISBN" />
              <button id="isbnAutofillBtn">ISBN AutoFill</button>
              <input id="fYear" placeholder="Year" />
              <input id="fPages" placeholder="Pages" />
              <input id="fGenre" placeholder="Genre(s)" class="full" />
              <input id="fLanguage" placeholder="Language" />
              <input id="fCover" placeholder="Cover" />
              <input id="fLocation" placeholder="Location (Pforta|Zuhause)" />
              <input id="fRating" placeholder="Rating 1-5" />
              <input id="fProgress" placeholder="Progress pages" />
              <input id="fTags" placeholder="Tags comma-separated" class="full" />
              <textarea id="fNotes" placeholder="Notes" class="full"></textarea>
              <button id="createBtn" class="primary">Create</button>
              <button id="updateBtn">Update Selected</button>
            </div>
          </div>
        </div>
      </section>

      <section id="graphView" class="hidden">
        <div class="panel">
          <h3>Graph Explorer</h3>
          <div class="panel-body">
            <div class="graph-controls">
              <input id="gQuery" placeholder="Query" />
              <select id="gType">
                <option value="">All Types</option>
                <option value="Book">Book</option>
                <option value="SheetMusic">SheetMusic</option>
              </select>
              <select id="gRead">
                <option value="all">Read + Unread</option>
                <option value="read">Read</option>
                <option value="unread">Unread</option>
              </select>
              <input id="gLanguage" placeholder="Language" />
              <input id="gGenre" placeholder="Genre" />
              <input id="gTag" placeholder="Tag" />
              <input id="gLocation" placeholder="Location" />
              <button id="graphReloadBtn" class="primary">Reload Graph</button>
            </div>

            <div class="toggles">
              <label><input type="checkbox" id="kItem" checked /> Item</label>
              <label><input type="checkbox" id="kCreator" checked /> Creator</label>
              <label><input type="checkbox" id="kGenre" checked /> Genre</label>
              <label><input type="checkbox" id="kTag" checked /> Tag</label>
              <label><input type="checkbox" id="kLanguage" checked /> Language</label>
              <label><input type="checkbox" id="kLocation" checked /> Location</label>
              <button id="graphFitBtn" class="ghost">Fit</button>
              <button id="graphPauseBtn" class="ghost">Pause</button>
            </div>

            <div class="legend">
              <span><i class="dot" style="background:#58a6ff"></i>Item</span>
              <span><i class="dot" style="background:#7ee787"></i>Creator</span>
              <span><i class="dot" style="background:#f2cc60"></i>Genre</span>
              <span><i class="dot" style="background:#ff7b72"></i>Tag</span>
              <span><i class="dot" style="background:#c297ff"></i>Language</span>
              <span><i class="dot" style="background:#6e7681"></i>Location</span>
            </div>

            <div class="graph-wrap">
              <canvas id="graphCanvas" width="1400" height="560"></canvas>
              <div class="graph-tip">Wheel: zoom | Drag canvas: pan | Drag node: move | Click node: open/filter</div>
            </div>
            <div class="status" id="graphInfo" style="margin-top:8px"></div>
          </div>
        </div>
      </section>

      <section id="toolsView" class="hidden">
        <div class="grid">
          <div class="panel">
            <h3>Diagnostics & Dedup</h3>
            <div class="panel-body">
              <div class="toolbar">
                <button id="doctorBtn">Doctor</button>
                <button id="doctorFixBtn" class="warn">Doctor Fix</button>
                <input id="dedupThreshold" value="0.88" style="width:90px" />
                <button id="dedupScanBtn">Dedup Scan</button>
              </div>
              <pre id="doctorOut" class="mono" style="white-space:pre-wrap"></pre>
            </div>
          </div>
          <div class="panel">
            <h3>Reading Intelligence</h3>
            <div class="panel-body">
              <div class="toolbar">
                <input id="planMinutes" value="120" style="width:90px" />
                <input id="planWeeks" value="4" style="width:70px" />
                <button id="planBtn">Reading Plan</button>
                <input id="recCount" value="10" style="width:70px" />
                <button id="recBtn">Recommend</button>
              </div>
              <pre id="planOut" class="mono" style="white-space:pre-wrap"></pre>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <section id="consoleShell" class="console-shell">
    <div class="console-head" id="consoleHead">
      <div class="console-title">Command Console</div>
      <div class="prompt" id="consolePromptLabel">alexandria (0 books)&gt;</div>
    </div>
    <div class="console-body">
      <div id="consoleLog" class="console-log"></div>
      <div class="console-input">
        <input id="consoleInput" class="mono" placeholder="help | ls | details b0001 | add title=&quot;Dune&quot; author=&quot;Frank Herbert&quot;" />
        <button id="consoleRunBtn" class="primary">Run</button>
        <button id="consoleClearBtn" class="ghost">Clear</button>
      </div>
    </div>
  </section>

  <script>
    const state = {
      items: [],
      selectedId: null,
      graph: { nodes: [], edges: [] },
      graphLayout: null,
      busy: 0,
      consoleHistory: [],
      consoleHistoryIndex: -1,
      kindFilters: new Set(["item", "creator", "genre", "tag", "language", "location"]),
    };
    const $ = (id) => document.getElementById(id);

    function esc(v){
      return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    }
    function fmt(v){ return (v === null || v === undefined || v === "") ? "-" : String(v); }

    function setStatus(msg, level="muted"){
      const el = $("statusLine");
      el.textContent = msg;
      el.className = "status " + (level || "muted");
    }
    function setBusy(on){
      state.busy += on ? 1 : -1;
      if(state.busy < 0){ state.busy = 0; }
      $("busyBadge").innerHTML = state.busy > 0 ? 'Working <span class="spinner"></span>' : "";
    }

    function logConsole(msg, level="muted"){
      const row = document.createElement("div");
      row.className = "console-line " + level;
      row.textContent = msg;
      $("consoleLog").appendChild(row);
      $("consoleLog").scrollTop = $("consoleLog").scrollHeight;
    }

    async function api(path, opts={}){
      setBusy(true);
      try {
        const resp = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
        let data = {};
        try { data = await resp.json(); } catch(_e) {}
        if(!resp.ok){ throw new Error(data.error || ("HTTP " + resp.status)); }
        return data;
      } finally {
        setBusy(false);
      }
    }

    function parseIntOrNull(v){
      const raw = String(v ?? "").trim();
      if(!raw){ return null; }
      const n = parseInt(raw, 10);
      return Number.isFinite(n) ? n : null;
    }

    function toPayloadFromForm(){
      return {
        title: $("fTitle").value.trim(),
        author: $("fAuthor").value.trim(),
        item_type: $("fType").value,
        isbn: $("fIsbn").value.trim(),
        year: parseIntOrNull($("fYear").value),
        pages: parseIntOrNull($("fPages").value),
        genre: $("fGenre").value.trim(),
        language: $("fLanguage").value.trim() || "English",
        cover: $("fCover").value.trim() || "Softcover",
        location: $("fLocation").value.trim() || "Zuhause",
        rating: parseIntOrNull($("fRating").value),
        progress_pages: parseIntOrNull($("fProgress").value),
        tags: $("fTags").value.trim(),
        notes: $("fNotes").value.trim(),
      };
    }

    function fillForm(item){
      if(!item){ return; }
      $("fTitle").value = item.title || "";
      $("fAuthor").value = item.author || "";
      $("fType").value = item.item_type || "Book";
      $("fIsbn").value = item.isbn || "";
      $("fYear").value = item.year ?? "";
      $("fPages").value = item.pages ?? "";
      $("fGenre").value = item.genre || "";
      $("fLanguage").value = item.language || "";
      $("fCover").value = item.cover || "";
      $("fLocation").value = item.location || "";
      $("fRating").value = item.rating ?? "";
      $("fProgress").value = item.progress_pages ?? "";
      $("fTags").value = (item.tags || []).join(", ");
      $("fNotes").value = item.notes || "";
    }

    function renderDetails(item){
      const dl = $("detailsList");
      if(!item){
        dl.innerHTML = "<dt>Selection</dt><dd>-</dd>";
        return;
      }
      const rows = [
        ["ID", item.book_id || "-"],
        ["Type", item.item_type],
        ["Title", item.title],
        ["Author", item.author],
        ["Composer", item.composer || "-"],
        ["ISBN", item.isbn || "-"],
        ["Year", fmt(item.year)],
        ["Genre", item.genre || "-"],
        ["Language", item.language],
        ["Cover", item.cover],
        ["Location", item.location],
        ["Pages", fmt(item.pages)],
        ["Progress", item.progress_label || "-"],
        ["Rating", fmt(item.rating)],
        ["Read", item.read ? "yes" : "no"],
        ["Series", item.series_name || "-"],
        ["Series #", fmt(item.series_index)],
        ["Tags", (item.tags || []).join(", ") || "-"],
        ["AI Tags", (item.ai_tags || []).join(", ") || "-"],
        ["AI Summary", item.ai_summary || "-"],
        ["AI Author", item.ai_author_note || "-"],
        ["Notes", item.notes || "-"],
      ];
      dl.innerHTML = rows.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
    }

    function renderBooks(){
      const body = $("booksBody");
      body.innerHTML = "";
      for(const item of state.items){
        const tr = document.createElement("tr");
        if(item.book_id === state.selectedId){ tr.classList.add("active"); }
        tr.innerHTML = `
          <td>${esc(item.book_id || "-")}</td>
          <td>${item.item_type === "SheetMusic" ? "Sheet" : "Book"}</td>
          <td class="clip" title="${esc(item.title)}">${esc(item.title)}</td>
          <td class="clip" title="${esc(item.display_creator || item.author)}">${esc(item.display_creator || item.author)}</td>
          <td>${esc(item.language || "-")}</td>
          <td>${item.read ? "yes" : "no"}</td>
        `;
        tr.onclick = async () => {
          state.selectedId = item.book_id;
          renderBooks();
          await loadDetails(item.book_id);
        };
        body.appendChild(tr);
      }
      $("statsChip").textContent = `${state.items.length} items`;
      $("consolePromptLabel").textContent = `alexandria (${state.items.length} books)>`;
    }

    function listFilters(){
      const p = new URLSearchParams();
      const query = $("searchInput").value.trim();
      if(query){ p.set("query", query); }
      const quickRead = $("quickRead").value;
      if(quickRead){ p.set("read", quickRead); }
      const quickType = $("quickType").value;
      if(quickType){ p.set("item_type", quickType); }
      const quickLang = $("quickLang").value;
      if(quickLang){ p.set("language", quickLang); }
      return p.toString();
    }

    async function loadBooks(){
      const data = await api("/api/books?" + listFilters());
      state.items = data.items || [];
      if(state.selectedId && !state.items.some(x => x.book_id === state.selectedId)){ state.selectedId = null; }
      renderBooks();
      if(state.selectedId){
        await loadDetails(state.selectedId);
      } else {
        renderDetails(null);
      }
    }

    async function loadDetails(reference){
      const data = await api("/api/books/" + encodeURIComponent(reference));
      renderDetails(data.item);
      fillForm(data.item);
    }

    async function createBook(){
      const payload = toPayloadFromForm();
      const data = await api("/api/books", { method:"POST", body: JSON.stringify(payload) });
      setStatus(`Saved: ${data.item.book_id}`, "ok");
      await loadBooks();
    }

    async function updateBook(){
      if(!state.selectedId){ setStatus("Select an item first.", "warn"); return; }
      const payload = toPayloadFromForm();
      const data = await api("/api/books/" + encodeURIComponent(state.selectedId), { method:"PUT", body: JSON.stringify(payload) });
      setStatus(`Updated: ${(data.item && data.item.book_id) || state.selectedId}`, "ok");
      await loadBooks();
      await loadDetails(state.selectedId);
    }

    async function deleteBook(){
      if(!state.selectedId){ setStatus("Select an item first.", "warn"); return; }
      if(!confirm("Delete selected item? (y/N)")){ return; }
      await api("/api/books/" + encodeURIComponent(state.selectedId), { method:"DELETE" });
      setStatus(`Removed: ${state.selectedId}`, "warn");
      state.selectedId = null;
      await loadBooks();
      renderDetails(null);
    }

    async function setRead(flag){
      if(!state.selectedId){ setStatus("Select an item first.", "warn"); return; }
      await api("/api/books/" + encodeURIComponent(state.selectedId) + "/read", { method:"POST", body: JSON.stringify({read: !!flag}) });
      setStatus(flag ? "Updated: marked read." : "Updated: marked unread.", "ok");
      await loadBooks();
      await loadDetails(state.selectedId);
    }

    async function readingList(action){
      if(!state.selectedId){ setStatus("Select an item first.", "warn"); return; }
      await api("/api/books/" + encodeURIComponent(state.selectedId) + "/reading-list", { method:"POST", body: JSON.stringify({action}) });
      setStatus(action === "add" ? "Updated: reading list +1." : "Updated: reading list -1.", "ok");
    }

    async function isbnAutofill(){
      const isbn = $("fIsbn").value.trim();
      if(!isbn){ setStatus("Enter ISBN first.", "warn"); return; }
      const data = await api("/api/books/isbn-autofill", { method:"POST", body: JSON.stringify({isbn}) });
      const m = data.metadata || {};
      if(m.title && !$("fTitle").value.trim()) $("fTitle").value = m.title;
      if(m.author && !$("fAuthor").value.trim()) $("fAuthor").value = m.author;
      if(m.year && !$("fYear").value.trim()) $("fYear").value = String(m.year);
      if(m.pages && !$("fPages").value.trim()) $("fPages").value = String(m.pages);
      if(m.genre && !$("fGenre").value.trim()) $("fGenre").value = m.genre;
      if(Array.isArray(m.tags) && m.tags.length && !$("fTags").value.trim()) $("fTags").value = m.tags.join(", ");
      if(m.language && !$("fLanguage").value.trim()) $("fLanguage").value = m.language;
      if(m.cover && !$("fCover").value.trim()) $("fCover").value = m.cover;
      setStatus("Saved: ISBN metadata loaded.", "ok");
    }

    function tab(name){
      const map = { Library:"libraryView", Graph:"graphView", Tools:"toolsView" };
      for(const [k,v] of Object.entries(map)){
        $(v).classList.toggle("hidden", k !== name);
        $("tab" + k).classList.toggle("active", k === name);
      }
      if(name === "Graph"){ ensureGraphRunning(); requestGraphDraw(); }
    }

    function graphFilters(){
      const p = new URLSearchParams();
      const pairs = [
        ["query", $("gQuery").value.trim()],
        ["item_type", $("gType").value],
        ["read", $("gRead").value],
        ["language", $("gLanguage").value.trim()],
        ["genre", $("gGenre").value.trim()],
        ["tag", $("gTag").value.trim()],
        ["location", $("gLocation").value.trim()],
      ];
      for(const [k,v] of pairs){ if(v) p.set(k, v); }
      return p.toString();
    }

    function updateKindFilters(){
      const boxToKind = [
        ["kItem", "item"],
        ["kCreator", "creator"],
        ["kGenre", "genre"],
        ["kTag", "tag"],
        ["kLanguage", "language"],
        ["kLocation", "location"],
      ];
      state.kindFilters.clear();
      for(const [id, kind] of boxToKind){
        if($(id).checked){ state.kindFilters.add(kind); }
      }
      if(state.kindFilters.size === 0){
        for(const [_id, kind] of boxToKind){ state.kindFilters.add(kind); }
      }
      rebuildGraphLayout();
      requestGraphDraw();
    }

    function rebuildGraphLayout(){
      const prev = state.graphLayout;
      const prevPos = {};
      if(prev && prev.nodes){
        for(const node of prev.nodes){ prevPos[node.id] = node; }
      }
      const nodes = [];
      const sourceNodes = state.graph.nodes || [];
      for(const raw of sourceNodes){
        if(!state.kindFilters.has(raw.kind)){ continue; }
        const p = prevPos[raw.id];
        nodes.push({
          ...raw,
          x: p ? p.x : (Math.random() - 0.5) * 420,
          y: p ? p.y : (Math.random() - 0.5) * 320,
          vx: p ? p.vx : 0,
          vy: p ? p.vy : 0,
          fixed: false,
          r: raw.kind === "item" ? 8 : 5,
          hover: false,
        });
      }
      const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
      const links = [];
      for(const e of state.graph.edges || []){
        const a = nodeById[e.source];
        const b = nodeById[e.target];
        if(!a || !b){ continue; }
        links.push({ a, b, kind: e.kind });
      }
      const neighborMap = {};
      for(const n of nodes){ neighborMap[n.id] = new Set(); }
      for(const l of links){
        neighborMap[l.a.id].add(l.b.id);
        neighborMap[l.b.id].add(l.a.id);
      }

      state.graphLayout = {
        nodes,
        links,
        neighborMap,
        panX: prev ? prev.panX : 0,
        panY: prev ? prev.panY : 0,
        zoom: prev ? prev.zoom : 1,
        running: prev ? prev.running : true,
        hoveredId: null,
        selectedId: prev ? prev.selectedId : null,
        pointerMode: null,
        dragNode: null,
        panStart: null,
        clickCandidate: null,
        raf: null,
      };
      if(nodes.length && !prev){
        fitGraph();
      }
    }

    async function loadGraph(){
      const data = await api("/api/graph?" + graphFilters());
      state.graph = data;
      rebuildGraphLayout();
      ensureGraphRunning();
      requestGraphDraw();
      const n = state.graphLayout ? state.graphLayout.nodes.length : 0;
      const e = state.graphLayout ? state.graphLayout.links.length : 0;
      $("graphInfo").textContent = `${n} nodes, ${e} edges`;
    }

    function graphCanvasContext(){
      const canvas = $("graphCanvas");
      const ctx = canvas.getContext("2d");
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(900, Math.floor(rect.width * dpr));
      const h = Math.max(420, Math.floor(rect.height * dpr));
      if(canvas.width !== w || canvas.height !== h){
        canvas.width = w;
        canvas.height = h;
      }
      return { canvas, ctx, rect, dpr, w, h };
    }

    function worldToScreen(x, y, layout, dpr, w, h){
      return {
        x: ((x + layout.panX) * layout.zoom + (w * 0.5 / dpr)) * dpr,
        y: ((y + layout.panY) * layout.zoom + (h * 0.5 / dpr)) * dpr,
      };
    }

    function screenToWorld(px, py, layout, dpr, w, h){
      const sx = px / dpr - (w * 0.5 / dpr);
      const sy = py / dpr - (h * 0.5 / dpr);
      return {
        x: sx / layout.zoom - layout.panX,
        y: sy / layout.zoom - layout.panY,
      };
    }

    function getNodeAt(px, py){
      const layout = state.graphLayout;
      if(!layout){ return null; }
      const { dpr, w, h } = graphCanvasContext();
      const world = screenToWorld(px, py, layout, dpr, w, h);
      for(let i = layout.nodes.length - 1; i >= 0; i--){
        const n = layout.nodes[i];
        const r = (n.r + 5) / layout.zoom;
        const dx = world.x - n.x;
        const dy = world.y - n.y;
        if((dx * dx + dy * dy) <= (r * r)){ return n; }
      }
      return null;
    }

    function fitGraph(){
      const layout = state.graphLayout;
      if(!layout || !layout.nodes.length){ return; }
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for(const n of layout.nodes){
        if(n.x < minX) minX = n.x;
        if(n.y < minY) minY = n.y;
        if(n.x > maxX) maxX = n.x;
        if(n.y > maxY) maxY = n.y;
      }
      const spanX = Math.max(80, maxX - minX);
      const spanY = Math.max(80, maxY - minY);
      const { dpr, w, h } = graphCanvasContext();
      const viewW = w / dpr;
      const viewH = h / dpr;
      const zx = (viewW * 0.82) / spanX;
      const zy = (viewH * 0.82) / spanY;
      layout.zoom = Math.max(0.35, Math.min(2.3, Math.min(zx, zy)));
      layout.panX = -(minX + maxX) * 0.5;
      layout.panY = -(minY + maxY) * 0.5;
      requestGraphDraw();
    }

    function stepGraphPhysics(){
      const layout = state.graphLayout;
      if(!layout || !layout.running){ return; }
      const nodes = layout.nodes;
      const links = layout.links;
      if(!nodes.length){ return; }

      const repulsion = 2500;
      for(let i = 0; i < nodes.length; i++){
        const a = nodes[i];
        for(let j = i + 1; j < nodes.length; j++){
          const b = nodes[j];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy + 0.05;
          const d = Math.sqrt(d2);
          const f = repulsion / d2;
          const ux = dx / d;
          const uy = dy / d;
          a.vx += ux * f;
          a.vy += uy * f;
          b.vx -= ux * f;
          b.vy -= uy * f;
        }
      }

      for(const l of links){
        const dx = l.b.x - l.a.x;
        const dy = l.b.y - l.a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const target = (l.a.kind === "item" || l.b.kind === "item") ? 110 : 76;
        const pull = (d - target) * 0.02;
        const ux = dx / d;
        const uy = dy / d;
        l.a.vx += ux * pull;
        l.a.vy += uy * pull;
        l.b.vx -= ux * pull;
        l.b.vy -= uy * pull;
      }

      for(const n of nodes){
        if(n.fixed){ continue; }
        n.vx *= 0.78;
        n.vy *= 0.78;
        n.x += n.vx * 0.08;
        n.y += n.vy * 0.08;
      }
    }

    function drawGraph(){
      const layout = state.graphLayout;
      const { ctx, dpr, w, h } = graphCanvasContext();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, w, h);
      if(!layout){ return; }

      ctx.save();
      ctx.translate(w * 0.5, h * 0.5);
      ctx.scale(layout.zoom * dpr, layout.zoom * dpr);
      ctx.translate(layout.panX, layout.panY);

      const selected = layout.selectedId || null;
      const hovered = layout.hoveredId || null;
      const neighbors = hovered && layout.neighborMap[hovered] ? layout.neighborMap[hovered] : null;

      for(const l of layout.links){
        const highlighted = hovered && (l.a.id === hovered || l.b.id === hovered || (neighbors && (neighbors.has(l.a.id) || neighbors.has(l.b.id))));
        ctx.lineWidth = highlighted ? 1.4 / layout.zoom : 1 / layout.zoom;
        ctx.strokeStyle = highlighted ? "#5f88cf" : "#2c416c";
        ctx.beginPath();
        ctx.moveTo(l.a.x, l.a.y);
        ctx.lineTo(l.b.x, l.b.y);
        ctx.stroke();
      }

      for(const n of layout.nodes){
        const isSelected = selected && n.id === selected;
        const isHovered = hovered && n.id === hovered;
        ctx.beginPath();
        ctx.fillStyle = n.color || "#8b949e";
        const rr = n.r / layout.zoom + (isSelected ? 3 / layout.zoom : isHovered ? 2 / layout.zoom : 0);
        ctx.arc(n.x, n.y, rr, 0, Math.PI * 2);
        ctx.fill();
        if(isSelected || isHovered){
          ctx.lineWidth = 1.5 / layout.zoom;
          ctx.strokeStyle = "#cfe2ff";
          ctx.stroke();
        }
      }

      ctx.font = `${11 / layout.zoom}px ui-sans-serif, system-ui`;
      ctx.fillStyle = "#dbe8ff";
      for(const n of layout.nodes){
        if(n.kind !== "item" && n.id !== hovered){ continue; }
        const label = n.label.length > 32 ? n.label.slice(0, 31) + "..." : n.label;
        ctx.fillText(label, n.x + (12 / layout.zoom), n.y + (4 / layout.zoom));
      }
      ctx.restore();
    }

    function graphLoop(){
      const layout = state.graphLayout;
      if(!layout){ return; }
      if(layout.running){ stepGraphPhysics(); }
      drawGraph();
      layout.raf = window.requestAnimationFrame(graphLoop);
    }

    function ensureGraphRunning(){
      const layout = state.graphLayout;
      if(!layout){ return; }
      if(layout.raf === null){
        layout.raf = window.requestAnimationFrame(graphLoop);
      }
    }

    function requestGraphDraw(){
      if(!$("graphView").classList.contains("hidden")){
        drawGraph();
      }
    }

    function selectItem(reference){
      tab("Library");
      state.selectedId = reference;
      return loadBooks().then(() => loadDetails(reference));
    }

    function applyNodeFilter(node){
      if(node.kind === "item"){
        const ref = node.id.replace(/^item:/, "");
        setStatus("Selected from graph: " + ref, "ok");
        return selectItem(ref);
      }
      if(node.kind === "creator"){
        $("searchInput").value = node.label;
        setStatus("Filter by creator: " + node.label, "ok");
        tab("Library");
        return loadBooks();
      }
      if(node.kind === "genre"){
        $("searchInput").value = "";
        $("gGenre").value = node.label;
        $("quickType").value = "";
        tab("Graph");
        return loadGraph();
      }
      if(node.kind === "tag"){
        $("searchInput").value = node.label;
        setStatus("Filter by tag: " + node.label, "ok");
        tab("Library");
        return loadBooks();
      }
      if(node.kind === "language"){
        $("quickLang").value = node.label;
        setStatus("Filter by language: " + node.label, "ok");
        tab("Library");
        return loadBooks();
      }
      if(node.kind === "location"){
        $("searchInput").value = "";
        $("gLocation").value = node.label;
        tab("Graph");
        return loadGraph();
      }
      return Promise.resolve();
    }

    function bindGraphInput(){
      const canvas = $("graphCanvas");

      canvas.addEventListener("wheel", (ev) => {
        const layout = state.graphLayout;
        if(!layout){ return; }
        ev.preventDefault();
        const { rect, dpr, w, h } = graphCanvasContext();
        const px = (ev.clientX - rect.left) * dpr;
        const py = (ev.clientY - rect.top) * dpr;
        const before = screenToWorld(px, py, layout, dpr, w, h);
        const factor = ev.deltaY < 0 ? 1.08 : 0.92;
        layout.zoom = Math.max(0.2, Math.min(3.2, layout.zoom * factor));
        const after = screenToWorld(px, py, layout, dpr, w, h);
        layout.panX += (after.x - before.x);
        layout.panY += (after.y - before.y);
        requestGraphDraw();
      }, { passive:false });

      canvas.addEventListener("mousedown", (ev) => {
        const layout = state.graphLayout;
        if(!layout){ return; }
        const { rect, dpr, w, h } = graphCanvasContext();
        const px = (ev.clientX - rect.left) * dpr;
        const py = (ev.clientY - rect.top) * dpr;
        const node = getNodeAt(px, py);
        layout.clickCandidate = { x:px, y:py, nodeId: node ? node.id : null, moved:false };
        if(node){
          layout.pointerMode = "node";
          layout.dragNode = node;
          node.fixed = true;
          canvas.classList.add("dragging");
        } else {
          layout.pointerMode = "pan";
          layout.panStart = { x:px, y:py, panX:layout.panX, panY:layout.panY };
          canvas.classList.add("dragging");
        }
      });

      window.addEventListener("mousemove", (ev) => {
        const layout = state.graphLayout;
        if(!layout){ return; }
        const { rect, dpr, w, h } = graphCanvasContext();
        const px = (ev.clientX - rect.left) * dpr;
        const py = (ev.clientY - rect.top) * dpr;
        if(layout.pointerMode === "node" && layout.dragNode){
          const world = screenToWorld(px, py, layout, dpr, w, h);
          layout.dragNode.x = world.x;
          layout.dragNode.y = world.y;
          if(layout.clickCandidate){
            const moved = Math.hypot(px - layout.clickCandidate.x, py - layout.clickCandidate.y) > 6;
            if(moved){ layout.clickCandidate.moved = true; }
          }
          requestGraphDraw();
          return;
        }
        if(layout.pointerMode === "pan" && layout.panStart){
          const dx = (px - layout.panStart.x) / dpr / layout.zoom;
          const dy = (py - layout.panStart.y) / dpr / layout.zoom;
          layout.panX = layout.panStart.panX + dx;
          layout.panY = layout.panStart.panY + dy;
          if(layout.clickCandidate){
            const moved = Math.hypot(px - layout.clickCandidate.x, py - layout.clickCandidate.y) > 6;
            if(moved){ layout.clickCandidate.moved = true; }
          }
          requestGraphDraw();
          return;
        }

        const node = getNodeAt(px, py);
        const nextHover = node ? node.id : null;
        if(nextHover !== layout.hoveredId){
          layout.hoveredId = nextHover;
          requestGraphDraw();
        }
      });

      window.addEventListener("mouseup", async (ev) => {
        const layout = state.graphLayout;
        if(!layout){ return; }
        const mode = layout.pointerMode;
        const clickCandidate = layout.clickCandidate;
        if(layout.dragNode){ layout.dragNode.fixed = false; }
        layout.pointerMode = null;
        layout.dragNode = null;
        layout.panStart = null;
        layout.clickCandidate = null;
        canvas.classList.remove("dragging");

        if(!clickCandidate || clickCandidate.moved || mode === "pan"){ return; }
        const { rect, dpr } = graphCanvasContext();
        const px = (ev.clientX - rect.left) * dpr;
        const py = (ev.clientY - rect.top) * dpr;
        const node = getNodeAt(px, py);
        if(!node){ return; }
        layout.selectedId = node.id;
        requestGraphDraw();
        try {
          await applyNodeFilter(node);
        } catch(err){
          setStatus(err.message || String(err), "err");
        }
      });

      canvas.addEventListener("dblclick", () => {
        fitGraph();
      });
    }

    async function runDoctor(fix=false){
      const data = await api("/api/doctor?fix=" + (fix ? "1" : "0"));
      $("doctorOut").textContent = JSON.stringify(data.report, null, 2);
    }
    async function runDedup(){
      const t = $("dedupThreshold").value.trim() || "0.88";
      const data = await api("/api/dedup?threshold=" + encodeURIComponent(t));
      $("doctorOut").textContent = JSON.stringify(data.findings, null, 2);
    }
    async function runPlan(){
      const m = $("planMinutes").value.trim() || "120";
      const w = $("planWeeks").value.trim() || "4";
      const data = await api("/api/reading-plan?minutes=" + encodeURIComponent(m) + "&weeks=" + encodeURIComponent(w));
      $("planOut").textContent = JSON.stringify(data.plan, null, 2);
    }
    async function runRecommend(){
      const c = $("recCount").value.trim() || "10";
      const data = await api("/api/recommend?count=" + encodeURIComponent(c));
      $("planOut").textContent = JSON.stringify(data.recommendations, null, 2);
    }

    function tokenize(input){
      const pattern = /"([^"]*)"|'([^']*)'|\\S+/g;
      const out = [];
      let m;
      while((m = pattern.exec(input)) !== null){
        out.push(m[1] ?? m[2] ?? m[0]);
      }
      return out;
    }

    function parseKV(tokens){
      const out = {};
      for(const tok of tokens){
        const idx = tok.indexOf("=");
        if(idx <= 0){ continue; }
        const k = tok.slice(0, idx).trim().toLowerCase();
        const v = tok.slice(idx + 1).trim();
        out[k] = v;
      }
      return out;
    }

    function resolveReference(raw){
      const key = String(raw || "").trim().toLowerCase();
      if(!key){ return null; }
      const exact = state.items.find((i) => String(i.book_id || "").toLowerCase() === key || String(i.isbn || "").toLowerCase() === key);
      if(exact){ return exact.book_id; }
      const fuzzy = state.items.find((i) => (i.title || "").toLowerCase().includes(key) || (i.author || "").toLowerCase().includes(key) || (i.display_creator || "").toLowerCase().includes(key));
      return fuzzy ? fuzzy.book_id : null;
    }

    function openConsole(open=true){
      $("consoleShell").classList.toggle("open", !!open);
      if(open){
        $("consoleInput").focus();
      }
    }

    async function runConsoleCommand(raw){
      const cmdline = String(raw || "").trim();
      if(!cmdline){ return; }
      logConsole(`$ ${cmdline}`, "muted");
      state.consoleHistory.push(cmdline);
      state.consoleHistoryIndex = state.consoleHistory.length;

      const tokens = tokenize(cmdline);
      if(!tokens.length){ return; }
      const cmd = tokens[0].toLowerCase();
      const args = tokens.slice(1);

      try {
        if(cmd === "clear"){
          $("consoleLog").textContent = "";
          return;
        }
        if(cmd === "q" || cmd === "quit"){
          openConsole(false);
          return;
        }
        if(cmd === "help" || cmd === "man"){
          logConsole("Commands: help, ls/list, search <query>, details <ref>, add key=value..., update <ref> key=value..., rm/remove <ref>, read <ref>, unread <ref>, location <ref> <Pforta|Zuhause>, reading add|remove <ref>, graph [key=value], clear, q", "ok");
          logConsole("Aliases: ls, rm, q", "muted");
          return;
        }
        if(cmd === "ls" || cmd === "list"){
          if(args.length){
            $("searchInput").value = args.join(" ");
          }
          await loadBooks();
          logConsole(`Listed ${state.items.length} item(s).`, "ok");
          return;
        }
        if(cmd === "search"){
          $("searchInput").value = args.join(" ");
          await loadBooks();
          logConsole(`Search returned ${state.items.length} item(s).`, "ok");
          return;
        }
        if(cmd === "details" || cmd === "open"){
          const ref = resolveReference(args.join(" "));
          if(!ref){ throw new Error("Item not found."); }
          await selectItem(ref);
          logConsole(`Opened details: ${ref}`, "ok");
          return;
        }
        if(cmd === "read" || cmd === "unread"){
          const ref = resolveReference(args.join(" "));
          if(!ref){ throw new Error("Item not found."); }
          await api("/api/books/" + encodeURIComponent(ref) + "/read", { method:"POST", body: JSON.stringify({read: cmd === "read"}) });
          await loadBooks();
          logConsole(cmd === "read" ? `Updated: ${ref} marked read.` : `Updated: ${ref} marked unread.`, "ok");
          return;
        }
        if(cmd === "rm" || cmd === "remove"){
          const ref = resolveReference(args.join(" "));
          if(!ref){ throw new Error("Item not found."); }
          await api("/api/books/" + encodeURIComponent(ref), { method:"DELETE" });
          if(state.selectedId === ref){ state.selectedId = null; }
          await loadBooks();
          renderDetails(null);
          logConsole(`Removed: ${ref}`, "ok");
          return;
        }
        if(cmd === "location"){
          if(args.length < 2){ throw new Error("Usage: location <ref> <Pforta|Zuhause>"); }
          const ref = resolveReference(args[0]);
          if(!ref){ throw new Error("Item not found."); }
          const value = args[1];
          if(!["Pforta", "Zuhause"].includes(value)){ throw new Error("Invalid location. Use: Pforta | Zuhause"); }
          await api("/api/books/" + encodeURIComponent(ref), { method:"PUT", body: JSON.stringify({location:value}) });
          await loadBooks();
          if(state.selectedId === ref){ await loadDetails(ref); }
          logConsole(`Updated: ${ref} location=${value}`, "ok");
          return;
        }
        if(cmd === "reading"){
          if(args.length < 2){ throw new Error("Usage: reading add|remove <ref>"); }
          const action = args[0].toLowerCase();
          if(action !== "add" && action !== "remove"){ throw new Error("Usage: reading add|remove <ref>"); }
          const ref = resolveReference(args.slice(1).join(" "));
          if(!ref){ throw new Error("Item not found."); }
          await api("/api/books/" + encodeURIComponent(ref) + "/reading-list", { method:"POST", body: JSON.stringify({action}) });
          logConsole(action === "add" ? `Updated: ${ref} reading+.` : `Updated: ${ref} reading-.`, "ok");
          return;
        }
        if(cmd === "add"){
          const kv = parseKV(args);
          if(!kv.title || !kv.author){ throw new Error("Usage: add title=<...> author=<...> [language=<...>] [genre=<...>] [isbn=<...>]"); }
          const payload = {
            title: kv.title,
            author: kv.author,
            item_type: kv.type || "Book",
            isbn: kv.isbn || "",
            year: parseIntOrNull(kv.year),
            pages: parseIntOrNull(kv.pages),
            genre: kv.genre || "",
            language: kv.language || "English",
            cover: kv.cover || "Softcover",
            location: kv.location || "Zuhause",
            rating: parseIntOrNull(kv.rating),
            progress_pages: parseIntOrNull(kv.progress),
            tags: kv.tags || "",
            notes: kv.notes || "",
          };
          const data = await api("/api/books", { method:"POST", body: JSON.stringify(payload) });
          await loadBooks();
          logConsole(`Saved: ${data.item.book_id}`, "ok");
          return;
        }
        if(cmd === "update"){
          if(args.length < 2){ throw new Error("Usage: update <ref> key=value ..."); }
          const ref = resolveReference(args[0]);
          if(!ref){ throw new Error("Item not found."); }
          const kv = parseKV(args.slice(1));
          const payload = {};
          for(const [k, v] of Object.entries(kv)){
            if(["year", "pages", "rating", "progress_pages", "progress"].includes(k)){
              payload[k === "progress" ? "progress_pages" : k] = parseIntOrNull(v);
            } else if(k === "read"){
              payload.read = ["1", "true", "yes", "y"].includes(String(v).toLowerCase());
            } else if(k === "tags"){
              payload.tags = v;
            } else if(k === "type"){
              payload.item_type = v;
            } else {
              payload[k] = v;
            }
          }
          await api("/api/books/" + encodeURIComponent(ref), { method:"PUT", body: JSON.stringify(payload) });
          await loadBooks();
          if(state.selectedId === ref){ await loadDetails(ref); }
          logConsole(`Updated: ${ref}`, "ok");
          return;
        }
        if(cmd === "graph"){
          const kv = parseKV(args);
          if(kv.query !== undefined) $("gQuery").value = kv.query;
          if(kv.type !== undefined) $("gType").value = kv.type;
          if(kv.read !== undefined) $("gRead").value = kv.read;
          if(kv.language !== undefined) $("gLanguage").value = kv.language;
          if(kv.genre !== undefined) $("gGenre").value = kv.genre;
          if(kv.tag !== undefined) $("gTag").value = kv.tag;
          if(kv.location !== undefined) $("gLocation").value = kv.location;
          tab("Graph");
          await loadGraph();
          logConsole("Graph refreshed.", "ok");
          return;
        }
        throw new Error("Unknown command. Try: help");
      } catch(err){
        logConsole(err.message || String(err), "err");
      }
    }

    function bindConsole(){
      $("toggleConsoleBtn").onclick = () => openConsole(!$("consoleShell").classList.contains("open"));
      $("openConsoleBtn").onclick = () => openConsole(true);
      $("consoleHead").onclick = () => openConsole(!$("consoleShell").classList.contains("open"));
      $("consoleRunBtn").onclick = async () => {
        const cmd = $("consoleInput").value;
        $("consoleInput").value = "";
        await runConsoleCommand(cmd);
      };
      $("consoleClearBtn").onclick = () => { $("consoleLog").textContent = ""; };
      $("consoleInput").addEventListener("keydown", async (ev) => {
        if(ev.key === "Enter"){
          ev.preventDefault();
          const cmd = $("consoleInput").value;
          $("consoleInput").value = "";
          await runConsoleCommand(cmd);
          return;
        }
        if(ev.key === "ArrowUp"){
          ev.preventDefault();
          if(state.consoleHistory.length === 0){ return; }
          state.consoleHistoryIndex = Math.max(0, state.consoleHistoryIndex - 1);
          $("consoleInput").value = state.consoleHistory[state.consoleHistoryIndex] || "";
          return;
        }
        if(ev.key === "ArrowDown"){
          ev.preventDefault();
          if(state.consoleHistory.length === 0){ return; }
          state.consoleHistoryIndex = Math.min(state.consoleHistory.length, state.consoleHistoryIndex + 1);
          $("consoleInput").value = state.consoleHistory[state.consoleHistoryIndex] || "";
        }
      });
      window.addEventListener("keydown", (ev) => {
        if(ev.ctrlKey && ev.key === "`"){
          ev.preventDefault();
          openConsole(!$("consoleShell").classList.contains("open"));
        }
      });
    }

    async function boot(){
      const status = await api("/api/status");
      $("serverLine").textContent = `${status.host}:${status.port} | ${status.data_file}`;
      $("statsChip").textContent = `${status.stats.total} items`;

      $("tabLibrary").onclick = () => tab("Library");
      $("tabGraph").onclick = async () => { tab("Graph"); await loadGraph(); };
      $("tabTools").onclick = () => tab("Tools");

      $("refreshBtn").onclick = () => loadBooks().catch((err) => setStatus(err.message, "err"));
      $("searchBtn").onclick = () => loadBooks().catch((err) => setStatus(err.message, "err"));
      $("searchInput").addEventListener("keydown", (e) => {
        if(e.key === "Enter"){ loadBooks().catch((err) => setStatus(err.message, "err")); }
      });
      $("quickRead").onchange = () => loadBooks().catch((err) => setStatus(err.message, "err"));
      $("quickType").onchange = () => loadBooks().catch((err) => setStatus(err.message, "err"));
      $("quickLang").onchange = () => loadBooks().catch((err) => setStatus(err.message, "err"));

      $("createBtn").onclick = () => createBook().catch((err) => setStatus(err.message, "err"));
      $("updateBtn").onclick = () => updateBook().catch((err) => setStatus(err.message, "err"));
      $("deleteBtn").onclick = () => deleteBook().catch((err) => setStatus(err.message, "err"));
      $("markReadBtn").onclick = () => setRead(true).catch((err) => setStatus(err.message, "err"));
      $("markUnreadBtn").onclick = () => setRead(false).catch((err) => setStatus(err.message, "err"));
      $("readingAddBtn").onclick = () => readingList("add").catch((err) => setStatus(err.message, "err"));
      $("readingRemoveBtn").onclick = () => readingList("remove").catch((err) => setStatus(err.message, "err"));
      $("isbnAutofillBtn").onclick = () => isbnAutofill().catch((err) => setStatus(err.message, "err"));

      $("graphReloadBtn").onclick = () => loadGraph().catch((err) => setStatus(err.message, "err"));
      $("graphFitBtn").onclick = () => fitGraph();
      $("graphPauseBtn").onclick = () => {
        if(!state.graphLayout){ return; }
        state.graphLayout.running = !state.graphLayout.running;
        $("graphPauseBtn").textContent = state.graphLayout.running ? "Pause" : "Resume";
      };
      for(const id of ["kItem", "kCreator", "kGenre", "kTag", "kLanguage", "kLocation"]){
        $(id).onchange = () => updateKindFilters();
      }

      $("doctorBtn").onclick = () => runDoctor(false).catch((err) => setStatus(err.message, "err"));
      $("doctorFixBtn").onclick = () => runDoctor(true).catch((err) => setStatus(err.message, "err"));
      $("dedupScanBtn").onclick = () => runDedup().catch((err) => setStatus(err.message, "err"));
      $("planBtn").onclick = () => runPlan().catch((err) => setStatus(err.message, "err"));
      $("recBtn").onclick = () => runRecommend().catch((err) => setStatus(err.message, "err"));

      bindGraphInput();
      bindConsole();
      window.addEventListener("resize", () => requestGraphDraw());

      await loadBooks();
      logConsole("Console ready. Type 'help' for command list.", "ok");
    }

    boot().catch((err) => {
      setStatus(err.message || String(err), "err");
      logConsole(err.message || String(err), "err");
    });
  </script>
</body>
</html>
"""
