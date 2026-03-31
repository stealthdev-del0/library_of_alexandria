from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from system import Book, Library


class LibraryFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.data_file = Path(self.tmpdir.name) / "library.json"
        self.library = Library(data_path=self.data_file)

    def test_duplicate_rules_allow_language_or_cover_variants(self) -> None:
        first = Book(
            title="Dune",
            author="Frank Herbert",
            language="English",
            cover="Softcover",
            isbn="",
        )
        second = Book(
            title="Dune",
            author="Frank Herbert",
            language="German",
            cover="Softcover",
            isbn="",
        )
        third = Book(
            title="Dune",
            author="Frank Herbert",
            language="English",
            cover="Hardcover",
            isbn="",
        )
        duplicate = Book(
            title="Dune",
            author="Frank Herbert",
            language="English",
            cover="Softcover",
            isbn="",
        )

        self.assertTrue(self.library.add_book(first))
        self.assertTrue(self.library.add_book(second))
        self.assertTrue(self.library.add_book(third))
        self.assertFalse(self.library.add_book(duplicate))
        self.assertEqual(len(self.library.books), 3)

    def test_persistence_roundtrip_keeps_books_sessions_inbox_and_ai(self) -> None:
        book = Book(
            title="Book A",
            author="Author A",
            pages=300,
            progress_pages=20,
            rating=4,
            tags=["alpha", "beta"],
            language="English",
            location="Pforta",
            cover="Hardcover",
        )
        sheet = Book(
            title="Nocturne",
            author="Chopin",
            item_type="SheetMusic",
            composer="Chopin",
            instrumentation="Piano",
            practice_status="Learning",
        )
        self.assertTrue(self.library.add_book(book))
        self.assertTrue(self.library.add_book(sheet))
        self.assertTrue(self.library.add_inbox_item("Try adding Hyperion"))
        self.assertTrue(self.library.schedule_session("b0001", when=date.today().isoformat(), minutes=25, kind="reading"))
        self.assertTrue(self.library.log_practice("b0002", minutes=30, bpm=88, practiced_on=date.today().isoformat()))
        self.assertTrue(self.library.set_ai_settings(safe_mode=False, model="llama3.2"))
        self.assertTrue(self.library.set_series("b0001", "Saga", 1))

        loaded = Library.load(self.data_file)
        self.assertEqual(len(loaded.books), 2)
        self.assertEqual(len(loaded.inbox), 1)
        self.assertGreaterEqual(len(loaded.sessions), 2)
        self.assertFalse(loaded.ai_settings.get("safe_mode", True))
        self.assertEqual(loaded.ai_settings.get("model"), "llama3.2")
        restored_book = loaded.get_by_book_id("b0001")
        self.assertIsNotNone(restored_book)
        assert restored_book is not None
        self.assertEqual(restored_book.series_name, "Saga")
        self.assertEqual(restored_book.series_index, 1)

    def test_bulk_edit_and_doctor_fix(self) -> None:
        self.assertTrue(
            self.library.add_book(
                Book(
                    title="Book 1",
                    author="Author 1",
                    genre="Sci-Fi",
                    tags=["space", "classic"],
                    rating=5,
                    read=False,
                )
            )
        )
        self.assertTrue(
            self.library.add_book(
                Book(
                    title="Book 2",
                    author="Author 2",
                    genre="Sci-Fi",
                    tags=["space"],
                    rating=4,
                    read=False,
                )
            )
        )
        result = self.library.bulk_edit(
            filters={"read": False, "genre": "Sci-Fi", "min_rating": 4},
            updates={
                "language": "German",
                "location": "Pforta",
                "add_tags": ["modern"],
                "series_name": "Space Saga",
                "series_index": 1,
            },
        )
        self.assertEqual(result["targets"], 2)
        self.assertEqual(result["updated"], 2)

        # Inject invalid data and verify doctor fix.
        first = self.library.get_by_book_id("b0001")
        assert first is not None
        first.language = "InvalidLanguage"
        first.cover = "InvalidCover"
        first.location = "Unknown"
        first.rating = 9
        first.progress_pages = -3
        first.tags = ["tag", "tag"]
        report = self.library.doctor_data(fix=True)
        self.assertGreaterEqual(report["fixed"], 1)

        healed = self.library.get_by_book_id("b0001")
        assert healed is not None
        self.assertIn(healed.language, {"German", "English", "French", "Japanese"})
        self.assertIn(healed.cover, {"Hardcover", "Softcover"})
        self.assertIn(healed.location, {"Pforta", "Zuhause"})
        self.assertTrue(healed.rating is None or 1 <= healed.rating <= 5)
        self.assertGreaterEqual(healed.progress_pages or 0, 0)
        self.assertEqual(len(healed.tags), len(set(healed.tags)))

    def test_dedup_scan_merge_and_reading_list_update(self) -> None:
        self.assertTrue(
            self.library.add_book(
                Book(title="The Pragmatic Programmer", author="Andrew Hunt", language="English", cover="Softcover")
            )
        )
        self.assertTrue(
            self.library.add_book(
                Book(title="The Pragmatic Programmer", author="Andrew Hunt", language="German", cover="Softcover")
            )
        )
        self.assertTrue(self.library.add_to_reading_list("b0002"))
        findings = self.library.find_potential_duplicates()
        self.assertTrue(any(item["left_id"] == "b0001" and item["right_id"] == "b0002" for item in findings))

        self.assertTrue(self.library.merge_items("b0001", "b0002"))
        self.assertEqual(len(self.library.books), 1)
        self.assertFalse(any(item == "b0002" for item in self.library.reading_list))

    def test_series_next_calendar_and_inbox(self) -> None:
        self.assertTrue(
            self.library.add_book(Book(title="Part 1", author="Author", read=False, pages=100, progress_pages=10))
        )
        self.assertTrue(
            self.library.add_book(Book(title="Part 2", author="Author", read=False, pages=120, progress_pages=0))
        )
        self.assertTrue(self.library.set_series("b0001", "Cycle", 1))
        self.assertTrue(self.library.set_series("b0002", "Cycle", 2))
        self.assertTrue(self.library.set_read("b0001", True))
        next_books = self.library.next_in_series("Cycle")
        self.assertEqual([book.book_id for book in next_books], ["b0002"])

        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        self.assertTrue(self.library.schedule_session("b0002", when=yesterday, minutes=30, kind="reading"))
        self.assertTrue(self.library.schedule_session("b0002", when=today.isoformat(), minutes=25, kind="reading"))
        self.assertTrue(self.library.mark_session_done("s000001"))
        self.assertTrue(self.library.mark_session_done("s000002"))
        self.assertGreaterEqual(self.library.streak(kind="reading"), 2)

        self.assertTrue(self.library.add_inbox_item("Read Hyperion"))
        items = self.library.list_inbox_items()
        self.assertEqual(len(items), 1)
        inbox_id = items[0]["id"]
        self.assertTrue(self.library.set_inbox_status(inbox_id, "done"))
        self.assertTrue(self.library.remove_inbox_item(inbox_id))
        self.assertEqual(len(self.library.list_inbox_items()), 0)


if __name__ == "__main__":
    unittest.main()
