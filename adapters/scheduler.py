import logging
from threading import Event, Thread
from core.ports import BookingUseCases


class ExpiryScheduler:
    def __init__(self, service: BookingUseCases):
        self.service, self.stop = service, Event()

    def start(self):
        def run():
            while not self.stop.wait(1):
                try:
                    self.service.expire()
                    self.service.dispatch()
                except Exception:
                    logging.exception('Error en tareas periódicas')
        self.thread = Thread(target=run, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
