import threading
import time
from contextlib import contextmanager


_status = None

_lock = threading.Lock()

_start_time = None

# Called after the status is cleared so the animation can erase its line
# immediately instead of waiting for its next refresh.
_clear_hooks = []



def register_clear_hook(callback):

    if callback not in _clear_hooks:

        _clear_hooks.append(callback)



def _run_clear_hooks():

    for callback in list(_clear_hooks):

        try:

            callback()

        except Exception:

            pass



def set_status(message):

    global _status
    global _start_time

    with _lock:

        _status = message

        _start_time = time.time()



def get_status():

    with _lock:

        return _status



def clear_status():

    global _status
    global _start_time

    with _lock:

        _status = None

        _start_time = None

    _run_clear_hooks()



def status_active():

    with _lock:

        return _status is not None



def get_status_age():

    with _lock:

        if _start_time:

            return time.time() - _start_time

        return 0



@contextmanager
def activity(label):
    """
    Show `label` for the duration of a block, then put back whatever was
    shown before (or nothing). Pass None to hide the animation temporarily,
    for example while the terminal is needed for a prompt.
    """

    global _status
    global _start_time

    with _lock:

        previous = (_status, _start_time)

        _status = label

        _start_time = time.time() if label else None

    if not label:

        _run_clear_hooks()

    try:

        yield

    finally:

        with _lock:

            _status, _start_time = previous

        if previous[0] is None:

            _run_clear_hooks()
