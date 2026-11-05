"""Único punto de composición: conoce núcleo y adaptadores concretos."""
from datetime import datetime, timezone
import secrets
from core.ports import Clock, IdSource
from core.service import BookingService
from adapters.storage import MySqlCatalogMock, MongoOrderStoreMock
from adapters.payments import PayPalMock, WompiMock, PseMock
from adapters.tickets import HmacTicketSigner, SvgTicketRenderer
from adapters.communications import WhatsAppMock, SendGridMock, DianInvoiceMock


class SystemClock(Clock):
    def now(self):
        return datetime.now(timezone.utc)


class SecureIds(IdSource):
    def new(self):
        return secrets.token_hex(16)


def build(clock=None):
    catalog = MySqlCatalogMock()
    gateways = {g.name: g for g in (PayPalMock(), WompiMock(), PseMock())}
    return BookingService(catalog, MongoOrderStoreMock(), clock or SystemClock(), SecureIds(), gateways,
                          HmacTicketSigner({e.id: secrets.token_bytes(32) for e in catalog.events()}),
                          SvgTicketRenderer(), {'whatsapp': WhatsAppMock(), 'sendgrid': SendGridMock()}, DianInvoiceMock())
