## Context

Esto empezó como "hay que meter caché" y acabó siendo un problema de dinero. Conviene que quede el
camino, porque la conclusión sólo es convincente con él:

```
síntoma          /floor tarda 3 s en pintar las mesas
primera lectura  N+1 en SQL en los endpoints de menú
comprobado       NO hay N+1 en SQL. Los cinco son una consulta limpia cada uno, y
                 `list_items` hasta lleva un comentario de quien ya lo pensó:
                 "One grouped query over the order's item ids, not N+1"
segunda lectura  el N+1 es del CLIENTE: ~60 peticiones por entrada
por qué          el navegador necesita el menú entero para calcular el precio de una línea
por qué eso      `add_item` acepta `unit_price` de quien llama y no lo valida
```

O sea: la lentitud es un síntoma, y la enfermedad es que la responsabilidad del precio está en el
sitio equivocado. Arreglar la enfermedad cura el síntoma; cachear el síntoma deja la enfermedad.

Lo que ya existe y en lo que esto se apoya:

- **`storefront/edit_order.py:316`** — el principio, escrito y defendido: *"El precio nunca viene del
  cliente: `add_item` lo recibe de quien llama, así que quien llama tiene que ser quien lo busca."*
  Este change lo lleva un paso más allá: que no lo busque *quien llama* sino `add_item` mismo, para
  que no haya tres "quien llama" con tres fórmulas.
- **`repo.product_price(tenant, product_id, branch_id)`** — el precio de sede, ya escrito, en el
  repositorio del storefront.
- **`repo.extra_price_of(tenant, variant_id)`** — el recargo, ya escrito, en el repositorio de `menu`.
  Y aquí una precisión que hay que tener antes de implementar: **`extra_price` NO es una columna de
  `product_variants`** (sus columnas son `id, product_id, name, is_active, tenant_id`). Es la suma de
  `variant_options.extra_price` de las opciones que la variante compone vía
  `product_variant_options`, y el API la expone como campo derivado. Así que el segundo término del
  precio es una agregación, no una lectura — dos ingredientes que ya existen, en dos módulos
  distintos.
- **`messaging.order_lines`** — el join `OrderItem → ProductVariant → Product` para nombrar una línea,
  en **una** consulta. Existe porque WhatsApp necesitaba contarle al cliente qué pidió; el Salón es el
  único consumidor que lo resuelve en el navegador.
- **`order_items.unit_price`** — la columna ya existe y se estampa por fila. El modelo era correcto
  desde el principio: una comanda de ayer conserva el precio de ayer. Sólo estaba mal el origen del
  número.
- **La red de seguridad de la receta** en `add_item` (`variant_has_recipe` → *"no descontaría
  inventario"*). Es la forma exacta que copia el rechazo por falta de precio.

## Goals / Non-Goals

**Goals**

- Que el precio de una línea se calcule en **un** sitio, en el servidor.
- Que abrir una comanda no cueste bajarse el menú.
- Que el Salón recupere el rollup de cocina que perdió como parche de rendimiento.
- Que un producto sin precio en la sede no se pueda vender, en vez de venderse a cero.
- Que los tres canales cobren lo mismo por el mismo plato.

**Non-Goals**

- **Caché.** Ni Redis, ni HTTP, ni Pinia. Ver decisión 6: sobra cuando las peticiones bajan de 60 a 4,
  y su coste (claves multi-tenant, invalidación cruzada entre módulos) no se paga por gusto.
- **Anulación manual del precio / descuentos por línea.** No existe hoy y este change no la inventa.
  Cuando haga falta se añade explícita, encima de un precio que el servidor ya sabe calcular — que es
  precisamente lo que hoy no se puede hacer.
- **Tocar el descuento de la comanda entera.** `Order totals and discount` se queda como está: opera
  sobre el total, no sobre la línea.
- Arreglar `CACHE_BACKEND: memory` con dos réplicas. Es real, es grave y es otro change.
- Optimizar los endpoints de menú. No hay nada que optimizar: ya son una consulta cada uno. Lo que
  cambia es cuántas veces se llaman.
- Recalcular precios de ítems ya escritos. Jamás: eso cambiaría cuentas cerradas.

## Decisiones

### 1. El precio se resuelve DENTRO de `add_item`, no en quien llama

El principio del storefront dice "quien llama tiene que ser quien lo busca". Eso ya era mejor que
recibirlo del cliente, pero produjo el problema que tenemos: **tres "quien llama" con tres fórmulas
distintas**, y la tabla del proposal lo prueba. Si `add_item` es el único que puede escribir una línea,
es el único sitio donde el precio no puede divergir.

```
antes                                   después
┌──────────┐                            ┌──────────┐
│ salón    │─ unit_price ──┐            │ salón    │──┐
├──────────┤               │            ├──────────┤  │
│ store    │─ lo busca ────┼─▶ add_item │ store    │──┼─▶ add_item ─▶ resolve_line_price()
├──────────┤               │  (lo cree) ├──────────┤  │              (product_price + extra)
│ edición  │─ lo busca ────┘            │ edición  │──┘
└──────────┘                            └──────────┘
  3 fórmulas                              1 fórmula
```

**Rechazado: un servicio de precios aparte que todos consulten.** Deja la puerta de `add_item`
abierta, así que el cuarto camino que aparezca podrá volver a pasar un número. Que el parámetro **no
exista** es lo que hace que la invariante no dependa de disciplina — el mismo razonamiento que sostiene
`GuardedWhatsAppGateway`.

### 2. La fórmula es la del salón, no la del storefront

`precio_sede + recargo_de_la_variante`, donde el recargo es la suma de las opciones que compone (ver
Context: no es una columna). El storefront hoy no suma el recargo, y eso significa que este change
**cambia lo que cobra el canal público** cuando la variante tenga recargo.

Medido antes de escribir esto: **ninguna variante activa tiene recargo hoy** (0 de 36, los tres
tenants). Así que las dos fórmulas dan el mismo número y este cambio es invisible — lo cual lo
convierte en el mejor momento para unificarlas, no en una razón para no hacerlo.

Se elige la del salón por dos razones. La primera es que es la semántica real: `extra_price` existe
para cobrarse; una variante "grande" que no cobra su recargo es una columna decorativa. La segunda es
que el salón es el canal donde alguien mira el número — si las dos difieren, la que está mal es la que
nadie está viendo.

Hoy el cambio es inocuo (`StorefrontMenuResponse` no expone variantes, así que `extra_price` siempre es
0 por ese lado) y queda escrito para que el día que la carta pública muestre variantes no parezca una
regresión.

### 3. Sin precio en la sede, se rechaza. No se vende a cero.

Hoy, tres sitios distintos convierten "no hay precio" en "vale cero":

```python
unit = unit if unit is not None else Decimal(0)      # edit_order.py:410 y :442
```
```ts
const unitPrice = (info?.unitPrice ?? 0).toFixed(2)  # stores/orders.ts:218
```

Un `?? 0` en el camino del dinero es un regalo silencioso. Y la forma correcta ya existe al lado, en la
misma función: `add_item` rechaza una variante sin receta porque *"no descontaría inventario"*. Esto es
lo mismo un renglón más abajo — una red de seguridad en el límite de la venta, con un mensaje que dice
qué falta y dónde.

**Consecuencia que hay que mirar antes de desplegar**: si hoy existen ventas a cero por esta causa,
mañana esas ventas fallan. No es un fallo del change: es el change negándose a hacer lo que estaba mal.

Medido (grupo 0, base de desarrollo): **0 líneas a cero de 245** escritas entre el 2026-06-30 y el
2026-08-09, y **0 variantes vendibles sin precio** en las sedes que existen de verdad. El agujero
estaba abierto y nadie se cayó por él — porque `OrderDetailView` siempre construye el índice antes de
dejar añadir, que es exactamente la muleta que este change retira. Cerrarlo ahora no rompe ninguna
venta existente.

Queda un aviso que no se puede resolver desde aquí: eso se midió en la base **local**. Si hay una de
producción aparte, la cuenta de "vendibles sin precio" hay que repetirla allí antes de desplegar. Es
la única de las tres que puede tumbar ventas.

### 4. La línea trae su etiqueta; el cliente no reconstruye el menú

El otro motivo por el que el navegador baja el menú es para traducir `product_variant_id` en "Bandeja
paisa · Estándar". El servidor ya sabe hacerlo y ya lo hace: `messaging.order_lines` es exactamente ese
join, en una consulta, escrito para que WhatsApp pudiera contarle al cliente qué pidió.

Así que el ítem leído lleva `product_name` y `variant_name`. Es dato **derivado** dentro de la
respuesta, no una columna: no se desnormaliza en la base, se resuelve al leer. Con eso:

- renombrar un producto cambia lo que dice una comanda viva, que es lo que se quiere;
- no hay una segunda copia del nombre que pueda quedarse vieja;
- y el KDS y la comanda dejan de necesitar el menú para pintar una línea.

**Rechazado: guardar el nombre en `order_items`.** Sería la tercera copia de un dato que ya tiene
dueño, y el argumento de "así queda el histórico" no aplica: el histórico del dinero es `unit_price`,
que sí se estampa. El nombre no es dinero.

### 5. `include=items` en la lista, y no un endpoint nuevo del Salón

Dos formas de matar las 12 peticiones de `fetchItems`:

| opción | a favor | en contra |
|---|---|---|
| `GET /orders?include=items` | un parámetro, sirve a KDS y Salón, no cambia el payload de quien no lo pide | un `include` es una puerta que luego crece |
| `GET /orders/floor?branch_id=X` | payload hecho a medida de una pantalla | una pantalla nueva = un endpoint nuevo; el backend acaba conociendo el frontend |

Se elige `include=items`. La segunda opción es tentadora porque el Salón necesita mesas + comandas +
ítems de una vez, pero un endpoint por pantalla es cómo el API acaba teniendo `/orders/floor`,
`/orders/kds`, `/orders/dispatch` con tres formas del mismo pedido. El `include` se acota a lo que hay:
**una sola clave, `items`, y nada más** — el día que alguien quiera `include=payments,delivery,items`
es el día de discutirlo, no hoy.

### 6. Nada de caché, y merece explicarse porque era la petición original

```
con caché (Redis)     60 peticiones · ~9 rondas · cada respuesta 2 ms en vez de 15 ms
                      → sigue tardando, y el precio sigue siendo del cliente

este change            4 peticiones · 1 ronda
                      → y el precio deja de ser del cliente
```

El coste dominante son los **viajes de ida y vuelta**, no las consultas. Una caché los hace más
baratos y no los reduce; y a cambio trae lo caro: claves con `tenant_id` (una clave sin él es una fuga
de datos entre negocios), invalidación cruzada entre módulos (una compra cambia el coste; una receta
cambia si una variante es vendible), y la ventana de datos viejos.

Y hay un aviso que no es teórico: **hoy `k8s/backend.yaml` corre `replicas: 2` con
`CACHE_BACKEND: "memory"`.** `RbacPermissionCache` depende de invalidación explícita y con dos procesos
esa invalidación llega a uno solo — quitarle un permiso a alguien funciona *a veces* durante 300
segundos. Cualquier caché nueva hereda eso. Arreglarlo es otro change y va antes que cachear nada.

### 7. Qué NO se toca del frontend, y por qué importa

`FloorView.vue:64-72` tiene `loadKitchen` comentado, y `stores/orders.ts:160` tiene
`buildVariantIndex` comentado dentro de `ensureLoaded`. Es un parche de rendimiento con un precio que
no se ve: el Salón perdió el rollup de cocina (las tarjetas degradan a ocupada/total).

Este change **descomenta**, no borra. Es la señal de que el problema se arregló en vez de esconderse:
si al final `loadKitchen` sigue comentado, el change no ha terminado.

Y una trampa que hay que conocer: `buildVariantIndex` **no** se puede quitar sin más, porque
`OrderDetailView.vue:88` lo llama y sin él `addItem` mandaría `unit_price = "0.00"`. El orden importa —
primero el servidor calcula el precio, después se borra el índice. Al revés, hay una ventana en la que
se factura a cero.

## Riesgos / Trade-offs

- **Es el camino del dinero.** Un error aquí no es una pantalla lenta, es una cuenta mal cobrada. De
  ahí que el cálculo esté en un sitio con pruebas propias y que el grupo 0 sea contar datos.
- **El canal público empieza a cobrar `extra_price`.** Correcto y deseado, invisible hoy, y un cambio
  de comportamiento que hay que tener escrito antes de que alguien lo lea como un bug.
- **Rechazar en vez de regalar rompe ventas que hoy pasan.** A propósito. El grupo 0 mide cuántas.
- **`include=items` es una puerta.** Se acota a una clave y se dice por qué en el spec; el siguiente
  que quiera añadir otra tendrá que argumentarlo.
- **El orden de los pasos no es negociable** (decisión 7): borrar `buildVariantIndex` antes de que el
  servidor calcule el precio factura a cero.

## Migration Plan

- **Sin migración.** `order_items.unit_price` ya existe y ya se estampa por fila. No hay columna nueva,
  no hay dato que rellenar, no hay `0048`.
- **Los ítems existentes no se tocan.** Conservan el precio con el que se escribieron, que es la
  propiedad que hace correcta una cuenta de ayer.
- **Orden de despliegue**: backend primero, frontend después. El backend acepta el `unit_price` viejo
  como campo ignorado durante una versión, así que un frontend antiguo contra un backend nuevo sigue
  funcionando —y empieza a cobrar bien—. Al revés no: un frontend que ya no manda precio contra un
  backend viejo escribiría ceros. **Esa ventana es la única forma de romper esto, y se evita con el
  orden.**
- **Rollback**: volver el backend deja al frontend nuevo mandando dos campos a un endpoint que espera
  tres. Si hay que revertir, se revierten los dos.

## Preguntas abiertas (no bloqueantes)

- **¿`extra_price` de las adiciones (`addons`) sigue como está?** Hoy el storefront las cotiza aparte
  (`addon_price`) y el salón tiene su propio camino. Este change no las toca, pero huele al mismo
  problema una capa más abajo y probablemente merezca la misma cirugía después.
- **¿El rechazo por falta de precio debería avisar en la pantalla de menú?** Un producto sin precio en
  una sede es un error de configuración que hoy no se ve hasta que alguien intenta venderlo. Un aviso
  en `/menu` sería el sitio, y es otro change.
- **¿Cuánto baja de verdad?** La estimación de 60 → 4 sale de contar llamadas, no de medir. El grupo 8
  la mide con el panel de Red antes y después, porque una cifra dicha sin medir es una conjetura con
  cara de dato.
