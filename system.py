from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ALLOWED_LOCATIONS = ("Pforta", "Zuhause")
ALLOWED_COVERS = ("Hardcover", "Softcover")
ALLOWED_LANGUAGES = ("German", "English", "French", "Japanese")
ALLOWED_ITEM_TYPES = ("Book", "SheetMusic")
ALLOWED_PRACTICE_STATUSES = ("Unstarted", "Learning", "Rehearsing", "Performance-ready", "Mastered")


class StorageError(RuntimeError):
    """Raised when loading or saving the library fails."""


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "read", "done"}:
        return True
    if text in {"0", "false", "no", "n", "unread"}:
        return False
    return bool(value)


def _optional_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _normalize_location(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "pforta":
        return "Pforta"
    return "Zuhause"


def _normalize_cover(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "").replace(" ", "")
    if text in {"hard", "hardcover", "hc"}:
        return "Hardcover"
    if text in {"soft", "softcover", "sc", "paperback", "pb"}:
        return "Softcover"
    return "Softcover"


def _normalize_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"german", "de", "deutsch"}:
        return "German"
    if text in {"english", "en", "englisch"}:
        return "English"
    if text in {"french", "fr", "francais", "français"}:
        return "French"
    if text in {"japanese", "jp", "ja", "japanisch"}:
        return "Japanese"
    return "English"


def _normalize_item_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if text in {"sheet", "sheetmusic", "score", "music"}:
        return "SheetMusic"
    return "Book"


def _normalize_practice_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"-", "none", "n/a"}:
        return ""
    mapping = {
        "unstarted": "Unstarted",
        "new": "Unstarted",
        "learning": "Learning",
        "rehearsing": "Rehearsing",
        "rehearse": "Rehearsing",
        "performance-ready": "Performance-ready",
        "performanceready": "Performance-ready",
        "ready": "Performance-ready",
        "mastered": "Mastered",
        "done": "Mastered",
    }
    return mapping.get(text, "")


def _normalize_goal(value: Any) -> int | None:
    amount = _optional_int(value)
    if amount is None or amount <= 0:
        return None
    return amount


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = [str(value).strip()]

    tags: list[str] = []
    seen: set[str] = set()
    for tag in candidates:
        if not tag:
            continue
        normalized = " ".join(tag.split()).lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            tags.append(normalized)
    return tags


def _normalize_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = [str(value).strip()]

    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not item:
            continue
        normalized = " ".join(item.split()).casefold()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


class Book:
    def __init__(
        self,
        title: str,
        author: str,
        year: int | None = None,
        isbn: str = "",
        genre: str = "",
        pages: int | None = None,
        read: bool = False,
        notes: str = "",
        rating: int | None = None,
        progress_pages: int | None = None,
        language: str = "English",
        location: str = "Zuhause",
        cover: str = "Softcover",
        read_at: str | None = None,
        book_id: str = "",
        tags: list[str] | tuple[str, ...] | set[str] | str | None = None,
        item_type: str = "Book",
        composer: str = "",
        instrumentation: str = "",
        catalog_number: str = "",
        key_signature: str = "",
        era_style: str = "",
        difficulty: str = "",
        duration_minutes: int | None = None,
        publisher: str = "",
        practice_status: str = "",
        last_practiced: str | None = None,
    ):
        self.book_id = str(book_id).strip()
        self.title = title.strip()
        self.item_type = _normalize_item_type(item_type)
        base_author = str(author).strip()
        base_composer = str(composer).strip()
        if self.item_type == "SheetMusic":
            if not base_composer:
                base_composer = base_author
            if not base_author:
                base_author = base_composer
        self.author = base_author
        self.composer = base_composer if self.item_type == "SheetMusic" else ""
        self.year = _optional_int(year)
        self.isbn = str(isbn).strip()
        self.genre = str(genre).strip()
        self.pages = _optional_int(pages)
        self.read = _to_bool(read)
        self.notes = str(notes).strip()
        self.language = _normalize_language(language)
        self.location = _normalize_location(location)
        self.cover = _normalize_cover(cover)
        self.read_at = _optional_date(read_at)
        self.tags = _normalize_tags(tags)
        self.instrumentation = str(instrumentation).strip() if self.item_type == "SheetMusic" else ""
        self.catalog_number = str(catalog_number).strip() if self.item_type == "SheetMusic" else ""
        self.key_signature = str(key_signature).strip() if self.item_type == "SheetMusic" else ""
        self.era_style = str(era_style).strip() if self.item_type == "SheetMusic" else ""
        self.difficulty = str(difficulty).strip() if self.item_type == "SheetMusic" else ""
        self.publisher = str(publisher).strip() if self.item_type == "SheetMusic" else ""
        self.duration_minutes = _optional_int(duration_minutes) if self.item_type == "SheetMusic" else None
        if self.duration_minutes is not None and self.duration_minutes < 0:
            self.duration_minutes = None
        if self.item_type == "SheetMusic":
            normalized_status = _normalize_practice_status(practice_status)
            self.practice_status = normalized_status or "Unstarted"
            self.last_practiced = _optional_date(last_practiced)
        else:
            self.practice_status = ""
            self.last_practiced = None

        self.rating = _optional_int(rating)
        if self.rating is not None and not (1 <= self.rating <= 5):
            self.rating = None

        self.progress_pages = _optional_int(progress_pages)
        if self.progress_pages is not None and self.progress_pages < 0:
            self.progress_pages = 0

        if self.pages is not None:
            if self.progress_pages is not None:
                self.progress_pages = min(self.pages, self.progress_pages)
            elif self.read:
                self.progress_pages = self.pages

        if self.pages is not None and self.progress_pages is not None and self.progress_pages >= self.pages:
            self.read = True

        if self.read and not self.read_at:
            self.read_at = date.today().isoformat()
        if not self.read:
            self.read_at = None

    def __repr__(self):
        year_text = self.year if self.year is not None else "Unknown"
        pages_text = self.pages if self.pages is not None else "Unknown"
        read_text = "Read" if self.read else "Unread"
        notes_text = self.notes if self.notes else "-"
        return (
            f"Book(book_id={self.book_id!r}, item_type={self.item_type!r}, title={self.title!r}, author={self.author!r}, "
            f"year={year_text}, isbn={self.isbn!r}, "
            f"genre={self.genre!r}, pages={pages_text}, progress={self.progress_pages!r}, rating={self.rating!r}, "
            f"language={self.language!r}, location={self.location!r}, cover={self.cover!r}, tags={self.tags!r}, "
            f"status={read_text}, notes={notes_text!r})"
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Book:
        title = str(payload.get("title", "")).strip()
        author = str(payload.get("author", "")).strip()
        if not author:
            author = str(payload.get("composer", "")).strip()
        if not title or not author:
            raise ValueError("Each book needs a non-empty title and author.")
        return cls(
            title=title,
            author=author,
            year=payload.get("year"),
            isbn=str(payload.get("isbn", "")).strip(),
            genre=str(payload.get("genre", "")).strip(),
            pages=payload.get("pages"),
            read=payload.get("read", False),
            notes=str(payload.get("notes", "")).strip(),
            rating=payload.get("rating"),
            progress_pages=payload.get("progress_pages"),
            language=payload.get("language", "English"),
            location=payload.get("location", "Zuhause"),
            cover=payload.get("cover", "Softcover"),
            read_at=payload.get("read_at"),
            book_id=str(payload.get("book_id", "")).strip(),
            tags=payload.get("tags", []),
            item_type=payload.get("item_type", "Book"),
            composer=str(payload.get("composer", "")).strip(),
            instrumentation=str(payload.get("instrumentation", "")).strip(),
            catalog_number=str(payload.get("catalog_number", "")).strip(),
            key_signature=str(payload.get("key_signature", "")).strip(),
            era_style=str(payload.get("era_style", "")).strip(),
            difficulty=str(payload.get("difficulty", "")).strip(),
            duration_minutes=payload.get("duration_minutes"),
            publisher=str(payload.get("publisher", "")).strip(),
            practice_status=str(payload.get("practice_status", "")).strip(),
            last_practiced=payload.get("last_practiced"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "item_type": self.item_type,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "isbn": self.isbn,
            "genre": self.genre,
            "pages": self.pages,
            "read": self.read,
            "read_at": self.read_at,
            "notes": self.notes,
            "rating": self.rating,
            "progress_pages": self.progress_pages,
            "language": self.language,
            "location": self.location,
            "cover": self.cover,
            "tags": self.tags,
            "composer": self.composer,
            "instrumentation": self.instrumentation,
            "catalog_number": self.catalog_number,
            "key_signature": self.key_signature,
            "era_style": self.era_style,
            "difficulty": self.difficulty,
            "duration_minutes": self.duration_minutes,
            "publisher": self.publisher,
            "practice_status": self.practice_status,
            "last_practiced": self.last_practiced,
        }

    def progress_label(self) -> str:
        if self.pages:
            current = self.progress_pages if self.progress_pages is not None else (self.pages if self.read else 0)
            percent = int(round((current / self.pages) * 100))
            return f"{percent}% ({current}/{self.pages})"
        if self.progress_pages is not None:
            return f"{self.progress_pages} p"
        if self.read:
            return "Done"
        return "-"

    def to_row(self):
        notes_preview = self.notes
        if len(notes_preview) > 28:
            notes_preview = notes_preview[:25] + "..."
        tags_text = ", ".join(self.tags) if self.tags else "-"
        return [
            self.book_id or "-",
            self.item_type,
            self.title,
            self.author,
            self.isbn or "-",
            str(self.year) if self.year is not None else "-",
            self.genre or "-",
            self.language,
            self.cover,
            self.instrumentation or "-",
            str(self.pages) if self.pages is not None else "-",
            self.progress_label(),
            str(self.rating) if self.rating is not None else "-",
            "yes" if self.read else "no",
            self.location,
            tags_text,
            notes_preview or "-",
        ]


class Library:
    def __init__(self, data_path: str | Path | None = None):
        self.books: list[Book] = []
        self.reading_list: list[str] = []
        self.goals: dict[str, int | None] = {"monthly": None, "yearly": None}
        self.smart_lists: dict[str, dict[str, Any]] = {}
        self.recommendation_profile: dict[str, Any] = self._default_recommendation_profile()
        self.data_path = Path(data_path).expanduser() if data_path else None

    def _next_book_id(self, used_ids: set[str] | None = None) -> str:
        used = set(used_ids or set())
        index = 1
        while True:
            candidate = f"b{index:04d}"
            if candidate.casefold() not in used:
                return candidate
            index += 1

    def _ensure_book_id(self, book: Book, used_ids: set[str] | None = None) -> str:
        if used_ids is None:
            used_ids = {item.book_id.casefold() for item in self.books if item.book_id}
        candidate = str(book.book_id).strip()
        if candidate and candidate.casefold() not in used_ids:
            book.book_id = candidate
            used_ids.add(candidate.casefold())
            return candidate
        assigned = self._next_book_id(used_ids)
        book.book_id = assigned
        used_ids.add(assigned.casefold())
        return assigned

    @staticmethod
    def _lookup_by_book_id(books: list[Book], reference: str) -> Book | None:
        key = reference.strip().casefold()
        if not key:
            return None
        for book in books:
            if book.book_id and book.book_id.casefold() == key:
                return book
        return None

    @staticmethod
    def _lookup_by_isbn(books: list[Book], reference: str) -> Book | None:
        key = reference.strip()
        if not key:
            return None
        for book in books:
            if book.isbn and book.isbn == key:
                return book
        return None

    @staticmethod
    def _book_signature(title: str, author: str, language: str, cover: str) -> tuple[str, str, str, str, str]:
        return (
            "book",
            str(title).strip().casefold(),
            str(author).strip().casefold(),
            _normalize_language(language).casefold(),
            _normalize_cover(cover).casefold(),
        )

    @staticmethod
    def _sheet_signature(
        title: str,
        composer: str,
        instrumentation: str,
        catalog_number: str,
        publisher: str,
    ) -> tuple[str, str, str, str, str, str]:
        return (
            "sheetmusic",
            str(title).strip().casefold(),
            str(composer).strip().casefold(),
            str(instrumentation).strip().casefold(),
            str(catalog_number).strip().casefold(),
            str(publisher).strip().casefold(),
        )

    def _item_signature(self, book: Book) -> tuple[Any, ...]:
        if book.item_type == "SheetMusic":
            return self._sheet_signature(
                title=book.title,
                composer=book.composer or book.author,
                instrumentation=book.instrumentation,
                catalog_number=book.catalog_number,
                publisher=book.publisher,
            )
        return self._book_signature(
            title=book.title,
            author=book.author,
            language=book.language,
            cover=book.cover,
        )

    def _has_duplicate_item(self, candidate: Book, exclude: Book | None = None) -> bool:
        candidate_signature = self._item_signature(candidate)
        for other in self.books:
            if exclude is not None and other is exclude:
                continue
            if candidate.isbn and other.isbn and candidate.isbn == other.isbn:
                return True
            if self._item_signature(other) == candidate_signature:
                return True
        return False

    @classmethod
    def load(cls, data_path: str | Path) -> Library:
        library = cls(data_path=data_path)
        library.load_from_disk()
        return library

    def _normalize_smart_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(filters, dict):
            raise ValueError("Smart list filters must be an object.")

        read_raw = filters.get("read")
        if read_raw in (None, "", "any", "*"):
            read_value = None
        else:
            text = str(read_raw).strip().lower()
            if text in {"read", "true", "1", "yes", "y"}:
                read_value = True
            elif text in {"unread", "false", "0", "no", "n"}:
                read_value = False
            else:
                raise ValueError("Smart list read filter must be read, unread, or any.")

        location_raw = filters.get("location")
        if location_raw in (None, "", "any", "*"):
            location_value = None
        else:
            location_text = str(location_raw).strip()
            if location_text.lower() == "pforta":
                location_value = "Pforta"
            elif location_text.lower() == "zuhause":
                location_value = "Zuhause"
            else:
                raise ValueError("Smart list location must be Pforta, Zuhause, or any.")

        genre_raw = filters.get("genre", "")
        if genre_raw in (None, "", "any", "*"):
            genre_value = None
        else:
            genre_text = str(genre_raw).strip()
            genre_value = genre_text if genre_text else None

        min_rating_raw = filters.get("min_rating")
        if min_rating_raw in (None, "", "any", "*"):
            min_rating_value = None
        else:
            min_rating_value = _optional_int(min_rating_raw)
            if min_rating_value is None or not (1 <= min_rating_value <= 5):
                raise ValueError("Smart list min_rating must be between 1 and 5.")

        tags_value = _normalize_tags(filters.get("tags", []))

        return {
            "read": read_value,
            "location": location_value,
            "genre": genre_value,
            "min_rating": min_rating_value,
            "tags": tags_value,
        }

    def _default_recommendation_profile(self) -> dict[str, Any]:
        return {
            "genres": [],
            "tags": [],
            "authors": [],
            "min_rating": None,
            "location": None,
            "prefer_unread": True,
        }

    def _normalize_recommendation_profile(self, profile: Any) -> dict[str, Any]:
        if profile in (None, {}):
            return self._default_recommendation_profile()
        if not isinstance(profile, dict):
            raise ValueError("Recommendation profile must be an object.")

        min_rating_raw = profile.get("min_rating")
        if min_rating_raw in (None, "", "any", "*"):
            min_rating_value = None
        else:
            min_rating_value = _optional_int(min_rating_raw)
            if min_rating_value is None or not (1 <= min_rating_value <= 5):
                raise ValueError("Recommendation min_rating must be between 1 and 5.")

        location_raw = profile.get("location")
        if location_raw in (None, "", "any", "*"):
            location_value = None
        else:
            location_text = str(location_raw).strip().lower()
            if location_text == "pforta":
                location_value = "Pforta"
            elif location_text == "zuhause":
                location_value = "Zuhause"
            else:
                raise ValueError("Recommendation location must be Pforta, Zuhause, or any.")

        prefer_unread_raw = profile.get("prefer_unread", True)
        prefer_unread_value = _to_bool(prefer_unread_raw) if prefer_unread_raw is not None else True

        return {
            "genres": _normalize_keywords(profile.get("genres", [])),
            "tags": _normalize_tags(profile.get("tags", [])),
            "authors": _normalize_keywords(profile.get("authors", [])),
            "min_rating": min_rating_value,
            "location": location_value,
            "prefer_unread": prefer_unread_value,
        }

    def _deserialize_payload(
        self, payload: Any
    ) -> tuple[list[Book], list[str], dict[str, int | None], dict[str, dict[str, Any]], dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ValueError("Library data must be a JSON object.")

        raw_books = payload.get("books", [])
        if raw_books is None:
            raw_books = []
        if not isinstance(raw_books, list):
            raise ValueError("Invalid 'books' structure in library data.")

        books: list[Book] = []
        used_ids: set[str] = set()
        for item in raw_books:
            if not isinstance(item, dict):
                continue
            try:
                book = Book.from_dict(item)
            except ValueError:
                continue
            self._ensure_book_id(book, used_ids)
            books.append(book)

        raw_reading = payload.get("reading_list", [])
        if raw_reading is None:
            raw_reading = []
        if not isinstance(raw_reading, list):
            raise ValueError("Invalid 'reading_list' structure in library data.")
        reading_refs: list[str] = []
        for item in raw_reading:
            reference = str(item).strip()
            if not reference:
                continue
            book = self._lookup_by_book_id(books, reference)
            if book is None:
                # Backwards compatibility: older files stored ISBNs here.
                book = self._lookup_by_isbn(books, reference)
            if book is None or not book.book_id:
                continue
            reading_refs.append(book.book_id)
        reading_list = _dedupe(reading_refs)

        raw_goals = payload.get("goals", {})
        if raw_goals is None:
            raw_goals = {}
        if not isinstance(raw_goals, dict):
            raw_goals = {}
        goals = {
            "monthly": _normalize_goal(raw_goals.get("monthly")),
            "yearly": _normalize_goal(raw_goals.get("yearly")),
        }

        raw_smart_lists = payload.get("smart_lists", {})
        if raw_smart_lists is None:
            raw_smart_lists = {}
        if not isinstance(raw_smart_lists, dict):
            raw_smart_lists = {}
        smart_lists: dict[str, dict[str, Any]] = {}
        for name, filters in raw_smart_lists.items():
            list_name = str(name).strip()
            if not list_name or not isinstance(filters, dict):
                continue
            try:
                smart_lists[list_name] = self._normalize_smart_filters(filters)
            except ValueError:
                continue

        raw_profile = payload.get("recommendation_profile", {})
        try:
            recommendation_profile = self._normalize_recommendation_profile(raw_profile)
        except ValueError:
            recommendation_profile = self._default_recommendation_profile()

        return books, reading_list, goals, smart_lists, recommendation_profile

    def _apply_state(self, payload: Any) -> None:
        books, reading_list, goals, smart_lists, recommendation_profile = self._deserialize_payload(payload)
        self.books = books
        self.reading_list = reading_list
        self.goals = goals
        self.smart_lists = smart_lists
        self.recommendation_profile = recommendation_profile

    def load_from_disk(self) -> None:
        if not self.data_path:
            return
        if not self.data_path.exists():
            return
        try:
            with self.data_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read {self.data_path}: {exc}") from exc

        try:
            self._apply_state(payload)
        except ValueError as exc:
            raise StorageError(f"Invalid data format in {self.data_path}: {exc}") from exc

    def _payload(self) -> dict[str, Any]:
        return {
            "version": 8,
            "books": [book.to_dict() for book in self.books],
            "reading_list": self.reading_list,
            "goals": self.goals,
            "smart_lists": self.smart_lists,
            "recommendation_profile": self.recommendation_profile,
        }

    def export_state(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload())

    def restore_state(self, payload: Any, persist: bool = True) -> bool:
        snapshot = self.export_state()
        self._apply_state(payload)
        if not persist:
            return True
        try:
            self.save()
        except StorageError:
            self._apply_state(snapshot)
            raise
        return True

    def save(self) -> None:
        if not self.data_path:
            return

        target = self.data_path
        temp_file = target.with_name(f"{target.name}.tmp")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with temp_file.open("w", encoding="utf-8") as handle:
                json.dump(self._payload(), handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            temp_file.replace(target)
        except OSError as exc:
            raise StorageError(f"Could not save library data to {target}: {exc}") from exc
        finally:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError:
                pass

    def _autosave(self) -> None:
        if self.data_path:
            self.save()

    def _commit(self, mutator) -> bool:
        snapshot = self.export_state()
        changed = bool(mutator())
        if not changed:
            return False
        try:
            self._autosave()
        except StorageError:
            self.restore_state(snapshot, persist=False)
            raise
        return True

    def add_book(self, book: Book) -> bool:
        if self._has_duplicate_item(book):
            return False

        def mutate():
            self._ensure_book_id(book)
            self.books.append(book)
            return True

        return self._commit(mutate)

    def remove_book(self, reference: str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False

        def mutate():
            new_books = [item for item in self.books if item is not book]
            if len(new_books) == len(self.books):
                return False
            self.books = new_books
            self.reading_list = [item for item in self.reading_list if item != book.book_id]
            return True

        return self._commit(mutate)

    def book_exists(
        self,
        isbn: str | None = None,
        title: str | None = None,
        author: str | None = None,
        language: str | None = None,
        cover: str | None = None,
        item_type: str | None = None,
        composer: str | None = None,
        instrumentation: str | None = None,
        catalog_number: str | None = None,
        publisher: str | None = None,
    ) -> bool:
        isbn_key = (isbn or "").strip()
        title_key = (title or "").strip().casefold()
        author_key = (author or "").strip().casefold()
        item_type_key = _normalize_item_type(item_type) if item_type not in (None, "") else None
        language_key = _normalize_language(language).casefold() if language not in (None, "") else None
        cover_key = _normalize_cover(cover).casefold() if cover not in (None, "") else None
        composer_key = (composer or "").strip().casefold()
        instrumentation_key = (instrumentation or "").strip().casefold()
        catalog_key = (catalog_number or "").strip().casefold()
        publisher_key = (publisher or "").strip().casefold()
        for book in self.books:
            if isbn_key and book.isbn and book.isbn == isbn_key:
                return True
            if not (title_key and author_key):
                continue
            if book.title.casefold() != title_key:
                continue
            if book.author.casefold() != author_key:
                continue
            if item_type_key and book.item_type != item_type_key:
                continue

            if (item_type_key or book.item_type) == "SheetMusic":
                if composer_key:
                    existing_composer = (book.composer or book.author).casefold()
                    if existing_composer != composer_key:
                        continue
                if instrumentation_key and book.instrumentation.casefold() != instrumentation_key:
                    continue
                if catalog_key and book.catalog_number.casefold() != catalog_key:
                    continue
                if publisher_key and book.publisher.casefold() != publisher_key:
                    continue
                return True

            if language_key and cover_key:
                if book.language.casefold() == language_key and book.cover.casefold() == cover_key:
                    return True
            elif language_key:
                if book.language.casefold() == language_key:
                    return True
            elif cover_key:
                if book.cover.casefold() == cover_key:
                    return True
            else:
                return True
        return False

    def find_book_by_title(self, title: str) -> list[Book]:
        value = title.strip().casefold()
        return [book for book in self.books if value in book.title.casefold()]

    def find_book_by_author(self, author: str) -> list[Book]:
        value = author.strip().casefold()
        return [book for book in self.books if value in book.author.casefold()]

    def find_sheet_by_composer(self, composer: str) -> list[Book]:
        value = composer.strip().casefold()
        if not value:
            return []
        return [
            book
            for book in self.books
            if book.item_type == "SheetMusic" and value in (book.composer or book.author).casefold()
        ]

    def books_by_item_type(self, item_type: str) -> list[Book]:
        normalized = _normalize_item_type(item_type)
        return [book for book in self.books if book.item_type == normalized]

    def sheets_by_instrumentation(self, instrumentation: str) -> list[Book]:
        value = instrumentation.strip().casefold()
        if not value:
            return []
        return [
            book
            for book in self.books
            if book.item_type == "SheetMusic" and value in (book.instrumentation or "").casefold()
        ]

    def get_by_book_id(self, book_id: str) -> Book | None:
        key = book_id.strip().casefold()
        if not key:
            return None
        for book in self.books:
            if book.book_id and book.book_id.casefold() == key:
                return book
        return None

    def get_by_isbn(self, isbn: str) -> Book | None:
        key = isbn.strip()
        if not key:
            return None
        for book in self.books:
            if book.isbn == key:
                return book
        return None

    def get_by_reference(self, reference: str) -> Book | None:
        key = reference.strip()
        if not key:
            return None
        by_id = self.get_by_book_id(key)
        if by_id:
            return by_id
        return self.get_by_isbn(key)

    def edit_book(self, reference: str, **updates: Any) -> bool:
        current = self.get_by_reference(reference)
        if not current:
            return False

        updated = Book(
            title=str(updates.get("title", current.title)).strip(),
            author=str(updates.get("author", current.author)).strip(),
            year=updates.get("year", current.year),
            isbn=str(updates.get("new_isbn", updates.get("isbn", current.isbn))).strip(),
            genre=str(updates.get("genre", current.genre)).strip(),
            pages=updates.get("pages", current.pages),
            read=updates.get("read", current.read),
            notes=str(updates.get("notes", current.notes)).strip(),
            rating=updates.get("rating", current.rating),
            progress_pages=updates.get("progress_pages", current.progress_pages),
            language=updates.get("language", current.language),
            location=updates.get("location", current.location),
            cover=updates.get("cover", current.cover),
            read_at=updates.get("read_at", current.read_at),
            book_id=current.book_id,
            tags=updates.get("tags", current.tags),
            item_type=updates.get("item_type", current.item_type),
            composer=str(updates.get("composer", current.composer)).strip(),
            instrumentation=str(updates.get("instrumentation", current.instrumentation)).strip(),
            catalog_number=str(updates.get("catalog_number", current.catalog_number)).strip(),
            key_signature=str(updates.get("key_signature", current.key_signature)).strip(),
            era_style=str(updates.get("era_style", current.era_style)).strip(),
            difficulty=str(updates.get("difficulty", current.difficulty)).strip(),
            duration_minutes=updates.get("duration_minutes", current.duration_minutes),
            publisher=str(updates.get("publisher", current.publisher)).strip(),
            practice_status=str(updates.get("practice_status", current.practice_status)).strip(),
            last_practiced=updates.get("last_practiced", current.last_practiced),
        )
        if not updated.title or not updated.author:
            raise ValueError("Title and author may not be empty.")
        if self._has_duplicate_item(updated, exclude=current):
            return False

        def mutate():
            idx = self.books.index(current)
            self.books[idx] = updated
            return True

        return self._commit(mutate)

    def set_read(self, reference: str, read: bool) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False

        def mutate():
            changed = False
            if book.read != read:
                changed = True
            if read and book.read_at is None:
                changed = True
            if not changed:
                return False

            book.read = read
            if read:
                book.read_at = date.today().isoformat()
                if book.pages is not None:
                    book.progress_pages = book.pages
            else:
                book.read_at = None
            return True

        return self._commit(mutate)

    def set_notes(self, reference: str, notes: str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False
        note_value = notes.strip()

        def mutate():
            if book.notes == note_value:
                return False
            book.notes = note_value
            return True

        return self._commit(mutate)

    def set_rating(self, reference: str, rating: int | None) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False

        normalized = _optional_int(rating)
        if normalized is not None and not (1 <= normalized <= 5):
            raise ValueError("Rating must be between 1 and 5.")

        def mutate():
            if book.rating == normalized:
                return False
            book.rating = normalized
            return True

        return self._commit(mutate)

    def set_progress(self, reference: str, progress_pages: int) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False

        value = _optional_int(progress_pages)
        if value is None or value < 0:
            raise ValueError("Progress must be a non-negative integer.")
        if book.pages is not None and value > book.pages:
            raise ValueError(f"Progress cannot exceed total pages ({book.pages}).")

        def mutate():
            if book.progress_pages == value:
                return False
            book.progress_pages = value
            if book.pages is not None and value >= book.pages:
                book.read = True
                book.read_at = date.today().isoformat()
            elif book.pages is not None and value < book.pages and book.read:
                book.read = False
                book.read_at = None
            return True

        return self._commit(mutate)

    def set_practice_status(self, reference: str, practice_status: str, practiced_on: str | None = None) -> bool:
        book = self.get_by_reference(reference)
        if not book or book.item_type != "SheetMusic":
            return False

        normalized = _normalize_practice_status(practice_status)
        if not normalized:
            raise ValueError("Practice status is invalid.")
        practiced_date = _optional_date(practiced_on) if practiced_on else date.today().isoformat()

        def mutate():
            changed = False
            if book.practice_status != normalized:
                book.practice_status = normalized
                changed = True
            if practiced_date and book.last_practiced != practiced_date:
                book.last_practiced = practiced_date
                changed = True
            return changed

        return self._commit(mutate)

    def set_location(self, reference: str, location: str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False

        normalized = _normalize_location(location)

        def mutate():
            if book.location == normalized:
                return False
            book.location = normalized
            return True

        return self._commit(mutate)

    def set_tags(self, reference: str, tags: list[str] | tuple[str, ...] | set[str] | str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False
        normalized = _normalize_tags(tags)

        def mutate():
            if book.tags == normalized:
                return False
            book.tags = normalized
            return True

        return self._commit(mutate)

    def add_tags(self, reference: str, tags: list[str] | tuple[str, ...] | set[str] | str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False
        additions = _normalize_tags(tags)
        if not additions:
            return False
        merged = _normalize_tags([*book.tags, *additions])

        def mutate():
            if merged == book.tags:
                return False
            book.tags = merged
            return True

        return self._commit(mutate)

    def remove_tags(self, reference: str, tags: list[str] | tuple[str, ...] | set[str] | str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False
        removals = {tag.casefold() for tag in _normalize_tags(tags)}
        if not removals:
            return False
        remaining = [tag for tag in book.tags if tag.casefold() not in removals]

        def mutate():
            if remaining == book.tags:
                return False
            book.tags = remaining
            return True

        return self._commit(mutate)

    def clear_tags(self, reference: str) -> bool:
        return self.set_tags(reference, [])

    def add_to_reading_list(self, reference: str) -> bool:
        book = self.get_by_reference(reference)
        if not book:
            return False
        if book.book_id in self.reading_list:
            return False

        def mutate():
            self.reading_list.append(book.book_id)
            return True

        return self._commit(mutate)

    def remove_from_reading_list(self, reference: str) -> bool:
        book = self.get_by_reference(reference)
        if book is None:
            reference_key = reference.strip()
            if not reference_key:
                return False
            # Allow removing stale entries by direct list ID.
            if reference_key.casefold() not in {item.casefold() for item in self.reading_list}:
                return False
            target_id = next((item for item in self.reading_list if item.casefold() == reference_key.casefold()), None)
            if target_id is None:
                return False
        else:
            target_id = book.book_id

        if target_id not in self.reading_list:
            matched = next((item for item in self.reading_list if item.casefold() == target_id.casefold()), None)
            if matched is None:
                return False
            target_id = matched

        def mutate():
            self.reading_list = [item for item in self.reading_list if item != target_id]
            return True

        return self._commit(mutate)

    def reading_list_books(self) -> list[Book]:
        index = {book.book_id: book for book in self.books if book.book_id}
        return [index[book_id] for book_id in self.reading_list if book_id in index]

    def books_by_read_status(self, read: bool) -> list[Book]:
        return [book for book in self.books if book.read == read]

    def books_by_genre(self, genre: str) -> list[Book]:
        value = genre.strip().casefold()
        return [book for book in self.books if book.genre.casefold() == value]

    def books_by_language(self, language: str) -> list[Book]:
        value = _normalize_language(language).casefold()
        return [book for book in self.books if book.language.casefold() == value]

    def books_by_tag(self, tag: str) -> list[Book]:
        requested = _normalize_tags(tag)
        if not requested:
            return []
        tag_key = requested[0]
        return [book for book in self.books if tag_key in book.tags]

    def find_books_by_notes(self, query: str) -> list[Book]:
        value = query.strip().casefold()
        if not value:
            return []
        return [book for book in self.books if value in book.notes.casefold()]

    def author_overview(self, top_genres: int = 3, top_tags: int = 3) -> list[dict[str, Any]]:
        genre_limit = _optional_int(top_genres) or 3
        tag_limit = _optional_int(top_tags) or 3
        if genre_limit <= 0:
            genre_limit = 3
        if tag_limit <= 0:
            tag_limit = 3

        buckets: dict[str, dict[str, Any]] = {}
        for book in self.books:
            author_name = book.author.strip()
            if not author_name:
                continue
            key = author_name.casefold()
            if key not in buckets:
                buckets[key] = {
                    "author": author_name,
                    "books": 0,
                    "genre_counts": {},
                    "genre_labels": {},
                    "tag_counts": {},
                    "tag_labels": {},
                }
            bucket = buckets[key]
            bucket["books"] += 1

            genre_parts = [part.strip() for part in (book.genre or "").split(",")]
            for genre_name in genre_parts:
                if not genre_name:
                    continue
                genre_key = " ".join(genre_name.split()).casefold()
                if not genre_key:
                    continue
                bucket["genre_labels"].setdefault(genre_key, " ".join(genre_name.split()))
                bucket["genre_counts"][genre_key] = bucket["genre_counts"].get(genre_key, 0) + 1

            for tag in book.tags:
                tag_key = tag.casefold()
                if not tag_key:
                    continue
                bucket["tag_labels"].setdefault(tag_key, tag)
                bucket["tag_counts"][tag_key] = bucket["tag_counts"].get(tag_key, 0) + 1

        summary: list[dict[str, Any]] = []
        for bucket in buckets.values():
            genre_counts = bucket["genre_counts"]
            genre_labels = bucket["genre_labels"]
            top_genre_entries = sorted(
                genre_counts.items(),
                key=lambda item: (-item[1], genre_labels.get(item[0], item[0]).casefold()),
            )[:genre_limit]
            top_genres_list = [f"{genre_labels.get(key, key)} ({count})" for key, count in top_genre_entries]

            tag_counts = bucket["tag_counts"]
            tag_labels = bucket["tag_labels"]
            top_tag_entries = sorted(
                tag_counts.items(),
                key=lambda item: (-item[1], tag_labels.get(item[0], item[0]).casefold()),
            )[:tag_limit]
            top_tags_list = [f"{tag_labels.get(key, key)} ({count})" for key, count in top_tag_entries]

            summary.append(
                {
                    "author": bucket["author"],
                    "books": bucket["books"],
                    "main_genres": top_genres_list,
                    "main_tags": top_tags_list,
                }
            )

        summary.sort(key=lambda item: (-item["books"], str(item["author"]).casefold()))
        return summary

    def sheet_stats(self) -> dict[str, Any]:
        sheets = [book for book in self.books if book.item_type == "SheetMusic"]
        total = len(sheets)

        composer_counts: dict[str, int] = {}
        instrumentation_counts: dict[str, int] = {}
        difficulty_counts: dict[str, int] = {}
        practice_counts: dict[str, int] = {}

        for sheet in sheets:
            composer = (sheet.composer or sheet.author).strip() or "-"
            composer_counts[composer] = composer_counts.get(composer, 0) + 1

            instrumentation = sheet.instrumentation.strip() or "-"
            instrumentation_counts[instrumentation] = instrumentation_counts.get(instrumentation, 0) + 1

            difficulty = sheet.difficulty.strip() or "-"
            difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1

            practice = sheet.practice_status.strip() or "Unstarted"
            practice_counts[practice] = practice_counts.get(practice, 0) + 1

        top_composers = sorted(composer_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:8]
        top_instrumentation = sorted(
            instrumentation_counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )[:8]
        by_difficulty = sorted(difficulty_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        by_practice = sorted(practice_counts.items(), key=lambda item: (-item[1], item[0].casefold()))

        return {
            "total": total,
            "top_composers": top_composers,
            "top_instrumentation": top_instrumentation,
            "by_difficulty": by_difficulty,
            "by_practice_status": by_practice,
        }

    def sorted_books(self, field: str) -> list[Book]:
        key = field.strip().lower()
        if key == "title":
            return sorted(self.books, key=lambda book: book.title.casefold())
        if key == "author":
            return sorted(self.books, key=lambda book: book.author.casefold())
        if key == "type":
            return sorted(self.books, key=lambda book: (book.item_type.casefold(), book.title.casefold()))
        if key == "year":
            return sorted(self.books, key=lambda book: (book.year is None, book.year if book.year is not None else 0))
        if key == "pages":
            return sorted(self.books, key=lambda book: (book.pages is None, book.pages if book.pages is not None else 0))
        if key == "language":
            return sorted(self.books, key=lambda book: (book.language.casefold(), book.title.casefold()))
        raise ValueError("Sort field must be one of: title, author, type, year, pages, language")

    def filter_books(
        self,
        *,
        read: bool | None = None,
        location: str | None = None,
        genre: str | None = None,
        min_rating: int | None = None,
        tags: list[str] | tuple[str, ...] | set[str] | str | None = None,
    ) -> list[Book]:
        location_value = None
        if location:
            if str(location).strip().lower() == "pforta":
                location_value = "Pforta"
            elif str(location).strip().lower() == "zuhause":
                location_value = "Zuhause"
            else:
                raise ValueError("Location must be Pforta or Zuhause.")

        genre_value = str(genre).strip().casefold() if genre else None
        min_rating_value = _optional_int(min_rating)
        if min_rating_value is not None and not (1 <= min_rating_value <= 5):
            raise ValueError("min_rating must be between 1 and 5.")

        required_tags = set(_normalize_tags(tags)) if tags is not None else set()

        result = []
        for book in self.books:
            if read is not None and book.read != read:
                continue
            if location_value and book.location != location_value:
                continue
            if genre_value and book.genre.casefold() != genre_value:
                continue
            if min_rating_value is not None:
                if book.rating is None or book.rating < min_rating_value:
                    continue
            if required_tags:
                if not required_tags.issubset(set(book.tags)):
                    continue
            result.append(book)
        return result

    def list_smart_lists(self) -> list[tuple[str, dict[str, Any]]]:
        return sorted(
            [(name, copy.deepcopy(filters)) for name, filters in self.smart_lists.items()],
            key=lambda item: item[0].casefold(),
        )

    def _find_smart_list_key(self, name: str) -> str | None:
        lookup = name.strip().casefold()
        for key in self.smart_lists:
            if key.casefold() == lookup:
                return key
        return None

    def get_smart_list(self, name: str) -> tuple[str, dict[str, Any]] | None:
        key = self._find_smart_list_key(name)
        if key is None:
            return None
        return key, copy.deepcopy(self.smart_lists[key])

    def save_smart_list(self, name: str, filters: dict[str, Any]) -> bool:
        list_name = str(name).strip()
        if not list_name:
            raise ValueError("Smart list name is required.")
        normalized = self._normalize_smart_filters(filters)
        existing_key = self._find_smart_list_key(list_name)

        def mutate():
            key = existing_key or list_name
            if existing_key and existing_key != list_name:
                self.smart_lists.pop(existing_key)
            if self.smart_lists.get(key) == normalized:
                return False
            self.smart_lists[key] = normalized
            return True

        return self._commit(mutate)

    def remove_smart_list(self, name: str) -> bool:
        key = self._find_smart_list_key(name)
        if key is None:
            return False

        def mutate():
            self.smart_lists.pop(key, None)
            return True

        return self._commit(mutate)

    def run_smart_list(self, name: str) -> list[Book]:
        found = self.get_smart_list(name)
        if not found:
            return []
        _, filters = found
        return self.filter_books(
            read=filters.get("read"),
            location=filters.get("location"),
            genre=filters.get("genre"),
            min_rating=filters.get("min_rating"),
            tags=filters.get("tags", []),
        )

    def get_recommendation_profile(self) -> dict[str, Any]:
        return copy.deepcopy(self.recommendation_profile)

    def set_recommendation_profile(self, profile: dict[str, Any]) -> bool:
        normalized = self._normalize_recommendation_profile(profile)

        def mutate():
            if self.recommendation_profile == normalized:
                return False
            self.recommendation_profile = normalized
            return True

        return self._commit(mutate)

    def clear_recommendation_profile(self) -> bool:
        return self.set_recommendation_profile(self._default_recommendation_profile())

    def _recommendation_score(self, book: Book, profile: dict[str, Any], profile_active: bool) -> float:
        if profile.get("prefer_unread", True) and book.read:
            return -1.0

        score = 0.0
        if not profile_active:
            # Sensible fallback: unread books first, then stronger ratings.
            score += 1.0 if not book.read else -0.5
            if book.rating is not None:
                score += book.rating / 10.0
            if book.progress_pages:
                score += 0.1
            return score

        genre_key = (book.genre or "").casefold()
        author_key = book.author.casefold()
        tag_set = {tag.casefold() for tag in book.tags}

        genres = set(profile.get("genres", []))
        if genres:
            if any(token in genre_key for token in genres):
                score += 4.0
            elif genre_key:
                score -= 0.5

        authors = set(profile.get("authors", []))
        if authors:
            if any(token in author_key for token in authors):
                score += 4.0
            else:
                score -= 0.5

        tags = set(profile.get("tags", []))
        if tags:
            match_count = len(tags.intersection(tag_set))
            if match_count > 0:
                score += min(7.0, 2.5 * match_count)
            else:
                score -= 0.5

        preferred_location = profile.get("location")
        if preferred_location:
            if book.location == preferred_location:
                score += 2.0
            else:
                score -= 1.0

        min_rating = profile.get("min_rating")
        if min_rating is not None:
            if book.rating is None:
                score -= 1.5
            elif book.rating < min_rating:
                score -= 3.0
            else:
                score += 1.0 + ((book.rating - min_rating + 1) * 0.5)
        elif book.rating is not None:
            score += book.rating / 10.0

        if not book.read:
            score += 1.0
        return score

    def recommended_books(self, limit: int = 10, include_existing_reading: bool = False) -> list[Book]:
        amount = _optional_int(limit)
        if amount is None or amount <= 0:
            raise ValueError("Recommendation limit must be a positive integer.")

        profile = self.get_recommendation_profile()
        profile_active = bool(
            profile.get("genres")
            or profile.get("tags")
            or profile.get("authors")
            or profile.get("min_rating") is not None
            or profile.get("location")
        )

        existing = {item.casefold() for item in self.reading_list}
        candidates = [
            book
            for book in self.books
            if include_existing_reading or not (book.book_id and book.book_id.casefold() in existing)
        ]

        scored: list[tuple[float, Book]] = []
        for book in candidates:
            score = self._recommendation_score(book, profile, profile_active)
            if score > 0:
                scored.append((score, book))

        scored.sort(
            key=lambda item: (
                -item[0],
                item[1].read,
                -(item[1].rating if item[1].rating is not None else 0),
                item[1].title.casefold(),
            )
        )
        if scored:
            return [book for _, book in scored[:amount]]

        # If strict matching returns nothing, offer unread fallback recommendations.
        fallback = [book for book in candidates if not book.read]
        fallback.sort(
            key=lambda book: (
                -(book.rating if book.rating is not None else 0),
                book.title.casefold(),
            )
        )
        return fallback[:amount]

    def apply_recommended_reading_list(self, limit: int = 10, mode: str = "replace") -> dict[str, Any]:
        mode_key = mode.strip().lower()
        if mode_key not in {"replace", "append"}:
            raise ValueError("Reading recommendation mode must be replace or append.")

        recommendations = self.recommended_books(limit=limit, include_existing_reading=(mode_key == "replace"))
        recommended_ids = [book.book_id for book in recommendations if book.book_id]
        before = self.reading_list[:]

        if mode_key == "replace":
            new_list = _dedupe(recommended_ids)
        else:
            new_list = _dedupe([*self.reading_list, *recommended_ids])

        before_set = set(before)
        new_set = set(new_list)
        added_count = len(new_set - before_set)
        removed_count = len(before_set - new_set)

        def mutate():
            if new_list == self.reading_list:
                return False
            self.reading_list = new_list
            return True

        changed = self._commit(mutate)
        return {
            "changed": changed,
            "mode": mode_key,
            "recommended": len(recommendations),
            "added": added_count,
            "removed": removed_count,
            "total": len(new_list),
            "books": recommendations,
        }

    def set_goal(self, period: str, target: int) -> bool:
        key = period.strip().lower()
        if key not in {"monthly", "yearly"}:
            raise ValueError("Goal period must be monthly or yearly.")
        normalized = _normalize_goal(target)
        if normalized is None:
            raise ValueError("Goal target must be a positive integer.")

        def mutate():
            if self.goals[key] == normalized:
                return False
            self.goals[key] = normalized
            return True

        return self._commit(mutate)

    def clear_goal(self, period: str) -> bool:
        key = period.strip().lower()
        if key not in {"monthly", "yearly"}:
            raise ValueError("Goal period must be monthly or yearly.")

        def mutate():
            if self.goals[key] is None:
                return False
            self.goals[key] = None
            return True

        return self._commit(mutate)

    def stats(self, today_value: date | None = None) -> dict[str, Any]:
        today_value = today_value or date.today()
        total = len(self.books)
        book_items = sum(1 for book in self.books if book.item_type == "Book")
        sheet_items = total - book_items
        read_books = [book for book in self.books if book.read]
        unread = total - len(read_books)

        this_month = 0
        this_year = 0
        for book in read_books:
            if not book.read_at:
                continue
            try:
                finished = date.fromisoformat(book.read_at)
            except ValueError:
                continue
            if finished.year == today_value.year:
                this_year += 1
            if finished.year == today_value.year and finished.month == today_value.month:
                this_month += 1

        location_counts = {
            location: sum(1 for book in self.books if book.location == location)
            for location in ALLOWED_LOCATIONS
        }

        genre_counts: dict[str, int] = {}
        for book in self.books:
            if not book.genre:
                continue
            genre_counts[book.genre] = genre_counts.get(book.genre, 0) + 1
        top_genres = sorted(genre_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:5]

        tag_counts: dict[str, int] = {}
        for book in self.books:
            for tag in book.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:8]

        ratings = [book.rating for book in self.books if book.rating is not None]
        average_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        monthly_goal = self.goals["monthly"]
        yearly_goal = self.goals["yearly"]
        profile = self.recommendation_profile or self._default_recommendation_profile()
        profile_active = bool(
            profile.get("genres")
            or profile.get("tags")
            or profile.get("authors")
            or profile.get("min_rating") is not None
            or profile.get("location")
        )
        return {
            "total": total,
            "books_only": book_items,
            "sheet_music": sheet_items,
            "read": len(read_books),
            "unread": unread,
            "reading_list": len(self.reading_list),
            "this_month": this_month,
            "this_year": this_year,
            "location_counts": location_counts,
            "top_genres": top_genres,
            "top_tags": top_tags,
            "average_rating": average_rating,
            "monthly_goal": monthly_goal,
            "yearly_goal": yearly_goal,
            "smart_lists": len(self.smart_lists),
            "recommendation_profile_active": profile_active,
        }

    def import_books(self, books: Iterable[Book]) -> dict[str, int]:
        snapshot = self.export_state()
        added = 0
        skipped = 0
        used_ids = {book.book_id.casefold() for book in self.books if book.book_id}
        for book in books:
            if self._has_duplicate_item(book):
                skipped += 1
            else:
                self._ensure_book_id(book, used_ids)
                self.books.append(book)
                added += 1

        if added == 0:
            return {"added": 0, "skipped": skipped, "invalid": 0, "metadata_updated": 0}

        try:
            self._autosave()
        except StorageError:
            self.restore_state(snapshot, persist=False)
            raise
        return {"added": added, "skipped": skipped, "invalid": 0, "metadata_updated": 0}

    def import_payload(self, payload: Any, apply_metadata: bool = False) -> dict[str, int]:
        if isinstance(payload, dict):
            raw_books = payload.get("books", [])
            raw_goals = payload.get("goals")
            raw_reading = payload.get("reading_list")
            raw_smart_lists = payload.get("smart_lists")
            raw_recommendation_profile = payload.get("recommendation_profile")
        elif isinstance(payload, list):
            raw_books = payload
            raw_goals = None
            raw_reading = None
            raw_smart_lists = None
            raw_recommendation_profile = None
        else:
            raise ValueError("Import file must contain an object or a list.")

        if raw_books is None:
            raw_books = []
        if not isinstance(raw_books, list):
            raise ValueError("Import payload has invalid books data.")

        snapshot = self.export_state()
        added = 0
        skipped = 0
        invalid = 0
        metadata_updated = 0
        used_ids = {book.book_id.casefold() for book in self.books if book.book_id}

        for item in raw_books:
            if not isinstance(item, dict):
                invalid += 1
                continue
            try:
                book = Book.from_dict(item)
            except ValueError:
                invalid += 1
                continue

            if self._has_duplicate_item(book):
                skipped += 1
                continue

            self._ensure_book_id(book, used_ids)
            self.books.append(book)
            added += 1

        if apply_metadata and isinstance(payload, dict):
            changed_metadata = False
            if isinstance(raw_goals, dict):
                goals = {
                    "monthly": _normalize_goal(raw_goals.get("monthly")),
                    "yearly": _normalize_goal(raw_goals.get("yearly")),
                }
                if goals != self.goals:
                    self.goals = goals
                    changed_metadata = True
            if isinstance(raw_reading, list):
                reading_refs: list[str] = []
                for item in raw_reading:
                    reference = str(item).strip()
                    if not reference:
                        continue
                    book = self.get_by_reference(reference)
                    if book and book.book_id:
                        reading_refs.append(book.book_id)
                reading_list = _dedupe(reading_refs)
                if reading_list != self.reading_list:
                    self.reading_list = reading_list
                    changed_metadata = True
            if isinstance(raw_smart_lists, dict):
                parsed_smart_lists: dict[str, dict[str, Any]] = {}
                for name, filters in raw_smart_lists.items():
                    list_name = str(name).strip()
                    if not list_name or not isinstance(filters, dict):
                        continue
                    try:
                        parsed_smart_lists[list_name] = self._normalize_smart_filters(filters)
                    except ValueError:
                        continue
                if parsed_smart_lists != self.smart_lists:
                    self.smart_lists = parsed_smart_lists
                    changed_metadata = True
            if isinstance(raw_recommendation_profile, dict):
                try:
                    profile = self._normalize_recommendation_profile(raw_recommendation_profile)
                except ValueError:
                    profile = self._default_recommendation_profile()
                if profile != self.recommendation_profile:
                    self.recommendation_profile = profile
                    changed_metadata = True
            if changed_metadata:
                metadata_updated = 1

        if added == 0 and metadata_updated == 0:
            return {
                "added": 0,
                "skipped": skipped,
                "invalid": invalid,
                "metadata_updated": metadata_updated,
            }

        try:
            self._autosave()
        except StorageError:
            self.restore_state(snapshot, persist=False)
            raise

        return {
            "added": added,
            "skipped": skipped,
            "invalid": invalid,
            "metadata_updated": metadata_updated,
        }
