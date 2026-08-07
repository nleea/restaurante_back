## Why

Hay un hueco en el canal y es el más grande que queda. El pipeline de entrada tiene tres puertas
y una de ellas no lleva a ningún sitio:

```
entrante → persistir + timbre
   ├─ saludo      → sólo status `new`               una vez, sin leer el texto
   ├─ asistente   → sólo `bot` (o `greeted` + "1")  exige opt-in, derecho y horario
   └─ status == `greeted` a secas  →  N A D A. Espera a que una persona lo lea.
```

Y `greeted` es **la mayoría de las conversaciones**, porque entrar al bot exige que el cliente
escriba "1" y que el tenant tenga el asistente contratado. Hoy "¿dónde están?" a las nueve de la
noche no lo contesta nadie hasta mañana, teniendo el sistema la dirección de la sede guardada.

El ROADMAP del programa (`docs/messaging/ROADMAP.md`) dice que la tesis es *"casi todo lo que un
dueño llama «el bot de WhatsApp» no necesita un LLM"*, y trae una tabla de motores a 0 tokens:
saludo, enlace, horarios, voucher, "va en camino", handoff. **Las FAQs por palabra clave no están
en esa tabla ni en las cinco fases.** No es una idea descartada: es un motor gratis que se pasó, y
es el que convierte el canal en algo que contesta para el tenant que no paga asistente.

Contrapeso, y hay que decirlo de frente: **este módulo rechazó el keyword matching por escrito.**
`autoreply.py`, regla #1: *"Nada de detectar intención… una lista de palabras clave es una fábrica
de bugs."* Eso se escribió del **saludo** —decidir la PRIMERA respuesta por intención— y sigue
vigente: el saludo no lee el texto y este cambio no lo toca. Pero la advertencia aplica igual, y
los cuatro defaults obvios son justo donde muerde:

| trigger ingenuo | lo que escribe el cliente | lo que contestaría |
|---|---|---|
| `pago` | "ya **pagué** y no me llegó" | "aceptamos efectivo, Nequi y tarjeta" |
| `envían` | "¿ya me lo **enviaron**?" | folleto de cobertura, no el estado del pedido |
| `dirección` | "mi **dirección** es la calle 5 #3-20" | "estamos en Cra 5 #12-30" |
| `domicilio` | "mi **domicilio** queda cerca del mercado" | "sí, hacemos entregas…" |

Los dos primeros son colisiones de **flexión**: los mata la coincidencia por palabra completa. Los
dos últimos son un cliente **hablando de sí mismo en vez de preguntar**: esos sólo los mata saber
que tiene un pedido vivo. Las dos defensas no se solapan, y ninguna sola alcanza. Este cambio
existe si y sólo si trae las dos.

## What Changes

- **Coincidencia por palabra o frase completa**, insensible a mayúsculas, tildes y singular/plural.
  Sin substring, sin regex, sin NLP y **sin *stemming*** — "pagué" no puede matchear "pago".
- **Sólo en `greeted`.** No en `new` (el saludo es dueño del primer mensaje, y saludo + FAQ serían
  dos automáticos de golpe), no en `bot` (el LLM tiene herramienta de horarios y redacta mejor; dos
  voces en un hilo se notan), no en `human` (hay alguien atendiendo).
- **Gate de pedido vivo**: silencio si el contacto tiene un pedido sin terminar dentro de la
  ventana de inactividad. Si la lectura falla, **también silencio** — al revés que el aviso de
  cerrado, porque aquí el statu quo ya es el silencio y callar no rompe nada.
- **Pedir persona, cancelar o devolver calla la FAQ**, antes de mirar los triggers. Esa misma lista
  **se rechaza como trigger al guardar** (422, igual que un marcador inexistente) y se rechaza
  **por contención**, no por igualdad: si no, un trigger `cancelaciones` pasa la validación y luego
  no dispara nunca porque el mensaje contiene `cancela`. Consecuencia aceptada a ojos abiertos:
  **una FAQ de política de cancelación es imposible por diseño** — cancelar y devolver plata los ve
  una persona, que es la regla que ya está escrita.
- **Las FAQs contestan con el negocio cerrado.** Es la excepción deliberada a la regla que se
  acabó de escribir para el asistente: una FAQ no promete atención, es un cartel en la puerta, y
  "¿a qué hora abren?" es *la* pregunta de la noche.
- **Marcador nuevo `{hours_line}`**: abierto → "hoy hasta las 22:00"; cerrado → "cerrados; abrimos
  mañana a las 8:00". Nace porque `{next_opening}` **está mal para una FAQ de horario**: por diseño
  salta las aperturas de hoy que ya pasaron, así que a las 2pm contesta "abrimos mañana a las 8:00"
  — cierto e inútil. Y nada se pega automáticamente al final del texto: la queja que originó todo
  esto fue una línea que el código añadía y el dueño no podía quitar.
- **Contestar no cambia el estado ni saca el hilo de la bandeja.** Es la propiedad que hace
  sobrevivible un falso positivo: sale un mensaje bochornoso, no se pierde un cliente, porque nadie
  "se queda hablando con el bot" y una persona ve el hilo igual.
- **Una emisión por `(conversación, FAQ)`** con el reclamo único que ya existe. Techo natural de
  cuatro automáticos por hilo.
- **Almacenamiento JSON nullable**: `null` = nunca las tocó → se siembran las cuatro sugeridas;
  `[]` = decidió que ninguna. Sin esa distinción, "borrarlas todas" y "restaurar sugeridas" se
  pisan y una FAQ borrada **resucita** en el siguiente render.
- **Defaults reescritos** para palabra completa: se cae `pago` a secas (es la palabra del reclamo),
  entran los plurales y las variantes que la gente escribe de verdad.
- **Cuarta sección en la pantalla**, con el patrón visual de `StatusMappingSection`: tarjetas
  colapsables, chips para los triggers, prioridad con **flechas ↑↓** (cero librería nueva, funciona
  con el pulgar y con teclado) y el puesto como cifra mono en el header.

## Capabilities

### Modified Capabilities

- `whatsapp-autoreply`: gana un cuarto mecanismo de respuesta —el primero que **lee el texto** del
  cliente—, sus dos gates, el marcador `{hours_line}` y la clave de emisión de las FAQs. Se modela
  como ampliación y no como capability nueva a propósito: es exactamente lo mismo que ya hace esta
  capability (texto determinista sobre datos que el sistema tiene, cero tokens), y partirlo dejaría
  las reglas de emisión única y los ajustes por tenant repartidos en dos sitios.
- `frontend-whatsapp-settings`: gana la cuarta sección del editor, con la validación de marcadores
  extendida a los textos de las FAQs y el aviso explícito de cuándo una FAQ **no** contesta.

## Impact

- **Backend `messaging`**: módulo nuevo de dominio con la normalización y el matching como
  **funciones puras** (mismo criterio que `templates.py`: sin base, sin red, sin reloj); columna
  `faqs` en los ajustes; validación al guardar; una consulta nueva de "pedidos vivos de este
  contacto" en el puerto del repositorio (ya lee tablas de `orders` para `order_context` y
  `order_lines`, así que la flecha existe); clave de emisión nueva.
- **Migración 0031**: columna JSON nullable + hueco para el id de FAQ en la tabla de emisiones. Los
  tenants existentes nacen en `null`, así que ven las cuatro sugeridas — encendidas. **Es el único
  punto del change que cambia el comportamiento de alguien sin que lo pida**, y por eso las
  sugeridas nacen **apagadas** (ver `design.md`).
- **`shared/customer_channel`**: las listas de vocabulario reservado (`opt-in`, handoff, reembolso)
  suben ahí, junto a `CUSTOMER_STATES` que los dos módulos ya importan. No son "palabras del
  asistente": son las palabras que ya tienen dueño en el canal. Toca código de un change archivado
  (`assistant-core` pasa a leerlas de `shared`), sin cambio de comportamiento.
- **Frontend**: cuarta sección, tipo `FaqEntry`/`FaqSettings` en el contrato, `dirty` y guardado.
  Sin librerías nuevas.
- **Sin permiso nuevo**: la pantalla ya está gateada con `messaging.manage`, así que no hace falta
  volver a sembrar el catálogo.
- **Volumen de salida**: los automáticos suben, pero son todos **respuesta a un mensaje del
  cliente** (la clase segura) y están topados por la emisión única. La invariante del canal —nunca
  iniciar una conversación— se sigue cumpliendo sola.
- **Carga de soporte**: el gate de pedido vivo **silencia sin decir por qué**, y el dueño va a
  probar la feature escribiéndose a sí mismo con un pedido de prueba abierto. El texto de ayuda de
  la sección es parte del entregable, no decoración.
- **No rompe nada**: el motor sólo actúa en `greeted`, que hoy no produce ninguna respuesta.

## Notes

Deuda de spec detectada al escribir esto, **fuera de alcance de este change**: el requisito
`Assistant offer only when entitled` de `whatsapp-autoreply` ya no describe el comportamiento real
—la oferta también se omite con el negocio cerrado, el opt-in no entra en modo bot fuera de
horario, y el aviso de cerrado sale una vez por tanda y no por mensaje—. Merece un `sync` propio
para no atribuir a las FAQs un cambio que no es suyo.
