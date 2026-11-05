from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


class RuleError(ValueError):
    pass


class EventState(str, Enum):
    SCHEDULED = 'Programado'
    SOLD_OUT = 'Agotado'
    CANCELLED = 'Cancelado'


class SeatState(str, Enum):
    AVAILABLE = 'Disponible'
    HELD = 'Bloqueado'
    SOLD = 'Vendido'


class OrderState(str, Enum):
    PENDING = 'Pendiente de Pago'
    APPROVED = 'Aprobada'
    REJECTED = 'Rechazada'
    EXPIRED = 'Expirada'


@dataclass(frozen=True)
class Event:
    id: str
    name: str
    kind: str
    venue_id: str
    starts_at: datetime
    state: EventState = EventState.SCHEDULED


@dataclass(frozen=True)
class Seat:
    id: str
    venue_id: str
    location: str
    base_price: Decimal
    state: SeatState = SeatState.AVAILABLE


@dataclass(frozen=True)
class Client:
    id: str
    name: str
    email: str
    mobile: str
    nationality: str

    def validate(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.id, self.name, self.email, self.mobile, self.nationality)):
            raise RuleError('Completa todos los datos del cliente.')
        if len(self.id) > 80 or any(len(v) > 180 for v in (self.name, self.email, self.mobile, self.nationality)):
            raise RuleError('Los datos exceden la longitud permitida.')
        if '@' not in self.email or '.' not in self.email.split('@')[-1]:
            raise RuleError('Correo electrónico inválido.')


@dataclass(frozen=True)
class Quote:
    subtotal: Decimal
    fee: Decimal
    discount: Decimal
    total: Decimal

    @staticmethod
    def calculate(seats: tuple[Seat, ...]):
        n = len(seats)
        if not 1 <= n <= 6:
            raise RuleError('Selecciona entre 1 y 6 entradas.')
        if len({s.id for s in seats}) != n:
            raise RuleError('No puedes repetir un asiento.')
        if any(s.base_price <= 0 for s in seats):
            raise RuleError('Precio de asiento inválido.')
        base = sum((s.base_price for s in seats), Decimal('0'))
        fee_rate, discount_rate = (('0.10', '0') if n <= 2 else ('0.08', '0.05') if n <= 5 else ('0.05', '0.10'))
        fee = (base * Decimal(fee_rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        discount = (base * Decimal(discount_rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        return Quote(base, fee, discount, base + fee - discount)


@dataclass(frozen=True)
class Order:
    id: str
    event_id: str
    client: Client
    seats: tuple[Seat, ...]
    quote: Quote
    created_at: datetime
    expires_at: datetime
    provider: str
    state: OrderState = OrderState.PENDING
    payment_id: str = ''
    reconciliation: bool = False

    def holds_at(self, now: datetime) -> bool:
        return self.state == OrderState.APPROVED or (self.state == OrderState.PENDING and now < self.expires_at)

    def expire(self, now: datetime):
        return replace(self, state=OrderState.EXPIRED) if self.state == OrderState.PENDING and now >= self.expires_at else self


@dataclass(frozen=True)
class PaymentRequest:
    order_id: str
    amount: Decimal
    currency: str = 'COP'


@dataclass(frozen=True)
class PaymentSession:
    id: str
    order_id: str
    provider: str


@dataclass(frozen=True)
class PaymentReference:
    transaction_id: str
    proof: str


@dataclass(frozen=True)
class VerifiedPayment:
    transaction_id: str
    order_id: str
    provider: str
    amount: Decimal
    currency: str
    status: str


@dataclass(frozen=True)
class TicketClaims:
    ticket_id: str
    order_id: str
    event_id: str
    client_id: str
    seat_id: str
    base_price: str
    order_total: str
    order_created_at: str
    code: str


@dataclass(frozen=True)
class Ticket:
    id: str
    order_id: str
    code: str
    security_hash: str
    issued_at: datetime
    claims: TicketClaims


@dataclass(frozen=True)
class Delivery:
    id: str
    order_id: str
    kind: str
    completed: bool = False
    attempts: int = 0
