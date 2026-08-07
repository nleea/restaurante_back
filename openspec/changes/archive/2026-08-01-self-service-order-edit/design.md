## Context

Este cambio nace de descartar el camino obvio. La petición original era *"que el asistente pueda
modificar un pedido"*, y al mirarlo de cerca aparecieron cuatro riesgos nuevos, ninguno inherente
al problema:

1. `add_item` recibe **el precio de quien llama**. Un asistente que añade tiene que decidir ese
   número, y si sale de su contexto acabas vendiendo al precio de la carta de hace tres meses.
2. Las exclusiones son hoy **una cadena de texto** (`"Sin cebolla · tocar timbre, bebé dormido"`).
   Un modelo que la reescribe se come lo que ya decía, y la cocina no puede notar lo que ya no
   está escrito.
3. Confirmar antes de escribir exige sostener una intención entre turnos, y un "sí" suelto tras
   otra pregunta se resuelve **adivinando**.
4. Entre que el modelo lee "no ha empezado" y escribe, el cocinero puede empezar.

Mover la edición a una vista disuelve los cuatro: el catálogo está delante, los precios salen del
read-model, las exclusiones se ven marcadas y quien confirma es una persona mirando.

Lo que el sistema ya trae y este diseño se apoya en ello:

- Un pedido de la carta nace `open` y **deliberadamente sin entrar a cocina**; el personal lo
  confirma y lo envía. La ventana más común de edición es esa, donde no hay carrera con nadie.
- El estado de cocina no vive en el pedido: vive en **(ítem × estación)**, y el `kitchen_state`
  del pedido es un rollup derivado.
- "Pagado" es derivado (`payments_total >= total`) y **pagar no cierra la comanda**: un pedido
  pagado y todavía abierto es un estado real.
- Al quedar `ready`, el sistema **crea la entrega solo** y el pedido entra a Despacho.
- El read-model de la carta ya expone `removable_ingredients` por producto, que es exactamente lo
  que la vista necesita pintar.

## Goals / Non-Goals

**Goals:**
- Que el cliente resuelva solo el caso frecuente: se me olvidó decir *sin lechuga*, quiero queso
  extra, quiero otra hamburguesa.
- Que ninguna edición pueda dejar al negocio debiendo dinero.
- Que nada llegue a la cuenta sin llegar a la cocina.
- Que `assistant-core` siga siendo de sólo-lectura.

**Non-Goals:**
- Quitar, bajar cantidad y cancelar. Son de una persona, y no por dificultad técnica: son las que
  crean devoluciones y discusiones.
- Pedir conversando (`ConversationCart`). Este cambio lo vuelve **innecesario** para editar; sigue
  siendo su propio change si algún día se quiere pedir por chat.
- Editar desde el panel del personal. El personal ya tiene sus pantallas y más libertad que ésta.

## Decisions

### 1. Una invariante en vez de una lista de verbos

    el total del pedido resultante  >=  el total anterior

Enumerar operaciones permitidas envejece mal: la primera combinación que nadie previó se cuela.
Una invariante sobre el resultado atrapa lo que la lista no vio, y hace caer solo el caso que el
dueño describió — cambiar una gaseosa por otra del mismo precio vale, cambiarla por agua no —
sin escribir en ningún sitio "el cambio debe ser del mismo precio".

*Se comprueba sobre el resultado, nunca por pasos.* Un cambio de producto es "quitar y poner"; con
validación por paso el intermedio siempre baja el total y nada funcionaría.

```
   ┌─ edición ─────────────────────────────┐
   │  quita gaseosa negra    (total baja)  │  ← nadie mira aquí
   │  pone  gaseosa roja     (total sube)  │
   └───────────────────────────────────────┘
                     ↓
            total_final >= total_inicial     ← aquí se decide
```

*Alternativa considerada:* permitir bajar y compensar con devoluciones. Rechazada: mete a la caja,
al arqueo y al cobro en la puerta en lo que debería ser corregir una lechuga.

### 2. Dos ventanas, porque son dos preguntas distintas

**Por ítem** — sólo si ninguna de sus estaciones pasó de `pending`. Es la granularidad correcta: la
limonada ya lista no puede impedir corregir la hamburguesa que aún no entró a la plancha.

**Por pedido** — la vista se apaga entera cuando **la comida deja de estar al alcance**. Y eso no
es "la cocina terminó": es un hecho físico que depende de cómo sale el pedido.

```
  sin cocina │ en cocina        │ ready, aún  │ in_transit │ entregado
             │                  │ en el pase  │            │
  ───────────┼──────────────────┼─────────────┼────────────┼──────────
  añadir  ✅ │ ✅ (auto-envía)  │     ✅      │     ❌     │    ❌
  notas   ✅ │ ✅ si ese ítem   │     ✅      │     ❌     │    ❌
             │    no empezó     │             │            │

  domicilio  → cierra en `in_transit`
  recoger/mesa → cierra en `ready` (no hay "salir": la comida espera en el mostrador)
```

Entre `ready` y `in_transit` pasan cosas normales: la bolsa está en el pase, el domiciliario no
ha llegado, o llegó y espera. Añadir unas papas ahí es perfectamente posible — el cocinero las
hace y el domiciliario espera dos minutos. Con la moto andando no hay nada que hacer.

*Consecuencia asumida:* añadir después de `ready` devuelve el pedido a `in_kitchen` y el tablero
de Despacho lo verá dejar de estar listo. Eso es **información correcta** para quien despacha
—*esto todavía no sale*—, no un efecto colateral que haya que ocultar.

*Alternativa considerada:* cerrar en `ready` para todos. Rechazada por conservadora: prohíbe algo
que en el local se resuelve solo, y trata igual una bolsa en el pase que una bolsa en la moto.

*El estado se relee al escribir.* Lo que la vista pintó hace veinte minutos no autoriza nada: entre
pintar y confirmar el cocinero pudo empezar, y quien manda es la base en el instante de escribir.
La vista puede mentir sin querer; el endpoint no.

### 3. Con pago, las líneas existentes sólo crecen

Un pedido pagado puede seguir abierto, así que "ya pagó" es un estado real y editable. Ahí la regla
se estrecha: se pueden añadir adiciones y cantidad a una línea, pero **no cambiar su producto**.

El motivo no es el dinero —un cambio a algo más caro también sube el total— sino el registro: si
mañana hay una discusión de *"yo pagué por una gaseosa negra"*, tiene que poder contestarse. Y de
ahí sale una consecuencia limpia de implementación: **sobre un pedido pagado, añadir crea líneas
nuevas**, nunca edita las viejas. Lo pagado queda congelado y lo nuevo se ve aparte.

|  | sin pago | con pago |
|---|---|---|
| añadir línea / cantidad / adición | ✅ | ✅ |
| notas | ✅ | ✅ |
| cambiar el producto de una línea | ✅ (si no baja) | ❌ |
| quitar / bajar / cancelar | ❌ | ❌ |

### 4. Token por pedido, no el token del chat

El token del chat identifica **al contacto**. Reutilizarlo convertiría un enlace reenviado sin
pensar en *"cualquiera edita todos tus pedidos"*. Un token por pedido acota el daño a ese pedido y,
de paso, sirve al cliente que pidió por la web y nunca escribió por WhatsApp.

Es una **URL-capacidad**: quien la tiene, edita. Por eso su caducidad es parte del diseño y no un
ajuste, y por eso un token vencido, desconocido o de otro tenant tienen que ser indistinguibles —
si no, el enlace sirve para averiguar qué pedidos existen.

### 5. Lo añadido se envía solo a cocina

`add_item` deja los ítems sin enrutar **a propósito**: el personal compone la comanda y luego la
manda, de modo que un toque equivocado no está ya cocinándose. Por esta vía no hay personal
componiendo. Si el pedido ya está en cocina y lo añadido se queda `pending`, el resto se cocina,
las papas no, y aparecen en la cuenta — que es peor que no haber dejado añadir.

*Alternativa considerada:* avisar al personal para que lo mande. Rechazada para la primera versión:
convierte un cambio del cliente en una tarea de alguien, y si nadie la ve, el fallo es el mismo.

### 6. El asistente enruta; sigue sin escribir

    "quiero queso extra"        →  enlace de ESE pedido
    "quítame la gaseosa"        →  una persona

Mandar al enlace a quien quiere quitar algo es una respuesta equivocada, no una a medias: llega a
una pantalla que no hace lo que pidió. Clasificar de qué tipo es la petición es justo lo que un
modelo hace bien, y no requiere que toque nada.

Y una asimetría deliberada: **el horario apaga al asistente, no a la vista.** El asistente calla
porque no hay nadie detrás; la vista depende del estado del pedido, y corregir a las 11 de la noche
un pedido que nadie ha empezado no molesta a nadie.

## Risks / Trade-offs

- **El enlace es una capacidad.** Quien lo tenga edita ese pedido. Se acota con la vida del token y
  con que sólo un pedido esté detrás, pero no se elimina: es el mismo trato que cualquier enlace de
  seguimiento de un pedido.
- **Un ticket nuevo a mitad de servicio.** La cocina puede ver aparecer algo cuando ya estaba
  cerrando ese pedido. El KDS es en vivo, así que se ve; que sea *cómodo* es otra cosa, y es la
  primera candidata a ajustarse con uso real.
- **Un pedido saldado puede volver a deber.** El sistema ya lo maneja (cerrar exige estar saldado),
  pero ahora pasará más a menudo, y la diferencia la cobra alguien en la puerta. Si la vista no lo
  enseña con todas las letras, la discusión ocurre allí.
- **La carrera con la cocina no desaparece, se acota.** Releer al escribir la reduce a la ventana
  de una petición; lo que queda se resuelve rechazando, que es la respuesta correcta.
- **No poder quitar es una frustración real.** Es una decisión de producto consciente: la
  alternativa era abrir devoluciones. El coste se paga en que la vista lo explique bien y ofrezca
  una persona en vez de esconder el botón.
