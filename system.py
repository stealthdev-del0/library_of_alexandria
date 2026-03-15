from __future__ import annotations


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
    ):
        self.title = title
        self.author = author
        self.year = year
        self.isbn = isbn
        self.genre = genre
        self.pages = pages
        self.read = read
        self.notes = notes

    def __repr__(self):
        year_text = self.year if self.year is not None else "Unknown"
        pages_text = self.pages if self.pages is not None else "Unknown"
        read_text = "Read" if self.read else "Unread"
        notes_text = self.notes if self.notes else "-"
        return (
            f"Book(title={self.title!r}, author={self.author!r}, year={year_text}, "
            f"isbn={self.isbn!r}, genre={self.genre!r}, pages={pages_text}, status={read_text}, notes={notes_text!r})"
        )

    def to_row(self):
        return [
            self.title,
            self.author,
            str(self.year) if self.year is not None else "-",
            self.genre or "-",
            str(self.pages) if self.pages is not None else "-",
            "✔" if self.read else "✘",
            "Yes" if self.notes else "No",
        ]


class Library:
    def __init__(self):
        self.books: list[Book] = []
        self.reading_list: list[str] = []

    def add_book(self, book: Book) -> bool:
        if self.book_exists(title=book.title, author=book.author):
            return False
        if self.book_exists(isbn=book.isbn):
            return False
        self.books.append(book)
        return True

    def remove_book(self, isbn: str) -> bool:
        key = isbn.strip()
        if not key:
            return False
        before = len(self.books)
        self.books = [book for book in self.books if book.isbn != key]
        self.reading_list = [x for x in self.reading_list if x != key]
        return len(self.books) != before

    def book_exists(self, isbn: str | None = None, title: str | None = None, author: str | None = None) -> bool:
        isbn_key = (isbn or "").strip()
        title_key = (title or "").strip().lower()
        author_key = (author or "").strip().lower()
        for b in self.books:
            if isbn_key and b.isbn and b.isbn == isbn_key:
                return True
            if title_key and author_key and b.title.lower() == title_key and b.author.lower() == author_key:
                return True
        return False

    def find_book_by_title(self, title: str) -> list[Book]:
        value = title.strip().lower()
        return [book for book in self.books if value in book.title.lower()]

    def find_book_by_author(self, author: str) -> list[Book]:
        value = author.strip().lower()
        return [book for book in self.books if value in book.author.lower()]

    def get_by_isbn(self, isbn: str) -> Book | None:
        key = isbn.strip()
        if not key:
            return None
        for book in self.books:
            if book.isbn == key:
                return book
        return None

    def set_read(self, isbn: str, read: bool) -> bool:
        book = self.get_by_isbn(isbn)
        if book:
            book.read = read
            return True
        return False

    def set_notes(self, isbn: str, notes: str) -> bool:
        book = self.get_by_isbn(isbn)
        if book:
            book.notes = notes
            return True
        return False

    def add_to_reading_list(self, isbn: str) -> bool:
        key = isbn.strip()
        if self.get_by_isbn(key) and key not in self.reading_list:
            self.reading_list.append(key)
            return True
        return False

    def remove_from_reading_list(self, isbn: str) -> bool:
        key = isbn.strip()
        if not key:
            return False
        before = len(self.reading_list)
        self.reading_list = [x for x in self.reading_list if x != key]
        return len(self.reading_list) != before

    def reading_list_books(self) -> list[Book]:
        index = {book.isbn: book for book in self.books if book.isbn}
        return [index[isbn] for isbn in self.reading_list if isbn in index]
