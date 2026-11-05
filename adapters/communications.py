from core.ports import Notification, Invoice


class NotificationMock(Notification):
    def __init__(self, channel):
        self.channel, self.sent = channel, {}
        self.fail = False

    def send(self, order, tickets, key):
        if self.fail:
            raise ConnectionError('Fallo simulado de comunicación')
        self.sent.setdefault(key, {'channel': self.channel, 'order_id': order.id,
                                  'recipient': order.client.mobile if self.channel == 'whatsapp' else order.client.email,
                                  'tickets': [t.code for t in tickets]})


class WhatsAppMock(NotificationMock):
    def __init__(self):
        super().__init__('whatsapp')


class SendGridMock(NotificationMock):
    def __init__(self):
        super().__init__('sendgrid')


class DianInvoiceMock(Invoice):
    def __init__(self):
        self.issued, self.fail = {}, False

    def issue(self, order, key):
        if self.fail:
            raise ConnectionError('Fallo simulado DIAN')
        self.issued.setdefault(key, {'order_id': order.id, 'amount': str(order.quote.total), 'status': 'SIMULADA'})
