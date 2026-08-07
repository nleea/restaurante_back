## Context

El canal tiene hoy tres respuestas automáticas y ninguna lee lo que el cliente escribió: el saludo
sale por existir un primer mensaje, los avisos de estado salen por una transición del pedido, y el
asistente sólo entra si el cliente pide entrar. Eso deja un tercio del sistema sin dueño: la
conversación **`greeted`**, que es la mayoría.

Lo que ya existe y este diseño se apoya en ello, sin construir nada nuevo:

- **`try_claim_emission` + índice único** para "esto ya se envió", con dos clases de clave
  conviviendo en una tabla (`greeting:<conv>`, `status:<pedido>:<estado>`). El docstring del modelo
  ya documenta el patrón de clave, así que una tercera clase encaja sin inventar mecanismo.
- **`render()` y los conjuntos de marcadores** en `messaging/domain/templates.py`: funciones puras,
  validación **al guardar** y no al enviar, y un 422 que nombra al culpable.
- **`is_open_at` / `next_opening`** sobre las ventanas de la sede, en hora **local** (todo
  "¿está abierto?" pasa por `business/application/clock.py`).
- **`orders.whatsapp_contact_id`**, que es lo que hace consultable el gate del pedido vivo. Existe
  desde el vínculo pedido-web ↔ contacto y ya lo usa la herramienta `my_orders` del asistente.
- **El espejo del front** (`front/src/lib/whatsappAutoreply.ts`) como precedente explícito de
  duplicar reglas para que la vista previa no dependa de la red. La verdad sigue siendo el 422.
- **`AssistantResponder.respond()` ya devuelve `bool`** ("no era mía") y `_assist` lo descarta hoy.
  El engarce de las FAQs le da sentido sin cambiar ninguna firma.

Y el antecedente incómodo, que es lo que obliga a que este diseño sea explícito: el módulo
**rechazó por escrito** el matching por palabras clave. La frase completa es *"Nada de detectar
intención: 'quiero pedir', 'buenas' y '?' merecen la misma primera respuesta, y una lista de
palabras clave es una fábrica de bugs"*, y se refiere a decidir la **primera** respuesta. El saludo
sigue siendo incondicional y este cambio no lo toca. Lo que cambia es que **después** del saludo,
donde hoy no hay nada, un texto que coincide con una pregunta conocida se contesta.

## Goals / Non-Goals

**Goals**

- Que las cuatro preguntas que todo restaurante recibe —dónde están, a qué hora, cómo se paga,
  si llevan a domicilio— se contesten solas, a cualquier hora, sin gastar un token.
- Que un falso positivo sea **recuperable**: el hilo sigue en la bandeja y sigue siendo de una
  persona.
- Que instalar el change no cambie el comportamiento de ningún tenant sin que lo pida.
- Que el dueño entienda, leyendo la pantalla, **por qué** una FAQ no contestó.

**Non-Goals**

- Entender la frase. No hay NLP, ni embeddings, ni sinónimos automáticos. Lo que no está en los
  triggers no dispara.
- Contestar dentro del asistente. Una conversación en `bot` la sigue atendiendo el modelo.
- Tomar pedidos, cancelar, devolver o cualquier escritura. Las FAQs son texto de sólo-lectura.
- Métodos de pago y cobertura como **dato** del sistema. En v1 son texto libre (ver decisión 5).
- Estadísticas de "qué preguntan más". Interesante y prescindible; la tabla de emisiones ya
  guardaría el rastro para hacerlo después.

## Decisiones

### 1. Coincidencia: palabra o frase completa, insensible al plural, sin *stemming*

Normalizar los dos lados igual —minúsculas, sin tildes, signos a espacio, espacios colapsados— y
buscar el trigger **rodeado de límites de palabra**. El truco es acolchar con espacios y preguntar
por contención: `" " + trigger + " " in " " + mensaje + " "`. Da semántica de palabra completa
también para frases de varias palabras (`"a que hora abren"`), sin regex.

Insensible a singular/plural: se prueba el trigger con y sin `s`/`es`. Es una frase de explicación
al dueño —*"no importa el singular o el plural"*— y es lo que evita el precipicio de que
`domicilio` no encuentre `domicilios`.

**Rechazado: *stemming* de sufijos genéricos.** Recortar tres caracteres haría que `pago` volviera a
encontrar `pagué`, que es el falso positivo más caro de la lista. Las flexiones verbales son trabajo
del dueño vía triggers explícitos, y la pantalla se lo dice.

Sobre la `ñ`: descomponer y quitar marcas convierte `mañana` en `manana`. Da igual — **los dos lados
reciben el mismo tratamiento**, y lo que importa es la consistencia, no la pureza lingüística.

Qué defensa mata qué:

```
                                  palabra completa   gate pedido vivo
"¿ya me lo enviaron?"                   ✅                  —
"ya pagué y no me llegó"                ✅                  —
"mi dirección es la calle 5"            ❌                  ✅
"mi domicilio queda cerca"              ❌                  ✅
```

Queda un residuo conocido: quien **no** tiene pedido vivo y manda su dirección igual recibe la de la
sede. Si un empleado había preguntado por ella, el hilo ya estaría en `human` y la FAQ calla; el caso
que sobrevive es alguien que la manda espontáneamente en un hilo `greeted`. Se acepta: la propiedad
de la decisión 2 lo deja en un mensaje bochornoso y nada más.

### 2. Dónde corre: sólo `greeted`, y contestar no cambia nada

| status | ¿contesta? | por qué |
|---|---|---|
| `new` | no | el saludo es dueño del primer mensaje |
| `greeted` | **sí** | es el hueco entero |
| `bot` | no | el LLM tiene herramientas y redacta mejor; dos voces en un hilo se notan |
| `human` | no | hay alguien atendiendo; interrumpir es peor que callar |
| `closed` | n/a | el hilo se reabre como `new` |

Que `new` quede fuera **sale gratis** y hay que dejarlo dicho para no romperlo al cablear: `conversation`
se lee **antes** de saludar (`manage_messaging.py`, comentado a propósito), así que el mensaje que
provoca el saludo sigue viendo `new` aquí. Sin eso, "¿dónde están?" como primer mensaje produciría
saludo **y** FAQ: dos automáticos por un entrante, cuando el saludo ya lleva el enlace.

El engarce, aprovechando el `bool` que hoy se tira:

```
handle_inbound
  ├─ _greet()                       → sólo `new`
  ├─ handled = _assist()            → `greeted`+opt-in, o `bot`
  └─ if not handled: _faq()         → `greeted` a secas
```

Son casi disjuntos. El único solape es `greeted` + `"1"`, que se queda el asistente — salvo cerrado,
donde calla, y entonces la FAQ tampoco puede contestar porque `1` es trigger reservado (decisión 4).

**La propiedad que sostiene el diseño**: contestar **no cambia el estado** de la conversación y **no
la saca de la bandeja**. Nadie se queda hablando con el bot; una persona ve el hilo igual. Es lo que
convierte un falso positivo en un bochorno recuperable en vez de un cliente perdido, y es la razón
por la que este change puede permitirse un matching tonto.

### 3. Gate de pedido vivo: qué es "vivo" y qué se hace si no se sabe

- **Vivo** = pedido del contacto (`orders.whatsapp_contact_id`) que no está entregado, cancelado ni
  cerrado.
- **Ventana** = la de inactividad de la conversación (`idle_hours`, 24 h por defecto). Sin ventana,
  un pedido abandonado hace tres semanas **silencia las FAQs para siempre** y nadie entiende por
  qué. Reusar `idle_hours` no es economía: es la misma pregunta —*"¿esto sigue vivo?"*— contestada
  con el mismo número que el dueño ya configuró.
- **Sólo por contacto**, nunca por cliente enlazado: lo único que se sabe con certeza es desde qué
  contacto escribió (mismo criterio que la herramienta `my_orders`).
- **Fallo leyendo → silencio.** Asimetría deliberada con el aviso de cerrado de esta semana, donde
  ante la duda se avisa: allí el silencio era una regresión, aquí el silencio **es el statu quo** del
  `greeted`. Contestarle un folleto a quien está a mitad de un pedido es el peor resultado posible.

Coste: una consulta indexada por entrante que llegue a esta etapa. Conviene comprobar que
`whatsapp_contact_id` está indexada y añadirlo si no.

### 4. Vocabulario reservado: una lista, dos usos, y rechazo por contención

Pedir persona (`humano`, `persona`, `asesor`, `agente`, `alguien`, `operador`), cancelar o devolver
(`cancelar`, `anular`, `devolver`, `reembolso`…) y el opt-in del asistente (`1`, `asistente`, `bot`)
**callan la FAQ** antes de mirar triggers. Y exactamente esa lista **se rechaza como trigger al
guardar**, con un 422 que nombra el culpable, igual que un marcador inexistente.

El rechazo compara **contención, no igualdad**, y esto es lo fino de la decisión:

```
FAQ "Política de cancelación", trigger "cancelaciones"
   ≠ "cancelar" → pasaría una validación por igualdad ✅
   mensaje "¿cómo hago una cancelación?" contiene "cancela" → silencio 🕳️
   → una FAQ encendida que no dispara nunca, sin nada que lo explique
```

Con contención, el 422 se convierte en la lección: *"«cancelaciones» contiene «cancela», y esos
mensajes los atiende una persona."* **Consecuencia aceptada: una FAQ de política de cancelación es
imposible.** Es coherente con la regla que ya está escrita —cancelar y devolver plata los ve una
persona— pero es lo primero que un dueño intentará construir, así que el mensaje de error tiene que
enseñar, no sólo prohibir.

**Casa de la lista: `shared/customer_channel/`**, junto a `CUSTOMER_STATES` que los dos módulos ya
importan. No son "palabras del asistente": son **las palabras que ya tienen dueño en el canal**, y
ahora las necesitan `messaging` (al guardar y al contestar) y `assistant` (al enrutar). Duplicarlas
con un comentario sería el precedente de la casa para *reglas espejadas entre capas* (el front espeja
`templates.py`), pero aquí las dos copias vivirían en el mismo lado de la misma frontera y derivarían
sin que nada lo note.

### 5. Cerrado sí, y por eso nace `{hours_line}`

Las FAQs contestan a cualquier hora. Una FAQ no promete atención —no dice "te respondemos"—, es un
cartel en la puerta, y las dos preguntas de la noche son justo el horario y la ubicación.

Eso rompe `{next_opening}` para la FAQ de horario: por diseño **salta las aperturas de hoy que ya
pasaron**, así que preguntando a las 2pm con horario 8:00–22:00 contesta "abrimos mañana a las 8:00".

```
A) {hours_today}   "hoy de 8:00 a 22:00"        → a las 11pm sigue diciendo "hoy de 8:00 a…" 🙃
B) {hours_line}    abierto  → "hoy hasta las 22:00"                          ← ELEGIDA
                   cerrado  → "cerrados; abrimos mañana a las 8:00"
C) dos textos por FAQ (abierto/cerrado), como el saludo → correcto, ×2 superficie de edición
```

**B**: un solo marcador, siempre correcto, contenido calculado. Y sigue siendo **un marcador dentro
de una frase que el dueño escribe** — no una línea que el código pega al final. Esa distinción no es
estética: la queja que originó todo este hilo de trabajo fue justo una línea pegada por el código
("Escribe *1*…") que no se podía quitar editando el texto. **Nada se añade automáticamente al final
de una FAQ.**

Métodos de pago y cobertura de domicilios se quedan **texto libre**: no hay fuente canónica de
métodos de pago, y la cobertura hoy son anillos por posición. Un `{payment_methods}` que se
desincronice de lo que Caja acepta de verdad es un pasivo con forma de marcador.

Tranquiliza el resto del recorrido: si alguien pregunta de noche y abre el enlace, el storefront ya
dice "abrimos a las X" y el checkout está bloqueado sin caja abierta (`409 cash_closed`). El cierre
no depende de que la FAQ lo diga.

### 6. Una emisión por `(conversación, FAQ)`

Tercera clase de clave en la tabla que ya existe: `faq:<conversación>:<id>`. Preguntar dos veces lo
mismo en un hilo recibe una respuesta; cuatro FAQs distintas dan un techo natural de cuatro
automáticos por hilo, el mismo orden de magnitud que el mapeo de estados.

Detalle de migración, **corregido al implementar**: se asumió que el id de FAQ necesitaría una
columna nueva, porque el docstring de la tabla enumera `conversation_id` / `order_id` /
`customer_state`. Al mirarlo de cerca, la unicidad de esa tabla NO vive en la tupla de columnas —
vive en una sola columna de texto, `dedupe_key`, precisamente porque en SQL dos NULL no son
iguales. Así que la clave nueva entra sin tocar el esquema: `emission_key` gana un parámetro
`detail` que forma parte de la clave y no tiene columna propia. Una columna sólo repetiría un
trozo de la clave sin una FK detrás; para auditar, el id se lee del propio `dedupe_key`.
**La migración 0031 acabó siendo una sola columna (`faqs`).**

**Rechazado: "no repetir si lo último que salió fue esta FAQ"** (el mecanismo del aviso de cerrado,
vía último mensaje saliente). Sirve para un aviso único y global; con N FAQs habría que comparar
contra N textos renderizados, y un texto editado a mitad de conversación rompería la comparación.
El reclamo por id no tiene ese problema.

### 7. Almacenamiento: columna JSON nullable, `null` ≠ `[]`

`faqs` como JSON en los ajustes del tenant, igual que `status_mapping` — configuración que se lee
entera y se escribe entera, sin consultas por dentro.

La fusión **no puede copiar** el patrón de `status_mapping`, y aquí está el bug que hay que evitar:

```
status_mapping   claves FIJAS (6 transiciones)  → fusionar por clave funciona
faqs             lista PROPIEDAD del dueño      → añade, borra, reordena
                                                  ↓
                 "no tengo FAQs" == "las borré todas"
                 → la FAQ borrada RESUCITA en el siguiente render
```

Misma clase de bug que el `armed` sin fila de las alertas. Se resuelve con la distinción
**`null` = nunca las tocó** (se siembran las sugeridas) frente a **`[]` = decidió que ninguna**, que
es lo que permite que "Restaurar sugeridas" y "borrarlas todas" coexistan sin revertirse la una a la
otra.

**Las sugeridas nacen apagadas.** El comentario del modelo de ajustes lo dice de la otra bandera:
*"Apagado por defecto: instalar este change no puede cambiar el comportamiento de nadie."* Sembrar
cuatro FAQs **encendidas** en tenants que ya están operando les cambiaría el canal sin pedirlo, y con
riesgo de falso positivo el primer día. El dueño las ve escritas, las lee y las enciende.

**Rechazado: tabla propia.** Reordenar sería una columna de posición y un `UPDATE` por fila para un
objeto que nunca se consulta por dentro y que se guarda entero desde una pantalla.

`FaqEntry` necesita además un campo que el brief no tenía: **`name`**. La UI pide nombre editable y
las sugeridas tienen nombre. El `id` lo acuña el front (`crypto.randomUUID`) y el backend valida
unicidad — es un blob de configuración, no una entidad.

### 8. Prioridad: orden de la lista, con flechas

El orden del array es la prioridad y gana la primera coincidencia. Se reordena con **↑↓**: cero
librerías (no hay ninguna de drag instalada), funciona con el pulgar en una app que es mobile-first
y funciona con teclado, que el drag no.

Dos detalles que se olvidan siempre y son parte del entregable:

- **El foco se pierde**: al mover un ítem al primer puesto, el ↑ que acabas de pulsar queda
  deshabilitado y el foco se va al `body`. Hay que reenfocar el control tras el movimiento.
- **El header se llena**: toggle + nombre + ↑ + ↓ + borrar en móvil no cabe. El **nombre se edita
  dentro de la tarjeta expandida**, no en el header (el brief lo quería en el header), y el header
  muestra el **puesto como cifra mono** — que además hace visible que el orden *es* la prioridad.
  Mono para etiquetas, el color reservado para calor y estado, como el resto de la casa.

**Rechazado: gana la coincidencia más específica** (frase más larga), que haría innecesario el orden
y quitaría el reordenar de la UI. Es más elegante y menos predecible: el dueño no puede *ver* por qué
ganó una FAQ, y "arrastra para ordenar" se explica en cinco palabras. Se descarta por explicabilidad,
no por dificultad.

### 9. Los defaults hay que reescribirlos

Palabra completa cambia qué triggers sirven. Los del brief, corregidos:

| FAQ | triggers sugeridos |
|---|---|
| Ubicación | `ubicacion`, `direccion`, `donde estan`, `donde queda`, `como llego` |
| Horario | `horario`, `a que hora abren`, `a que hora cierran`, `hasta que hora`, `estan abiertos` |
| Métodos de pago | `metodos de pago`, `medios de pago`, `como pago`, `aceptan tarjeta`, `aceptan nequi` |
| Domicilios | `domicilio`, `hacen entregas`, `hacen envios`, `delivery`, `llevan a` |

El cambio de fondo: **`pago` a secas desaparece**. Es la palabra del reclamo ("ya pagué", "el pago no
me llegó") y es el falso positivo con peor cara del conjunto. `direccion` se queda pese al riesgo
porque el gate de pedido vivo lo cubre y sin ella la FAQ de ubicación pierde la forma más común de
preguntar. Los plurales no se listan: los cubre la decisión 1.

## Riesgos

- **Falso positivo residual** (dirección espontánea sin pedido vivo). Mitigado por la propiedad de la
  decisión 2, no eliminado.
- **Silencio inexplicable** por el gate. Es carga de soporte real; se ataca con el texto de ayuda de
  la sección y con una traza en el log que diga cuál gate calló.
- **La `{hours_line}` de una sede sin horarios cargados** no tiene nada que decir. Debe degradar a
  omitir la frase, no a dejar el marcador crudo a la vista del cliente — misma excepción que ya hace
  `{order_items}` (el hueco lo lee un cliente, no el dueño en la pantalla de ajustes).
- **Mensajes largos**: un trigger dentro de un párrafo de cuarenta palabras probablemente no es una
  pregunta de FAQ. Se deja fuera de v1 a propósito (un umbral de longitud es un número inventado),
  pero es la primera palanca a añadir si aparecen falsos positivos.

## Preguntas abiertas (no bloqueantes)

- ¿Merece la FAQ de horario un trigger para "¿están abiertos ahora?" que conteste distinto a "¿qué
  horario tienen?" La `{hours_line}` ya cubre las dos con una frase; si no basta, es una FAQ más.
- ¿Se registra en algún sitio qué FAQ disparó, para que el dueño vea cuáles sirven? La tabla de
  emisiones lo guardaría gratis; explotarlo es otro change.
- ¿Debería `{hours_line}` estar disponible también en el saludo? Es inofensivo y útil, pero el saludo
  ya resuelve lo mismo con sus dos variantes. Fuera de alcance.
