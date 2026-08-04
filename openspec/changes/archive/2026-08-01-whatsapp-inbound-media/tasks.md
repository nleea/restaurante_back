> Lee `design.md`. La decisión que ordena el change está en el **orden** del grupo 4: el mensaje se
> guarda antes de tocar el archivo, y por eso un fallo bajando la imagen no puede costar el mensaje.
> Si eso se invierte, el change deja de ser seguro aunque las pruebas pasen.
>
> Orden: 1 → 2 → 3 → 4 → 5 (backend probado) → 6 → 7.

## 1. Backend — el puerto y el adaptador

- [x] 1.1 `fetch_media(session, provider_message_id, remote_jid, from_me=False) -> tuple[bytes, str]`
      en el puerto `WhatsAppGateway`; devuelve los bytes y el mime que reporta el puente
- [x] 1.2 Implementación en `BridgeWhatsAppGateway` sobre
      `POST /chat/getBase64FromMediaMessage/{instance}`, con la **clave Baileys completa**
      (`{id, remoteJid, fromMe}`) y timeout corto
- [x] 1.3 El guard de salida (`GuardedWhatsAppGateway`) delega esto **sin comprobar nada**: la
      invariante que protege es de SALIDA, y descargar no escribe a nadie. Dejarlo dicho en el
      docstring o alguien lo "arregla"
- [x] 1.4 Un fallo del puente levanta un error del dominio, no un `httpx.HTTPError` crudo, para que
      quien llama pueda tragárselo sabiendo qué pasó
- [x] 1.5 Pruebas del adaptador con el puente falso: éxito, timeout, respuesta sin base64, mime que
      no coincide con lo prometido en el sobre

## 2. Backend — decidir sin descargar, y guardar

- [x] 2.1 `media_intent(mimetype, file_length)` como función **pura** en el dominio de messaging:
      decide `store` / `placeholder` según la tabla del diseño (§4). Se prueba sin red ni base
- [x] 2.2 Tope de 5 MB y tipos: imagen y `application/pdf`. Audio, video, sticker, ubicación y
      documentos de otro tipo → marcador
- [x] 2.3 `store_inbound_media(tenant_id, conversation_id, mime, data)` reusando el MISMO mecanismo
      que `store_payment_proof` (`R2Storage.presign_put` + PUT por httpx). Prefijo de clave
      `whatsapp-media/<tenant>/<conversación>/<uuid><ext>`. Sin boto3, sin credenciales fuera
- [x] 2.4 Sin R2 configurado: no levanta, deja el marcador y **registra por qué** con esas palabras
- [x] 2.5 Pruebas de la decisión pura, una por fila de la tabla del diseño

## 3. Backend — persistencia

- [x] 3.1 Columnas nullable en `whatsapp_messages`: `media_url`, `media_type` (`image`/`document`),
      `media_mime`, y `provider_remote_jid` (la clave que el puente exige para devolver el archivo)
- [x] 3.2 `media_type` se guarda **también cuando no se descarga nada**: es lo que permite decir
      "llegó una imagen" sin tener el archivo, y lo que `payment-proof-by-whatsapp` va a leer
- [x] 3.3 Adjuntar el archivo a un mensaje ya guardado (update por id, no insert)
- [x] 3.4 Migración **0032_whatsapp_message_media** (up/down/up en Postgres, sin deriva). Todo
      nullable: los mensajes que ya existen no tienen archivo y así se leen

## 4. Backend — el engarce, en este orden

> El orden ES el requisito. Cualquier reordenación que ponga la descarga antes de persistir el
> mensaje rompe "un fallo cuesta el archivo, nunca el mensaje".

- [x] 4.1 Guardar el mensaje (insert-or-ignore) — si es **redistribución** (`None`), terminar aquí
      sin descargar ni subir nada
- [x] 4.2 El pie de foto pasa a ser el contenido cuando existe; sin pie, el marcador de siempre
- [x] 4.3 Decidir con `media_intent` leyendo el sobre — **sin descargar**
- [x] 4.4 Descargar, subir, actualizar la fila. Cualquier fallo aquí: se traga, se registra, y el
      mensaje se queda con su marcador
- [x] 4.5 Tocar el timbre SSE **después** de adjuntar, para que el primer refresco ya traiga la
      imagen (un solo timbre, no dos)
- [x] 4.6 Saludo / asistente / FAQs siguen al final y sin cambios
- [x] 4.7 Aislar la parte de archivo en una función propia (`attach_media`) para que mudarla a un
      worker el día que la latencia moleste sea mover una llamada, no reescribir el flujo

## 5. Backend — pruebas de extremo a extremo

- [x] 5.1 Webhook con `imageMessage` → mensaje en el hilo con `media_url` y `media_type=image`
- [x] 5.2 Webhook con `documentMessage` + `application/pdf` → igual; con otro mime → marcador
- [x] 5.3 `fileLength` por encima del tope → **cero llamadas al puente** (es la aserción, no un
      efecto secundario) y marcador en el hilo
- [x] 5.4 El puente falla al devolver el archivo → el mensaje SIGUE en el hilo, sin URL, y el
      webhook responde 200
- [x] 5.5 Redistribución del mismo mensaje → un mensaje, un archivo, cero descargas la segunda vez
- [x] 5.6 Pie de foto → es el contenido del mensaje
- [x] 5.7 Sin R2 configurado → comportamiento de hoy, y traza explicando la causa
- [x] 5.8 `ruff`, `mypy` y la suite completa en verde

## 6. Frontend — el hilo

- [x] 6.1 Tipos de multimedia en el contrato del mensaje (`media_url`, `media_type`, `media_mime`)
- [x] 6.2 Imagen en línea en el hilo, a un tamaño en el que se lea un comprobante, y a tamaño
      completo al pulsar
- [x] 6.3 PDF como enlace para abrir, no incrustado
- [x] 6.4 Pie de foto como texto del mensaje, con la imagen al lado o debajo
- [x] 6.5 Archivo que no se pudo traer: se dice con palabras, **sin imagen rota**
- [x] 6.6 Pruebas del hilo: imagen, PDF, pie, y el caso del archivo perdido
- [x] 6.7 `pnpm type-check`, `lint` y `test:unit` en verde

## 7. Documentación

- [x] 7.1 `docs/messaging/BRIDGE.md`: la tabla de rutas gana
      `POST /chat/getBase64FromMediaMessage/{instance}`, y **hay que corregir la sección "Cambiar de
      puente"** — ya no es verdad que el puerto tenga un solo método ni que no sepa de multimedia
- [x] 7.2 Dejar dicho en `BRIDGE.md` que la descarga depende de que Evolution conserve el mensaje en
      su base: es configuración del despliegue y explica el fallo más probable
- [x] 7.3 Nota sobre la URL pública y opaca de R2, con el precedente del comprobante: es privacidad
      por opacidad, no por permisos
