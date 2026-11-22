"""Cancellation shared by one worker and its subprocesses; never global per job."""
from contextvars import ContextVar
import threading

cancel_event = ContextVar('shortforge_cancel', default=None)

class Cancelled(RuntimeError):
    pass

def check_cancelled():
    event = cancel_event.get()
    if event is not None and event.is_set():
        raise Cancelled('Processamento cancelado pelo usuário.')
