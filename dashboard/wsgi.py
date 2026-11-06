"""Gunicorn entrypoint. Import only in the single serving worker on Linux."""
import atexit
from dashboard.app import create_app, single_server

_server_lock = single_server()
_server_lock.__enter__()
atexit.register(_server_lock.__exit__, None, None, None)
app = create_app()
