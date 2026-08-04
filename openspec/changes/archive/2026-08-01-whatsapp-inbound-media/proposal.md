## Why

Hoy, cuando un cliente manda una foto por WhatsApp, **la foto se tira**. El webhook la reconoce
—el parser ya mapea `imageMessage → image`— y guarda en su lugar la cadena
`[imagen recibida — no soportada todavía]`. El límite era deliberado y está comentado en el código
(*"Text-only is a deliberate scope limit; an agent seeing this can ask the customer to write it
out"*), y para la fase 1 del canal fue la decisión correcta: validar el puente antes de gastar en
almacenamiento.

Ya no lo es, por una razón concreta que sale del proceso real de un pedido por transferencia:

```
el cliente se sale del navegador a pagar   →   paga en Nequi / el banco
                                                      │
                                    y la app del banco ofrece "compartir por WhatsApp"
                                                      │
                                    el comprobante llega al número del negocio
                                                      │
                          y el sistema lo convierte en «[imagen recibida — no soportada todavía]»
```

El comprobante entra por el único camino que el cliente tiene a mano y **el sistema lo descarta**.
El empleado ve un marcador, saca el teléfono, mira la foto ahí, y vuelve al sistema a registrar el
pago de memoria. Es exactamente el "volver al papel" que el proyecto se puso como barra a no
cruzar, con un teléfono en vez de papel.

Este cambio **no** habla de pagos: enseña al canal a recibir archivos. Que además desbloquea el
flujo del comprobante es la razón por la que se hace ahora, y va en un change aparte
(`payment-proof-by-whatsapp`) porque son dos cosas distintas — una capacidad y una política sobre
ella. Recibir imágenes sirve solo: la foto del plato que llegó mal, la captura de una dirección, el
producto que el cliente señala con el dedo.

## What Changes

- **Imágenes y PDF entrantes se guardan y se ven en la bandeja.** El resto —audio, video,
  stickers, ubicación— sigue con su marcador de texto: no es que no importen, es que ninguno tiene
  hoy un lector que los aproveche, y guardarlos sería pagar almacenamiento por nada.
- **Los bytes se piden al puente, no se esperan en el webhook.** El sobre de Evolution trae
  `mimetype` y `fileLength`, así que se decide **antes de descargar** — un video de 20 MB se
  rechaza leyendo el sobre. Con `base64: true` en el webhook, cada mensaje con archivo engordaría
  la petición pública del webhook con ~6,7 MB de JSON para poder decidir después.
- **El mensaje se guarda PRIMERO y el archivo se adjunta después.** Un fallo bajando la imagen
  cuesta la imagen, nunca el mensaje: en el hilo queda dicho que llegó un archivo y que no se pudo
  traer, que es la verdad y es depurable.
- **El pie de foto pasa a ser el contenido del mensaje** cuando existe. Hoy también se descarta, y
  tirar lo que el cliente escribió es el mismo error que tirar la imagen.
- **Una redistribución no duplica nada**: el insert del mensaje ya es insert-or-ignore sobre el id
  del proveedor, y si no gana la inserción no se descarga ni se sube nada.
- **El puerto del canal gana un segundo método.** `WhatsAppGateway` tenía uno (`send_text`) y
  `BRIDGE.md` lo presumía —*"ni plantillas, ni botones, ni multimedia"*—; ahora tiene
  `fetch_media`, y el documento se corrige. Sigue siendo sustituible: la API oficial de Meta
  también sabe descargar multimedia.
- **La invariante de salida no se toca.** Todo esto es entrante. Nada de aquí puede iniciar una
  conversación.

## Capabilities

### Modified Capabilities

- `whatsapp-messaging`: el webhook deja de descartar imágenes y PDF — los guarda, los deja
  legibles en el hilo y mantiene el marcador para los tipos que sigue sin soportar. La
  idempotencia y el aislamiento por sucursal siguen igual.
- `frontend-whatsapp-inbox`: el hilo pinta la imagen y enlaza el PDF, en vez de mostrar el texto
  del marcador.

## Impact

- **Backend `messaging`**: `fetch_media` en el puerto y en el adaptador de Evolution
  (`POST /chat/getBase64FromMediaMessage/{instance}`, que exige la **clave completa** del mensaje
  —id + remoteJid + fromMe—, no sólo el `provider_message_id` que se guarda hoy); función de
  guardado que reusa el mecanismo ya existente (`R2Storage.presign_put` + PUT por httpx, el mismo
  que usa el comprobante del checkout, así que no entra ni boto3 ni una credencial nueva).
- **Migración 0032**: columnas de multimedia en `whatsapp_messages` (`media_url`, `media_type`,
  `media_mime`) y la clave del proveedor que hace falta para pedir el archivo. Todo nullable: los
  mensajes que ya existen no tienen archivo y así se leen.
- **R2**: prefijo nuevo `whatsapp-media/<tenant>/<conversación>/`. Es el mismo trato que los
  comprobantes: URL pública con un uuid impredecible en la clave. **No es privacidad por permisos,
  es por opacidad** — igual que hoy, y conviene saberlo dicho.
- **Latencia del webhook**: un mensaje con imagen tarda lo que tarde la descarga. Se acota con
  timeout y tope de tamaño, y si molesta se mueve a un worker (ver `design.md`).
- **Coste**: unas decenas de imágenes al día por sede, con tope de 5 MB. Es el orden de magnitud
  de los comprobantes que ya se suben por el checkout.
- **Sin permiso nuevo**: quien ya puede leer la bandeja (`messaging.read`) ve los archivos de sus
  conversaciones.
- **No rompe nada**: sin R2 configurado o con el puente sin soporte, el comportamiento es el de
  hoy — el marcador de texto y el hilo coherente.
