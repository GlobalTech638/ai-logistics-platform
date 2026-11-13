from app.db.migrate import migration_checksum, migration_files, strip_transaction_wrappers


def test_migration_files_are_ordered_and_named():
    files = migration_files()
    assert files
    assert [path.name for path in files] == sorted(path.name for path in files)
    assert files[0].name == "001_initial.sql"
    assert files[-1].name == "017_shipment_operating_costs.sql"


def test_checksum_is_stable_and_sensitive_to_content():
    assert migration_checksum("SELECT 1;") == migration_checksum("SELECT 1;")
    assert migration_checksum("SELECT 1;") != migration_checksum("SELECT 2;")


def test_strip_transaction_wrappers_preserves_migration_body_and_comments():
    sql = """-- Migration comment
BEGIN;

CREATE TABLE example (id integer);

COMMIT;
"""
    normalized = strip_transaction_wrappers(sql)
    assert "-- Migration comment" in normalized
    assert "BEGIN;" not in normalized
    assert "COMMIT;" not in normalized
    assert "CREATE TABLE example" in normalized


def test_strip_transaction_wrappers_does_not_remove_inner_transaction_words():
    sql = """-- Migration comment
CREATE TABLE example (id integer DEFAULT 1);
"""
    assert strip_transaction_wrappers(sql) == sql
