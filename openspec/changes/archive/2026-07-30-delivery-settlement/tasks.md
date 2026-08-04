## 0. Decisiones resueltas

- [x] 0.1 Verificar un pago requiere `orders.pay` — verificar ES registrar un cobro, solo que
      mirando un comprobante en vez de recibiendo plata
- [x] 0.2 Confirmar/cancelar una devolución requiere `finance.manage` — autorizar una devolución
      es una decisión de plata, no una operación de caja
- [x] 0.3 Un domicilio no entregado **cierra su pedido como write-off**: descuenta inventario
      (la comida se cocinó) y absorbe el impago como pérdida, sin fiárselo al cliente

## 1. Backend — gate de cocina para asignar

- [x] 1.1 `MessagingRepository`-style read: exponer `kitchen_state` del pedido en la lectura de
      entregas (una columna más en el batch que ya toca `orders`, sin estado nuevo en la entrega)
- [x] 1.2 `assign_delivery`: rechazar con conflicto cuando `kitchen_state != ready`, con mensaje
      que diga que la cocina no ha terminado
- [x] 1.3 Incluir `kitchen_state` en `DeliveryResponse` para que Despacho pueda pintar el bloqueo
- [x] 1.4 Tests: asignar `ready` pasa; `in_kitchen` y `none` dan conflicto; efectivo se rechaza
      igual que prepago; la entrega no cambia de estado al ser rechazada

## 2. Backend — "no entregado" desde cualquier estado no terminal

- [x] 2.1 `mark_delivered`: permitir `delivered=False` desde `pending`, `assigned` e `in_transit`;
      mantener `delivered=True` solo desde `in_transit`
- [x] 2.2 Rechazar cualquier transición desde un estado terminal (`delivered`, `not_delivered`)
- [x] 2.3 Tests: resolver un pedido que nunca salió; rechazar marcar entregado antes de partir;
      rechazar re-resolver una entrega terminal

## 3. Backend — verificación de pago como puerta a la cocina

- [x] 3.1 Caso de uso `verify_payment(order_id)`: registra el pago por el saldo pendiente con el
      método del pedido **y** enruta a cocina, en una sola operación atómica
- [x] 3.2 Idempotencia: verificar un pedido ya cubierto no registra un segundo pago, pero sí enruta
- [x] 3.3 `route_order`: rechazar con conflicto si el método no es efectivo y el pago no cubre el
      total. Efectivo enruta sin precondición
- [x] 3.4 Endpoint + permiso (según 0.1)
- [x] 3.5 Tests: verificar paga y enruta; fallo al registrar deja el pedido sin pagar y sin
      enrutar; prepago sin verificar no enruta; efectivo enruta sin pago; verificar dos veces no
      duplica el cobro

## 4. Backend — la entrega cierra la comanda

- [x] 4.1 `mark_delivered(delivered=True)` llama a `close_order` (el mismo use case, no una copia:
      sus invariantes de pago e inventario deben valer igual venga el cierre de donde venga)
- [x] 4.2 Cobro en efectivo: acción única que registra el pago en efectivo y cierra. Si el pago
      falla, no se cierra ni se marca la entrega
- [x] 4.3 Exponer el saldo a cobrar en la lectura del domiciliario (`OrderSummary` ya lleva
      `total`, `paid` y `payment_method`)
- [x] 4.4 `close_order(write_off=True)`: cierra y descuenta inventario **sin** crear
      `customer_credit`. Alcanzable solo desde la ruta de entrega no resuelta — ningún endpoint
      lo expone al cierre ordinario
- [x] 4.5 `mark_delivered(delivered=False)` cierra el pedido en modo write-off
- [x] 4.6 Tests: prepago entregado cierra; efectivo confirma y cierra en un paso; un pedido sin
      pagar ni cliente no cierra por la vía ordinaria y dice qué falta; fallo de pago deja todo
      abierto; sin caja abierta el cobro se rechaza
- [x] 4.7 Tests del write-off: efectivo no entregado cierra **sin** crear `customer_credit`;
      el inventario sí se descuenta; un cierre ordinario impagado con cliente sigue creando
      fiado (la invariante vieja no se relaja); la merma es derivable (cerrado + no entregado +
      total > pagado)

## 5. Backend — devoluciones

- [x] 5.1 Modelo + migración: `order_refunds` (`pending | done | cancelled`), pedido de origen,
      monto, método original, empleado y motivo en cada transición
- [x] 5.2 Entidad de dominio, puerto de repositorio y adaptador
- [x] 5.3 Crear la obligación al marcar `not_delivered` un pedido con pagos; efectivo no genera
      devolución; una sola devolución por pedido
- [x] 5.4 Listar pendientes por sucursal, atravesando cierres de caja
- [x] 5.5 Confirmar: movimiento de caja `out` **con el método original**, jamás efectivo; registra
      autor y momento; confirmar dos veces da conflicto
- [x] 5.6 Cancelar con motivo obligatorio; no crea movimiento
- [x] 5.7 Endpoints + permisos (según 0.2)
- [x] 5.8 Tests: una devolución por transferencia **no altera** `expected_amount` del arqueo;
      efectivo no genera devolución; pendiente sobrevive al cierre de turno; confirmar/cancelar
      registran autor; cancelar sin motivo es 422

## 6. Backend — la caja no cierra con domicilios sin resolver

- [x] 6.1 `close_session`: rechazar con conflicto si hay entregas de la sesión en `pending`,
      `assigned` o `in_transit`, identificándolas en la respuesta
- [x] 6.2 Precisar el conteo pendiente: "sin resolver" = no `delivered` y no `not_delivered`
      (el código ya lo hace así; alinear nombres y el texto del spec)
- [x] 6.3 Sin override: no añadir bypass ni reutilizar `incident` como escape
- [x] 6.4 Pedidos sin cobrar siguen siendo informativos y **no** bloquean
- [x] 6.5 Devoluciones pendientes **no** bloquean
- [x] 6.6 Tests: bloquea con `in_transit`; bloquea con `pending`/`assigned`; `not_delivered` no
      bloquea; resolver la última desbloquea; sin cobrar solo no bloquea; devolución pendiente
      no bloquea

## 7. Frontend — Despacho

- [x] 7.1 Pintar las entregas no listas bloqueadas y visibles, con el motivo explícito
- [x] 7.2 Deshabilitar asignar solo en esas, sin ocultarlas
- [x] 7.3 Que se desbloqueen solas con el doorbell de realtime, sin recargar
- [x] 7.4 Tests: la no lista aparece y no se puede asignar; el motivo es específico, no genérico

## 8. Frontend — Domiciliario

- [x] 8.1 Parada en efectivo: mostrar el monto a cobrar y un botón que confirma plata y entrega
- [x] 8.2 Parada prepagada: solo "entregado", sin pedir dinero
- [x] 8.3 Fallo al confirmar: decirlo y dejar la parada pendiente, nunca como entregada
- [x] 8.4 Tests: efectivo pide monto; prepago no; el fallo no marca entregado

## 9. Frontend — Salón y Caja

- [x] 9.1 Acción de verificar pago: qué revisar y por cuánto; confirma pago + cocina en un paso
- [x] 9.2 Prepago sin verificar no ofrece "enviar a cocina"
- [x] 9.3 El pedido entregado desaparece de la lista de pendientes por cobrar
- [x] 9.4 Cierre de caja bloqueado: listar los domicilios que lo impiden y cómo llegar a ellos;
      **sin** botón de cerrar de todos modos
- [x] 9.5 Panel de devoluciones pendientes: confirmar y cancelar (motivo obligatorio), mostradas
      al cerrar como información sin bloquear
- [x] 9.6 Controles ocultos/deshabilitados sin permiso
- [x] 9.7 Tests: verificar paga y enruta; el cierre bloqueado nombra a los culpables y no ofrece
      override; cancelar sin motivo se rechaza; sin permiso no aparece el control

## 10. Puertas de calidad

- [x] 10.1 Backend: `ruff`, `mypy --strict`, `pytest` completo en verde
- [x] 10.2 Frontend: lint, type-check, unit tests y build de producción en verde
- [x] 10.3 Migración probada up/down contra Postgres real
- [ ] 10.4 Manual, el recorrido completo: pedido por transferencia → verificar → cocina → listo →
      asignar → entregado → cerrado solo; y pedido en efectivo → cocina → listo → asignar →
      cobrar en la puerta → cerrado solo
- [ ] 10.5 Manual, los bordes: intentar asignar sin cocina lista; intentar cerrar caja con un
      domicilio en la calle; no entregar un prepagado y confirmar la devolución verificando que
      el arqueo no se mueve
