"""
NEXUS Status Manager

Controls temporary assistant states.
Thread safe.
"""

import threading
import time


_status = None
_start_time = None

_lock = threading.RLock()



def set_status(message: str):

    global _status
    global _start_time

    if not message:
        return


    with _lock:

        _status = str(message)

        _start_time = time.monotonic()



def get_status():

    with _lock:

        return _status



def clear_status():

    global _status
    global _start_time


    with _lock:

        _status = None

        _start_time = None



def status_active():

    with _lock:

        return _status is not None



def get_status_age():

    with _lock:

        if _start_time is None:

            return 0


        return time.monotonic() - _start_time



def timeout_clear(seconds=120):

    global _status
    global _start_time


    with _lock:

        if _status is None:

            return False


        if _start_time is None:

            return False


        if time.monotonic() - _start_time > seconds:

            _status = None

            _start_time = None

            return True


    return False
