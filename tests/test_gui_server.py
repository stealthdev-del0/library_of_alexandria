from __future__ import annotations

import unittest

from gui_server import GUI_HTML, build_graph_payload, filter_books
from system import Book


class GUIServerHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.books = [
            Book(
                title="Dune",
                author="Frank Herbert",
                genre="Sci-Fi, Classic",
                language="English",
                location="Zuhause",
                tags=["science fiction", "desert"],
                read=False,
            ),
            Book(
                title="Faust",
                author="Goethe",
                genre="Drama",
                language="German",
                location="Pforta",
                tags=["classic", "theatre"],
                read=True,
            ),
            Book(
                title="Nocturne in C# Minor",
                author="Chopin",
                item_type="SheetMusic",
                composer="Chopin",
                instrumentation="Piano",
                genre="Romantic",
                language="French",
                location="Zuhause",
                tags=["piano"],
                read=False,
            ),
        ]
        for idx, book in enumerate(self.books, start=1):
            book.book_id = f"b{idx:04d}"

    def test_filter_books_query_and_facets(self) -> None:
        result = filter_books(self.books, query="dune")
        self.assertEqual([item.book_id for item in result], ["b0001"])

        result = filter_books(self.books, item_type="SheetMusic")
        self.assertEqual([item.book_id for item in result], ["b0003"])

        result = filter_books(self.books, read="read")
        self.assertEqual([item.book_id for item in result], ["b0002"])

        result = filter_books(self.books, language="German")
        self.assertEqual([item.book_id for item in result], ["b0002"])

        result = filter_books(self.books, tag="science fiction")
        self.assertEqual([item.book_id for item in result], ["b0001"])

    def test_graph_payload_contains_nodes_and_edges(self) -> None:
        payload = build_graph_payload(self.books)
        nodes = payload["nodes"]
        edges = payload["edges"]

        self.assertTrue(any(node["id"] == "item:b0001" for node in nodes))
        self.assertTrue(any(node["id"] == "creator:frank herbert" for node in nodes))
        self.assertTrue(any(node["id"] == "genre:sci-fi" for node in nodes))
        self.assertTrue(any(node["id"] == "tag:science fiction" for node in nodes))
        self.assertTrue(any(edge["source"] == "item:b0001" and edge["target"] == "creator:frank herbert" for edge in edges))
        self.assertTrue(any(edge["source"] == "item:b0003" and edge["kind"] == "created_by" for edge in edges))

    def test_gui_html_exposes_console_and_graph_interactions(self) -> None:
        self.assertIn("console-shell", GUI_HTML)
        self.assertIn("bindGraphInput", GUI_HTML)
        self.assertIn("graphPauseBtn", GUI_HTML)
        self.assertIn("mark read", GUI_HTML)
        self.assertIn("reading list", GUI_HTML)
        self.assertIn("tag add", GUI_HTML)


if __name__ == "__main__":
    unittest.main()
