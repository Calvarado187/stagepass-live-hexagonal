import hashlib
import hmac
import json
from dataclasses import asdict
from html import escape
from core.ports import TicketSigner, TicketRenderer


class HmacTicketSigner(TicketSigner):
    """Adaptador completo: HMAC-SHA256 con secreto independiente por evento."""
    def __init__(self, event_secrets: dict[str, bytes]):
        if any(len(secret) < 32 for secret in event_secrets.values()):
            raise ValueError('Se requieren secretos de al menos 32 bytes.')
        self._secrets = dict(event_secrets)

    def sign(self, claims):
        canonical = json.dumps(asdict(claims), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        return hmac.new(self._secrets[claims.event_id], canonical, hashlib.sha256).hexdigest()

    def verify(self, claims, signature):
        if claims.event_id not in self._secrets or not isinstance(signature, str) or not signature.isascii():
            return False
        return hmac.compare_digest(self.sign(claims), signature)


class SvgTicketRenderer(TicketRenderer):
    """Adaptador completo: ticket vectorial descargable, sin librerías externas."""
    def render(self, ticket, event, seat):
        def e(value):
            return escape(str(value), quote=True)
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420" role="img" aria-label="Ticket StagePass Live">
<rect width="960" height="420" rx="24" fill="#141425"/>
<rect x="700" width="260" height="420" rx="24" fill="#c7ff6b"/>
<path d="M700 20V400" stroke="#53604c" stroke-dasharray="8 8"/>
<g fill="#f8f6ff" font-family="Arial, sans-serif">
<text x="40" y="55" font-size="20" letter-spacing="4">STAGEPASS / LIVE</text>
<text x="40" y="122" font-size="32" font-weight="bold">{e(event.name)}</text>
<text x="40" y="159" font-size="18">{e(event.kind)} · {e(event.starts_at.strftime('%Y-%m-%d %H:%M UTC'))}</text>
<text x="40" y="215" font-size="28">{e(seat.location)}</text>
<text x="40" y="252" font-size="16">Recinto: {e(event.venue_id)} · Precio base: COP {e(seat.base_price)}</text>
<text x="40" y="307" font-size="13">CÓDIGO DE CANJE · {e(ticket.code)}</text>
<text x="40" y="341" font-size="11">Orden: {e(ticket.order_id)}</text>
<text x="40" y="371" font-size="9">HMAC-SHA256: {e(ticket.security_hash)}</text>
</g><g fill="#142019" font-family="Arial, sans-serif" text-anchor="middle">
<text x="830" y="135" font-size="18">ENTRADA</text><text x="830" y="181" font-size="32" font-weight="bold">{e(seat.id)}</text>
<text x="830" y="235" font-size="14">FIRMA VERIFICABLE</text><text x="830" y="280" font-size="12">DEMOSTRACIÓN ACADÉMICA</text>
<text x="830" y="301" font-size="12">Sin validez comercial</text></g></svg>'''
