from dataclasses import replace
from datetime import timedelta
from .models import (RuleError, EventState, SeatState, OrderState, Quote, Order,
                     PaymentRequest, TicketClaims, Ticket, Delivery)
from .ports import (BookingUseCases, Clock, IdSource, Catalog, OrderStore,
                    PaymentGateway, TicketSigner, TicketRenderer, Notification, Invoice)


class BookingService(BookingUseCases):
    def __init__(self, catalog: Catalog, store: OrderStore, clock: Clock, ids: IdSource,
                 gateways: dict[str, PaymentGateway], signer: TicketSigner,
                 renderer: TicketRenderer, notifications: dict[str, Notification], invoice: Invoice):
        self.catalog, self.store, self.clock, self.ids = catalog, store, clock, ids
        self.gateways, self.signer, self.renderer = gateways, signer, renderer
        self.notifications, self.invoice = notifications, invoice

    def _expire(self):
        count = 0
        now = self.clock.now()
        for order in self.store.orders():
            updated = order.expire(now)
            if updated != order:
                self.store.save_order(updated)
                count += 1
        return count

    def expire(self):
        with self.store.transaction():
            return self._expire()

    def _availability(self, event_id):
        event = self.catalog.event(event_id)
        states = {}
        now = self.clock.now()
        for order in self.store.orders():
            if order.event_id == event_id and order.holds_at(now):
                for seat in order.seats:
                    states[seat.id] = SeatState.SOLD if order.state == OrderState.APPROVED else SeatState.HELD
        return tuple(replace(s, state=states.get(s.id, SeatState.AVAILABLE)) for s in self.catalog.seats(event.venue_id))

    def availability(self, event_id):
        with self.store.transaction():
            self._expire()
            return self._availability(event_id)

    def events(self):
        with self.store.transaction():
            self._expire()
            return tuple(replace(e, state=EventState.SOLD_OUT) if e.state == EventState.SCHEDULED
                         and all(s.state == SeatState.SOLD for s in self._availability(e.id)) else e
                         for e in self.catalog.events())

    def _selected(self, event_id, seat_ids):
        if not isinstance(seat_ids, tuple) or not all(isinstance(s, str) for s in seat_ids):
            raise RuleError('Selección inválida.')
        seats = {s.id: s for s in self._availability(event_id)}
        if any(s not in seats for s in seat_ids):
            raise RuleError('Asiento ajeno al recinto o inexistente.')
        return tuple(seats[s] for s in seat_ids)

    def quote(self, event_id, seat_ids):
        with self.store.transaction():
            return Quote.calculate(self._selected(event_id, seat_ids))

    def reserve(self, event_id, client, seat_ids, provider):
        client.validate()
        if provider not in self.gateways:
            raise RuleError('Pasarela desconocida.')
        # El mock serializa la transacción completa en un único proceso.
        with self.store.transaction():
            self._expire()
            event = self.catalog.event(event_id)
            if event.state != EventState.SCHEDULED:
                raise RuleError('El evento no admite reservas.')
            if event.starts_at <= self.clock.now():
                raise RuleError('La función ya comenzó.')
            seats = self._selected(event_id, seat_ids)
            quote = Quote.calculate(seats)
            if any(s.state != SeatState.AVAILABLE for s in seats):
                raise RuleError('Uno o más asientos ya no están disponibles.')
            now = self.clock.now()
            count = sum(len(o.seats) for o in self.store.orders()
                        if o.event_id == event_id and o.client.id == client.id and o.holds_at(now))
            if count + len(seats) > 6:
                raise RuleError('Máximo acumulado: 6 entradas por cliente y evento, incluidas reservas activas.')
            order = Order(self.ids.new(), event_id, client, seats, quote, now, now + timedelta(minutes=10), provider)
            session = self.gateways[provider].register(PaymentRequest(order.id, quote.total))
            if session.order_id != order.id or session.provider != provider or not session.id:
                raise RuleError('Registro de pago inconsistente.')
            order = replace(order, payment_id=session.id)
            self.store.save_order(order)
            return order

    def confirm(self, provider, reference):
        if provider not in self.gateways:
            raise RuleError('Pasarela desconocida.')
        payment = self.gateways[provider].verify(reference)
        with self.store.transaction():
            self._expire()
            order = self.store.order(payment.order_id)
            if (payment.provider != order.provider or payment.provider != provider
                    or payment.transaction_id != order.payment_id
                    or payment.amount != order.quote.total or payment.currency != 'COP'):
                raise RuleError('El pago no coincide con la orden.')
            if payment.status not in ('approved', 'rejected', 'pending'):
                raise RuleError('Estado de pago no reconocido.')
            if order.state == OrderState.APPROVED:
                return order  # Confirmación repetida: nunca vuelve a emitir.
            if order.state != OrderState.PENDING:
                if payment.status == 'approved':
                    order = replace(order, reconciliation=True)
                    self.store.save_order(order)
                return order
            if payment.status == 'pending':
                return order
            if payment.status == 'rejected':
                order = replace(order, state=OrderState.REJECTED)
                self.store.save_order(order)
                return order
            order = replace(order, state=OrderState.APPROVED)
            for seat in order.seats:
                tid, code = self.ids.new(), self.ids.new().upper()
                claims = TicketClaims(tid, order.id, order.event_id, order.client.id, seat.id,
                                      str(seat.base_price), str(order.quote.total), order.created_at.isoformat(), code)
                ticket = Ticket(tid, order.id, code, self.signer.sign(claims), self.clock.now(), claims)
                self.store.save_ticket(ticket)
            self.store.save_order(order)
            for kind in (*self.notifications, 'invoice'):
                self.store.save_delivery(Delivery(order.id + ':' + kind, order.id, kind))
            return order

    def get_order(self, order_id):
        with self.store.transaction():
            self._expire()
            return self.store.order(order_id)

    def tickets(self, order_id):
        with self.store.transaction():
            self.store.order(order_id)
            return self.store.tickets(order_id)

    def _ticket(self, order_id, ticket_id):
        order = self.get_order(order_id)
        ticket = next((t for t in self.tickets(order_id) if t.id == ticket_id), None)
        if ticket is None or order.state != OrderState.APPROVED:
            raise RuleError('Ticket no disponible.')
        return order, ticket

    def verify_ticket(self, order_id, ticket_id):
        _, ticket = self._ticket(order_id, ticket_id)
        return self.signer.verify(ticket.claims, ticket.security_hash)

    def ticket_svg(self, order_id, ticket_id):
        order, ticket = self._ticket(order_id, ticket_id)
        if not self.signer.verify(ticket.claims, ticket.security_hash):
            raise RuleError('Firma del ticket inválida.')
        seat = next(s for s in order.seats if s.id == ticket.claims.seat_id)
        return self.renderer.render(ticket, self.catalog.event(order.event_id), seat)

    def dispatch(self):
        completed = 0
        with self.store.transaction():
            for delivery in self.store.deliveries():
                if delivery.completed:
                    continue
                order = self.store.order(delivery.order_id)
                try:
                    if delivery.kind == 'invoice':
                        self.invoice.issue(order, delivery.id)
                    else:
                        self.notifications[delivery.kind].send(order, self.store.tickets(order.id), delivery.id)
                except Exception:
                    self.store.save_delivery(replace(delivery, attempts=delivery.attempts + 1))
                else:
                    self.store.save_delivery(replace(delivery, completed=True, attempts=delivery.attempts + 1))
                    completed += 1
        return completed
