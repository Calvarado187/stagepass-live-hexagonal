# Contratos HTTP de la demostración

Base: `http://127.0.0.1:8083`. `Content-Type: application/json` para POST. Importes como cadenas decimales; fechas ISO 8601 UTC. Los errores contienen `{"error":"descripción"}`. Códigos: 200 consulta, 201 reserva, 400 entrada mal formada, 403 origen no permitido, 404 ruta desconocida, 409 regla de negocio/conflicto, 413 cuerpo fuera de tamaño y 500 error no esperado.

## Cotizar

`POST /api/quote`

```json
{"event_id":"neon","seat_ids":["A1","A2","A3"]}
```

Respuesta: `subtotal=450000.00`, `fee=36000.00`, `discount=22500.00`, `total=463500.00`.

## Reservar

`POST /api/orders`

```json
{
  "event_id":"neon",
  "seat_ids":["A1","A2","A3"],
  "provider":"wompi",
  "client":{
    "id":"DEMO-01",
    "name":"Cliente de prueba",
    "email":"demo@example.com",
    "mobile":"3000000000",
    "nationality":"Colombiana"
  }
}
```

Se devuelve la orden con `id`, `payment_id`, `quote`, `created_at`, `expires_at` y estado `Pendiente de Pago`. Guardar el `id` devuelto; no enviar un precio desde el navegador.

## Confirmación asíncrona simulada

1. `POST /api/demo/payment` con `{"order_id":"ID_DEVUELTO","status":"approved"}`. Alternativas: `pending`, `rejected`.
2. La respuesta contiene `provider` y `notification`.
3. Enviar **el objeto notification completo** a `POST /api/webhooks/wompi` (o la pasarela elegida).
4. Consultar `GET /api/orders/ID_DEVUELTO` para obtener los tickets.

Los campos técnicos de referencia son `resource_id` para PayPal, `transaction_id` para Wompi y `cus` para PSE. Todos llevan `signature`. Son contratos ficticios exclusivos de la demo. El adaptador valida la firma y consulta su transacción registrada; el núcleo verifica orden, referencia, pasarela, importe, moneda, estado y vencimiento. Enviar directamente un supuesto estado `approved` a un webhook no autoriza una orden.

## Ticket

Con los identificadores devueltos, consultar `/api/orders/{orden}/tickets/{ticket}/svg` para descargar el gráfico y `/api/orders/{orden}/tickets/{ticket}/verify` para recibir `{"valid":true}`. La verificación usa los datos guardados y su firma; no es un servicio de validación de un archivo arbitrario ni un mecanismo de canje único.

## Límites deliberados

La aplicación escucha solo en loopback, tiene un límite de 16 KiB por solicitud y rechaza orígenes de navegador distintos del servidor. No implementa sesiones autenticadas: los identificadores opacos de orden permiten demostrar consultas, no sustituyen autorización. El endpoint de simulación existe exclusivamente en esta entrega local.
