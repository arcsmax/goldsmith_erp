"""Scheduled / unattended background jobs for Goldsmith ERP.

Each module here exposes a ``main() -> int`` entry point runnable via
``python -m goldsmith_erp.jobs.<name>`` so it can be driven by a systemd
timer, a cron entry, or a container exec without a running FastAPI process.
"""
