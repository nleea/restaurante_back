"""Los enlaces públicos que el negocio manda a sus clientes.

Vive en `shared` y no dentro de un módulo porque ya lo necesitan tres sitios —el saludo de
WhatsApp, el asistente y cualquier aviso futuro— y porque un enlace mal formado no es un fallo
de messaging ni del asistente: es un cliente abriendo la carta del negocio equivocado.
"""

from __future__ import annotations

from urllib.parse import quote


def tenant_base_url(base_url: str, slug: str | None) -> str:
    """Antepone el subdominio del tenant al dominio público de la carta.

    `https://wsquote.uk` + `demo` → `https://demo.wsquote.uk`

    El front deduce a qué API hablar del subdominio del navegador, así que sin esto el
    cliente abriría un enlace que no sabe de qué negocio es — o peor, que resuelve al
    negocio equivocado. Un enlace es un dato por tenant, no una constante de despliegue.
    """
    base = base_url.rstrip("/")
    # Sin dominio configurado no hay nada que prefijar, y devolver `"demo."` sería peor que
    # devolver nada: es *truthy*, así que la guarda de "sin dominio, sin enlace" de quien llama
    # no dispararía y el cliente recibiría `demo./my-order/tok` por WhatsApp.
    if not base:
        return ""
    if not slug:
        return base
    if "://" in base:
        scheme, host = base.split("://", 1)
        return f"{scheme}://{slug}.{host}"
    return f"{slug}.{base}"


def order_edit_url(base_url: str, slug: str | None, edit_token: str) -> str:
    """El enlace con el que un cliente abre SU pedido para corregirlo.

    Sin dominio configurado no hay enlace: se devuelve cadena vacía y quien llama decide qué
    decir. Un enlace relativo mandado por WhatsApp no es clicable, así que media URL es peor
    que ninguna — el cliente ve texto raro y cree que el sistema está roto.
    """
    base = tenant_base_url(base_url, slug)
    return f"{base}/my-order/{edit_token}" if base else ""


def table_order_url(
    base_url: str, slug: str | None, branch_code: str, table_code: str
) -> str:
    """La dirección que va codificada en el QR pegado a una mesa.

    Vive aquí, con los demás enlaces públicos, por un motivo que no es de orden: esta URL se
    IMPRIME. Un enlace de WhatsApp mal construido se corrige mandando otro; una calcomanía mal
    construida hay que despegarla de diez mesas. Que exista un solo sitio donde se decide la
    forma es lo que hace que el papel y el router no puedan discrepar.

    Sede y mesa van las dos en el path porque el front las lee de ahí (`/store/:branchCode/
    table/:tableCode`) y porque el backend público sólo acepta esa forma: el código de mesa es
    único DENTRO de su sede, así que uno sin la otra no identifica nada.

    Sin dominio configurado se devuelve cadena vacía, igual que los demás: media URL impresa en
    una calcomanía es el peor resultado posible, porque no falla hasta que un cliente la escanea.
    """
    base = tenant_base_url(base_url, slug)
    if not base:
        return ""
    return (
        f"{base}/store/{quote(branch_code, safe='')}"
        f"/table/{quote(table_code, safe='')}"
    )


def delivery_payment_url(base_url: str, slug: str | None, raw_token: str) -> str:
    """El enlace con el que un cliente paga SU domicilio ya cotizado.

    Mismo contrato que `order_edit_url`: sin dominio configurado, cadena vacía, porque media
    URL mandada por WhatsApp es peor que ninguna.

    El token va percent-encoded aunque hoy salga de `token_urlsafe`: quien acuñe el token
    mañana no tiene por qué saber que su alfabeto viaja en un path, y un `/` suelto partiría
    la ruta en dos silenciosamente.
    """
    base = tenant_base_url(base_url, slug)
    return f"{base}/payment/delivery/{quote(raw_token, safe='')}" if base else ""
