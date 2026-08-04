> Lee `design.md`. Lo que más fácil se rompe aquí no es el código: es **gastar el permiso**. Si
> algo llama a `requestPermission()` fuera del clic que lo enciende, la feature queda muerta para
> ese dispositivo para siempre y no hay arreglo desde la app.
>
> Se despliega con `alert-reminders`: sin esto, aquél insiste donde no hay nadie mirando.

## 1. El transporte

- [x] 1.1 `composables/useBrowserNotifications.ts`: estado del permiso, encender/apagar, emitir,
      sonido y contador del título. Sin dependencias nuevas
- [x] 1.2 `requestPermission()` **sólo** desde el gesto de encender. Nunca en `onMounted`
- [x] 1.3 `notify(alert)` con `tag` por id de alerta, para que el sistema colapse repetidas
- [x] 1.4 Conjunto de ids ya notificados, **sembrado al cargar** con lo que ya había: recargar la
      página no puede reproducir las alertas de ayer
- [x] 1.5 Contador en `document.title`, restaurando el título limpio al llegar a cero. Funciona
      con el permiso denegado — es la única señal que no pide nada
- [x] 1.6 Sonido opcional, apagado por defecto, data-URI corto (design §4)
- [x] 1.7 Preferencia en `localStorage`: es del dispositivo, no de la cuenta
- [x] 1.8 Sin soporte en el navegador: todo lo demás sigue funcionando y se dice
- [x] 1.9 Pruebas con `Notification` simulado: se pide permiso sólo al encender; una alerta nueva
      notifica; una ya notificada no; el título cuenta y se limpia; denegado no rompe nada

## 2. El panel

- [x] 2.1 Interruptor de notificaciones y de sonido en la vista de alertas
- [x] 2.2 Estado del permiso en palabras, incluido "lo bloqueó el navegador: se reactiva ahí, no
      aquí"
- [x] 2.3 **Decir la limitación al encenderlas**: hace falta que quede una pestaña abierta. Es la
      diferencia entre una expectativa cumplida y "no me avisó"
- [x] 2.4 Alimentar el transporte con las alertas nuevas de cada refresco, no con la lista entera
- [x] 2.5 Tocar la notificación enfoca la app y abre esa alerta
- [x] 2.6 Pruebas: sólo lo nuevo notifica; recargar no reproduce; el interruptor pide permiso

## 3. Cierre

- [x] 3.1 Puertas verdes: `vitest`, `type-check`, `eslint`
- [ ] 3.2 Comprobar a mano en Chrome y en Safari: pestaña de fondo, permiso denegado, y sin sonido
