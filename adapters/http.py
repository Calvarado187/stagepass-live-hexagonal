from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json
import logging
from core.models import Client, RuleError
from core.ports import BookingUseCases


def encode(value):
    if is_dataclass(value):
        return {k: encode(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def make_server(service: BookingUseCases, gateways, port=8083):
    assets = Path(__file__).resolve().parents[1] / 'web'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, content_type='application/json; charset=utf-8'):
            body = json.dumps(encode(data), ensure_ascii=False).encode() if content_type.startswith('application/json') else data.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.handle_request(False)

        def do_POST(self):
            self.handle_request(True)

        def handle_request(self, post):
            try:
                path = urlsplit(self.path).path
                parts = path.strip('/').split('/')
                data = {}
                if post:
                    origin = self.headers.get('Origin')
                    if origin and origin != 'http://' + self.headers.get('Host', ''):
                        return self.reply({'error': 'Origen no permitido.'}, 403)
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 16384:
                        return self.reply({'error': 'Tamaño de solicitud inválido.'}, 413)
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError('Se requiere un objeto JSON.')
                if not post and path in ('/', '/app.js', '/style.css'):
                    name, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}[path]
                    return self.reply((assets / name).read_text(encoding='utf-8'), content_type=mime + '; charset=utf-8')
                if not post and path == '/api/events':
                    return self.reply(service.events())
                if not post and len(parts) == 4 and parts[:2] == ['api', 'events'] and parts[3] == 'seats':
                    return self.reply(service.availability(parts[2]))
                if post and path == '/api/quote':
                    return self.reply(service.quote(data['event_id'], tuple(data['seat_ids'])))
                if post and path == '/api/orders':
                    c = data['client']
                    client = Client(*(c[k] for k in ('id', 'name', 'email', 'mobile', 'nationality')))
                    return self.reply(service.reserve(data['event_id'], client, tuple(data['seat_ids']), data['provider']), 201)
                if not post and len(parts) >= 3 and parts[:2] == ['api', 'orders']:
                    order_id = parts[2]
                    if len(parts) == 3:
                        return self.reply({'order': service.get_order(order_id), 'tickets': service.tickets(order_id)})
                    if len(parts) == 6 and parts[3] == 'tickets':
                        if parts[5] == 'svg':
                            return self.reply(service.ticket_svg(order_id, parts[4]), content_type='image/svg+xml; charset=utf-8')
                        if parts[5] == 'verify':
                            return self.reply({'valid': service.verify_ticket(order_id, parts[4])})
                if post and path == '/api/demo/payment':
                    order = service.get_order(data['order_id'])
                    payload = gateways[order.provider].simulate(order.payment_id, data['status'])
                    return self.reply({'provider': order.provider, 'notification': payload})
                if post and len(parts) == 3 and parts[:2] == ['api', 'webhooks']:
                    provider = parts[2]
                    if provider not in gateways:
                        raise RuleError('Pasarela desconocida.')
                    reference = gateways[provider].parse_notification(data)
                    order = service.confirm(provider, reference)
                    service.dispatch()
                    return self.reply(order)
                self.reply({'error': 'Ruta inexistente.'}, 404)
            except RuleError as exc:
                self.reply({'error': str(exc)}, 409)
            except (KeyError, TypeError, ValueError, UnicodeError):
                self.reply({'error': 'Solicitud inválida o campos faltantes.'}, 400)
            except Exception:
                logging.exception('Error no esperado')
                self.reply({'error': 'Error interno. Revisa el registro del servidor.'}, 500)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)
