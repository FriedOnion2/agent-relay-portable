"""One bounded local background job, with progress and cooperative cancellation."""

from .messages import text as message_text, error_text
import copy
import threading
import uuid


class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.thread = None
        self.value = dict(ok=True, status='idle')
        self.closing = False

    def status(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def start(self, kind, function):
        with self.lock:
            if self.closing or (self.thread and self.thread.is_alive()):
                raise ValueError(message_text('msg.a_job_is_already_running_or_the_service_is_exiting'))
            self.event = threading.Event()
            key = uuid.uuid4().hex
            self.value = dict(ok=True, id=key, kind=kind, status='running', progress={})
            def progress(value):
                with self.lock:
                    self.value['progress'] = copy.deepcopy(value)
            def run():
                try:
                    result = function(progress, self.event)
                    with self.lock:
                        self.value.update(status='canceled' if result.get('canceled') else 'completed', result=result)
                except Exception as exc:
                    with self.lock:
                        self.value.update(status='failed', error=error_text(exc))
            self.thread = threading.Thread(target=run, name='relay-' + kind, daemon=False)
            self.thread.start()
            return copy.deepcopy(self.value)

    def cancel(self, key):
        with self.lock:
            if key != self.value.get('id'):
                raise ValueError(message_text('msg.the_job_changed_refresh_its_status'))
            self.event.set()
            return dict(ok=True)

    def close(self):
        with self.lock:
            self.closing = True
            self.event.set()
            thread = self.thread
        if thread:
            thread.join(timeout=20)
        # Thread is non-daemon: Python waits for its current atomic read/transaction.
        # No writer can be silently killed while the portable directory is copied.
