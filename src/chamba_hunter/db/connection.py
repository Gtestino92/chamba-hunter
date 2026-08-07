from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "chamba-hunter.db"


class Database:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self.path)

        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()

        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()

        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()