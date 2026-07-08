"""Marker file making ``scripts/ci`` a regular Python package.

Required so mypy treats ``scripts/ci/log_worker_identity.py`` as
``scripts.ci.log_worker_identity`` (not also ``log_worker_identity``),
which would otherwise emit a "Source file found twice" error.

Has no runtime effect — the helper scripts are invoked via
``python scripts/ci/<name>.py`` in CI steps, not via package import.
"""
