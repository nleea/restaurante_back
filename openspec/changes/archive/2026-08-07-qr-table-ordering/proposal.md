## Why

Un restaurante de diez mesas puede no tener meseros. Hoy la única forma de que un plato llegue a
una mesa es que un empleado autenticado abra la comanda desde el Salón: sin esa persona, el salón
no vende. La carta pública ya resuelve pedir sin sesión —menú por sede, empleado de sistema,
enlace propio para corregir— pero sólo sabe de `takeaway` y `delivery`, y el cliente teclea quién
es y a dónde va.

Un QR pegado en la mesa cambia exactamente **tres datos de origen**, y ninguno de ellos es el
mecanismo de pedir:

| | Carta pública hoy | QR en mesa |
|---|---|---|
| negocio | subdominio | subdominio |
| sede | `/{branch_code}` en la URL | **el QR** |
| mesa | no existe | **el QR** |
| quién | nombre + teléfono tecleados | nombre de pila + cookie de invitado |

Lo demás ya está: `dine_in` es canal válido, `orders.dining_table_id` existe, `open_order` ya
valida que la mesa sea de esa sede, y el portón de pago de cocina (`may_cook`) trata un pedido sin
método elegido como efectivo, así que un pedido de mesa puede entrar a cocina sin haber pagado.

Hay una diferencia de fondo con la carta pública, y es deliberada: **el pedido de mesa sí se
enruta a cocina.** El storefront no enruta a propósito («the order lands OPEN and pending for staff
to confirm»), porque un pedido de domicilio lo hace un desconocido a distancia. En la mesa, quien
confirma es alguien sentado en el local, delante del plato que va a pagar. Quien confirma es el
cliente, y confirmar es el compromiso.

## What Changes

- **La mesa tiene código público.** `dining_tables` gana `code`: corto, URL-safe, único en la sede,
  generado al crear la mesa y **estable** —va impreso en una calcomanía y no se puede rotar sin
  volver a imprimir. El QR apunta a `/{branch_code}/table/{table_code}`.
- **Resolución pública de mesa.** `GET /storefront/{branch_code}/tables/{table_code}` devuelve la
  mesa (número, sede, si el local puede recibir pedidos ahora) o 404. La sede sale del QR y **nunca**
  del cuerpo del pedido, igual que en la carta.
- **Ingesta pública de pedido de mesa.**
  `POST /storefront/{branch_code}/tables/{table_code}/orders` abre un `dine_in` sobre el empleado de
  sistema, con `dining_table_id`, sin cliente registrado y sin método de pago —se paga al cerrar—, y
  **enruta a cocina inmediatamente**. Acuña su enlace de edición como todo camino público.
- **El comensal tiene nombre, no cuenta.** `orders.diner_name` nullable: el nombre de pila que se
  pide antes del carrito. No crea `customers`, no pide teléfono. Es lo que la cocina lee en el
  tiquete y lo que el cajero señala para partir la cuenta.
- **De dónde vino el pedido queda dicho.** `orders.origin` (`staff` | `web` | `qr`, por defecto
  `staff`). Hoy «el mesero lo tomó» y «el cliente escaneó» son el mismo `dine_in` sobre el mismo
  empleado de sistema, indistinguibles. El KDS, el Salón y los reportes necesitan distinguirlos.
- **Cada confirmación es una ronda.** El cliente añade desde su enlace y vuelve a confirmar; eso
  enruta lo añadido, que es lo que `edit_order` ya hace. No hay entidad de ronda: rondas distintas
  son tiquetes distintos porque se enrutaron en momentos distintos.
- **La mesa se ocupa cuando hay comida, no cuando hay curiosidad.** Escanear no ocupa nada. La mesa
  pasa a `occupied` al confirmarse el primer pedido.
- **BREAKING (corrección):** cerrar o cancelar una comanda deja de liberar la mesa
  incondicionalmente. La mesa queda `free` sólo cuando no queda ninguna comanda abierta en ella.
  Con una comanda por mesa el comportamiento no cambia; con varias, hoy el primero que paga deja
  la mesa 5 «libre» con tres personas comiendo en ella.

## Capabilities

### New Capabilities
- `qr-table-ordering`: el pedido de mesa por código público — resolución de la mesa, ingesta que sí
  enruta, el comensal con nombre, y la ocupación de la mesa atada a que haya comida.
- `frontend-qr-table-order`: lo que ve el comensal en su celular — la mesa dicha en claro, el
  nombre antes del carrito, revisar y confirmar, y las rondas siguientes desde el mismo enlace.

### Modified Capabilities
- `order-management`: `diner_name` y `origin` en la comanda; la mesa se libera sólo cuando no queda
  ninguna comanda abierta en ella.
- `storefront-public-api`: dos caminos públicos nuevos direccionados por mesa, y la excepción
  explícita a la regla de «no enrutar» para el canal `dine_in`.
- `frontend-kitchen`: el tiquete dice la mesa y el comensal, y marca los de origen `qr`.

## Impact

- **Base de datos** (migración `0045`): `dining_tables.code` (`String(12)`, no nulo, único por
  `(branch_id, code)`), `orders.diner_name` (`String(60)`, nullable), `orders.origin`
  (`String(16)`, no nulo, default `staff`). Backfill de `code` para las mesas existentes.
- **Backend**: `orders` (entidad, `open_order`, `_free_table`), `storefront` (resolución de mesa,
  ingesta `dine_in`), sin tocar `kitchen`.
- **Frontend**: vista nueva de pedido en mesa, ruta pública `/store/:branchCode/table/:tableCode`,
  sello de mesa/comensal en el KDS.
- **Riesgo principal**: entre el celular de cualquiera y la cocina ya no hay nadie. Lo que queda
  protegiendo es la caja abierta, el horario y que la mesa sea un sitio físico. Si algún día hay
  que poner un freno, el sitio es la confirmación, no la ingesta.
- **Fuera de alcance**: imprimir las calcomanías (`table-qr-admin`), cobrar (`table-bill-settlement`)
  y la factura electrónica DIAN (deuda anotada, calendario propio).
