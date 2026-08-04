## Why

El módulo avisa **una vez** por alerta y nunca más. Está escrito así a propósito: una alerta
abierta ocupa el sitio, y mientras exista la condición no vuelve a notificar. La razón está en el
docstring del ciclo de vida —*"una implementación ingenua avisa del mismo tomate cada cinco
minutos hasta que alguien la silencia, y a partir de ahí el módulo está muerto"*— y el miedo era
legítimo.

Pero el remedio estaba mal. Con el worker corriendo desde ayer, el resultado real fue: **un aviso,
a una hora en la que nadie miraba la pantalla, y silencio durante veinticuatro horas** con el stock
igual de bajo. Eso no es "no ser ruido": es no avisar. Un aviso que sale una vez y depende de que
justo en ese segundo alguien estuviera mirando no es un sistema de alertas, es una lotería.

El diagnóstico correcto es que al diseño le faltaba una salida, no repeticiones. Hoy una alerta
sólo se calla de dos maneras: **alguien la toma**, o **la condición desaparece**. Falta la tercera
—**"ya lo sé, cállate"**— y sin ella la repetición era efectivamente insoportable, porque no había
forma de pararla. Con las tres salidas, repetir deja de ser ruido y pasa a ser insistencia, que es
lo que un aviso operativo tiene que ser.

## What Changes

- **Recordatorio periódico** mientras la alerta siga abierta y sin tomar: `remind_every_minutes`
  por regla. `0` = no repetir (el comportamiento de hoy).
- **Tres salidas, y las tres paran los recordatorios**:
  1. **Tomarla** (`acknowledge`) — alguien se hace cargo. Ya existe.
  2. **Resolverse** — el stock subió por encima del umbral más el colchón. Ya existe.
  3. **Silenciar** — **nueva**. Deja de recordar ESTA alerta sin que nadie se haga cargo y sin
     mentir diciendo que se tomó. Es la salida que faltaba y sin la cual esto no se puede
     construir.
- **Los recordatorios del panel NUNCA salen por WhatsApp.** El panel cuesta cero y puede insistir
  cada 5 minutos; WhatsApp no.
- **WhatsApp insiste, pero en su propia escala: primero pronto, luego cada 4 horas.** El primer
  mensaje sale al cumplirse el plazo de escalado, que **pasa a ser 5 minutos por defecto** (hoy son
  30), y a partir de ahí uno cada 4 horas mientras nadie la tome, la resuelva o la calle. Son
  **6 mensajes al día como techo absoluto** por alerta, contra los 288 que saldrían a cadencia de
  panel. Esa diferencia es la que separa insistir de que te bloqueen el número.
- **Con 5 minutos, WhatsApp deja de ser "escalado" y pasa a ser un segundo canal principal**, y
  conviene decirlo: a los 5 minutos casi nadie ha tenido tiempo de mirar el panel, así que el
  primer mensaje va a salir casi siempre. Es una decisión de producto legítima —el dueño quiere
  enterarse en el teléfono, no en una pantalla— y sigue siendo por regla: `escalation_after_minutes`
  se puede subir, y `escalate_to_whatsapp` apagar.
- **Silenciar es por alerta, no por regla.** "Deja de avisarme de las servilletas" no puede
  significar "deja de avisarme de que falta stock". Al resolverse y volver a dispararse, la alerta
  nueva vuelve a recordar: el silencio muere con la alerta que silenció.
- **El suelo es el barrido.** El barrido corre cada 5 minutos, así que un recordatorio configurado
  por debajo de 5 se comporta como 5. Se dice en la pantalla en vez de dejar que alguien ponga 1 y
  concluya que está roto.
- **Un recordatorio se reclama antes de enviarse**, con el mismo `UPDATE … WHERE` que ya usan
  disparar, tomar y escalar. Dos barridos solapados no pueden mandar el mismo recordatorio dos
  veces.
- **La pantalla gana el botón de silenciar** y el editor de reglas gana el intervalo.

## Capabilities

### Modified Capabilities

- `alert-notifications`: el ciclo de vida gana el recordatorio periódico y su tercera salida; la
  regla gana el intervalo; el escalado a WhatsApp queda explícitamente fuera de la repetición.
- `frontend-alerts`: la tarjeta de una alerta gana la acción de silenciar y la señal de que está
  silenciada; el editor de reglas gana el intervalo con su suelo.

## Impact

- **Backend `alerts`**: `remind_every_minutes` en `AlertRule`; `last_notified_at` y
  `reminders_muted_at` en `Alert`; `claim_reminder` y `mute_reminders` en el repositorio;
  `remind_pending` en el ciclo de vida, llamado por el barrido junto a `escalate_pending`; un tipo
  de aviso nuevo (`NOTIFY_REMINDER`) que los canales distinguen del primero.
- **Migración 0035**: tres columnas. `remind_every_minutes` con `server_default` (ver abajo);
  las dos de la alerta, nullable.
- **Cambio de comportamiento al desplegar, y es el único**: `remind_every_minutes` nace en **5**
  para las reglas existentes, no en 0. Nacer en 0 sería desplegar el arreglo y que el que lo pidió
  siga sin recibir recordatorios hasta que descubra un ajuste nuevo. Cinco porque es lo que pide
  quien tiene el problema y porque coincide con el barrido, que es la cadencia más rápida que el
  sistema puede entregar de verdad.
- **Volumen de avisos en tiempo real**: sube, y es lo que se pide. Acotado por las tres salidas y
  por el suelo del barrido.
- **Volumen de WhatsApp**: sube de 1 por alerta a un máximo de 6 al día por alerta, y sólo
  mientras nadie haga nada con ella. Las tres salidas lo cortan en seco.
- **Sin permiso nuevo**: silenciar pide `alerts.read`, igual que tomar — quien puede tomarla puede
  callarla.
- **No rompe nada**: `remind_every_minutes = 0` reproduce exactamente el comportamiento actual, y
  ese es el valor que hace de escape si la insistencia molesta.

## Notes

Fuera de alcance, dicho para que no se pida como bug:

- **Silenciar por un rato** (posponer 2 horas). Silenciar aquí dura hasta que la alerta se resuelva.
  Un temporizador exige elegir una duración, y elegirla es una decisión que nadie quiere tomar con
  el teléfono en la mano y la cocina llena.
- **Recordar también las alertas ya tomadas.** Si alguien la tomó y cuatro horas después sigue sin
  resolverse, hoy nadie lo vuelve a mirar. Es un problema real, pero su solución es un plazo de
  "tomada y olvidada" con su propia escalada, no un recordatorio más.
