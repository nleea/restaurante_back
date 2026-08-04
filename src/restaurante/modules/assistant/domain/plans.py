"""El catálogo de planes: qué modelo, a qué precio y con qué techo por llamada.

El plan elige proveedor y modelo, **no el tenant** (decisión 3 del diseño). Compramos los
tokens al por mayor, así que el modelo es una palanca de margen NUESTRA: cuando cambian los
precios movemos a todo el mundo, y eso sólo se puede hacer si nadie eligió el suyo. Que el
proveedor sea una columna de esta tabla y no una constante del módulo es lo que hace que
añadir un plan sobre otro proveedor sea una fila, no un refactor.

Los precios están aquí y no en la base de datos a propósito. Son un hecho del proveedor, no
un dato del negocio: si viven en una tabla, el día que suban queda una fila vieja diciendo lo
que costaba antes y el libro mayor empieza a mentir sobre nuestro margen.

Con el techo por llamada, el coste máximo de una llamada se sabe ANTES de hacerla:

    coste_máximo = max_input/1e6 · precio_in + max_output/1e6 · precio_out

que es lo que convierte "la cuota se puede pasar" en un número exacto en vez de un encogimiento
de hombros: se comprueba antes y se apunta después, así que como mucho se pasa por una llamada.

Dos cosas sobre estos precios (tarifa OpenAI consultada el 2026-07-31, por millón de tokens):

- Son los de **contexto corto**. OpenAI cobra más caro a partir de cierto tamaño de entrada
  (`gpt-5.6-sol` pasa de $5 a $10 de entrada), y los techos de entrada de aquí —miles de
  tokens, no cientos de miles— mantienen cada llamada dentro del tramo barato. El techo, que
  existe para acotar el gasto de un desconocido escribiendo por WhatsApp, resulta ser también
  lo que impide caer en la tarifa cara sin enterarse.
- No se modela el descuento por entrada cacheada (`cached input`, hasta 10× más barata). El
  coste que se apunta es por tanto una COTA SUPERIOR, y equivocarse por arriba es el lado
  correcto: un tenant sale menos rentable de lo que es, nunca más.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from restaurante.modules.assistant.domain.entities import DEFAULT_PLAN

PROVIDER_OPENAI = "openai"


@dataclass(frozen=True)
class PlanSpec:
    """Lo que implica un plan: modelo, precio y los dos techos."""

    name: str
    provider: str
    model: str
    price_in_per_mtok: Decimal
    price_out_per_mtok: Decimal
    # La entrada la controla un desconocido por WhatsApp: puede mandar 5.000 caracteres. Se
    # recorta, y por eso el techo de coste es real y no una esperanza.
    max_input_tokens: int
    max_output_tokens: int
    #: Cuánto puede "pensar" antes de contestar. `"none"` por dos motivos, y el segundo lo
    #: descubrió una llamada real:
    #:
    #: 1. Lo que contesta este asistente son horarios, carta y estado de un pedido — datos
    #:    que le damos hechos con herramientas. Pagar razonamiento por "¿a qué hora abren?"
    #:    es margen quemado.
    #: 2. `/v1/chat/completions` **rechaza con 400** las herramientas si el modelo trae su
    #:    razonamiento por defecto: hay que apagarlo explícitamente. Subirlo en un plan futuro
    #:    obliga a mover ese plan a la API de `responses`, no basta con cambiar este campo.
    reasoning_effort: str = "none"

    def cost(self, tokens_in: int, tokens_out: int) -> Decimal:
        """Lo que nos costó una llamada. Sin redondear a céntimos: son millonésimas."""
        million = Decimal(1_000_000)
        return (
            Decimal(tokens_in) / million * self.price_in_per_mtok
            + Decimal(tokens_out) / million * self.price_out_per_mtok
        )

    @property
    def max_cost_per_call(self) -> Decimal:
        """El techo, calculado con los dos límites. Es el desbordamiento máximo de la cuota."""
        return self.cost(self.max_input_tokens, self.max_output_tokens)


#: Catálogo. Tres escalones sobre los modelos actuales de OpenAI.
#:
#: `basic` es el de partida y es el barato a propósito: lo que contesta este asistente son
#: preguntas de carta y horarios sobre datos que ya le damos hechos con herramientas. Pagar
#: un modelo de frontera por "¿a qué hora abren?" es margen quemado, no calidad.
PLANS: dict[str, PlanSpec] = {
    "basic": PlanSpec(
        name="basic",
        provider=PROVIDER_OPENAI,
        model="gpt-5.6-luna",
        price_in_per_mtok=Decimal("0.20"),
        price_out_per_mtok=Decimal("1.20"),
        max_input_tokens=2000,
        max_output_tokens=400,
    ),
    "pro": PlanSpec(
        name="pro",
        provider=PROVIDER_OPENAI,
        model="gpt-5.6-terra",
        price_in_per_mtok=Decimal("2.00"),
        price_out_per_mtok=Decimal("12.00"),
        max_input_tokens=4000,
        max_output_tokens=700,
    ),
    "max": PlanSpec(
        name="max",
        provider=PROVIDER_OPENAI,
        model="gpt-5.6-sol",
        price_in_per_mtok=Decimal("5.00"),
        price_out_per_mtok=Decimal("30.00"),
        max_input_tokens=6000,
        max_output_tokens=1000,
    ),
}


def resolve_plan(name: str | None) -> PlanSpec:
    """El plan por nombre. Un plan desconocido cae al de partida, nunca a "sin techo".

    Es la diferencia entre una fila con un plan viejo y una llamada sin límite de gasto.
    """
    return PLANS.get(name or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])
