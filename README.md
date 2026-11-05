# StagePass Live · Taller 13: Arquitectura Hexagonal

Solución académica de reserva y venta de entradas. Incluye núcleo funcional, aplicación web, pruebas y UML editable. Python 3.10 o superior; **sin paquetes externos para ejecutar o probar**.

## Ejecutar

1. Extraer el ZIP completo.
2. Abrir una terminal en la carpeta `StagePassLive`.
3. Ejecutar `python app.py` (Windows: también puede abrir `iniciar.bat`).
4. Abrir **http://127.0.0.1:8083**. Para otro puerto: `python app.py --port 8090`.
5. Elegir evento, asientos y completar datos ficticios; reservar y simular pago aprobado o rechazado. Descargar cada ticket y verificar su firma.

Pruebas: `python -m unittest discover -s tests -v`.

## Qué funciona y qué se simula

| Componente | Estado |
|---|---|
| Entidades, reglas, puertos y casos de uso | Implementados y probados |
| HTTP y pantalla web | Implementados; compra, cotización, webhook y descargas |
| `HmacTicketSigner` | Adaptador completo: firma y verifica HMAC-SHA256 con secreto por evento |
| `SvgTicketRenderer` | Adaptador completo: genera un ticket SVG válido, escapando texto |
| `SystemClock`, `SecureIds`, planificador | Implementados con biblioteca estándar |
| Catálogo MySQL legado | Mock de recintos, eventos y asientos; sin servidor MySQL |
| Persistencia MongoDB | Mock transaccional en memoria; sin servidor MongoDB |
| PayPal / Wompi / PSE | Mocks con registro, firma de notificación y verificación; no son los contratos oficiales ni hacen cobros |
| WhatsApp / SendGrid / DIAN | Mocks idempotentes; guardan resultados en memoria, no envían ni facturan realmente |

**Los datos y secretos son volátiles: se borran al reiniciar.** El enunciado permite mocks para los adaptadores restantes. Esta entrega no pretende implementar conectores comerciales. La API es para una demostración local, sin autenticación; el identificador del cliente se proporciona en el formulario. No publicar este servidor en Internet ni usar datos reales. Una versión productiva requiere identidad autenticada, autorización por orden, almacenamiento duradero, secretos persistentes, transacciones distribuidas, reembolsos y conectores oficiales.

## Reglas y decisiones

- Vigencia: `expires_at = created_at + 10 minutos`; se acepta confirmación verificada solo si se procesa **antes** del vencimiento. En el instante exacto expira. No basta que el proveedor diga que pagó antes si la confirmación llega tarde.
- La disponibilidad se calcula por `(evento, asiento)`, aunque dos eventos compartan recinto. El catálogo legado aporta la descripción y precio; el estado dinámico proviene de las órdenes.
- Se cuentan aprobadas y pendientes no vencidas para el máximo de seis por cliente/evento. Rechazadas y expiradas liberan cupo.
- Cargo y descuento se calculan **ambos sobre el subtotal base**, no uno sobre el resultado del otro. Se redondean a dos decimales, `ROUND_HALF_UP`, usando `Decimal`.
- 1–2: cargo 10%, descuento 0%; 3–5: cargo 8%, descuento 5%; 6: cargo 5%, descuento 10%. Más de seis no es admisible por el límite acumulado.
- Cada operación de inventario es atómica en el mock mediante `RLock`. El proceso admite múltiples solicitudes HTTP, pero no varios procesos compartiendo memoria.
- El planificador revisa vencimientos cada segundo. Las consultas y transacciones también revisan el reloj: un asiento es lógicamente disponible exactamente desde el vencimiento, aunque la limpieza ocurra en el siguiente ciclo.
- Las confirmaciones repetidas no duplican tickets. Los pagos aprobados tardíos dejan `reconciliation=True` sin emitir entradas; la devolución real queda fuera de los mocks.
- Una compra aprobada registra tareas para WhatsApp, correo y factura. Los errores se reintentan; no revocan tickets. La bandeja de salida también es volátil en esta demo.
- El hash autentica datos inmutables de la orden, cliente, evento y asiento, más identificador y código del ticket. No cifra los datos. Verificar integridad no equivale a controlar un canje único: el control de acceso/uso no forma parte del enunciado implementado.

## Organización

```
core/models.py          Entidades y políticas de negocio
core/ports.py           Contratos primarios y secundarios
core/service.py         BookingService: casos de uso
adapters/http.py        Adaptador primario HTTP y webhook
adapters/scheduler.py   Adaptador primario temporal
adapters/storage.py     Mocks MySQL y MongoDB
adapters/payments.py    Mocks de las tres pasarelas
adapters/tickets.py     HMAC y SVG completos
adapters/communications.py  Mocks WhatsApp, SendGrid y DIAN
bootstrap.py           Inyección explícita de dependencias
web/                   HTML, CSS y JavaScript de presentación
tests/                 Reglas, concurrencia, firmas y API
docs/                  Informe, UML y evidencia de validación
```

El núcleo solo importa tipos de la biblioteca estándar y módulos del propio núcleo. Las clases concretas de infraestructura se ensamblan en `bootstrap.py`. `BookingService` implementa el puerto primario; los adaptadores secundarios implementan contratos del núcleo. El formulario no calcula precios ni decide el vencimiento.

## Diagrama UML

Abrir `docs/StagePassLive_UML.drawio` en Draw.io/diagrams.net mediante **Archivo → Abrir desde → Dispositivo**. Contiene vistas detalladas con atributos, métodos, asociaciones, composiciones, dependencias y realizaciones. `StagePassLive_UML.pdf` es la versión vectorial para leer o imprimir. Las clases están nombradas como en el código; el informe incluye equivalencias en español.

## API principal

| Método y ruta | Uso |
|---|---|
| GET `/api/events` | Cartelera con estado actual |
| GET `/api/events/{id}/seats` | Disponibilidad por función |
| POST `/api/quote` | Cotización autoritativa |
| POST `/api/orders` | Crear orden y bloquear asientos |
| GET `/api/orders/{id}` | Orden y tickets emitidos |
| POST `/api/demo/payment` | Solo demo: preparar resultado simulado |
| POST `/api/webhooks/{provider}` | Validar notificación y procesar confirmación |
| GET `/api/orders/{id}/tickets/{ticket}/svg` | Ticket gráfico |
| GET `/api/orders/{id}/tickets/{ticket}/verify` | Verificación de firma |

El documento `docs/API.md` contiene ejemplos reproducibles. `docs/VALIDACION.md` resume las pruebas. El informe explica decisiones, trazabilidad y límites de esta implementación.

## Referencias

- [Enfoque original de puertos y adaptadores, Alistair Cockburn](https://alistair.cockburn.us/hexagonal-architecture/).
- [Biblioteca HMAC de Python](https://docs.python.org/3/library/hmac.html).
- [Formato nativo editable de Draw.io](https://www.drawio.com/docs/manual/editor/save-file-formats/).
- Enunciado suministrado: *13 - Taller Arquitectura Hexagonal*, UNAB, Arquitectura de Software, MSc. Feisar Moreno.
