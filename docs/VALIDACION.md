# Validación de StagePass Live

Entorno de comprobación: Windows, Python 3.10. Comando: `python -m unittest discover -s tests -v`. Resultado: **64 pruebas aprobadas**. El registro completo se entrega en `pruebas.txt`.

| Área | Evidencia |
|---|---|
| Tarifas | Cantidades 1, 2, 3, 5 y 6; precios mixtos y redondeo monetario |
| Entradas inválidas | Cero, siete, duplicados, asiento/evento/pasarela inexistente, cliente inválido |
| Inventario | Asiento bloqueado, funciones distintas en el mismo recinto, evento agotado |
| Límite acumulado | Aprobadas y pendientes, seis exactas, cupo recuperado al rechazar o expirar |
| Tiempo | Diez minutos exactos, 599.999999 segundos y frontera de 600 segundos |
| Pagos | Tres pasarelas, firma falsa, moneda/importe/referencia/proveedor incorrectos, pendientes y rechazos |
| Reintentos | Notificación repetida sin tickets duplicados; registro idempotente |
| Pago tardío | Conciliación sin ticket ni apropiación de un asiento vuelto a reservar |
| Ticket | Firma válida, datos alterados, secreto incorrecto, secreto débil, XML SVG y escape de contenido |
| Efectos secundarios | WhatsApp/correo/factura una sola vez; fallos y reintentos sin revocar compra |
| Atomicidad | Fallo al firmar el segundo ticket revierte toda la emisión |
| Concurrencia | Veinte intentos por el mismo asiento: un ganador; ocho reservas simultáneas por cliente: máximo seis |
| Dependencias | Inspección AST de todos los imports del núcleo |
| HTTP | Página inicial, JSON inválido, campos faltantes, ruta desconocida, origen ajeno y compra completa |

También se revisaron en el navegador: cartelera, selección de tres asientos, total de COP 463.500, reserva con contador 10:00, aprobación simulada, tres enlaces de descarga y mensaje de firma válida. `StagePassLive_Vista.jpg` muestra la orden confirmada.

Estas pruebas respaldan los escenarios descritos; no equivalen a una auditoría productiva ni prueban conexiones a servicios comerciales. Las bases de datos y proveedores externos son mocks declarados.
