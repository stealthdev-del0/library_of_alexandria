import readline

from system import Book, Library

COMMANDS = [
    "add",
    "list",
    "find title",
    "find author",
    "check",
    "remove",
    "mark read",
    "mark unread",
    "notes",
    "reading add",
    "reading list",
    "reading remove",
    "history",
    "help",
    "quit",
]

CANCELED = object()

def print_help():
    print("Commands:")
    print("  add                - add a new book")
    print("  list               - list all books")
    print("  find title         - search books by title")
    print("  find author        - search books by author")
    print("  check              - check if book exists by ISBN")
    print("  remove             - remove a book by ISBN")
    print("  mark read          - mark a book read")
    print("  mark unread        - mark a book unread")
    print("  notes              - add or update notes")
    print("  reading add        - add a book to reading list")
    print("  reading list       - show reading list")
    print("  reading remove     - remove from reading list")
    print("  history            - show command history")
    print("  help               - print this help")
    print("  quit               - exit program")


def setup_autocomplete():
    def completer(text, state):
        options = [cmd for cmd in COMMANDS if cmd.startswith(text)]
        return options[state] if state < len(options) else None
    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def prompt_or_cancel(prompt):
    text = input(prompt).strip()
    if text.lower() == "cancel":
        return None
    return text


def get_optional_int(prompt):
    while True:
        text = input(prompt).strip()
        if text == "":
            return None
        if text.lower() == "cancel":
            return CANCELED
        try:
            return int(text)
        except ValueError:
            print("Invalid number. Leave blank, type cancel, or enter an integer.")


def print_table(rows, headers):
    col_widths = [max(len(str(item)) for item in [header] + [row[i] for row in rows]) for i, header in enumerate(headers)]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(sep)
    print("| " + " | ".join(header.ljust(col_widths[i]) for i, header in enumerate(headers)) + " |")
    print(sep)
    for row in rows:
        print("| " + " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))) + " |")
    print(sep)


def print_books(library):
    if not library.books:
        print("No books yet. Use 'add' to add your first book.")
        return
    rows = [book.to_row() for book in library.books]
    headers = ["Title", "Author", "Year", "Genre", "Pages", "Read", "Notes"]
    print_table(rows, headers)


def interactive_demo():
    library = Library()
    history = []
    while True:
        cmd = input("Library> ").strip().lower()
        if cmd:
            history.append(cmd)
        if cmd == "":
            continue
        if cmd in ("quit", "exit"):
            print("Goodbye.")
            break
        if cmd == "help":
            print_help()
            continue
        if cmd == "add":
            print("(Type 'cancel' at any prompt to abort)")
            title = prompt_or_cancel("Title: ")
            if title is None or title == "":
                print("Add canceled or missing title.")
                continue
            author = prompt_or_cancel("Author: ")
            if author is None or author == "":
                print("Add canceled or missing author.")
                continue
            year = get_optional_int("Year (optional): ")
            if year is CANCELED:
                print("Add canceled.")
                continue
            isbn = prompt_or_cancel("ISBN (optional): ")
            if isbn is None:
                print("Add canceled.")
                continue
            isbn = isbn or ""
            genre = prompt_or_cancel("Genre (optional): ")
            if genre is None:
                print("Add canceled.")
                continue
            genre = genre or ""
            pages = get_optional_int("Pages (optional): ")
            if pages is CANCELED:
                print("Add canceled.")
                continue
            read_input = prompt_or_cancel("Mark as read? (y/n, optional): ")
            if read_input is None:
                print("Add canceled.")
                continue
            read = str(read_input).lower() in ("y", "yes")
            notes = prompt_or_cancel("Notes (optional): ")
            if notes is None:
                print("Add canceled.")
                continue
            notes = notes or ""
            book = Book(title=title, author=author, year=year, isbn=isbn, genre=genre, pages=pages, read=read, notes=notes)
            if library.add_book(book):
                print("Added.")
            else:
                print("Book already exists (same ISBN or same title and author).")
            continue
        if cmd == "list":
            print_books(library)
            continue
        if cmd.startswith("find"):
            parts = cmd.split(maxsplit=1)
            if len(parts) != 2 or parts[1] not in ("title", "author"):
                print("Usage: find title | find author")
                continue
            if parts[1] == "title":
                q = input("Title search: ").strip()
                results = library.find_book_by_title(q)
            else:
                q = input("Author search: ").strip()
                results = library.find_book_by_author(q)
            if not results:
                print("No matches.")
                continue
            print_table([b.to_row() for b in results], ["Title", "Author", "Year", "Genre", "Pages", "Read", "Notes"])
            continue
        if cmd == "check":
            isbn = input("ISBN to check: ").strip()
            if not isbn:
                print("ISBN is required for check.")
                continue
            book = library.get_by_isbn(isbn)
            print("Present." if book else "Not found.")
            continue
        if cmd == "remove":
            isbn = input("ISBN to remove: ").strip()
            if not isbn:
                print("ISBN is required for remove.")
                continue
            if library.remove_book(isbn):
                print("Removed.")
            else:
                print("Book not found.")
            continue
        if cmd == "mark read":
            isbn = input("ISBN: ").strip()
            if not isbn:
                print("ISBN is required.")
                continue
            if library.set_read(isbn, True):
                print("Marked read.")
            else:
                print("Book not found.")
            continue
        if cmd == "mark unread":
            isbn = input("ISBN: ").strip()
            if not isbn:
                print("ISBN is required.")
                continue
            if library.set_read(isbn, False):
                print("Marked unread.")
            else:
                print("Book not found.")
            continue
        if cmd == "notes":
            isbn = input("ISBN: ").strip()
            if not isbn:
                print("ISBN is required.")
                continue
            note = input("Notes: ").strip()
            if library.set_notes(isbn, note):
                print("Notes updated.")
            else:
                print("Book not found.")
            continue
        if cmd == "reading add":
            isbn = input("ISBN to add to reading list: ").strip()
            if library.add_to_reading_list(isbn):
                print("Added to reading list.")
            else:
                print("Book not found or already on reading list.")
            continue
        if cmd == "reading list":
            books = library.reading_list_books()
            if not books:
                print("Reading list is empty.")
            else:
                print_table([b.to_row() for b in books], ["Title", "Author", "Year", "Genre", "Pages", "Read", "Notes"])
            continue
        if cmd == "reading remove":
            isbn = input("ISBN to remove from reading list: ").strip()
            if not isbn:
                print("ISBN is required.")
                continue
            if library.remove_from_reading_list(isbn):
                print("Removed from reading list.")
            else:
                print("Book not in reading list.")
            continue
        if cmd == "history":
            if not history:
                print("No commands yet.")
            else:
                for i, h in enumerate(history, 1):
                    print(f"{i}. {h}")
            continue
        candidates = [c for c in COMMANDS if c.startswith(cmd)]
        if candidates:
            print("Unknown command. Did you mean:")
            for c in candidates:
                print(f"  {c}")
        else:
            print("Unknown command. Type help.")


def main():
    print("Library of Alexandria")
    print("Type 'help' for commands. Type 'quit' to exit.\n")
    print_help()
    try:
        setup_autocomplete()
    except Exception:
        pass
    interactive_demo()


if __name__ == "__main__":
    main()
