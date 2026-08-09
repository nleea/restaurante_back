## Why

Abrir el Salón tarda hasta tres segundos, y abrir una comanda paga lo mismo. La causa no es el
tiempo de Postgres: **el navegador se baja el menú entero antes de poder trabajar**, y lo hace porque
se le ha dado la responsabilidad de calcular el precio de una línea.

El rastro completo, con las cifras de un tenant de 40 productos y 12 comandas abiertas:

```
buildVariantIndex(branchId)                       stores/orders.ts:136
├─ menu.fetchProducts()                            1   ← barrera
├─ menu.loadPrices(branchId)                       1   ← barrera
└─ products.map(p => loadVariants(p.id))          40   ← UNA POR PRODUCTO
                                                  ↓
   index[variant.id] = { productName, variantName,
                         unitPrice: base + variant.extra_price }

buildItemIndex(branchId)                          stores/kitchen.ts:373
├─ orders.loadOrders()                             1   ← REPETIDA (ensureLoaded ya la hizo)
├─ orders.loadTables()                             1   ← REPETIDA
└─ orders.map(o => fetchItems(o.id))              12   ← UNA POR COMANDA
                                                 ───
                                        ~60 peticiones · ~7 barreras secuenciales
```

Y para qué: para poder hacer esto al añadir un plato (`stores/orders.ts:216`):

```ts
const info = this.variantIndex[variantId]
const unitPrice = (info?.unitPrice ?? 0).toFixed(2)
await api.addItem(orderId, { product_variant_id, quantity, unit_price: unitPrice })
```

**El cliente calcula el dinero y el servidor se lo cree.** `add_item`
(`manage_orders.py:658`) valida tres cosas —que la variante exista, que tenga receta, que la cantidad
sea positiva— y del precio no comprueba nada: lo escribe en `unit_price`, lo multiplica en
`line_subtotal`, y de ahí va al total, al cierre y a caja.

Dos cosas hacen que esto no sea una discusión de opiniones:

**1. Este repo ya decidió lo contrario, por escrito.** La carta pública hace exactamente lo correcto,
y lo defiende en un comentario (`storefront/edit_order.py:316`):

> *"Se resuelve TODO contra el catálogo antes de escribir nada. El precio nunca viene del cliente:
> `add_item` lo recibe de quien llama, así que quien llama tiene que ser quien lo busca."*

Alguien pensó esto para el camino anónimo, donde salta a la vista. El camino del personal nunca
recibió el mismo trato. No proponemos una idea nueva: proponemos aplicar la que ya está escrita.

**2. El mismo plato se cobra distinto según el canal.**

| camino | fórmula | dónde |
|---|---|---|
| Salón (navegador) | `precio_sede + variant.extra_price` | `stores/orders.ts:148` |
| Carta pública (servidor) | `product_price`, **sin** `extra_price` | `edit_order.py:410` |
| `add_item` (servidor) | lo que le llegue | `manage_orders.py:686` |

**Y aquí hay que ser exacto, porque medirlo cambió la fuerza del argumento** (grupo 0, base de
desarrollo, 2026-08-09):

| cuenta | resultado |
|---|---|
| variantes activas con `extra_price > 0` | **0 de 36**, en los tres tenants |
| líneas ya escritas a `unit_price = 0` | **0 de 245**, desde 2026-06-30 |
| variantes vendibles sin precio en una sede real | **0** |

Las tres divergencias son **reales en el código y ninguna ha cobrado mal a nadie**. `extra_price` es 0
en todas las variantes, así que `base + extra_price` y `base` dan hoy el mismo número; el menú público
además no expone variantes. El `?? 0` nunca se disparó porque `OrderDetailView` siempre construye el
índice antes de dejar añadir.

Eso **rebaja** la justificación y conviene decirlo así en vez de dejar el susto puesto: esto no apaga
un incendio. Es un cambio de rendimiento —los 3 segundos son medibles y reales— que además cierra una
puerta del camino del dinero **antes** de que cueste algo. Que hoy no cueste nada es exactamente lo
que lo hace un buen momento para hacerlo: el día que alguien configure una variante con recargo, o un
producto se quede sin precio en una sede nueva, los tres caminos ya cobrarán lo mismo.

La tercera divergencia, la más fea de leer aunque nunca haya disparado: **sin precio en esa sede se
vende gratis**, en los dos caminos (`unit = unit if unit is not None else Decimal(0)`, dos veces en el
storefront; `?? 0` en el salón). Un producto sin precio no debería poder venderse, igual que hoy no se
puede vender una variante sin receta.

**Contrapeso, y hay que decirlo:** mandar el precio desde el cliente tiene un caso legítimo —un
descuento, un precio a mano, "te lo dejo en 20"—. No es el caso: no existe ninguna UI de descuento y
`addItem` no acepta un precio escrito por nadie, sólo el que sacó del índice. Es un accidente, no una
función. Si algún día hace falta la anulación manual, se añade explícita, con su permiso y su rastro,
sobre un precio que el servidor ya sabe calcular.

## What Changes

- **`add_item` resuelve el precio él mismo.** `unit_price` deja de viajar en la petición. El servidor
  lo compone de `product_prices` (por sede) + el recargo de la variante, que es exactamente lo que el
  salón hace hoy en el navegador — se mueve de sitio, no cambia de fórmula.
  Ojo con el segundo término: **`extra_price` no es una columna de `product_variants`**. Es un dato
  derivado, la suma de `variant_options.extra_price` de las opciones que la variante compone
  (`product_variant_options`). La consulta ya existe: `extra_price_of(tenant, variant_id)` en el
  repositorio de `menu`.
- **Un solo sitio calcula el precio de una línea.** Los tres caminos —salón, carta pública, edición
  autoservicio— pasan a llamar al mismo código. La carta pública deja de pasar un precio y **gana el
  `extra_price` que hoy le falta**.
- **Sin precio en la sede, la venta se rechaza.** Es la misma red de seguridad que ya existe para la
  receta, y con el mismo criterio: *"no descontaría inventario"* / *"no tiene precio en esta sede"*.
  Se cae el `else Decimal(0)` de los dos caminos del storefront y el `?? 0` del salón.
- **La línea trae su etiqueta resuelta.** El ítem que devuelve el API lleva el nombre del producto y
  el de la variante, con el join que `messaging.order_lines` ya tiene escrito
  (`OrderItem → ProductVariant → Product`, una consulta). El cliente deja de necesitar el menú para
  saber qué dice una línea.
- **`GET /orders` puede traer los ítems** (`include=items`), para que pintar el Salón sea una
  petición y no una por comanda.
- **`buildVariantIndex` desaparece del frontend.** Con el precio y la etiqueta resueltos, no tiene
  razón de existir. Con ella se van sus 40 peticiones.
- **`FloorView` recupera `loadKitchen`.** Está comentado (`FloorView.vue:64-72`) como parche de
  rendimiento, y con él comentado el Salón perdió el rollup de cocina. Vuelve a encenderse.
- **Se quitan las dos peticiones repetidas** de `buildItemIndex`: `loadOrders` y `loadTables`, que
  `ensureLoaded` acaba de hacer.
- **Nada de caché.** Se consideró y se descarta: ver `design.md`, decisión 6. El coste son los viajes
  de ida y vuelta, no las consultas.

## Capabilities

### Modified Capabilities

- `order-management`: `add_item` deja de aceptar un precio y pasa a resolverlo; se añade el rechazo
  por falta de precio en la sede; el ítem leído gana el nombre de su producto y de su variante; la
  lista de pedidos puede traer sus ítems.
- `frontend-salon`: la comanda deja de construir un índice del menú para nombrar y cotizar líneas —
  las lee de la propia línea. El Salón recupera el rollup de cocina.
- `storefront-public-api`: la toma de pedidos públicos deja de pasar el precio y hereda el rechazo por
  falta de precio; **empieza a cobrar `extra_price`** cuando la variante lo tenga.
- `self-service-order-edit`: la edición del cliente pasa por el mismo cálculo; se cae su
  `else Decimal(0)`, que vendía gratis un producto sin precio en la sede.

## Impact

- **Backend `orders`**: el cálculo del precio de una línea como función/consulta única en el módulo;
  `add_item` cambia de firma (un parámetro menos); el esquema del ítem gana dos campos de lectura;
  `list_orders` gana un `include`. **No hay migración**: `order_items.unit_price` ya existe y ya se
  estampa por fila, así que el modelo era correcto — sólo estaba mal de dónde salía el número.
- **Backend `storefront`**: `_price_addition` y `_price_edit` dejan de resolver el precio por su
  cuenta y delegan. Menos código, y el mismo resultado en los dos canales.
- **Frontend**: se borran `buildVariantIndex` y el `variantIndex`; `buildItemIndex` se queda en poco;
  `addItem` manda dos campos en vez de tres; `FloorView` descomenta `loadKitchen`. Sin librerías
  nuevas.
- **Rendimiento esperado**: ~60 peticiones y ~7 barreras → ~4 peticiones y 1 barrera, en las tres
  pantallas que hoy pagan el fan-out (`/floor`, `/floor/order/:id`, `/kitchen`). La más importante es
  la segunda: abrir una comanda para añadir un plato es la acción más repetida de un servicio.
- **Cambio de comportamiento en el canal público**, y es el único de todo el change: un producto con
  variante de recargo pasa a cobrarse más caro por la web de lo que se cobraba. Hoy no puede ocurrir
  porque el menú público no expone variantes; queda dicho para que no sorprenda cuando las exponga.
- **Rechazar en vez de regalar** también es un cambio de comportamiento: un producto sin precio en la
  sede hoy se vende a cero y a partir de esto no se vende. Medido en el grupo 0: **cero casos** en la
  base de desarrollo, así que no rompe ninguna venta existente. Si hay una base de producción aparte,
  esa cuenta hay que repetirla allí antes de desplegar — es la única que puede tumbar ventas.
- **Sin permiso nuevo**: los endpoints ya están gateados con `orders.create` / `orders.manage`, así que
  no hay que volver a sembrar el catálogo.
- **Riesgo**: es el camino del dinero. Un error aquí no es una pantalla lenta, es una cuenta mal
  cobrada. De ahí que el cálculo viva en un sitio con pruebas propias. El grupo 0 ya contó los datos
  que dependen del comportamiento viejo y salieron a cero, lo que hace el despliegue mucho más
  tranquilo de lo que este párrafo sugería al escribirse.

## Notes

Dos deudas detectadas al investigar esto, **fuera de alcance** y cada una merece change propio.

**Sedes duplicadas por diferencia de mayúsculas.** El tenant `demo` tiene dos sedes activas marcadas
las dos `is_primary`, con códigos `main` y `MAIN`; la segunda es la de verdad (19 precios, 147 pedidos)
y la primera está huérfana, creada por `scripts.seed` el 2026-07-30. `seed.py:144` ya lleva un
comentario sobre exactamente este problema, así que la guarda existe y no funcionó. Importa porque la
carta pública se direcciona por código de sede (`/store/{branch_code}`): dos códigos que sólo difieren
en mayúsculas son dos sedes para el sistema y la misma para quien escribe una URL.

**Caché en memoria con dos réplicas.**
`k8s/backend.yaml` corre `replicas: 2` con `CACHE_BACKEND: "memory"`. `RbacPermissionCache` depende de
invalidación explícita —su docstring lo dice— y con dos procesos esa invalidación llega a uno: quitarle
un permiso a alguien funciona *a veces* durante `cache_ttl_seconds` (300s). Es un problema de
correctness que existe hoy, es independiente de esto, y hay que arreglarlo antes de cachear nada.
