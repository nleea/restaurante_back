## Context

Las alertas ya llegan al navegador: el store abre un SSE con sondeo de reserva y refresca el panel.
Lo que falta no es el dato, es que **salga de la pestaña**. Durante un servicio nadie tiene abierta
la pantalla de alertas: están en Caja, en Comandas o en el KDS.

Con `alert-reminders` esto pasa de carencia a defecto activo: el sistema insistiría cada cinco
minutos en un sitio donde no hay nadie.

## Goals / Non-Goals

**Goals:**

- Que una alerta se vea sin estar en la pantalla de alertas.
- Que se oiga cuando la pantalla no se mira, que es la mitad del turno en una cocina.
- Que no se gaste el permiso del navegador, porque sólo se puede pedir bien una vez.

**Non-Goals:**

- **Web Push** (avisar con el navegador cerrado). Ver "Riesgos".
- **Notificar cada recordatorio.** Decisión 3.
- **Preferencia sincronizada entre dispositivos.** Es del aparato, no de la persona.
- **Notificar otra cosa que no sean alertas.** El transporte queda reusable; engancharlo a
  comandas o al domiciliario es de quien lo necesite.

## Decisions

### 1. El permiso se pide con el gesto, jamás al cargar

`Notification.requestPermission()` sólo se llama desde el `click` que enciende las notificaciones.

**Por qué importa tanto:** un `denied` es **permanente desde la página**. No hay segundo intento:
para revertirlo hay que entrar a los ajustes del navegador, y nadie lo hace. Pedirlo al cargar es
la forma conocida de conseguir un `denied` de alguien que ni sabía qué le estaban preguntando, y a
partir de ahí la feature está muerta para ese dispositivo para siempre.

### 2. Tres señales, y la más tonta es la que nunca falla

| señal | necesita permiso | sirve con la pestaña de fondo | sirve con el navegador cerrado |
|---|---|---|---|
| Notificación del sistema | sí | sí | **no** |
| Sonido | no | sí | no |
| Contador en el título | no | sí (al volver) | no |

El contador del título es la que sobrevive a todo —permiso denegado, navegador sin soporte— y por
eso no es opcional ni configurable: se pinta siempre.

### 3. Una notificación por alerta, no por recordatorio

El panel insiste cada 5 minutos; el escritorio, una vez por alerta.

**Por qué:** una notificación del sistema es intrusiva por diseño. Repetirla cada cinco minutos
consigue que la persona la apague, y cuando la apaga la apaga **para todo**, incluida la alerta de
mañana que sí importaba. La insistencia tiene que vivir donde es barata (el panel) y donde cuesta
(WhatsApp, cada 4h) — el escritorio está en medio y su cadencia correcta es "una vez, cuando pasa".

Se lleva un conjunto de ids ya notificados en memoria de la sesión. Recargar la página no reproduce
las alertas viejas: al cargar se siembra el conjunto con lo que ya había, y sólo notifica lo que
aparece **después**.

### 4. El sonido, apagado por defecto y con data-URI

Apagado porque un sonido inesperado en un local es peor que ningún sonido. Data-URI corto y no un
fichero: un `.mp3` por red es una petición que puede fallar justo cuando hace falta, y el aviso se
perdería en silencio.

### 5. Preferencia en `localStorage`, no en el perfil

Es del dispositivo: el permiso del navegador ya lo es, así que guardar la preferencia en el
servidor produciría el estado imposible de "encendido según su cuenta, denegado según su navegador".
Un mesero que apaga el sonido en su tablet no se lo apaga a la de al lado.

### 6. Capability propia, no parte del panel

`browser-notifications` describe un **transporte**. El día que las comandas quieran avisar así,
reusan el composable; si esto viviera dentro de `frontend-alerts`, lo copiarían.

## Risks / Trade-offs

- **Con el navegador cerrado no llega nada.** Es la limitación de la API y no se disimula: el panel
  lo dice al encenderlas. El hueco lo cubre el escalado a WhatsApp, que con `alert-reminders`
  insiste cada 4 horas. Cerrarlo del todo es Web Push —service worker, VAPID, tabla de
  suscripciones, emisor en el servidor— y tiene que justificarse como change propio.
- **El usuario puede denegar y quedarse sin la señal principal** → quedan el título y el sonido, y
  el panel explica que se reactiva en el navegador, no en la app.
- **Varias pestañas abiertas notifican varias veces** → aceptado. La alternativa (coordinar
  pestañas con `BroadcastChannel` y elegir una "líder") es maquinaria real para un molestia menor,
  y `tag` en la notificación ya hace que el sistema colapse las repetidas de la misma alerta.
- **Un turno con muchas alertas produce muchas notificaciones** → una por alerta, y las alertas
  están acotadas por sujeto. Si son muchas, es que hay muchos problemas.

## Migration Plan

Sólo frontend y aditivo. Nadie recibe una notificación hasta que la enciende: el estado inicial es
"apagado" y sin permiso pedido.

**Rollback**: quitar el código deja una clave huérfana en `localStorage` de cada dispositivo. Nada
depende de ella.

## Open Questions

Ninguna.
