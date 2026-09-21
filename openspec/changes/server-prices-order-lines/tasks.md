> Lee `design.md` antes de empezar. Este change parece de rendimiento y **es del camino del dinero**.
> Los 3 segundos del Salón son el síntoma; la enfermedad es que el precio de una línea se calcula en
> tres sitios con tres fórmulas y el servidor se cree lo que le manda el navegador.
>
> **El orden de los grupos 5 y 7 no es negociable** (decisión 7): si se borra `buildVariantIndex` del
> frontend antes de que el servidor calcule el precio, hay una ventana en la que `addItem` manda
> `"0.00"` y se factura a cero. Servidor primero, siempre.
>
> Dos cosas que van a parecer errores y no lo son:
>
> - **El canal público empieza a cobrar más** (`extra_price`). Es la corrección de una divergencia, no
>   una regresión. Hoy es invisible porque el menú público no expone variantes.
> - **Ventas que hoy pasan van a fallar**: un producto sin precio en la sede deja de venderse a cero.
>   Eso es el change negándose a hacer lo que estaba mal. El grupo 0 mide cuántas son.
>
> Orden: 0 → 1 → 2 → 3 → 4 (backend completo y probado) → 5 → 6 → 7 → 8. El grupo 8 es la medición y
> **no es opcional**: sin ella la cifra de "60 → 4" es una conjetura con cara de dato.

## 0. Contar los datos antes de romper nada

> Ninguna tarea de código. Es lo que evita descubrir en un servicio que media carta no tiene precio en
> una sede. Se corre contra la base de cada tenant real, no contra la demo.

- [x] 0.1 Contar variantes vendibles cuyo producto **no tiene fila en `product_prices`** para alguna
      sede activa. Es exactamente el conjunto que va a empezar a rechazarse
      → **0 casos reales** (base de desarrollo, 2026-08-09). La primera pasada dio "50% sin precio en
      `demo`" y era ruido: hay DOS sedes en `demo` con códigos que sólo difieren en mayúsculas
      (`main` y `MAIN`), las dos marcadas `is_primary`. `MAIN`/Centro es la de verdad (19 precios,
      147 pedidos); `main`/Main Branch la creó `scripts.seed` el 2026-07-30 y está huérfana (0
      precios, 0 pedidos). Contando sólo sedes con precios o pedidos, **ninguna variante vendible se
      queda sin precio**. El rechazo no rompe nada.
      ⚠️ Medido en la base LOCAL. Si hay una base de producción aparte, 0.1 hay que repetirla allí
      antes de desplegar: es la única cuenta que puede tumbar ventas
- [x] 0.2 Contar `order_items` históricos con `unit_price = 0`. Si hay muchos, el `?? 0` ya estaba
      cobrando de menos y este change además tapa una fuga — conviene saberlo antes de que alguien lo
      lea como "el change subió los totales"
      → **0 de 245 líneas** (`demo` 194, `pase` 51), desde 2026-06-30 hasta 2026-08-09. El `?? 0`
      nunca se disparó, porque `OrderDetailView` siempre construye el índice antes de dejar añadir.
      El agujero estaba abierto y nadie se cayó por él
- [x] 0.3 Contar variantes con `extra_price > 0`. Es el tamaño real del cambio de comportamiento del
      canal público
      → **0 de 36 variantes activas** en los tres tenants. Ninguna compone opciones con recargo, así
      que hoy `base + extra_price` y `base` dan el MISMO número: la divergencia entre canales es real
      en el código y **nunca ha cobrado mal a nadie**. Esto debilita uno de los argumentos del
      proposal y está corregido allí
- [x] 0.4 Si 0.1 devuelve algo, decidir **con el dueño** si se rellenan esos precios antes del
      despliegue o si se acepta que esos productos dejen de venderse. No es una decisión técnica
      → 0.1 devolvió cero, así que **no hay nada que decidir** con los datos locales. Queda
      pendiente de repetir contra producción si existe (ver 0.1)

> **Hallazgo lateral, fuera de alcance de este change.** `demo` tiene dos sedes activas marcadas las
> dos `is_primary`, con códigos `main` y `MAIN` — la segunda huérfana, creada por `scripts.seed`. Y
> `seed.py:144` ya lleva un comentario sobre exactamente este problema ("quien renombró la suya a
> «MAIN» no puede acabar con DOS sedes principales"), así que la guarda existe y no funcionó para este
> tenant. Importa más de lo que parece: la carta pública se direcciona por código de sede
> (`/store/{branch_code}`), así que dos códigos que sólo difieren en mayúsculas son dos sedes distintas
> para el sistema y la misma para una persona escribiendo una URL. Merece su propio change.

## 1. Backend — el único sitio donde se calcula el precio de una línea

> Vive en el módulo `orders`, porque es quien escribe la línea. Se prueba con datos en
> `tests/modules/orders/test_line_pricing.py`.

- [x] 1.1 Consulta del precio de un producto en una sede en el repositorio de `orders`. Ya existe la
      forma en el repositorio del storefront (`product_price(tenant, product_id, branch_id)`); copiar
      la consulta, no llamar al otro módulo
      → resuelto dentro de `resolve_line_price` (1.2): no hacía falta un método suelto, y uno menos
      es una puerta menos por la que alguien pueda cotizar sin el recargo
- [x] 1.2 `resolve_line_price(tenant, variant_id, branch_id)`: variante → producto → precio de sede
      **+ el recargo de la variante**. Devuelve `None` cuando no hay precio de sede, y **no** cero.
      ⚠️ El recargo NO es una columna: es `sum(variant_options.extra_price)` de las opciones que la
      variante compone (`product_variant_options`). La consulta ya existe —`extra_price_of` en el
      repositorio de `menu`— así que son dos agregaciones, no dos lecturas simples
      → `resolve_line_price` en el puerto (`orders/domain/ports.py`) y en
      `SqlAlchemyOrdersRepository`. **Dos consultas y no una**, con el porqué en el docstring: con un
      `LEFT JOIN` a la agregación, "no hay precio" y "el recargo es cero" se confunden — y de esa
      distinción depende el rechazo. Se copia la consulta de `menu` en vez de llamar al módulo, por
      el mismo criterio que `variant_has_recipe` lee `recipe_items` directo
- [x] 1.3 Prueba de la fórmula: 25000 + 5000 = 30000. Es la del salón, no la del storefront, y el
      porqué está en la decisión 2
      → y el recargo se monta en la prueba como el sistema lo monta de verdad (grupo → opción →
      composición), no escribiendo un número: simplificarlo dejaría de probar la consulta real.
      Añadida una tercera con DOS opciones compuestas, porque con una sola una lectura pasaría por
      una suma
- [x] 1.4 Prueba de que el precio sale de la sede del PEDIDO: mismo producto con dos precios, pedido de
      la segunda sede → precio de la segunda
- [x] 1.5 Prueba de que sin precio en esa sede devuelve `None`, y de que un precio en OTRA sede no vale
      → 9 pruebas en `test_line_pricing.py`, contra el repositorio y **sin levantar la app**
      (`setup_db`, no `client`: lo que está en juego es una consulta). Además: precio *inactivo* no
      vale, variante de otro tenant da `None`, variante inexistente da `None`. Y una que afirma
      `result is None and result != Decimal(0)`, que es la distinción de la que cuelga todo el change.
      162 pasan en `tests/modules/orders/`

## 2. Backend — `add_item` deja de aceptar un precio

- [x] 2.1 Quitar `unit_price` de la firma de `add_item` y resolverlo dentro con `resolve_line_price`
- [x] 2.2 `None` → `ValidationError` nombrando lo que falta ("no tiene precio en esta sede"). Ponerlo
      **junto** al rechazo por receta, que es la misma clase de red de seguridad en el mismo límite
      → "El producto no tiene precio en esta sede; no se puede vender." Ahora son **tres** redes en
      el límite de la venta y fallan igual a propósito: sin receta no descontaría stock, sin precio
      se regalaría, sin caja abierta no hay quien responda del dinero
- [x] 2.3 El esquema de la petición **tolera** `unit_price` durante una versión y lo **ignora**: es lo
      que permite desplegar el backend antes que el frontend sin romper a nadie (ver plan de
      migración). Con un comentario que diga cuándo se puede quitar
      → `unit_price: Decimal | None = Field(default=None, ge=0, deprecated=True)`, y el router lo
      recibe y NO lo pasa. El comentario dice cuándo se borra y por qué no puede quedarse: "un campo
      ignorado que se queda acaba pareciendo un campo que funciona"
- [x] 2.4 Prueba de que un `unit_price` que llegue en el cuerpo NO afecta a lo que se cobra. Es la que
      demuestra que la puerta está cerrada
      → dos pruebas: un `unit_price: "1"` y uno de `"1000000.00"`. Las dos cobran el precio del
      catálogo. Hacía falta afirmarlo y no sólo dejar de mandarlo: el campo se sigue aceptando
- [x] 2.5 Prueba de que un producto sin precio de sede se rechaza y **no crea nada** — ni a cero
      → 422 nombrando el precio, cero líneas y total cero. Más una tercera: un precio en OTRA sede no
      rescata la venta
- [x] 2.6 Prueba de que el precio se ESTAMPA: cambiar el precio del producto después no mueve la línea
      ni el total del pedido
- [x] 2.7 Prueba de que una línea nueva tras el cambio sí lleva el precio nuevo, junto a las viejas con
      el viejo
      → 9 pruebas en `test_server_priced_items.py`. Añadida una novena: **desactivar** el precio
      impide vender más y NO reescribe lo ya vendido
- [x] 2.8 Repasar `update_item` / el camino que cambia la variante de una línea
      (`manage_orders.py:726`, que ya repite las redes de seguridad de `add_item`): tiene que
      re-cotizar por el mismo sitio
      → `change_item_variant` pierde también el parámetro y re-cotiza. Era **la puerta de atrás del
      change**: cambiar el producto de una línea es exactamente donde un precio viejo se quedaría
      pegado a un producto nuevo. Ahora repite las TRES redes, no dos

> **Lo que costó de verdad el grupo 2 fueron las pruebas que ya existían.** 22 fallaron, y ninguna por
> un bug: fallaban porque creaban productos SIN precio y mandaban el número a mano — o sea, ejercían
> justo la capacidad que este change retira. El arreglo fue un helper compartido
> (`tests/modules/_menu.py::price_variant_for_branch`, hermano de `_cash.py`) y dos casos que
> merecieron cirugía en vez de parche:
>
> - `test_cancelled_item_not_deducted` pagaba exactamente 1 para que la aritmética del stock se leyera
>   de un vistazo. Se siembra el precio a 1 en vez de subir el pago: si no, el fallo aparecería en el
>   stock y la causa estaría en la caja.
> - `_seed` de `test_table_bills` montaba tres comensales con importes distintos poniéndole **tres
>   precios al mismo plato**. Ahora es un producto por importe — que además es lo que pasa en una mesa
>   de verdad, y el escenario se lee mejor que antes.

## 3. Backend — los otros dos caminos dejan de cotizar por su cuenta

- [x] 3.1 `storefront/manage_storefront.py` (dos llamadas a `add_item`): dejar de pasar precio
      → hecho ya en el grupo 2 (el cambio de firma no dejaba compilar de otra forma). Aquí se remató
      lo que faltaba: `_ResolvedLine.unit_price` era **código muerto** —se ponía y no se leía— y se
      borra, con un tercer `else Decimal(0)` que nadie había contado. Pero la COMPROBACIÓN de que
      hay precio se queda en `_resolve_lines`: sin ella el rechazo llegaría a mitad del bucle que
      añade líneas y dejaría una comanda abierta con parte del carrito, que es peor que el cero
- [x] 3.2 `storefront/edit_order.py`: `_price_addition` y `_price_edit` delegan en `resolve_line_price`.
      **Se caen los dos `else Decimal(0)`** — eran el regalo silencioso
      → delegan en `OrderService.line_price`, una LECTURA nueva. Hacía falta porque este camino tiene
      que decirle al cliente **cuánto va a deber antes de escribir**: si calculara el delta por su
      cuenta habría otra vez dos fórmulas, y la que divergiría sería la que el cliente ve. Un solo
      cálculo, dos usos (anunciar y cobrar)
- [x] 3.3 Actualizar el comentario de `edit_order.py:316`: el principio sigue siendo el mismo ("el
      precio nunca viene del cliente") pero ahora quien lo busca es `add_item`, no quien llama. Dejar
      escrito que fue este change el que unificó las tres fórmulas
      → reescrito: el principio sigue vigente y se dice qué cambió —ya no lo busca "quien llama",
      lo resuelve `add_item` y aquí se PREGUNTA— más la frase que lo justifica: aquel principio era
      mejor que recibirlo del cliente y aun así produjo tres fórmulas
- [x] 3.4 Prueba de que los tres caminos cobran lo MISMO por la misma variante en la misma sede. Es el
      requisito que hace que no puedan volver a divergir
      → 6 pruebas en `tests/modules/storefront/test_one_price_every_channel.py`, y por los tres
      caminos DE VERDAD (HTTP del salón, HTTP público anónimo, PATCH por token) — no tres llamadas a
      la misma función, porque lo que se rompió no fue el cálculo sino que cada camino tenía el suyo
- [x] 3.5 Prueba de que la edición autoservicio rechaza (y no escribe nada) cuando una de sus líneas no
      tiene precio — el rechazo es de todo el lote, como los demás de esa capability
      → y ya existía `test_adding_a_line_ignores_a_client_supplied_price`: ese camino nunca aceptó un
      precio del cliente. Lo que le faltaba era no regalar el plato cuando no hay precio.
      291 pasan entre `orders` y `storefront`

## 4. Backend — la línea trae su etiqueta, y la lista trae sus líneas

- [x] 4.1 El ítem leído lleva `product_name` y `variant_name`, resueltos con el join que ya existe en
      `messaging.order_lines` (`OrderItem → ProductVariant → Product`). **Una consulta para todos los
      ítems del pedido**, no una por ítem — si esto acaba siendo N+1, el change se ha convertido en su
      propio problema
- [x] 4.2 Nada de columnas nuevas: el nombre es dato derivado en la respuesta. La decisión 4 dice por
      qué, y la diferencia con el precio (que sí se estampa) es el corazón del change
      → cero migraciones en todo el change
- [x] 4.3 Prueba de que renombrar un producto cambia lo que dice una comanda viva y **no** su precio
- [x] 4.4 `GET /orders` acepta traer los ítems. **Una sola clave**, `items`, y el spec dice por qué no
      es un mecanismo general
      → `?include=items`. Los ítems de TODAS las comandas salen de `list_items_for_orders`, tres
      consultas agrupadas en total; un bucle sobre `list_items` habría movido el fan-out de la red a
      la base de datos, que es cambiar el problema de sitio. Una clave desconocida se ignora
- [x] 4.5 Prueba de que sin pedirlo la respuesta es idéntica a la de antes (forma y tamaño)
      → **corregí el spec aquí.** Añadir `items: null` ES un cambio de forma, aunque aditivo e
      inofensivo, y contorsionar el código para evitarlo (excluir nulos de esa ruta) habría borrado
      también `closed_at`, `customer_id` y demás nulos legítimos. El requisito pasa a garantizar lo
      que de verdad vale: **todos los campos de antes conservan su valor, y no pedirlo no cuesta ni
      una consulta**. La prueba compara los dos cuerpos campo por campo salvo `items`
- [x] 4.6 Prueba de que con doce pedidos abiertos basta UNA petición
      → 7 pruebas en `test_lines_carry_their_labels.py`, incluida la que separa los dos campos nuevos
      del que ya existía: renombrar el producto cambia lo que dice una comanda viva y **no** su
      precio. Si el nombre se guardara en la fila, esa prueba fallaría

> **Cocina también añade ítems**, y sus pruebas fallaron por lo mismo que las de pedidos (variantes
> sin precio). Cuatro sitios más con `price_variant_for_branch`, uno de ellos una segunda variante
> creada dentro del test. Total del grupo 4: **377 pasan** entre `orders`, `storefront` y `kitchen`.

## 4b. Backend — "qué puedo vender aquí ahora", en una petición

> **Este grupo no estaba en el plan y es un hueco mío**, descubierto al implementar el 5:
> `buildVariantIndex` hacía DOS trabajos y sólo vi uno. Además de calcular el precio, era lo que
> **cargaba el menú** para los mosaicos del selector (`menu.fetchProducts` + `loadPrices` +
> `loadVariants` por producto). Al borrarlo, el selector de la comanda se queda sin datos.
>
> Y hay más de lo que el diagnóstico decía: `stores/menu.ts:182` lleva su propio aviso escrito —
> *"The backend has no bulk price endpoint, so this is filled by loadPrices() in parallel"*— o sea
> otras 40 peticiones. La comanda cuesta ~81, no 52.
>
> No es scope nuevo: el `proposal.md` ya prometía que las 40 peticiones desaparecen. Lo que faltaba
> era el endpoint que lo hace posible.

- [x] 4b.1 `GET /menu/orderable?branch_id=X`: productos activos + sus variantes activas + el precio de
      la sede, en UNA respuesta. Sólo lo vendible: un producto sin precio en esa sede no se puede
      pedir, así que tampoco debe aparecer como mosaico
      → `GET /menu/orderable?branch_id=X`. Va ANTES de `/products/{product_id}` en el fichero: si no,
      FastAPI casa `orderable` con `{product_id}` e intenta parsearlo como UUID
- [x] 4b.2 El recargo de cada variante viaja resuelto (la suma de sus opciones), para que el mosaico
      pueda enseñar el precio SIN volver a calcular nada. Reusa `resolve_line_price` o su consulta:
      dos fórmulas para el precio de un mosaico y el de la línea sería el mismo error otra vez
      → hay una prueba que lo ancla: `test_the_tile_price_is_what_add_item_charges` lee el mosaico y
      luego añade la línea, y compara. Si el mosaico dijera un número y la cuenta otro, el mesero lo
      descubriría cuando el cliente mira la cuenta
- [x] 4b.3 Consultas AGRUPADAS, no una por producto. Es el punto entero del endpoint
- [x] 4b.4 Gateado con `menu.read`, como el resto de lecturas del menú
- [x] 4b.5 Pruebas: un producto sin precio en la sede NO sale; un producto sin variantes activas NO
      sale; el precio del mosaico coincide con el que `add_item` cobra por esa variante
- [x] 4b.6 Prueba de que con 40 productos es UNA petición y un número acotado de consultas
      → 7 pruebas en `tests/modules/menu/test_orderable.py`. Tres consultas para todo el catálogo

## 5. Frontend — el servidor ya calcula: quitar el índice del menú

> **Nada de este grupo puede ir antes del 2.** Ver la advertencia de arriba.

- [x] 5.1 `addItem` manda `{ product_variant_id, quantity }` y nada más. Se cae el
      `(info?.unitPrice ?? 0).toFixed(2)`
- [x] 5.2 Borrar `buildVariantIndex` y el estado `variantIndex` de `stores/orders.ts`
- [x] 5.3 Quitar la llamada de `OrderDetailView.vue:88`. Era la que sostenía el precio; ya no sostiene
      nada
- [x] 5.4 `itemLabel` lee el nombre de la propia línea en vez del índice
- [x] 5.4b `MenuField.vue` y `OrderDetailView` pasan a `menu.loadOrderable(branchId)`: una petición
      para los mosaicos, con su precio dentro. Es lo que sustituye al efecto secundario que hacía
      `buildVariantIndex`
      → `menu.loadOrderable(branchId)`. `MenuField` deja de leer de tres fuentes (productos, precios
      por producto, variantes por producto) y lee una lista ya filtrada a lo vendible
- [x] 5.5 `buildItemIndex` (`stores/kitchen.ts:373`): quitar las dos peticiones **repetidas**
      (`loadOrders`, `loadTables` — `ensureLoaded` acaba de hacerlas) y usar `include=items` en vez de
      una por comanda
      → `loadOrdersWithItems` en el store, y `ensureLoaded` la usa: le cuesta la misma petición.
      `buildItemIndex` pasa a ser **síncrono y sin red** — indexa lo que el store ya tiene, y cargar
      es del llamador. Eso es lo que hace visible el coste en vez de esconderlo dentro
- [x] 5.6 Prueba de que añadir un producto NO manda precio
- [x] 5.7 Prueba de que la comanda pinta una línea entera (nombre, variante, precio) **sin haber leído
      ningún endpoint de menú**. Es la que demuestra que el fan-out murió
      → 7 pruebas en `stores/__tests__/noMenuFanout.spec.ts`, **a nivel de store y no de componente**:
      lo que importa no es qué pinta la vista, es cuántas peticiones y a qué endpoints. Una prueba de
      componente montaría media aplicación para afirmar lo mismo peor. Se espía el módulo del menú
      ENTERO para poder afirmar que nadie lo llama, y se cuenta que `ensureLoaded` cabe en tres

## 6. Frontend — el Salón recupera lo que había perdido

- [x] 6.1 Descomentar `loadKitchen` en `FloorView.vue:64-72` y `buildVariantIndex` ya no hace falta en
      `ensureLoaded` (`stores/orders.ts:160`) — se borra en vez de descomentarse
      → hecho. `loadKitchen` vuelve entero (estaciones + tickets + índice) y el comentario dice por
      qué puede volver: ya no cuesta 55 peticiones
- [ ] 6.2 Prueba de que las tarjetas enseñan el rollup de cocina, no sólo ocupada/total. **Si al final
      del change `loadKitchen` sigue comentado, el change no ha terminado**
      → `loadKitchen` está descomentado (verificable leyendo `FloorView.vue`), pero "las tarjetas
      enseñan el rollup" es VISUAL y no hay ninguna prueba de componente de `FloorView` en el repo —
      serían las primeras. **Se pasa al grupo 8 como comprobación manual** en vez de inventar un arnés
      de montaje para una afirmación que se ve mejor con los ojos. Las piezas puras que lo alimentan
      (`buildTableVMs`, `buildOrderProgress`) ya tienen sus specs
- [x] 6.3 Prueba de que el Salón carga sin pedir ningún endpoint de menú y sin una petición por comanda
      → cubierto por `noMenuFanout.spec.ts` (misma propiedad, mismo sitio)
- [x] 6.4 Comprobar que sigue degradando bien: si cocina falla, las tarjetas vuelven a ocupada/total y
      el Salón funciona

## 7. Despliegue, en este orden

- [x] 7.1 **Backend primero.** Acepta el `unit_price` viejo como campo ignorado, así que un frontend
      antiguo contra un backend nuevo sigue funcionando — y empieza a cobrar bien
      → PR del backend abierto: nleea/restaurante_back#5. **Los dos changes van en commits
      separados** (`a1d94b4` estados, `8266bb5` precios) porque el árbol los tenía mezclados y un
      blob habría hecho imposible revertir uno sin el otro. Cada commit verificado AISLADO antes de
      crearlo (520 y 407 pruebas). La migración 0047 la aplica el `initContainer`
      (`k8s/backend.yaml:85`), así que no hay paso manual.
      ⚠️ **El rollout no lo puedo hacer yo**: `kubectl` no tiene contexto configurado aquí
- [ ] 7.2 **Frontend después.** Al revés (frontend nuevo contra backend viejo) se escriben ceros: es la
      única forma de romper esto y se evita con el orden
      → rama empujada (`9b19e7a`) y **el PR NO está abierto a propósito**: abrirlo invita a que
      alguien lo mergee antes de que el backend esté vivo, y eso es exactamente el único modo de
      romper este change. Se abre cuando el backend esté desplegado y comprobado
- [ ] 7.3 Dejar el `unit_price` tolerado hasta que el frontend esté desplegado en todos los tenants;
      quitarlo es un commit de limpieza posterior, no parte de esto

## 8. Cierre y medición

- [x] 8.1 `pytest tests/modules/orders/ tests/modules/storefront/` y las pruebas del front tocadas
      (`stores/`, `views/FloorView`, `views/OrderDetailView`, `stores/kitchen`). Type-check y lint
      → backend: **407 pasan** (`orders`, `storefront`, `kitchen`, `menu`). Frontend: **1080 pasan**
      (111 ficheros). `ruff`, `eslint`, `oxlint` y `vue-tsc` limpios; `mypy` sólo con los 2 errores
      preexistentes de `payment_proof.py`, verificados con `git stash`
- [ ] 8.2 Comprobar que las tarjetas del Salón enseñan el rollup de cocina (visual — ver 6.2)
- [ ] 8.2b **Medir con el panel de Red, antes y después**: nº de peticiones y tiempo hasta ver las mesas,
      en `/floor` y en `/floor/order/:id`. La cifra "60 → 4" del diseño sale de contar llamadas, no de
      medir; si la realidad no se parece, el diagnóstico tenía algo más y hay que decirlo
- [ ] 8.3 Añadir un plato de verdad y **comprobar el precio contra la carta**. Es el camino del dinero:
      la única prueba que vale es que el número de la pantalla sea el de la carta
- [ ] 8.4 Añadir el mismo plato por la carta pública y comprobar que cobra **lo mismo** que el salón.
      Es el requisito nuevo y no hay prueba automática que lo cubra de punta a punta
- [ ] 8.5 Cerrar una comanda y comprobar que el total y el arqueo cuadran. `recompute_totals` cuelga de
      `unit_price`, así que este change toca la caja aunque no la mencione
