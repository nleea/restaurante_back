## Why

`qr-table-ordering` pone varias comandas vivas en una misma mesa: una por comensal, cada una con su
nombre. Falta cobrarlas, y ahí el sistema de hoy sólo sabe hacer una cosa: cobrar **una** comanda.
`OrderPayment` cuelga de un `order_id` y `close_order` exige que los pagos de *esa* comanda cubran
*su* total. «Todo junto» —que es lo que pasa en la práctica en casi todas las mesas— no tiene dónde
vivir.

El problema no es de dinero, es de **gesto**. La plata que entra es la misma; lo que falta es que un
cajero pueda decir «la mesa 5 completa» una sola vez, y «Luis paga lo suyo» cuando toca. Hoy tendría
que cobrar y cerrar tres comandas a mano, sumando de cabeza, con el riesgo obvio de dejar una
abierta.

Y falta el papel. Lo único que existe es `receipt_prints`, que es una **auditoría de impresiones**
—quién imprimió y si fue reimpresión—, no un documento. Nadie puede entregarle nada al cliente.

## What Changes

- **La cuenta de mesa.** `table_bills`: agrupa una o más comandas **abiertas de la misma mesa** para
  cobrarlas en un gesto. `orders.table_bill_id` nullable — una comanda pertenece como mucho a una
  cuenta abierta.
- **Junto por defecto, separado a un toque.** Abrir la cuenta de una mesa toma por defecto **todas**
  sus comandas abiertas; el cajero puede quitar las que no van. Separar no es otro mecanismo: es la
  misma cuenta con menos miembros. Pagar solo es una cuenta de uno.
- **Cobrar la cuenta reparte en cascada.** Un pago sobre la cuenta se reparte a las comandas
  miembro por orden de antigüedad, llenando cada una hasta su total antes de pasar a la siguiente, y
  escribe `order_payments` y movimientos de caja reales. Cubierta la cuenta, sus comandas se cierran
  en cascada. **`close_order` no se toca**: cada comanda llega al cierre genuinamente pagada.
- **La tirilla.** `POST /table-bills/{id}/receipts` registra la impresión de la cuenta;
  `receipt_prints` gana `table_bill_id` y `order_id` pasa a nullable, con exactamente uno de los dos
  presente. La tirilla lleva los datos del negocio (nombre, NIT, dirección, sede), la mesa, la fecha,
  el cajero, cada comanda agrupada por comensal con su etiqueta, los totales y los métodos de pago —
  y dice explícitamente que **no es una factura electrónica**. Un papel que se parece a una factura
  sin serlo es peor que un papel que dice lo que es.
- **Fiado queda fuera del grupo.** Una cuenta se cobra completa o no se cobra. El comensal que va a
  fiado se saca de la cuenta y se cierra por el camino de siempre, que ya sabe asignar cliente y
  registrar el crédito.
- **La mesa se libera sola.** Ya no hay nada que hacer aquí: `qr-table-ordering` dejó la mesa atada a
  que no quede ninguna comanda abierta, y el cierre en cascada la apaga en la última.

## Capabilities

### New Capabilities
- `table-bill-settlement`: la cuenta de mesa — agrupar comandas abiertas de una mesa, cobrarlas en un
  gesto con reparto en cascada, cerrarlas juntas, y la tirilla del grupo.

### Modified Capabilities
- `order-management`: una impresión de recibo puede referirse a una cuenta de mesa en vez de a una
  comanda suelta.
- `frontend-cash`: cobrar una mesa desde la Caja — ver sus comandas por comensal, quitar las que no
  van, cobrar en uno o varios métodos, e imprimir.
- `frontend-salon`: la mesa muestra cuántas comandas vive y cuánto suma, y desde ahí se va a cobrar.

## Impact

- **Base de datos** (migración `0046`): tabla `table_bills` (`tenant_id`, `branch_id`,
  `dining_table_id`, `status`, `total`, `opened_by_employee_id`, `created_at`, `closed_at`);
  `orders.table_bill_id` (nullable, FK, `ON DELETE SET NULL`, índice parcial de unicidad para que
  una comanda no esté en dos cuentas abiertas); `receipt_prints.table_bill_id` (nullable, FK) y
  `receipt_prints.order_id` pasa a nullable con CHECK de exclusividad.
- **Backend**: `orders` (entidad de cuenta, reparto, cierre en cascada, impresión), sin tocar
  `cash` —los movimientos se siguen creando por el camino de pago existente.
- **Frontend**: panel de cobro de mesa en Caja, resumen de mesa en Salón, plantilla imprimible.
- **Depende de**: `qr-table-ordering` (varias comandas por mesa y la liberación condicional de la
  mesa). Se puede implementar en paralelo, pero no tiene sentido desplegarlo antes.
- **Riesgo principal**: el reparto toca dinero. Un reparto que se equivoque deja una comanda cerrada
  sin cubrir o cobra dos veces. Es atómico o no es.
- **Fuera de alcance**: factura electrónica DIAN (documento equivalente POS, CUFE, resolución de
  numeración) — deuda anotada con calendario propio. Dividir un plato entre dos comensales
  («partir la milanesa»): no se modela; quien la pidió la paga.
