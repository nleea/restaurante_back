"""El QR de una mesa: de una URL a un dibujo que se puede pegar en una madera.

Función pura y sin base de datos —entra una URL, sale un SVG— para que se pueda probar el
dibujo sin montar un tenant, y para que quien la llame sea el único que decida QUÉ URL se
imprime (ver `shared/links.table_order_url`).

**SVG y no PNG** porque una calcomanía se imprime, y un mapa de bits se imprime a la resolución
que le tocó. Un vector se amplía a 12 cm sin pixelarse y pesa menos que el PNG equivalente.

**Corrección de errores ALTA (H, ~30%)** y no la mínima. Este código va a vivir pegado a una
mesa de restaurante: se mancha de grasa, se raya con los platos y se despega por una esquina. La
diferencia entre el nivel bajo y el alto es un dibujo un poco más denso a cambio de que siga
leyéndose con casi un tercio del área destruida. En una pantalla daría igual; en una mesa no.
"""

from __future__ import annotations

import io

import segno

# El margen en módulos alrededor del dibujo. El estándar pide 4; menos de eso hace que muchos
# lectores no encuentren el código contra un fondo oscuro. Es zona blanca en la calcomanía, no
# espacio desperdiciado.
QUIET_ZONE = 4


def table_qr_svg(url: str, *, scale: int = 8) -> str:
    """El SVG del QR que codifica `url`.

    `scale` es el tamaño en px de cada módulo del dibujo. No fija el tamaño impreso —el SVG
    escala— pero sí un ancho por defecto razonable para verlo en pantalla antes de mandarlo a
    imprimir.
    """
    if not url:
        # Una URL vacía significa que el dominio público no está configurado. Codificarla daría
        # un QR perfectamente legible que lleva a ninguna parte, y eso no se descubre hasta que
        # alguien lo escanea sentado en la mesa. Mejor que reviente aquí.
        raise ValueError("No hay URL pública que codificar en el QR.")
    qr = segno.make(url, error="h")
    # `segno` escribe BYTES aunque el formato sea texto, así que el buffer es binario y se
    # decodifica aquí. Devolver bytes obligaría a cada llamante a acordarse de la codificación
    # para meterlo en un JSON o en un `<div>`.
    buffer = io.BytesIO()
    qr.save(
        buffer,
        kind="svg",
        scale=scale,
        border=QUIET_ZONE,
        xmldecl=False,
        # `omitsize` cambia `width`/`height` fijos por un `viewBox`, y NO es cosmético: sin
        # viewBox el dibujo tiene un tamaño intrínseco (392 px) que el CSS no puede cambiar.
        # Ponerle `max-width: 180px` encogía la CAJA y dejaba el dibujo igual, así que el QR
        # salía RECORTADO por la esquina superior izquierda — y un QR recortado no lo lee
        # ningún lector. Con viewBox, el dibujo escala con su caja.
        omitsize=True,
        # Fondo blanco explícito. Por defecto `segno` deja el claro TRANSPARENTE, y entonces la
        # zona tranquila —que existe precisamente para dar contraste al lector— se queda del
        # color de lo que haya debajo. Sobre papel de color o una tarjeta con fondo, eso mata
        # justo lo que el margen venía a garantizar.
        light="#ffffff",
    )
    return buffer.getvalue().decode("utf-8")
