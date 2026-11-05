from contextlib import contextmanager
from threading import RLock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from core.models import Event, Seat, RuleError
from core.ports import Catalog, OrderStore


class MySqlCatalogMock(Catalog):
    """Sustituto del catálogo legado: NO establece una conexión MySQL."""
    def __init__(self):
        future = datetime.now(timezone.utc).replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(days=30)
        self.data = (
            Event('neon', 'Neon Nights', 'Concierto', 'arena', future),
            Event('escena', 'La última escena', 'Teatro', 'teatro', future + timedelta(days=1)),
            Event('horizonte', 'Horizonte Festival', 'Festival', 'arena', future + timedelta(days=2)),
        )

    def events(self):
        return self.data

    def event(self, event_id):
        found = next((e for e in self.data if e.id == event_id), None)
        if not found:
            raise RuleError('Evento inexistente.')
        return found

    def seats(self, venue_id):
        if venue_id not in ('arena', 'teatro'):
            raise RuleError('Recinto inexistente.')
        return tuple(Seat(f'{row}{n}', venue_id, f'{"VIP" if row == "A" else "GENERAL"}-{row}{n:02}',
                          Decimal('150000.00' if row == 'A' else '90000.00'))
                     for row in 'ABC' for n in range(1, 9))


class MongoOrderStoreMock(OrderStore):
    """Memoria volátil; exclusión mutua y rollback para UN proceso.

    Las entidades inmutables permiten snapshots superficiales seguros.
    No es un driver de MongoDB. Reiniciar borra órdenes y tickets.
    """
    def __init__(self):
        self._orders, self._tickets, self._deliveries = {}, {}, {}
        self._lock = RLock()

    @contextmanager
    def transaction(self):
        with self._lock:
            snapshot = self._orders.copy(), self._tickets.copy(), self._deliveries.copy()
            try:
                yield
            except BaseException:
                self._orders, self._tickets, self._deliveries = snapshot
                raise

    def orders(self):
        return tuple(self._orders.values())

    def order(self, order_id):
        if order_id not in self._orders:
            raise RuleError('Orden inexistente.')
        return self._orders[order_id]

    def save_order(self, order):
        self._orders[order.id] = order

    def tickets(self, order_id):
        return tuple(t for t in self._tickets.values() if t.order_id == order_id)

    def save_ticket(self, ticket):
        self._tickets[ticket.id] = ticket

    def deliveries(self):
        return tuple(self._deliveries.values())

    def save_delivery(self, delivery):
        self._deliveries[delivery.id] = delivery
