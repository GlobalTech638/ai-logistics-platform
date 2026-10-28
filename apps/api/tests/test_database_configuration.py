import os
import subprocess
import sys


def test_production_requires_explicit_database_url():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["APP_ENV"] = "production"

    result = subprocess.run(
        [sys.executable, "-c", "import app.db.database"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Production requires DATABASE_URL to be explicitly configured" in result.stderr


def test_development_database_default_remains_available():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["APP_ENV"] = "development"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.db.database import DATABASE_URL; print(DATABASE_URL)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "postgresql://postgres:postgres@localhost:5432/logistics"
