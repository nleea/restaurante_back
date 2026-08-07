## Context

El punto de partida es mejor de lo que parece: casi todo esto ya existe y está probado en el camino
de la carta pública.

| Pieza | Dónde | Estado |
|---|---|---|
| Canal `dine_in` | `CHANNELS` en `manage_orders.py` | existe |
| `orders.dining_table_id` + validación de sede | `open_order` | existe |
| Mesas (CRUD, número único por sede) | `order-management` | existe |
| Pedir sin sesión, tenant por subdominio | `storefront` | existe |
| Empleado de sistema | `resolve_system_employee` | existe |
| Enlace propio del pedido | `mint_edit_token` + `/my-order/{token}` | existe |
| Enrutar lo añadido a cocina | `edit_order` → `KitchenRouter` | existe |
| Cookie de invitado | `guest-profile` | existe |
| Portón de caja abierta | `open_order` → `CashClosedError` | existe |

Dos hechos verificados que sostienen el diseño:

1. **`may_cook` deja pasar un pedido sin método de pago.** El adaptador hace
   `(order.payment_method or METHOD_CASH) == METHOD_CASH → True`. Un pedido de mesa que se paga al
   cerrar no elige método al confirmar, y por tanto **no** cae en la regla de «prepago sin
   verificar no llega al fogón». No hay que tocar esa regla ni añadirle una excepción.
2. **`_free_table` libera la mesa sin condición** en `close_order`, y su gemelo en `cancel_order`.
   Con una comanda por mesa era correcto. Este cambio introduce varias, y eso convierte una línea
   correcta en un bug: el primero que paga apaga la mesa para todos.

## Goals / Non-Goals

**Goals:**
- Que alguien sentado en la mesa 5 pida sin que exista un mesero, y que la comida salga a la mesa 5.
- Que varias personas de la misma mesa tengan cada una su comanda, distinguibles por nombre.
- Que confirmar sea del cliente y llegue a cocina en el acto.
- Que la mesa refleje la verdad: ocupada mientras haya comida, libre cuando no quede nadie.

**Non-Goals:**
- Cobrar. Este cambio deja las comandas **abiertas**; las cierra `table-bill-settlement`.
- Imprimir los QR (`table-qr-admin`).
- Factura electrónica. La tirilla es el documento por ahora, y vive en el cambio del cobro.
- Reservas, unir mesas, mover una comanda de mesa. Nada de eso lo pide un local de diez mesas.
- Registrar al comensal como `customers`. Un nombre de pila no es un cliente.

## Decisions

### 1. El QR lleva sede y mesa; el cuerpo del pedido no lleva ninguna de las dos

`https://<tenant>.<dominio>/store/<branch_code>/table/<table_code>`

*Por qué*: es la regla que la carta pública ya defiende explícitamente — «the branch therefore comes
from the URL path and never from the payload… the branch they ordered from is the branch they saw».
Si la mesa viajara en el cuerpo, cualquiera podría pedir a la mesa 5 mientras mira la carta de otra
sede. Con la mesa en la ruta, el pedido no puede contradecir al menú que se vio.

*Alternativa descartada*: un único token opaco que cifre sede+mesa. Más corto de imprimir, pero
ilegible para depurar («¿a qué mesa apunta esta calcomanía?») y obliga a un secreto rotable en algo
que está pegado con adhesivo a una madera.

### 2. El código de mesa es estable y no es un secreto

`dining_tables.code`: 6 caracteres, alfabeto sin ambigüedades (sin `0/O`, `1/I/L`), único por sede,
generado al crear la mesa, inmutable.

*Por qué no rotarlo*: está impreso. Un código que rota exige reimprimir diez calcomanías cada vez, y
un negocio que no reimprime a tiempo se queda sin poder vender en salón. La rotación defiende contra
un ataque —pedir a la mesa 5 desde la calle— que ya está acotado por tres cosas que sí son
dinámicas: la caja tiene que estar abierta, el horario tiene que estar abierto, y la mesa es un
sitio físico donde alguien va a tener que pagar antes de irse.

*Por qué no reusar `number`*: el número es del negocio y lo cambian («ahora la 5 es la 12»).
El código es de la calcomanía y no cambia nunca. Confundirlos hace que renumerar las mesas invalide
el papel pegado.

### 3. El comensal tiene nombre, no cuenta

`orders.diner_name`, nullable, pedido antes del carrito.

*Por qué en la comanda y no en `customers`*: `find_or_create_by_phone` necesita teléfono, y pedir
teléfono para almorzar es fricción que nadie acepta sentado en una mesa. Un nombre de pila no
identifica a nadie y no debe ensuciar la base de clientes, que sostiene fiado, historial y
estadísticas de compra.

*Por qué es necesario y no cosmético*: lo destapó el cobro. Si el cajero parte la cuenta, tiene que
poder señalar la comanda de Luis; tres comandas anónimas en la mesa 5 sólo se distinguen por la
hora. La alternativa —numerarlas `M5-1`, `M5-2`— le pasa el problema al cliente, que tendría que
acordarse de que él era la 2.

*Nullable* porque toda comanda anterior a este cambio, y toda comanda que abra un mesero, no lo
tiene.

### 4. `origin` existe porque `channel` no alcanza

`orders.origin`: `staff` | `web` | `qr`. Default `staff`.

*Por qué*: un `dine_in` abierto por el mesero y uno abierto por QR son hoy idénticos —mismo canal,
mismo empleado de sistema en cuanto el storefront entra en juego—. La cocina quiere el sello para
saber que nadie humano revisó ese pedido; el Salón quiere pintar distinto una mesa que se atiende
sola; y el reporte del mes quiere poder decir cuánto vendió el QR. Es una columna, y las tres
preguntas son imposibles de responder sin ella.

*Por qué un campo y no derivarlo*: derivarlo sería «canal `dine_in` + empleado de sistema», que es
inferencia frágil y se rompe el día que un mesero use el empleado de sistema por cualquier motivo.

### 5. El pedido de mesa SÍ enruta, y esa es la excepción a escribir

El storefront no enruta a propósito. `dine_in` por QR sí.

*Por qué la excepción es legítima*: la razón de no enrutar es que un pedido web lo hace un
desconocido a distancia y el negocio quiere una mirada humana antes de gastar insumos. En la mesa,
el que confirma está sentado en el local. Confirmar es el compromiso, y la revisión que en el web
hace el personal aquí la hace el propio cliente mirando su carrito.

*Por qué queda escrito como requisito y no como un `if`*: es la decisión más consecuente del cambio.
Un `if channel == dine_in: route()` suelto en el caso de uso, sin el porqué al lado, es exactamente
la clase de línea que alguien «arregla» dentro de seis meses por coherencia con el resto.

*Y no choca con el portón de pago*: verificado arriba (Context, hecho 1).

### 6. Una ronda no es una entidad

Cada confirmación enruta lo que haya sin enrutar. Rondas distintas producen tiquetes distintos
porque se crean en momentos distintos, y el KDS ya los ordena por antigüedad.

*Por qué no un `round_number`*: no habría nada que preguntar que el `created_at` del tiquete no
responda ya, y añadir el contador obliga a decidir qué pasa cuando una ronda se cancela entera.
Si algún día la cocina pide ver «ronda 2» literal, se deriva contando enrutamientos distintos del
mismo pedido; no hace falta guardarlo.

*Lo que sí hay que respetar*: `edit_order` ya se niega a cambiar una línea que la estación empezó.
Esa frontera —lo editable contra lo comprometido— es justo lo que el botón «Confirmar» significa
para el cliente, y ya está implementada. Este cambio no la toca.

### 7. Ocupar y liberar la mesa siguen al trabajo, no a la gente

- Escanear no ocupa.
- La mesa pasa a `occupied` cuando se confirma el primer pedido.
- La mesa vuelve a `free` cuando su última comanda abierta se cierra o se cancela.

*Por qué el cambio en liberar es urgente y va en ESTE cambio, no en el del cobro*: el bug lo
introduce esta propuesta, no la siguiente. En cuanto haya dos comandas en una mesa, `_free_table`
miente — y `qr-table-ordering` puede desplegarse solo. Arreglarlo aquí es la diferencia entre un
cambio que se puede soltar y uno que depende de que el siguiente llegue a tiempo.

*Por qué no ocupar al escanear*: alguien que pasa y escanea por curiosidad dejaría la mesa marcada
como ocupada sin nadie sentado, y el salón la retiraría de la oferta. Una mesa se ocupa cuando hay
comida en camino.

## Risks / Trade-offs

- **La cocina queda expuesta.** Sin mirada humana, un pedido falso llega al fogón. Acotado por caja
  abierta + horario + presencia física. Es una decisión tomada a ojos abiertos, no un descuido; si
  hay que poner freno, el sitio es la confirmación.
- **La calcomanía es eterna.** Quien fotografíe el QR puede pedir a esa mesa mientras el local esté
  abierto y la caja abierta. Aceptado por §2.
- **El comensal se equivoca de mesa.** Nada lo impide: escanea la de al lado, la comida sale a la de
  al lado. Es el mismo error que comete un mesero, y se corrige igual: hablando. No se modela.
- **Comandas abiertas durante horas.** Con pago al cerrar, la mesa 5 tiene tres comandas abiertas
  toda la comida. El tablero de caja tiene que poder distinguir «abierta porque están comiendo» de
  «abierta y olvidada»; el sello `origin=qr` más la mesa dan lo necesario para pintarlo.
- **Nombres repetidos.** Dos «Ana» en la mesa 5. El cajero desempata por la etiqueta del pedido
  (`order_label`, que ya existe y ya se usa en chat, mostrador y tiquete). No se inventa nada.

## Migration Plan

`0045_qr_table_ordering.py`:

1. `dining_tables.code` se añade nullable, se backfillea con códigos generados para toda mesa
   existente, y se pasa a no-nulo con índice único `(branch_id, code)` en la misma migración.
2. `orders.diner_name` nullable y `orders.origin` no nulo con server default `staff` — lo anterior
   a este cambio es, por definición, del personal.
3. `downgrade` quita las tres columnas. Verificar `upgrade` → `downgrade -1` → `upgrade` contra
   Postgres, como el resto de migraciones del proyecto.

Sin ventana de incompatibilidad: nada lee las columnas nuevas hasta que el código nuevo está
desplegado, y el código nuevo tolera `diner_name` nulo desde el primer día.

## Open Questions

- ¿El nombre de pila se recuerda entre visitas con la cookie de invitado, o se pregunta cada vez?
  Recordarlo es más amable y la cookie ya existe; pero el celular de Ana se lo puede pasar a Luis
  para que pida, y entonces la comanda de Luis diría «Ana». Propuesta: **precargar y dejar editar**,
  que es como se comporta hoy el checkout con el perfil de invitado. Si se recuerda Ok, si no se pregunta
