## 1. Migración y esquema

- [x] 1.1 Tabla `table_bills` (`tenant_id`, `branch_id`, `dining_table_id`, `status`, `total`, `opened_by_employee_id`, `created_at`, `closed_at`)
- [x] 1.2 `orders.table_bill_id` nullable + FK `ON DELETE SET NULL`
- [x] 1.3 ~~Índice único parcial~~ → reclamación atómica: la pertenencia es una columna escalar, así que lo que hay que impedir es RECLAMAR una comanda ya tomada. Se hace con UPDATE condicional + recuento de filas (design §4, corregido al implementar)
- [x] 1.4 `receipt_prints.table_bill_id` nullable + FK; `receipt_prints.order_id` pasa a nullable; CHECK `(order_id IS NULL) <> (table_bill_id IS NULL)`
- [x] 1.5 Migración `0046_table_bills.py`; verificar `upgrade` → `downgrade -1` → `upgrade` contra Postgres con impresiones preexistentes

## 2. La cuenta (agrupar, antes de tocar dinero)

- [x] 2.1 Entidad `TableBill` y puertos de repositorio
- [x] 2.2 `open_table_bill`: miembros por defecto = todas las comandas abiertas de la mesa; validar misma mesa, misma sede, todas `open`
- [x] 2.3 Rechazar una comanda que ya está en otra cuenta abierta (conflicto legible, con el índice único detrás)
- [x] 2.4 `dissolve_table_bill`: suelta los miembros intactos, sin pagos
- [x] 2.5 La cuenta NO congela importe; el total se calcula al cobrar (design §1)
- [x] 2.6 Tests: mesas mezcladas rechazadas, comanda cerrada rechazada, doble cuenta rechazada, disolver no deja rastro

## 3. Reparto en cascada (la parte peligrosa)

- [x] 3.1 Función pura del reparto: dados (miembros ordenados, pagos) → asignaciones. Sin base de datos, testeable a mano
- [x] 3.2 Orden determinista: `created_at`, `id` para desempatar (design §2 — sin esto los tests son inestables)
- [x] 3.3 Tests de la función pura: un pago cubre todo, dos métodos con una comanda a caballo, pago parcial, sobrepago, un solo miembro, importes con decimales
- [x] 3.4 `charge_table_bill` escribe cada asignación por el camino de pago existente (pago + movimiento de caja atómicos), sin duplicar esa lógica
- [x] 3.5 Exige sesión de caja abierta reusando la regla existente; sin sesión no escribe nada
- [x] 3.6 Pago parcial deja la cuenta abierta y no cierra nada

## 4. Cierre en cascada

- [x] 4.1 Cubierta la cuenta: cerrar todos los miembros por `close_order` **sin tocarlo** — cada comanda llega genuinamente pagada (design §1)
- [x] 4.2 Reparto + cierre en UNA transacción
- [x] 4.3 Test del fallo a mitad: forzar un error después de cubrir la primera comanda y comprobar que no sobrevive ningún pago, movimiento ni cierre
- [x] 4.4 Marcar la cuenta `settled`
- [x] 4.5 Tests: la mesa se libera cuando la cuenta llevaba las últimas comandas; sigue ocupada si queda otra; inventario descontado una sola vez por comanda
- [x] 4.6 Rechazar `settle` con remanente: error que nombra lo que falta y no cierra nada (design §5)

## 5. API

- [x] 5.1 `POST /orders/table-bills` (abrir), `DELETE /orders/table-bills/{id}` (disolver)
- [x] 5.2 `POST /orders/table-bills/{id}/payments` (cobrar), `GET /orders/table-bills/{id}` (estado y miembros con sus totales)
- [x] 5.3 `POST /orders/table-bills/{id}/receipts` (registrar impresión)
- [x] 5.4 Gates RBAC: los mismos permisos que cobrar y cerrar una comanda; ningún permiso nuevo (evita el 403 universal de un permiso sin sembrar)
- [x] 5.5 Tests de API: 403 sin permiso, 409 en conflicto, 422 en remanente

## 6. Impresión

- [x] 6.1 `record_receipt_print` acepta comanda **o** cuenta, exactamente una; validado en el caso de uso además del CHECK
- [x] 6.2 Una impresión de cuenta NO marca las comandas miembro (design §6)
- [x] 6.3 Lectura para la tirilla: negocio (nombre, NIT, dirección), sede, mesa, cajero, miembros por comensal con etiqueta y líneas, totales, métodos usados
- [x] 6.4 Tests: primera vs reimpresión de cuenta, impresión de comanda posterior sigue siendo primera, referencia doble o nula rechazada

## 7. Frontend — Caja

- [x] 7.1 Servicio y store de cuentas de mesa
- [x] 7.2 Panel de mesas ocupadas con comensales y suma corriente
- [x] 7.3 Abrir una mesa preselecciona todos sus pedidos, agrupados por comensal con etiqueta, líneas y total
- [x] 7.4 Deseleccionar miembros recalcula el total; con cero seleccionados el cobro se deshabilita
- [x] 7.5 Varios pagos de distinto método con el restante siempre a la vista
- [x] 7.6 Al liquidar, decir qué comandas se cerraron y ofrecer la tirilla
- [x] 7.7 Fiado: el panel explica que hay que sacar al comensal y cobrarlo aparte, **antes** de que el cajero reciba dinero
- [ ] 7.8 El feed de movimientos presenta como un solo cobro los movimientos de una misma cuenta
- [x] 7.9 Tests de componente: preselección, deselección, cero seleccionados, restante tras pago parcial

## 8. Frontend — tirilla y Salón

- [x] 8.1 Plantilla imprimible (CSS de impresión, como el Reporte Z) con todo lo de 6.3
- [x] 8.2 Frase visible de que **no es una factura electrónica** (design §6)
- [x] 8.3 Reimpresión registrada como tal
- [ ] 8.4 Tarjeta de mesa del Salón: cuántas comandas, quiénes y cuánto suman
- [x] 8.5 Acción «cobrar» desde la tarjeta que lleva a Caja con la mesa preseleccionada; oculta sin permiso
- [ ] 8.6 Tests: tarjeta con tres comensales, mesa libre sin total, acción ausente sin permiso

## 9. Cierre

- [x] 9.1 `openspec validate table-bill-settlement --strict`
- [x] 9.2 Suites completas de backend y frontend, lint y tipos en los módulos tocados
- [ ] 9.3 Prueba manual del camino completo: tres comensales por QR en la mesa 5, cobrar junto, imprimir; repetir separando a uno; comprobar el arqueo y el Reporte Z del turno
- [ ] 9.4 Prueba manual del caso feo: cobrar mientras un comensal añade una ronda
