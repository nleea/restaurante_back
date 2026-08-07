> Lee `design.md` antes de empezar. Este change hace **justo lo que el módulo se escribió para no
> hacer**, y sólo es defendible si trae las tres salidas completas (grupos 2 y 5) y deja WhatsApp
> fuera (grupo 3). Si al terminar un recordatorio puede salir por WhatsApp, el change ha fallado
> aunque los recordatorios funcionen.
>
> Orden: 1 → 2 → 3 → 4 (backend completo y probado) → 5 → 6. El 7 al final.

## 1. Backend — almacenamiento

- [x] 1.1 Migración `0035`: `alert_rules.remind_every_minutes` (`INTEGER NOT NULL DEFAULT 5`) y
      `alerts.last_notified_at` / `alerts.reminders_muted_at` (nullable)
- [x] 1.2 **El `DEFAULT 5` es deliberado y va explicado en el docstring de la migración**: nacer
      en 0 sería desplegar el arreglo y que quien lo pidió siga sin recordatorios (design §4)
- [x] 1.3 Campos en `AlertRule` (`remind_every_minutes: int = DEFAULT_REMIND_MINUTES`) y en `Alert`
      (`last_notified_at`, `reminders_muted_at`), con el round-trip del repositorio
- [x] 1.4 Prueba de que una alerta abierta ANTES del change (`last_notified_at IS NULL`) se trata
      como debida — son justo las que llevan un día calladas

## 2. Backend — el recordatorio y sus tres salidas

- [x] 2.1 `claim_reminder(tenant_id, alert_id, now, due_before)`: `UPDATE … SET last_notified_at
      WHERE status='fired' AND reminders_muted_at IS NULL AND (last_notified_at IS NULL OR
      last_notified_at <= due_before) RETURNING`. Sólo el que toca una fila avisa
- [x] 2.2 `list_pending_reminders(now)` uniendo alerta y regla, saltando `remind_every_minutes = 0`
- [x] 2.3 `NOTIFY_REMINDER` como tipo de aviso, junto a `NOTIFY_FIRED` y `NOTIFY_ESCALATED`: un
      recordatorio con el mismo texto que el primero se lee como un problema nuevo (design §8)
- [x] 2.4 `remind_pending()` en el ciclo de vida, llamado por el barrido junto a `escalate_pending`
- [x] 2.5 `last_notified_at` se estampa **también al disparar**, para que el primer recordatorio
      caiga un intervalo después y no en el barrido siguiente
- [x] 2.6 `mute_reminders(alert_id)`: sella `reminders_muted_at` y **no toca `status` ni
      `acknowledged_by`**. Silenciar no es tomar, y ésa es la diferencia que sostiene el panel
- [x] 2.7 Pruebas de las tres salidas: tomada no recuerda, resuelta no recuerda, silenciada no
      recuerda — y una abierta sin tocar SÍ recuerda
- [x] 2.8 Prueba de que silenciar deja la alerta abierta, sin dueño y sin `acknowledged_at`
- [x] 2.9 Prueba de que el silencio muere con la alerta: resolver y volver a disparar recuerda
- [x] 2.10 Prueba de concurrencia: dos reclamos del mismo recordatorio, uno solo envía
- [x] 2.11 Prueba de que recordar NO crea una alerta nueva ni mueve `fired_at`

## 3. Backend — WhatsApp con su propio reloj

- [x] 3.1 `remind_pending` usa **sólo** `self._channels`, nunca `self._escalation`: un
      recordatorio del panel no puede provocar un mensaje
- [x] 3.2 `escalated_at` pasa a `last_escalated_at` (mismo dato, otro significado: la ÚLTIMA vez).
      Sin columna nueva
- [x] 3.3 `DEFAULT_ESCALATION_MINUTES` de 30 a **5**: el primer WhatsApp sale a los 5 minutos. Va
      en la migración `0035` junto al resto, con el `server_default` de la columna
- [x] 3.4 `WHATSAPP_REESCALATION_HOURS = 4` como constante del módulo, **no** como campo de la
      regla. El comentario tiene que decir por qué no es configurable (design §3)
- [x] 3.5 `escalate_pending` re-escala pasadas 4 h desde `last_escalated_at`, reclamando antes de
      enviar igual que hoy
- [x] 3.6 Prueba del ritmo entero: a los 5 min sale el primero; a las 2 h **no** sale nada; a las
      4 h sale el segundo
- [x] 3.7 Prueba del techo: 24 h de alerta ignorada producen **6 mensajes**, ni uno más
- [x] 3.8 Prueba de que las tres salidas cortan también el escalado, no sólo los recordatorios
- [x] 3.9 Prueba de que sin canal de escalado configurado los recordatorios del panel siguen
      llegando

## 4. Backend — API

- [x] 4.1 `POST /alerts/{id}/mute` con `alerts.read` —quien puede tomarla puede callarla— y
      `remind_every_minutes` en el esquema de la regla (lectura y guardado)
- [x] 4.2 `reminders_muted_at` en la respuesta de una alerta, para que el panel lo pueda pintar
- [x] 4.3 Pruebas de API: silenciar responde la alerta ya silenciada; sin permiso, 403; silenciar
      dos veces no rompe

## 5. Frontend — el panel

- [x] 5.1 Acción "Silenciar" en `AlertCard`, sólo en las abiertas sin tomar
- [x] 5.2 Una alerta silenciada se sigue listando y **dice que lo está**, distinta de una tomada
- [x] 5.3 Decir el alcance en el propio gesto: sólo esta alerta, sólo mientras siga abierta. Sin
      eso se lee como "apagar la regla" y nadie lo va a pulsar
- [x] 5.4 Pruebas: silenciar llama al endpoint, la tarjeta lo refleja, y una silenciada no aparece
      como tomada por nadie

## 6. Frontend — la pantalla de reglas

- [x] 6.1 Campo de intervalo de recordatorio por regla
- [x] 6.2 Decir que `0` = avisa una vez y no insiste, como elección explícita y no como hueco
- [x] 6.3 Decir el suelo del barrido: por debajo de 5 minutos los recordatorios llegan cada 5. Sin
      esto alguien pone 1 y concluye que está roto (design §7)
- [x] 6.4 Pruebas de la sección

## 7. Cierre

- [x] 7.1 Reescribir el docstring de `lifecycle.py`: la regla ya no es "preferimos un aviso perdido
      a cuarenta repetidos" sino "repetimos, y por eso callar cuesta un toque". Dejarlo como está
      haría que el siguiente lector borrara esto por contradecir el módulo
- [x] 7.2 Documentar el ciclo con las tres salidas donde viva la doc de alertas
- [x] 7.3 Puertas verdes: `ruff`, `mypy`, suite de backend, `vitest`, `type-check` y `eslint`
- [ ] 7.4 Comprobar contra el entorno real: bajar un stock, ver el aviso, esperar el recordatorio,
      silenciarlo y comprobar que se calla
