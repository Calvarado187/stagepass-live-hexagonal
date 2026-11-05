'use strict';
const $ = id => document.getElementById(id);
const money = value => new Intl.NumberFormat('es-CO', {style:'currency', currency:'COP', maximumFractionDigits:2}).format(value);
let events = [], selected = new Set(), eventId = '', order = null, busy = false, quoteVersion = 0;
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo completar la solicitud.');
  return result;
}
function message(text) { $('message').textContent = text; $('message').classList.toggle('visible', !!text); }
function element(tag, text, cls) { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; return node; }
async function showEvents() {
  events = await api('/api/events'); $('events').replaceChildren();
  events.forEach((event, i) => {
    const button = element('button', '', 'event' + (event.id === eventId ? ' active' : ''));
    const art = element('div', '', 'event-art'); art.append(element('span', event.kind.toUpperCase()), element('b', ['///','◒','≈'][i]));
    const copy = element('div', '', 'event-copy');
    copy.append(element('h3', event.name), element('p', new Date(event.starts_at).toLocaleString('es-CO', {dateStyle:'medium',timeStyle:'short'}) + ' · ' + event.state), element('p', 'Elegir asientos ↗', 'event-link'));
    button.append(art, copy); button.disabled = event.state !== 'Programado' || !!order || busy;
    button.addEventListener('click', () => selectEvent(event.id).catch(e => message(e.message))); $('events').append(button);
  });
}
async function selectEvent(id) {
  eventId = id; selected.clear(); $('booking').hidden = false;
  $('event-title').textContent = events.find(e => e.id === id).name;
  await refreshSeats(); await refreshQuote(); await showEvents();
}
async function refreshSeats() {
  const seats = await api('/api/events/' + eventId + '/seats'); $('seats').replaceChildren();
  seats.forEach(seat => {
    if (seat.state !== 'Disponible') selected.delete(seat.id);
    const button = element('button', seat.id, 'seat' + (selected.has(seat.id) ? ' selected' : ''));
    button.type = 'button'; button.disabled = seat.state !== 'Disponible' || busy;
    button.title = seat.location + ' · ' + money(seat.base_price) + ' · ' + seat.state;
    button.setAttribute('aria-pressed', String(selected.has(seat.id)));
    button.addEventListener('click', async () => {
      if (!selected.has(seat.id) && selected.size >= 6) return message('Puedes seleccionar hasta seis entradas.');
      selected.has(seat.id) ? selected.delete(seat.id) : selected.add(seat.id);
      button.classList.toggle('selected', selected.has(seat.id)); button.setAttribute('aria-pressed', String(selected.has(seat.id)));
      await refreshQuote().catch(e => message(e.message));
    }); $('seats').append(button);
  });
}
async function refreshQuote() {
  const version = ++quoteVersion; $('reserve').disabled = true;
  if (!selected.size) { $('quote').replaceChildren(element('p','Selecciona tus asientos para calcular el total.')); return; }
  const quote = await api('/api/quote', {event_id:eventId,seat_ids:[...selected]});
  if (version !== quoteVersion) return;
  $('quote').replaceChildren();
  [['Entradas (' + selected.size + ')',quote.subtotal],['Cargo administrativo',quote.fee],['Descuento','-' + quote.discount],['Total COP',quote.total]].forEach(([label,value],i) => {
    const row = element('p','',i === 3 ? 'total' : ''); row.append(element('span',label),element('span',money(value))); $('quote').append(row);
  }); $('reserve').disabled = busy || !!order;
}
$('form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || order) return; busy = true; $('reserve').disabled = true; message('');
  try {
    const data = Object.fromEntries(new FormData($('form'))); const provider = data.provider; delete data.provider;
    order = await api('/api/orders', {event_id:eventId,seat_ids:[...selected],client:data,provider});
    sessionStorage.setItem('stagepassOrder',order.id); $('booking').hidden = true;
    await refreshOrder(); await showEvents(); $('order-panel').scrollIntoView({behavior:'smooth'});
  } catch(e) { message(e.message); }
  finally { busy = false; if (!order) { await refreshSeats().catch(()=>{}); await refreshQuote().catch(e=>message(e.message)); } }
});
async function refreshOrder() {
  if (!order) return;
  const result = await api('/api/orders/' + order.id); order = result.order;
  $('order-panel').hidden = false; $('booking').hidden = true;
  $('order-info').textContent = order.state + ' · ' + order.seats.map(s=>s.id).join(', ') + ' · ' + money(order.quote.total) + ' · Orden ' + order.id;
  if (order.reconciliation) $('order-info').textContent += ' · Pago tardío: requiere conciliación; no se emitieron entradas.';
  $('payment-controls').hidden = order.state !== 'Pendiente de Pago'; $('tickets').replaceChildren();
  result.tickets.forEach(ticket => {
    const row = element('div','','ticket'); const link = element('a','Descargar ticket SVG ↗');
    link.href = '/api/orders/' + order.id + '/tickets/' + ticket.id + '/svg'; link.download = 'StagePass-' + ticket.claims.seat_id + '.svg';
    const verify = element('button','Verificar firma','secondary');
    verify.addEventListener('click',async()=>{try {const r = await api('/api/orders/' + order.id + '/tickets/' + ticket.id + '/verify');message(r.valid ? 'Firma válida: el ticket conserva su integridad.' : 'Firma inválida.');}catch(e){message(e.message);}});
    row.append(element('strong','Asiento ' + ticket.claims.seat_id),link,verify); $('tickets').append(row);
  }); tick();
}
async function pay(status) {
  if (busy) return; busy = true; $('approve').disabled = $('reject').disabled = $('another').disabled = true; message('');
  try {
    const simulation = await api('/api/demo/payment',{order_id:order.id,status});
    await api('/api/webhooks/' + simulation.provider,simulation.notification); await refreshOrder();
  } catch(e) {message(e.message);} finally {busy = false; $('approve').disabled = $('reject').disabled = $('another').disabled = false;}
}
$('approve').addEventListener('click',()=>pay('approved')); $('reject').addEventListener('click',()=>pay('rejected'));
$('another').addEventListener('click',async()=>{order=null;sessionStorage.removeItem('stagepassOrder');$('order-panel').hidden=true;message('');await selectEvent(eventId || events[0].id).catch(e=>message(e.message));});
function tick() {
  if (!order) return;
  if(order.state !== 'Pendiente de Pago') {$('countdown').textContent=order.state === 'Aprobada' ? '✓ Confirmada' : order.state;return;}
  const seconds = Math.max(0,Math.ceil((new Date(order.expires_at)-Date.now())/1000));
  $('countdown').textContent = String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
}
setInterval(tick,1000); setInterval(()=>{if(order && order.state === 'Pendiente de Pago' && !busy) refreshOrder().catch(e=>message(e.message));},5000);
(async()=>{await showEvents();const id=sessionStorage.getItem('stagepassOrder');if(id){order={id};try{await refreshOrder();eventId=order.event_id;await showEvents();}catch(e){order=null;sessionStorage.removeItem('stagepassOrder');message('La sesión anterior ya no está disponible. Puedes crear una nueva reserva.');}}})().catch(e=>message(e.message));
