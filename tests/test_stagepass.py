import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import unittest
import xml.etree.ElementTree as ET
from bootstrap import build
from core.models import Client, RuleError, Quote, OrderState, EventState, SeatState, PaymentReference, PaymentRequest
from adapters.http import make_server
from adapters.tickets import HmacTicketSigner


class ManualClock:
    def __init__(self):
        self.value = datetime.now(timezone.utc)
    def now(self):
        return self.value
    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock()
        self.s = build(self.clock)
        self.c = Client('CC1', 'Ana Pérez', 'ana@example.com', '+573001112233', 'Colombiana')

    def reserve(self, n=1, provider='wompi', event='neon', client=None, seats=None):
        return self.s.reserve(event, client or self.c, seats or tuple('A'+str(i) for i in range(1,n+1)), provider)

    def confirm(self, order, status='approved'):
        gateway = self.s.gateways[order.provider]
        payload = gateway.simulate(order.payment_id, status)
        return self.s.confirm(order.provider, gateway.parse_notification(payload))

    def test_fee_one(self):
        self.assertEqual(self.reserve().quote.total, Decimal('165000.00'))
    def test_fee_two(self):
        self.assertEqual(self.reserve(2).quote.total, Decimal('330000.00'))
    def test_fee_three(self):
        q = self.reserve(3).quote
        self.assertEqual((q.fee,q.discount,q.total), (Decimal('36000'),Decimal('22500'),Decimal('463500')))
    def test_fee_five(self):
        self.assertEqual(self.reserve(5).quote.total, Decimal('772500'))
    def test_fee_six(self):
        q=self.reserve(6).quote
        self.assertEqual((q.fee,q.discount,q.total),(Decimal('45000'),Decimal('90000'),Decimal('855000')))
    def test_mixed_prices(self):
        self.assertEqual(self.reserve(seats=('A1','B1','C1')).quote.total,Decimal('339900'))
    def test_round_half_up(self):
        seat=replace(self.s.catalog.seats('arena')[0],base_price=Decimal('0.05'))
        self.assertEqual(Quote.calculate((seat,)).fee,Decimal('0.01'))
    def test_empty_selection(self):
        with self.assertRaises(RuleError): self.s.reserve('neon',self.c,(),'wompi')
    def test_seven_forbidden(self):
        with self.assertRaises(RuleError): self.reserve(7)
    def test_duplicate_seat(self):
        with self.assertRaises(RuleError): self.reserve(seats=('A1','A1'))
    def test_unknown_seat(self):
        with self.assertRaises(RuleError): self.reserve(seats=('Z99',))
    def test_unknown_event(self):
        with self.assertRaises(RuleError): self.reserve(event='missing')
    def test_unknown_gateway(self):
        with self.assertRaises(RuleError): self.reserve(provider='missing')
    def test_invalid_client(self):
        with self.assertRaises(RuleError): self.reserve(client=replace(self.c,email='invalid'))
    def test_cancelled_event(self):
        self.s.catalog.data = tuple(replace(e,state=EventState.CANCELLED) for e in self.s.catalog.data)
        with self.assertRaises(RuleError): self.reserve()
    def test_event_started(self):
        self.clock.advance(days=60)
        with self.assertRaises(RuleError): self.reserve()
    def test_exact_ten_minutes(self):
        o=self.reserve()
        self.assertEqual(o.expires_at-o.created_at,timedelta(minutes=10))
    def test_blocked_inventory(self):
        self.reserve()
        self.assertEqual(self.s.availability('neon')[0].state,SeatState.HELD)
    def test_duplicate_booking_rejected(self):
        self.reserve()
        with self.assertRaises(RuleError): self.reserve(client=replace(self.c,id='CC2'))
    def test_pending_counts_toward_six(self):
        self.reserve(5)
        with self.assertRaises(RuleError): self.reserve(seats=('B1','B2'))
    def test_approved_counts_toward_six(self):
        self.confirm(self.reserve(6))
        with self.assertRaises(RuleError): self.reserve(seats=('B1',))
    def test_six_across_orders_allowed(self):
        self.reserve(5)
        self.assertEqual(self.reserve(seats=('B1',)).state,OrderState.PENDING)
    def test_limit_per_event(self):
        self.reserve(6)
        self.assertEqual(len(self.reserve(6,event='horizonte').seats),6)
    def test_same_venue_separate_inventory(self):
        self.reserve()
        self.assertEqual(self.s.availability('horizonte')[0].state,SeatState.AVAILABLE)
    def test_expired_releases_inventory(self):
        o=self.reserve();self.clock.advance(minutes=10)
        self.assertEqual(self.s.expire(),1)
        self.assertEqual(self.s.get_order(o.id).state,OrderState.EXPIRED)
        self.assertEqual(self.s.availability('neon')[0].state,SeatState.AVAILABLE)
    def test_before_boundary_still_held(self):
        self.reserve();self.clock.advance(seconds=599,microseconds=999999)
        self.assertEqual(self.s.expire(),0)
    def test_payment_before_boundary_accepted(self):
        o=self.reserve();self.clock.advance(seconds=599,microseconds=999999)
        self.assertEqual(self.confirm(o).state,OrderState.APPROVED)
    def test_payment_at_boundary_no_ticket(self):
        o=self.reserve();self.clock.advance(minutes=10)
        result=self.confirm(o)
        self.assertEqual(result.state,OrderState.EXPIRED)
        self.assertTrue(result.reconciliation)
        self.assertEqual(self.s.tickets(o.id),())
    def test_late_payment_cannot_steal_new_hold(self):
        o=self.reserve();self.clock.advance(minutes=10)
        newer=self.reserve(client=replace(self.c,id='CC2'))
        self.confirm(o)
        self.assertEqual(self.s.get_order(newer.id).state,OrderState.PENDING)
        self.assertEqual(self.s.tickets(o.id),())
    def test_expired_not_counted(self):
        self.reserve(6);self.clock.advance(minutes=10)
        self.assertEqual(len(self.reserve(6).seats),6)
    def test_rejected_releases(self):
        o=self.reserve(6);self.confirm(o,'rejected')
        self.assertEqual(len(self.reserve(6).seats),6)
    def test_pending_no_tickets_or_extension(self):
        o=self.reserve();self.clock.advance(minutes=4)
        result=self.confirm(o,'pending')
        self.assertEqual(result.expires_at,o.expires_at)
        self.assertEqual(self.s.tickets(o.id),())
    def test_approved_issues_one_ticket_per_seat(self):
        o=self.reserve(3);self.confirm(o)
        self.assertEqual(len(self.s.tickets(o.id)),3)
        self.assertEqual(len({t.code for t in self.s.tickets(o.id)}),3)
    def test_replay_idempotent(self):
        o=self.reserve(2);self.confirm(o)
        original=self.s.tickets(o.id);self.confirm(o)
        self.assertEqual(self.s.tickets(o.id),original)
        self.assertEqual(len(self.s.store.deliveries()),3)
    def test_paypal(self):
        self.assertEqual(self.confirm(self.reserve(provider='paypal')).state,OrderState.APPROVED)
    def test_pse(self):
        self.assertEqual(self.confirm(self.reserve(provider='pse')).state,OrderState.APPROVED)
    def test_false_signature(self):
        o=self.reserve()
        with self.assertRaises(RuleError): self.s.confirm('wompi',PaymentReference(o.payment_id,'forged'))
        self.assertEqual(self.s.tickets(o.id),())
    def test_non_ascii_signature(self):
        o=self.reserve()
        with self.assertRaises(RuleError): self.s.confirm('wompi',PaymentReference(o.payment_id,'ñ'))
    def test_wrong_amount(self):
        o=self.reserve();g=self.s.gateways['wompi']
        g._payments[o.payment_id]=replace(g._payments[o.payment_id],amount=Decimal('1'))
        with self.assertRaises(RuleError):self.confirm(o)
    def test_wrong_currency(self):
        o=self.reserve();g=self.s.gateways['wompi']
        g._payments[o.payment_id]=replace(g._payments[o.payment_id],currency='USD')
        with self.assertRaises(RuleError):self.confirm(o)
    def test_wrong_transaction(self):
        o=self.reserve();g=self.s.gateways['wompi']
        g._payments[o.payment_id]=replace(g._payments[o.payment_id],transaction_id='wrong')
        with self.assertRaises(RuleError):self.confirm(o)
    def test_wrong_provider(self):
        o=self.reserve();g=self.s.gateways['wompi']
        g._payments[o.payment_id]=replace(g._payments[o.payment_id],provider='paypal')
        with self.assertRaises(RuleError):self.confirm(o)
    def test_register_idempotent(self):
        g=self.s.gateways['wompi'];r=PaymentRequest('one',Decimal('5'))
        self.assertEqual(g.register(r),g.register(r))
    def test_valid_ticket_signature(self):
        o=self.reserve();self.confirm(o);t=self.s.tickets(o.id)[0]
        self.assertTrue(self.s.verify_ticket(o.id,t.id))
        self.assertEqual(len(t.security_hash),64)
        self.assertTrue(t.code.isalnum())
    def test_tampered_claim(self):
        o=self.reserve();self.confirm(o);t=self.s.tickets(o.id)[0]
        self.assertFalse(self.s.signer.verify(replace(t.claims,seat_id='B8'),t.security_hash))
    def test_different_event_secret(self):
        o=self.reserve();self.confirm(o);t=self.s.tickets(o.id)[0]
        other=HmacTicketSigner({'neon':b'x'*32})
        self.assertFalse(other.verify(t.claims,t.security_hash))
    def test_weak_secret_rejected(self):
        with self.assertRaises(ValueError): HmacTicketSigner({'neon':b'weak'})
    def test_svg_parseable_and_escaped(self):
        self.s.catalog.data=tuple(replace(e,name='<script>alert(1)</script>') for e in self.s.catalog.data)
        o=self.reserve();self.confirm(o);t=self.s.tickets(o.id)[0]
        svg=self.s.ticket_svg(o.id,t.id)
        root=ET.fromstring(svg)
        self.assertEqual(root.tag,'{http://www.w3.org/2000/svg}svg')
        self.assertNotIn('<script>',svg)
        self.assertIn('&lt;script&gt;',svg)
    def test_no_ticket_download_before_payment(self):
        o=self.reserve()
        with self.assertRaises(RuleError):self.s.ticket_svg(o.id,'missing')
    def test_notifications_and_invoice_once(self):
        o=self.reserve();self.confirm(o)
        self.assertEqual(self.s.dispatch(),3);self.assertEqual(self.s.dispatch(),0)
        self.assertEqual(len(self.s.invoice.issued),1)
        self.assertTrue(all(len(n.sent)==1 for n in self.s.notifications.values()))
    def test_notification_failure_does_not_revoke_ticket(self):
        self.s.notifications['whatsapp'].fail=True
        o=self.reserve();self.confirm(o)
        self.assertEqual(self.s.dispatch(),2)
        self.assertEqual(len(self.s.tickets(o.id)),1)
        self.s.notifications['whatsapp'].fail=False
        self.assertEqual(self.s.dispatch(),1)
    def test_invoice_failure_retried(self):
        self.s.invoice.fail=True;o=self.reserve();self.confirm(o)
        self.assertEqual(self.s.dispatch(),2)
        self.s.invoice.fail=False;self.assertEqual(self.s.dispatch(),1)
    def test_atomic_rollback_when_signer_fails(self):
        o=self.reserve(2)
        original=self.s.signer.sign;counter=[0]
        def failing(claims):
            counter[0]+=1
            if counter[0]==2:raise RuntimeError('simulated')
            return original(claims)
        self.s.signer.sign=failing
        with self.assertRaises(RuntimeError):self.confirm(o)
        self.assertEqual(self.s.tickets(o.id),())
        self.assertEqual(self.s.get_order(o.id).state,OrderState.PENDING)
        self.s.signer.sign=original;self.confirm(o)
        self.assertEqual(len(self.s.tickets(o.id)),2)
    def test_gateway_failure_no_hold(self):
        def failure(_):raise ConnectionError('offline')
        self.s.gateways['wompi'].register=failure
        with self.assertRaises(ConnectionError):self.reserve()
        self.assertEqual(self.s.store.orders(),())
        self.assertEqual(self.s.availability('neon')[0].state,SeatState.AVAILABLE)
    def test_concurrent_same_seat_one_winner(self):
        def attempt(i):
            try:self.reserve(client=replace(self.c,id=str(i)));return True
            except RuleError:return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(attempt,range(20))),1)
    def test_concurrent_limit(self):
        def attempt(i):
            try:self.reserve(seats=('A'+str(i),));return True
            except RuleError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt,range(1,9))),6)
    def test_sold_out_after_all_seats_sold(self):
        for row in 'ABC':
            for start,end in ((1,5),(5,9)):
                o=self.reserve(client=replace(self.c,id=f'{row}{start}'),seats=tuple(row+str(i) for i in range(start,end)))
                self.confirm(o)
        self.assertEqual(self.s.events()[0].state,EventState.SOLD_OUT)
    def test_core_imports_only_domain_and_standard_types(self):
        allowed={'dataclasses','datetime','decimal','enum','typing','models','ports'}
        for path in (Path(__file__).resolve().parents[1]/'core').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node,ast.Import):
                    for name in node.names:self.assertIn(name.name.split('.')[0],allowed)
                if isinstance(node,ast.ImportFrom):self.assertIn(node.module.split('.')[0],allowed)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service=build();cls.server=make_server(cls.service,cls.service.gateways,0)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def call(self,path,data=None,headers=None):
        request=Request(self.url+path,data=None if data is None else json.dumps(data).encode(),headers=headers or {'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=5) as r:return r.status,r.read(),r.headers
        except HTTPError as e:return e.code,e.read(),e.headers
    def test_home(self):
        status,body,headers=self.call('/')
        self.assertEqual(status,200);self.assertIn(b'STAGEPASS',body)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_invalid_body(self):
        self.assertEqual(self.call('/api/orders',[])[0],400)
    def test_missing_fields(self):
        self.assertEqual(self.call('/api/orders',{})[0],400)
    def test_unknown_route(self):
        self.assertEqual(self.call('/missing')[0],404)
    def test_cross_origin_rejected(self):
        self.assertEqual(self.call('/api/orders',{}, {'Origin':'https://malicious.example'})[0],403)
    def test_full_http_purchase_webhook_download(self):
        client={'id':'HTTP1','name':'Test','email':'test@example.com','mobile':'3001234567','nationality':'Colombiana'}
        status,body,_=self.call('/api/orders',{'event_id':'neon','seat_ids':['B1','B2'],'client':client,'provider':'pse'})
        self.assertEqual(status,201);order=json.loads(body)
        _,body,_=self.call('/api/demo/payment',{'order_id':order['id'],'status':'approved'});payment=json.loads(body)
        status,body,_=self.call('/api/webhooks/pse',payment['notification']);self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['state'],'Aprobada')
        _,body,_=self.call('/api/orders/'+order['id']);tickets=json.loads(body)['tickets'];self.assertEqual(len(tickets),2)
        status,body,_=self.call('/api/orders/'+order['id']+'/tickets/'+tickets[0]['id']+'/svg')
        self.assertEqual(status,200);ET.fromstring(body)


if __name__ == '__main__':
    unittest.main()
