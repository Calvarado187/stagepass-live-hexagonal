"""Pasarelas SIMULADAS: no cobran dinero ni llaman servicios externos."""
import hmac
import hashlib
import secrets
from dataclasses import replace
from threading import RLock
from core.models import PaymentSession, PaymentReference, VerifiedPayment, RuleError
from core.ports import PaymentGateway


class GatewayMock(PaymentGateway):
    name = ''
    reference_field = ''

    def __init__(self):
        self._key = secrets.token_bytes(32)
        self._payments = {}
        self._lock = RLock()

    def register(self, request):
        with self._lock:
            existing = next((p for p in self._payments.values() if p.order_id == request.order_id), None)
            if existing:
                if existing.amount != request.amount or existing.currency != request.currency:
                    raise RuleError('Intento de registro con valores diferentes.')
                return PaymentSession(existing.transaction_id, request.order_id, self.name)
            transaction_id = secrets.token_hex(16)
            self._payments[transaction_id] = VerifiedPayment(transaction_id, request.order_id, self.name,
                                                           request.amount, request.currency, 'pending')
            return PaymentSession(transaction_id, request.order_id, self.name)

    def _proof(self, payment):
        message = '|'.join((payment.transaction_id, payment.order_id, payment.provider,
                            str(payment.amount), payment.currency, payment.status)).encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def simulate(self, transaction_id, status):
        if status not in ('approved', 'rejected', 'pending'):
            raise RuleError('Resultado de simulación inválido.')
        with self._lock:
            if transaction_id not in self._payments:
                raise RuleError('Transacción inexistente.')
            current = self._payments[transaction_id]
            if current.status != 'pending' and current.status != status:
                raise RuleError('La transacción ya tiene resultado definitivo.')
            current = replace(current, status=status)
            self._payments[transaction_id] = current
            return {self.reference_field: transaction_id, 'signature': self._proof(current)}

    def parse_notification(self, payload):
        transaction_id, proof = payload.get(self.reference_field), payload.get('signature')
        if not isinstance(transaction_id, str) or not isinstance(proof, str):
            raise RuleError('Notificación mal formada.')
        return PaymentReference(transaction_id, proof)

    def verify(self, reference):
        with self._lock:
            payment = self._payments.get(reference.transaction_id)
            if not payment or not reference.proof.isascii() or not hmac.compare_digest(self._proof(payment), reference.proof):
                raise RuleError('Confirmación no auténtica.')
            return payment


class PayPalMock(GatewayMock):
    name, reference_field = 'paypal', 'resource_id'


class WompiMock(GatewayMock):
    name, reference_field = 'wompi', 'transaction_id'


class PseMock(GatewayMock):
    name, reference_field = 'pse', 'cus'
