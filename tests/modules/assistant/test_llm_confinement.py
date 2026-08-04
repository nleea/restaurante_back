"""LangChain no sale de `infrastructure/llm/`. Esta prueba ES la condición del override.

`pyproject.toml` relaja `mypy` para ese paquete porque LangChain no está tipado como el resto
del código. Esa excepción sólo es honesta mientras el confinamiento se cumpla: el día que un
`AIMessage` suba a un caso de uso, el override deja de cubrir un adaptador y pasa a cubrir la
lógica de negocio. Por eso el confinamiento se comprueba y no se confía.

Se mira el CÓDIGO FUENTE, no los módulos importados: un import dentro de una función o detrás
de un `TYPE_CHECKING` no aparecería mirando `sys.modules`, y contaría igual.
"""

from __future__ import annotations

import ast
from pathlib import Path

import restaurante.modules.assistant as assistant_pkg

#: Lo que no puede aparecer. `openai` va incluido: el cliente del proveedor es tan de
#: infraestructura como el envoltorio que lo usa.
FORBIDDEN_ROOTS = ("langchain", "langchain_core", "langchain_openai", "openai")

#: Las dos capas que tienen que poder existir con el proveedor cambiado entero.
CONFINED_LAYERS = ("domain", "application")


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_provider_types_in_domain_or_application() -> None:
    root = Path(assistant_pkg.__file__).parent
    offenders: list[str] = []
    for layer in CONFINED_LAYERS:
        for path in (root / layer).rglob("*.py"):
            leaked = _imported_roots(path.read_text(encoding="utf-8")) & set(
                FORBIDDEN_ROOTS
            )
            if leaked:
                offenders.append(f"{path.relative_to(root)}: {sorted(leaked)}")

    assert not offenders, (
        "LangChain/OpenAI se escapó del adaptador: "
        + "; ".join(offenders)
        + ". El override de mypy de `infrastructure/llm/*` depende de que esto no pase."
    )


def test_the_adapter_is_where_langchain_lives() -> None:
    """El contrapunto: si NADIE importa LangChain, esta prueba no está probando nada.

    Sin esto, borrar el adaptador dejaría la suite en verde y el confinamiento «demostrado»
    sobre un módulo vacío.
    """
    engine = Path(assistant_pkg.__file__).parent / "infrastructure" / "llm" / "engine.py"
    assert engine.exists()
    assert _imported_roots(engine.read_text(encoding="utf-8")) & set(FORBIDDEN_ROOTS)
