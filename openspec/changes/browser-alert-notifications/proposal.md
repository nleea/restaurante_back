## Why

Hoy una alerta sólo existe **dentro de la pantalla de alertas**. Quien está en Caja, en Comandas o
en otra pestaña no se entera de nada, y ése es el estado normal de todo el mundo durante un
servicio: nadie tiene abierta la pantalla de alertas, porque su trabajo está en otra.

Con los recordatorios de `alert-reminders` el problema no se arregla, se multiplica: el sistema
insistiría cada cinco minutos en un sitio donde nadie está mirando. Un aviso que sólo se ve
entrando a buscarlo no es un aviso, es un informe.

## What Changes

- **Notificación del sistema operativo** cuando salta una alerta, mientras haya una pestaña de la
  app abierta —aunque esté de fondo, minimizada o detrás de otra ventana—. Es la API de
  notificaciones del navegador; no hace falta nada del servidor.
- **Permiso pedido en el momento correcto**: nunca al entrar. Se pide cuando el usuario enciende
  las notificaciones desde el panel de alertas, con el gesto delante. Pedirlo al cargar es la forma
  conocida de que lo denieguen para siempre, y el navegador no da segunda oportunidad.
- **Sonido corto y opcional**, apagado por defecto. En una cocina la pantalla no se mira; el oído
  es el único canal que queda.
- **Contador en el título de la pestaña** (`(2) El Pase`). Es el único aviso que sobrevive con el
  permiso denegado, y no pide permiso a nadie.
- **Un aviso por alerta, no por recordatorio.** Los recordatorios cada 5 minutos son para el panel;
  convertir cada uno en una notificación del escritorio sería exactamente la razón por la que la
  gente las desactiva.
- **Tocar la notificación abre esa alerta** en el panel, en su sucursal.
- **Todo vive en el navegador de cada persona**: preferencia y permiso son de ese dispositivo. Un
  mesero con el sonido apagado en su tablet no se lo apaga a nadie más.

## Capabilities

### New Capabilities

- `browser-notifications`: el permiso, la preferencia por dispositivo, la emisión de una
  notificación del sistema, el sonido y el contador del título. Capability propia y no parte de
  `frontend-alerts` porque es un **transporte**, no una pantalla: el día que las comandas o el
  domiciliario quieran avisar así, reusan esto y no copian el panel de alertas.

### Modified Capabilities

- `frontend-alerts`: el panel gana el interruptor de notificaciones y el estado del permiso, y es
  quien alimenta al transporte con las alertas nuevas.

## Impact

- **Sólo frontend. Cero backend, cero migración, cero endpoint.** Las alertas ya llegan al
  navegador por SSE con sondeo de reserva; esto sólo las convierte en algo visible fuera de la
  pestaña.
- **`composables/useBrowserNotifications.ts`**: permiso, emisión, sonido, contador del título.
  Estado en `localStorage` porque es una preferencia de dispositivo, no de usuario.
- **Sin dependencias nuevas.** `Notification` y `Audio` son del navegador; el sonido es un data-URI
  corto para no pedir un fichero por red.
- **Degradación honesta**: sin soporte o con permiso denegado, quedan el contador del título y el
  panel. Nada se rompe y se dice por qué.
- **Sin permiso de RBAC nuevo**: quien ya ve el panel (`alerts.read`) puede activarlas.

## Notes

**Lo que esto NO hace, y es la limitación importante: con el navegador CERRADO no llega nada.**
La API de notificaciones exige una pestaña viva. Avisar con todo cerrado es *Web Push*, y eso es
otra cosa entera —service worker, claves VAPID, tabla de suscripciones por dispositivo y un
emisor en el servidor—, con sus propios modos de fallo (suscripciones caducadas, un usuario que
cambia de teléfono). No se mete aquí a propósito.

Para el caso "no hay nadie delante de ninguna pantalla" **ya existe el escalado a WhatsApp**, que
con `alert-reminders` insiste cada 4 horas. Los dos canales se reparten el trabajo: el navegador
cubre a quien está trabajando, WhatsApp a quien no. Si algún día hace falta cubrir el hueco de en
medio —el dueño en su casa, sin la app abierta y sin querer un WhatsApp—, ése es el change de Web
Push y tiene que justificarse solo.
