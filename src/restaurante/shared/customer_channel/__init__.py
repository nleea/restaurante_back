"""El canal por el que el NEGOCIO le habla al CLIENTE (hoy, WhatsApp).

Vive en `shared` por la misma razón que `shared/realtime`: lo usan varios módulos de
negocio (pedidos, domicilios, storefront) y ninguno de ellos puede depender de
`messaging`. Aquí sólo están los puertos y sus implementaciones nulas; quien los
cumple es `messaging`, enchufado en la raíz de composición.
"""
