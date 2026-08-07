## 1. Migración y esquema

- [x] 1.1 `dining_tables.code` (`String(12)`) en `DiningTableModel`, con índice único `(branch_id, code)` y comentario de por qué es estable y no secreto (design §2)
- [x] 1.2 `orders.diner_name` (`String(60)`, nullable) y `orders.origin` (`String(16)`, no nulo, server default `staff`) en `OrderModel`
- [x] 1.3 Migración `0045_qr_table_ordering.py`: añadir `code` nullable → backfill de las mesas existentes → no-nulo + único, todo en el mismo `upgrade`
- [x] 1.4 Verificar `upgrade` → `downgrade -1` → `upgrade` contra Postgres, con mesas preexistentes en la base

## 2. El código de mesa (aislado y primero: todo lo demás lo usa)

- [x] 2.1 Generador de códigos: 6 caracteres, alfabeto sin `0/O/1/I/L`, determinista de probar (semilla inyectable)
- [x] 2.2 Reintento ante colisión dentro de la sede, acotado; el único constraint de verdad es el índice único
- [x] 2.3 `create_dining_table` acuña el código; `update_dining_table` NO lo toca aunque cambie el `number` (spec: sobrevive a renumerar)
- [x] 2.4 `code` en la entidad `DiningTable`, en los esquemas de respuesta y en el listado
- [x] 2.5 Tests: se acuña al crear, único por sede, sobrevive a renumerar, backfill no deja duplicados

## 3. Comanda con comensal y origen

- [x] 3.1 `diner_name` y `origin` en la entidad `Order` y en `open_order` (validar `origin` contra el conjunto permitido)
- [x] 3.2 Ninguno de los dos es editable después de crear; ningún endpoint de actualización los expone
- [x] 3.3 Esquemas de respuesta de pedido devuelven ambos
- [x] 3.4 Tests: defaults (`null` / `staff`), origen inválido rechazado, pedidos preexistentes leen `staff`

## 4. Ocupar y liberar la mesa (la corrección: va antes de que haya varias comandas)

- [x] 4.1 `_free_table` libera sólo cuando no queda ninguna comanda **abierta** en la mesa; consulta en el repositorio, no en memoria
- [x] 4.2 El mismo criterio en el camino de `cancel_order`
- [x] 4.3 Ocupar sigue en `open_order` y es idempotente: una segunda comanda en una mesa ya ocupada no cambia nada
- [x] 4.4 Tests: última comanda libera, comanda con hermana abierta no libera, cancelar se comporta igual, una mesa sin comandas no se rompe

## 5. Resolución pública de mesa

- [x] 5.1 Puerto y repositorio de storefront: mesa activa por `(tenant, branch_id, code)`
- [x] 5.2 `GET /storefront/{branch_code}/tables/{table_code}`: número, sede y si se puede pedir ahora (caja abierta + horario), reusando lo que ya calcula `/hours`
- [x] 5.3 404 para código desconocido, mesa inactiva o mesa de otra sede — sin caer nunca a otra mesa (design §1)
- [x] 5.4 La resolución no escribe: assert explícito en test de que el estado de la mesa no cambia
- [x] 5.5 Tests: mesa de otra sede rechazada, inactiva rechazada, caja cerrada se reporta sin fallar

## 6. Ingesta pública del pedido de mesa

- [x] 6.1 Comando y esquema: `diner_name` obligatorio, líneas obligatorias, **sin** teléfono ni tipo de entrega
- [x] 6.2 Caso de uso `create_table_order`: valida líneas antes de escribir nada (como `create_order`), abre `dine_in` con mesa, `origin=qr`, sin método de pago y sin cliente
- [x] 6.3 Añade líneas con addons y nota compuesta por el servidor (reusar `_compose_note` y `_resolve_lines`)
- [x] 6.4 Acuña el enlace de edición
- [x] 6.5 **Enruta a cocina en la misma operación**, con el porqué escrito al lado de la llamada (design §5) — es la excepción a «el storefront no enruta»
- [x] 6.6 Caja cerrada: `CashClosedError` sube como conflicto con frase de cara al cliente
- [x] 6.7 Tests: pedido creado + tiquetes existen, `customer_id` nulo, carrito vacío no crea ni pedido ni tiquete, caja cerrada no crea nada, producto no vendible rechazado
- [x] 6.8 Test de la ronda: añadir por el token enruta sólo lo añadido y no duplica los tiquetes anteriores
- [x] 6.9 Test del portón de pago: un pedido sin método pasa `may_cook` (fija por escrito el hecho verificado en design, Context §1)

## 7. Frontend — la pantalla del comensal

- [x] 7.1 Ruta pública `/store/:branchCode/table/:tableCode`, sin guardas de sesión
- [x] 7.2 Servicio y store: resolver mesa, crear pedido de mesa, y de ahí en adelante reusar el store de «mi pedido» por token
- [x] 7.3 Resolución fallida → callejón sin salida que nombra el problema; nunca un menú vacío
- [x] 7.4 Número de mesa siempre visible y sin control para cambiarlo
- [x] 7.5 Nombre de pila antes del carrito, precargado del perfil de invitado y editable
- [x] 7.6 Paso de revisión con líneas, exclusiones y total; «Confirmar» inequívoco y no alcanzable desde el menú por accidente
- [x] 7.7 Tras confirmar, la misma pantalla pasa a ser el pedido del comensal (token), con rondas nuevas desde ahí
- [x] 7.8 Reabrir el QR en el mismo dispositivo con pedido vivo vuelve al pedido, no a un carrito vacío
- [x] 7.9 Negocio que no puede atender: dicho antes del menú, con la hora de apertura cuando ése es el motivo
- [x] 7.10 Tests de componente: mesa visible, sin selector de mesa, no confirma vacío, línea en cocina sin controles

## 8. Frontend — el pase

- [x] 8.1 El tiquete del KDS muestra mesa y comensal cuando el pedido los tiene
- [x] 8.2 Sello mono de «pedido por QR» para `origin=qr`; sin color (el color es del calor y del estado)
- [x] 8.3 Tests: tiquete de mesa con nombre, sello sólo en `qr`, rondas como tiquetes separados con su propia antigüedad

## 9. Cierre

- [x] 9.1 Semillas de demo: mesas con código y un pedido de QR vivo, para que el KDS y el Salón se puedan mirar sin base de producción
- [x] 9.2 `openspec validate qr-table-ordering --strict`
- [x] 9.3 Suites completas de backend y frontend, lint y tipos en los módulos tocados
- [ ] 9.4 Prueba manual: escanear con un teléfono real (no con el emulador del navegador), pedir dos rondas, ver el tiquete en el pase, y comprobar que la mesa queda ocupada y no se libera sola
