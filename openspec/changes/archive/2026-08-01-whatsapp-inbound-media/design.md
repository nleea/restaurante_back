## Context

El canal recibe hoy sólo texto. Lo demás se reconoce y se sustituye por una cadena:

```
webhook → _inbound_content(inbound)
            ├─ text  → el texto
            └─ resto → "[imagen recibida — no soportada todavía]"   ← el archivo se pierde aquí
```

Lo que ya existe y este diseño se apoya en ello:

- **El parser distingue el tipo.** `_BAILEYS_MEDIA_TYPES` mapea `imageMessage → image`,
  `documentMessage → document`, `stickerMessage → sticker`… El trabajo de clasificar está hecho.
- **Escritura a R2 desde el servidor.** `orders/infrastructure/payment_proof.py` valida bytes y
  sube reusando `R2Storage.presign_put` **contra nosotros mismos** — sin boto3 y sin que la
  credencial salga del servidor. El docstring explica por qué los bytes pasan por la API en vez de
  ir con una URL prefirmada: *"una firma autoriza un PUT pero no acota cuántos bytes se meten"*.
  Aquí el argumento es el mismo y el mecanismo se reusa tal cual, con otro prefijo de clave.
- **PDF ya es un tipo aceptado** en el comprobante del checkout (`PROOF_TYPES`), *"porque los
  bancos lo mandan así"*. La misma razón vale para lo que llega por el chat.
- **La idempotencia del entrante** es un insert-or-ignore sobre `(tenant, provider_message_id)`, y
  devuelve `None` en la redistribución. Es el gancho natural para no descargar dos veces.
- **El timbre SSE de la bandeja** ya existe y la bandeja además reconsulta por su cuenta.

## Goals / Non-Goals

**Goals**

- Que el comprobante que un cliente manda por WhatsApp **quede dentro del sistema**, y que quien
  atiende no tenga que sacar el teléfono para verlo.
- Que un fallo bajando un archivo cueste el archivo y nunca el mensaje.
- Que el hilo siga siendo legible para los tipos que no se soportan.
- Que no entre ninguna dependencia nueva: ni cliente de S3, ni cola nueva, ni librería de imagen.

**Non-Goals**

- **Enviar** multimedia. El puerto de salida sigue teniendo un solo método (`send_text`) y la
  invariante de salida no se toca.
- Audio, video, stickers y ubicación. Se quedan con su marcador: ninguno tiene hoy quien los lea, y
  guardarlos es pagar por nada. Cuando haya un lector, se añaden uno a uno.
- Miniaturas, recorte, compresión o conversión. Lo que llega se guarda como llega.
- Nada de pagos ni de comprobantes: eso es `payment-proof-by-whatsapp`, que depende de esto.
- Transcribir notas de voz. Es un LLM y es otro programa.

## Decisiones

### 1. Los bytes se piden; no se esperan en el webhook

Evolution v2 ofrece las dos vías:

```
A) webhook.base64: true                    los bytes llegan dentro del webhook
   → una sola llamada
   → ✗ el webhook (endpoint PÚBLICO) recibe ~6,7 MB de JSON por cada 5 MB de archivo,
     TAMBIÉN cuando el archivo no nos interesa

B) POST /chat/getBase64FromMediaMessage    se piden cuando ya sabemos qué son  ← ELEGIDA
   → ✗ una segunda llamada
   → ✅ el sobre trae `mimetype` y `fileLength`: un video de 20 MB se rechaza SIN descargarlo
```

El argumento decisivo es el segundo: **decidir antes de gastar**. Con A, el tope de tamaño se
comprueba cuando los bytes ya viajaron.

Riesgo real de B, y hay que decirlo: depende de que Evolution conserve el mensaje en su propia base
para poder devolverlo. Si está configurado sin persistencia, la descarga falla. Por eso se pide
**inmediatamente al recibir** y no cuando alguien pulsa "ver" — un comprobante que se descarga a
demanda es un comprobante que se pierde justo cuando alguien fue a buscarlo.

### 2. Descarga en línea, con timeout, y una salida documentada

La descarga ocurre dentro de la petición del webhook. Es lo simple, y para unas decenas de imágenes
al día por sede sobra.

**Rechazado por ahora: un worker `arq`.** Es lo correcto a escala y ya hay infraestructura (el de
geocoding, el de alertas), pero pesa: otro proceso que alguien tiene que estar corriendo. Y la
casa ya tiene una advertencia operativa parecida —el worker de geocoding **debe** correr en una
sola instancia o los proveedores banean el tenant—, así que añadir procesos no es gratis.

La salida está escrita: si el webhook empieza a tardar, lo que se mueve es una función ya aislada
(`attach_media`), no el flujo. El orden de `handle_inbound` lo hace posible sin reescribir nada.

### 3. Primero el mensaje, después el archivo. Y en ese orden por una razón

```
1. persistir el mensaje (insert-or-ignore)     ← si es redistribución, TERMINA aquí
2. ¿es imagen o PDF, y cabe?                   ← se lee del sobre, sin descargar
3. pedir los bytes al puente                   ← con timeout
4. subir a R2 y actualizar la fila             ← el archivo se adjunta a lo ya guardado
5. tocar el timbre SSE                         ← ya con la imagen puesta
6. saludo / asistente / FAQs
```

Un fallo en 3 o 4 deja el mensaje de 1 en el hilo, con su tipo dicho y sin URL. El hilo entonces
enseña *"llegó una imagen y no se pudo traer"* — feo y **honesto**, que es la postura del módulo con
los huecos.

El timbre va **después** de adjuntar (paso 5) para que el primer refresco de la bandeja ya traiga la
imagen. La alternativa —timbrar dos veces, antes y después— haría parpadear la pantalla para
ahorrar medio segundo.

### 4. Qué se guarda, y qué no

| tipo Baileys | qué se hace | por qué |
|---|---|---|
| `imageMessage` | se guarda | es el 95% de lo que manda un cliente, y es el comprobante |
| `documentMessage` con `application/pdf` | se guarda | Nequi y los bancos mandan el comprobante en PDF |
| `documentMessage` con otro mime | marcador | un `.docx` no lo va a abrir nadie desde la bandeja |
| `audioMessage`, `videoMessage` | marcador | sin lector; el video además es caro |
| `stickerMessage` | marcador | es un webp, así que "es una imagen" — pero es ruido puro |
| `locationMessage` | marcador | no es un archivo; merece su propio trabajo (un mapa) |

Tope de **5 MB**, el mismo número y por la misma razón que el comprobante del checkout: *"un
comprobante es una captura de pantalla; lo que pase de aquí no es un comprobante"*.

### 5. El pie de foto ES el mensaje

Hoy `_inbound_content` devuelve el marcador para todo lo que no sea texto, así que un cliente que
manda una foto **con** el texto "aquí va mi comprobante del pedido A3F2" pierde la frase. Descartar
lo que el cliente escribió es el mismo error que descartar la imagen, y encima es el que más duele:
la frase es lo que le dice al agente de qué es la foto.

Así que: **si hay pie de foto, el pie de foto es el contenido**; el tipo y la URL viajan en columnas
aparte. Sin pie, el contenido sigue siendo el marcador, que es lo que mantiene el hilo legible.

Consecuencia que hay que ver: ese pie pasa a ser texto que el saludo, el asistente y las FAQs
pueden leer. No es un problema nuevo —es el mismo texto que si lo hubiera escrito suelto— pero
significa que una foto con pie *"¿dónde están?"* puede disparar una FAQ. Es correcto: preguntó.

### 6. La URL es pública y opaca, igual que el comprobante

El objeto va a R2 con una clave que lleva un uuid impredecible, y se sirve por URL pública. **No es
privacidad por permisos: es por opacidad.** Quien tenga la URL, ve la foto.

Es exactamente el trato que ya tienen los comprobantes del checkout (`proof_url` es una URL
pública), así que esto no introduce una postura nueva — la hereda. Se deja dicho aquí porque una
foto que un cliente manda por su chat *se siente* más privada que un comprobante que subió a
propósito, y la propiedad técnica es la misma.

Si algún día hay que cerrarlo, se cierra para los dos a la vez (URL firmada de lectura, corta), y es
un change propio.

### 7. La clave del mensaje hay que guardarla

`getBase64FromMediaMessage` no acepta un id suelto: quiere la **clave** Baileys
(`{id, remoteJid, fromMe}`). Hoy sólo se guarda `provider_message_id`.

`remoteJid` se podría reconstruir del teléfono del contacto, pero los JIDs de WhatsApp tienen más de
una forma —`@s.whatsapp.net`, `@lid`— y esa reconstrucción ya fue una de las cuatro trampas de la
integración original. Reconstruir lo que el proveedor nos dio es pedir que vuelva a morder.

Se guarda el `remoteJid` tal cual llegó, en su columna, nullable.

## Riesgos

- **Evolution sin persistencia de mensajes** → la descarga falla siempre y el hilo se llena de
  "no se pudo traer". Es configuración del despliegue, y el log tiene que decirlo con esas
  palabras, no con un stack trace.
- **R2 sin configurar** → mismo caso, y ya hay precedente de cómo se dice
  (`"El almacenamiento de archivos no está configurado."`).
- **Un cliente mandando 40 fotos** infla la factura. El tope por archivo existe; un tope por
  conversación y día se deja fuera hasta que haga falta, porque el número que se invente hoy va a
  estar mal.
- **La latencia del webhook** con archivos grandes. Timeout corto y tope de tamaño; la salida al
  worker está escrita.

## Preguntas abiertas (no bloqueantes)

- ¿Se enseña el tamaño/el nombre del PDF en la bandeja, o basta un enlace "ver comprobante.pdf"?
- ¿Hace falta borrar la multimedia de una conversación cerrada pasado un tiempo? Hoy nada se borra
  en este sistema; abrir ese tema aquí sería abrirlo para todo.
- ¿Un `documentMessage` que es imagen (`image/jpeg` mandado como archivo, cosa que WhatsApp Web
  hace) se trata como imagen? Probablemente sí, y es una línea en el mapa de tipos.
