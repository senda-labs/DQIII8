"""Library for metadata_audit.py / metadata_remove.py / metadata_purge_backups.py.

No CLI, no __main__ — pure library. metadata_audit.py imports only the
inspect_*()/detect_*() surface of this package; it must never import
safeio's write path or any fmt_*.remove_*()/clean_*() function (enforced by
tests/test_metadata_no_write_audit.py, an AST-walk test).
"""
