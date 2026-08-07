## Context

El módulo de alertas está construido alrededor de una idea explícita: **no convertirse en ruido**.
Tres mecanismos la sostienen —el disparo se reclama contra un índice único parcial, la histéresis
es asimétrica y obligatoria, y un canal caído pierde el aviso pero no el hecho—, y el docstring del
ciclo de vida lo remata: *"preferimos un aviso perdido a cuarenta repetidos"*.

Con el worker corriendo un día entero, ese diseño produjo: un aviso, a una hora en la que nadie
miraba, y silencio. La condición seguía siendo verdad todo el tiempo.

La frase del docstring es correcta como advertencia y equivocada como diseño. "Un aviso perdido"
no es el precio de evitar cuarenta repetidos: es el fallo, porque **avisar una vez es avisar a
quien estuviera mirando en ese segundo**. Lo que hacía insoportable la repetición no era la
repetición: era que sólo se podía parar tomando la alerta (mentir: "me hago cargo") o esperando a
que la condición desapareciera sola. Faltaba decir "ya lo sé".

## Goals / Non-Goals

**Goals:**

- Que una alerta abierta siga avisando hasta que alguien haga algo con ella.
- Que "algo" sean tres cosas y las tres estén a un toque: tomarla, resolverla, callarla.
- Que la insistencia no pueda costar dinero ni el número de WhatsApp del negocio.
- Que quien despliegue esto reciba recordatorios sin tener que descubrir un ajuste nuevo.

**Non-Goals:**

- **Posponer con temporizador** ("recuérdamelo en 2 horas"). Ver decisión 5.
- **Recordar alertas ya tomadas.** Tomada y olvidada es un problema real y distinto; su solución
  es un plazo propio con su escalada, no un recordatorio más.
- **Recordatorios por WhatsApp.** Decisión 3. No es una limitación temporal: es la regla.
- **Silenciar una regla entera** desde el panel. Para eso está apagarla en la pantalla de reglas,
  que ya existe y ya pide `alerts.manage`.
- **Un historial de cuántas veces se recordó.** Se guarda la última vez, no la lista.

## Decisions

### 1. La tercera salida es lo que hace construible el resto

```
                     ┌── tomar ────────► acknowledged
   fired ── recuerda ─┼── silenciar ───► fired, callada
                     └── resolverse ──► resolved ──► armed (pasado el colchón)
```

**Silenciar no es tomar, y la diferencia importa.** Tomar registra quién se hace cargo; es una
afirmación sobre una persona y el panel la muestra. Silenciar no registra a nadie: es "ya lo sé,
el proveedor viene el viernes". Si la única forma de callar una alerta fuera tomarla, el registro
de quién atiende qué se llenaría de mentiras en una semana y dejaría de servir para nada.

**Alternativa descartada:** un solo botón "visto" que hiciera las dos cosas. Más simple de
construir y destruye el único dato que hace útil el panel — quién está en qué.

### 2. Silenciar muere con la alerta

`reminders_muted_at` vive en la fila de la alerta, no en la regla. Cuando la condición se resuelve,
la alerta se cierra y con ella el silencio; si vuelve a dispararse, la alerta nueva recuerda otra
vez.

**Por qué no un silencio por regla o por sujeto con caducidad:** "deja de avisarme de las
servilletas" no puede acabar significando "deja de avisarme de que falta stock", y un silencio que
sobrevive a la resolución convierte un olvido de hace tres semanas en la razón por la que hoy no
suena nada. El silencio tiene que morir con el problema que silenció.

### 3. Dos cadencias, no una: el panel cada 5 minutos, WhatsApp cada 4 horas

El ciclo de vida ya tiene **dos listas de canales separadas** —`channels` (tiempo real, siempre) y
`escalation_channels` (WhatsApp, sólo en el worker)—. Ahora las dos insisten, **con relojes
distintos**, y la separación pasa de ser "quién avisa" a ser "cada cuánto puede".

```
panel     ├─ 0min ─┼─5─┼─5─┼─5─┼─5─┼─5─┼─5─┤   288/día como techo
whatsapp  ├─ 5min ─┼──────── 4h ───────┼── 4h ──┤     6/día como techo
```

`escalated_at` deja de ser "ya escaló" y pasa a ser `last_escalated_at`: **cuándo fue la última
vez**. El primer envío sigue rigiéndose por `escalation_after_minutes` —que baja de 30 a **5** por
defecto— y los siguientes por `WHATSAPP_REESCALATION_HOURS = 4`.

**Los dos números hacen cosas distintas y por eso uno es configurable y el otro no.** El primero
dice *cuándo el negocio quiere enterarse* y es asunto suyo: 5 minutos si quiere saberlo en el
teléfono, una hora si prefiere que alguien mire el panel antes. El segundo acota *cuántos mensajes
puede llegar a mandar ese número en un día*, y eso no es asunto de ninguna regla: quien paga un
mensaje de más no es el dueño, es el número, y bloquearlo deja mudo todo el WhatsApp del
restaurante, pedidos incluidos.

Consecuencia asumida de bajar a 5: **el primer mensaje va a salir casi siempre**, porque en cinco
minutos nadie ha mirado el panel. WhatsApp deja de ser "lo que pasa cuando fallamos" y pasa a ser
el canal principal para el dueño. Es legítimo —es lo que pidió— y el techo de 6/día sigue en pie.

**Cuatro horas fijas y no un valor por regla.** Un ajuste por regla es un ajuste para ponerlo en
15 minutos el día que algo urge, y ese día es exactamente el que hay que impedir. Si alguna vez ha
de moverse, se mueve en el código, con alguien leyendo por qué era 4.

Sigue habiendo un interruptor por regla, y es el que ya existe: `escalate_to_whatsapp`. Apagado, no
sale nada. Encendido, sale a la cadencia del canal, no a la que a nadie se le ocurra.

### 4. Nace en 5, no en 0

`remind_every_minutes` llega con `server_default = 5` para las reglas que ya existen.

Rompe la costumbre de la casa —"instalar esto no puede cambiarle el comportamiento a nadie"— y se
hace a ojos abiertos: **el comportamiento actual es el defecto que este change arregla**. Nacer en
0 significaría desplegar el arreglo y que quien lo pidió siga sin recibir recordatorios hasta que
descubra por su cuenta un campo nuevo en una pantalla de ajustes.

Cinco minutos porque es lo que pidió quien tiene el problema, y porque coincide con el barrido:
es la cadencia más rápida que el sistema puede entregar de verdad, así que cualquier valor menor
sería una promesa que no se cumple. Quien lo quiera más callado sube el número; quien no quiera
ninguno pone 0, y eso reproduce exactamente lo de hoy.

### 5. Sin temporizador de posposición

Silenciar dura hasta que la alerta se resuelva. Nada de "recuérdamelo en 2 horas".

**Por qué:** elegir una duración es una decisión, y la persona que pulsa esto tiene el teléfono en
una mano y la cocina llena. Un desplegable de duraciones convierte un gesto de un toque en tres, y
el que no lo quiera usar acabará tomando la alerta —mintiendo— porque es más rápido. Si algún día
hace falta, `reminders_muted_at` admite convertirse en `reminders_muted_until` sin migración de
datos.

### 6. El recordatorio se reclama antes de enviarse

`claim_reminder` es un `UPDATE alerts SET last_notified_at = :now WHERE id = :id AND status =
'fired' AND reminders_muted_at IS NULL AND last_notified_at <= :due RETURNING`, y sólo el que toca
una fila envía.

Es la **cuarta aparición de la misma idea** en el proyecto —el disparo, la toma, el escalado y
ahora esto—, mantenida igual a propósito. Reclamar-antes-de-enviar además ordena bien el fallo: un
canal que revienta pierde ese recordatorio, y el siguiente llega en un intervalo. Al revés
—enviar y luego marcar— un canal lento produciría recordatorios duplicados, que es exactamente lo
que la gente odia de las alertas.

`last_notified_at` se estampa **también al disparar**, para que el primer recordatorio caiga un
intervalo después del aviso inicial y no inmediatamente en el barrido siguiente.

### 7. El suelo es el barrido, y se dice

El barrido corre cada 5 minutos (`SWEEP_MINUTE_STEP`), así que un intervalo de 1 minuto produce
recordatorios cada 5. No se rechaza al guardar: se **dice en la pantalla**. Rechazarlo obligaría a
acoplar la pantalla de reglas a una constante del worker, y el día que el barrido baje a 1 minuto
las validaciones guardadas seguirían mintiendo.

### 8. El aviso dice que es un recordatorio

Tipo de aviso nuevo, `NOTIFY_REMINDER`, junto a `NOTIFY_FIRED` y `NOTIFY_ESCALATED`. Un
recordatorio que llega con el mismo texto que el primero se lee como un problema nuevo, y a la
tercera vez el panel parece estar contando cuatro alertas donde hay una.

## Risks / Trade-offs

- **Esto es, literalmente, lo que el módulo se escribió para no hacer →** mitigado por las tres
  salidas (decisión 1), por el `0` que reproduce lo de hoy, y por que el canal caro queda fuera. La
  advertencia del docstring se reescribe, no se ignora: pasa de "no repetimos" a "repetimos, y por
  eso callar tiene que costar un toque".
- **5 minutos por defecto le cambia el comportamiento a todos al desplegar →** asumido y
  explicado (decisión 4). Es un aviso en la pantalla cada cinco minutos sobre algo que ya estaba
  encendido y que nadie ha tocado, no un mensaje a nadie. Lo apaga tomarlo, resolverlo o callarlo.
- **Una tanda de alertas simultáneas produce una tanda de recordatorios simultáneos →** son avisos
  en tiempo real, que cuestan cero; y si molestan, molestan de la forma correcta: hay algo que
  arreglar.
- **Silenciar puede usarse para tapar** un problema real sin que nadie se entere → el panel sigue
  listando la alerta como abierta y marcada como silenciada. Se ve que alguien la calló; lo que no
  hay es a quién culpar, y eso es a propósito.

## Migration Plan

1. Migración `0035`: `alert_rules.remind_every_minutes` (`INTEGER NOT NULL DEFAULT 5`, ver
   decisión 4) y `alerts.last_notified_at` / `alerts.reminders_muted_at` (nullable).
2. Las alertas abiertas al desplegar tienen `last_notified_at` en `NULL`. Se tratan como debidas y
   reciben un recordatorio en el primer barrido — **que es exactamente lo que se quiere**: son las
   alertas que llevan un día calladas.
3. Backend y frontend son aditivos; se despliegan juntos.
4. **Rollback**: revertir el código deja las columnas sin lector. Nada depende de ellas y ninguna
   alerta se pierde: se vuelve a avisar una sola vez.

## Open Questions

Ninguna.
