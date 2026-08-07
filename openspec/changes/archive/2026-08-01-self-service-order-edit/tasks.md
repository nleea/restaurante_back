> Depende de `storefront-branch-scoped`, `whatsapp-autoreply` (el enlace y su token) y
> `assistant-core` (el enrutado). Lee `design.md` antes de empezar: la invariante del total y
> las dos ventanas son el cambio entero — el resto es fontanería alrededor.

## 1. Backend — el token del pedido

- [x] 1.1 Token de edición por pedido: columna en `orders` (o tabla propia si se prefiere
      rotarlo), con vencimiento propio e independiente del `store_token` de la conversación
- [x] 1.2 Acuñarlo al crear el pedido, en TODOS los caminos de creación pública (con y sin código
      de sucursal), y devolverlo en la respuesta
- [x] 1.3 Resolución del token → pedido, filtrada por tenant; vencido, desconocido y de otro
      tenant deben ser indistinguibles para quien pregunta
- [x] 1.4 Migración **0029_order_edit_token** (up/down/up en Postgres, sin deriva); el token nace nulo en los pedidos existentes y eso deja la vista sin abrir
      para ellos, que es el comportamiento correcto

## 2. Backend — las reglas (el corazón del cambio)

> 2.1–2.4 viven como funciones PURAS en `storefront/domain/order_edit.py`, probadas sin base de
> datos en `tests/modules/storefront/test_order_edit_rules.py`. 2.5 y 2.6 son de quien las usa
> (grupos 3 y 4), no de las reglas.

- [x] 2.1 Ventana por ítem: editable sólo si TODAS sus estaciones siguen en `pending`
- [x] 2.2 Ventana por pedido, según cómo sale: con entrega, nada editable desde `in_transit`; sin
      entrega, desde `kitchen_state = ready`. En ambos casos, tampoco si el pedido ya no está
      abierto
- [x] 2.3 Invariante: el total del pedido resultante nunca menor que el anterior, comprobada
      **una vez, sobre el resultado**, no por operación
- [x] 2.4 Regla de pago (`payments_total >= total`): las líneas existentes sólo crecen; cambiar el
      producto de una línea se rechaza; lo añadido entra como línea nueva
- [x] 2.5 Todo lo anterior se comprueba **releyendo el estado al escribir**, nunca con lo que el
      cliente traiga ni con lo que la vista leyó al pintarse
- [x] 2.6 Una edición rechazada no deja rastro: se valida antes de mutar, como hace `close_order`

## 3. Backend — componer la edición

- [x] 3.1 Añadir ítem con el precio resuelto del catálogo de la sucursal; un precio que venga del
      cliente se ignora
- [x] 3.2 Subir cantidad y adjuntar adiciones sobre una línea existente
- [x] 3.3 Cambiar el producto de una línea (no existe hoy como caso de uso) — sólo sin pago
- [x] 3.4 Notas: exclusiones + texto libre, compuestas por el servidor a partir de la elección del
      cliente, nunca aceptando la cadena ya montada
- [x] 3.5 Auto-enviar a cocina lo añadido cuando el resto del pedido ya está enrutado
      (adaptador `_KitchenDispatchAdapter` en el composition root del storefront, SIN la puerta
      de pago: por aquí sólo se enruta un pedido que ya la cruzó, y un falso "no" dejaría unas
      papas facturadas sin cocinar)
- [x] 3.6 Recomputar totales y devolver total nuevo y saldo pendiente
- [x] 3.7 Atribuir la edición al cliente por su canal: evento `storefront.order_edited` con
      `actor_id` = el empleado que firma el pedido ("Pedidos web") y el detalle diciendo
      `canal=enlace_cliente`; se guarda la IP (único rastro sin sesión) y NUNCA el token

## 4. Backend — API pública

- [x] 4.1 `GET /storefront/orders/{token}`: líneas, adiciones, notas descompuestas (exclusiones
      aparte del texto libre, vía `split_note`), editabilidad y motivo por ítem, total y saldo
- [x] 4.2 `PATCH /storefront/orders/{token}`: el catálogo de verbos permitidos ES la forma del
      cuerpo (`add` / `edit`) — lo que no se puede pedir no tiene campo, el precio incluido
- [x] 4.3 `OrderEditRefused` movido a `storefront/domain/errors.py` con código propio
      (`order_edit_refused`) y `refusal` en el cuerpo; registrado en `shared/api/errors.py`,
      que mapea por tipo EXACTO — sin esa entrada heredar de `ConflictError` daba un 400
- [x] 4.4 Router propio montado ANTES del storefront: `/storefront/orders/{token}` y
      `/storefront/{branch_code}/menu` tienen la misma forma y gana la declarada primero

## 5. Backend — pruebas

> Todo por HTTP y sólo con el token, repartido en dos ficheros:
> `test_storefront_order_edit_api.py` (la superficie: token, vista, verbos, rastro) y
> `test_storefront_order_edit_windows.py` (las reglas: invariante, las dos ventanas, el pago).
> Las funciones puras siguen probadas aparte en `test_order_edit_rules.py`.

- [x] 5.1 Un token abre su pedido y sólo el suyo; con otro pedido, se rechaza
- [x] 5.2 Vencido / desconocido / de otro tenant: misma respuesta, sin filtrar existencia
- [x] 5.3 Cambio del mismo precio pasa; a algo más barato se rechaza; a algo más caro pasa
- [x] 5.4 El intermedio de un cambio de producto no dispara el rechazo (se valida el resultado)
- [x] 5.5 Quitar, bajar cantidad y cancelar se rechazan por esta vía (bajar con su motivo;
      quitar y cancelar ni siquiera tienen verbo: el cuerpo los ignora)
- [x] 5.6 Ítem con una estación empezada: sólo lectura; otro ítem del mismo pedido sigue editable
- [x] 5.7 Domicilio `in_transit`: se rechaza todo, añadir incluido
- [x] 5.8 Domicilio `ready` con la entrega aún sin salir: añadir SÍ se acepta y se enruta
- [x] 5.9 Pedido sin entrega (recoger/mesa) en `ready`: se rechaza todo
- [x] 5.10 La cocina empieza entre pintar y confirmar → se rechaza (releído al escribir)
- [x] 5.11 Con pago: adición y cantidad sí; cambio de producto no; lo añadido es línea nueva
- [x] 5.12 Lo añadido con el pedido ya en cocina queda enrutado, no `pending`
- [x] 5.13 Un precio enviado por el cliente se ignora
- [x] 5.14 Una edición rechazada deja el pedido byte a byte como estaba

## 6. Frontend — la vista "mi pedido"

> Ruta `/my-order/:token` (`MyOrderView.vue`) + `components/myorder/{MyOrderLine,DishPicker}.vue`,
> `services/myOrder.api.ts` y la aritmética pura en `lib/myOrder.ts`. Signature: la misma comanda
> de papel térmico del storefront, pero todavía sobre el pase y con un lápiz al lado — lo empezado
> queda sellado con el motivo escrito al lado.
> Añadido de paso: `contactPhone` (teléfono de la sede) en el `GET`, porque ofrecer "lo resuelve
> una persona" sin decir cómo alcanzarla deja al cliente donde estaba.

- [x] 6.1 Ruta pública que abre el pedido por token; sin login y sin depender de WhatsApp
      (y el enlace se ofrece al confirmar en la carta: quien pide por la web no recibe nada por
      WhatsApp, así que sin eso el único camino sería el chat)
- [x] 6.2 Líneas con producto, cantidad, adiciones y notas; total
- [x] 6.3 Exclusiones como casillas (desde `removable_ingredients`) con lo actual ya marcado, más
      el texto libre — sin pedir que se reescriba lo que ya había
- [x] 6.4 Añadir del catálogo, subir cantidad, adiciones y cambio de producto según lo permitido
- [x] 6.5 Lo no editable se ve inerte y **explicado** ("ya lo están preparando"), no escondido
- [x] 6.6 Quitar / cancelar: se explica que lo hace una persona y se ofrece cómo escribirle
- [x] 6.7 Delta a pagar bien visible antes de confirmar, diciendo cuándo se cobra
- [x] 6.8 Enlace vencido: se explica sin revelar si el pedido existe
- [x] 6.9 Un rechazo del servidor se enseña tal cual y la vista se resincroniza con la realidad

## 7. Frontend — pruebas

> `views/__tests__/MyOrderView.spec.ts` (8 casos, servicios doblados) y
> `lib/__tests__/myOrder.spec.ts` (10 casos: el delta replica el orden de operaciones del
> servidor, y la nota viaja siempre con las exclusiones).

- [x] 7.1 Exclusiones actuales aparecen marcadas; añadir una conserva las otras y la nota libre
- [x] 7.2 Ítem en preparación: control inerte y explicado
- [x] 7.3 Pedido listo: la vista se explica y ofrece una persona
- [x] 7.4 El delta a pagar se muestra antes de confirmar
- [x] 7.5 Un rechazo del servidor no se pinta como aplicado

## 8. Asistente — enrutar, no escribir

> Dos capas: una determinista antes del modelo (cancelar/devolver → persona; cerrado → frase
> fija) y el propio modelo para lo que exige leer la frase. Pruebas en
> `tests/modules/assistant/test_order_edit_routing.py`.

- [x] 8.1 Distinguir petición de cambio: añadir/adición/nota/cambio → enlace de ESE pedido;
      quitar/cancelar/devolver → persona.
      **Cancelar y devolver** se atajan por palabras ANTES del modelo (`REFUND_WORDS`) y pasan
      la conversación a `human`. **Quitar NO**, a propósito: "quítame la cebolla" es una
      exclusión que la vista sí hace y "quítame la gaseosa" no, y distinguirlas exige entender
      la frase — lo decide el modelo con una regla explícita del prompt. Una lista de palabras
      mandaría a una persona a quien sólo quería tocar una casilla
- [x] 8.2 Herramienta `my_order_link` (sólo `list_orders`): el enlace del pedido ABIERTO de ESE
      contacto. Sin contacto conocido o sin dominio público, la herramienta no existe — no una
      que devuelva basura. La URL la compone la raíz de composición (`shared/links.py`, sacado
      de autoreply para no tener dos reglas de un mismo enlace)
- [x] 8.3 Fuera de horario: frase fija con la próxima apertura, cero llamadas. Puerto
      `OpeningHoursReader` + adaptador sobre `business`, con una regla propia del adaptador:
      **un horario SIN configurar no es un horario cerrado** (si no, el asistente nace mudo).
      Un fallo leyendo el reloj tampoco calla al asistente
- [x] 8.4 Pruebas (12): cancelar/devolver → persona, sin llamada y sin enlace; quitar un
      ingrediente SÍ llega al modelo; cerrado no gasta ni una llamada y no inventa el día
      cuando no hay horario; la herramienta entrega el enlace del contacto y nada cuando no
      hay pedido abierto o el pedido no tiene token
- [x] 8.5 Confinamiento y sólo-lectura verdes, y **ampliados**: `my_order_link` entra ahora en
      el registro que audita `ReadOnlyGuard`, así que la herramienta nueva pasa por la misma
      frontera que el resto en vez de quedarse fuera de la prueba

## 9. Puertas de calidad

- [x] 9.1 Backend: `ruff` limpio, `mypy` 394 ficheros, `pytest` 863 en verde; `alembic` up/down
      de la 0029 ya verificado al crearla (grupos 4–5 no añaden migración)
- [x] 9.2 Frontend: lint, type-check, 646 unit y build en verde

> `poetry run python -m scripts.seed_demo` deja el recorrido listo e imprime los pasos con la
> URL real de la sede. Sembrado ya en la base local: la Hamburguesa Clásica trae
> `["Queso cheddar", "Tomate", "Lechuga"]` como quitables (comprobado contra la API).
> Ojo con `BASE_DOMAIN`: la `.env` local apunta a `wsquote.uk` y el front de desarrollo sirve
> en `demo.localhost:5173`; sin `BASE_DOMAIN=localhost` no se resuelve ningún tenant. La guía
> impresa lo avisa sola.

- [x] 9.3 Manual: pedir por la carta, abrir el enlace, quitar la lechuga con el pedido aún sin
      enviar; enviar a cocina, añadir algo y verlo aparecer en el KDS; empezar a preparar un ítem
      y comprobar que ya no se deja editar; con el pedido listo pero la entrega sin salir, añadir
      todavía debe poder; al pasar la entrega a `in_transit`, la vista se apaga
