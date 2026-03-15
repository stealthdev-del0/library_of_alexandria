# Library of Alexandria

A minimal Python book library demo.

## Files

- `system.py`: Defines `Book` and `Library` classes.
- `main.py`: Interactive CLI to add/find/list/remove books.

## Run

```bash
python3 main.py
```

## Commands

- `add`: Add a book.
  - Enter title, author, optionally year (leave blank for unknown), ISBN, genre, and optionally pages.
  - Type `cancel` during prompts to abort adding.
- `list`: Show all books.
- `find title`: Search by title.
- `find author`: Search by author.
- `remove`: Remove by ISBN.
- `help`: Show command list.
- `quit`: Exit.

## Notes

- Year and pages are optional; leave blank for unknown values.
- This project is for local quick demos and learning.
