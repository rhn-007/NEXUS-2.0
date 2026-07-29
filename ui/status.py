import threading
import time


_status = None

_lock = threading.Lock()

_start_time = None



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



def status_active():

    with _lock:

        return _status is not None



def get_status_age():

    with _lock:

        if _start_time:

            return time.time() - _start_time

        return 0
