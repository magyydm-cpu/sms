from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import Database  # noqa: E402
from database.migrations import apply_migrations  # noqa: E402
from services import Services  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "debt_manager_test.db")


@pytest.fixture
def db(db_path):
    database = Database(db_path)
    apply_migrations(database)
    yield database
    database.close()


@pytest.fixture
def services(db):
    return Services(db)


@pytest.fixture
def debtor(services):
    return services.debtors.create("محمد أحمد", "07701234567", "عميل تجريبي")
