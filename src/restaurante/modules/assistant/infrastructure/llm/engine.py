"""El único fichero del asistente que sabe que LangChain existe.

Y la regla que lo hace válido: **nada de LangChain sale de este paquete**. `respond` recibe un
`EngineRequest` nuestro y devuelve un `EngineReply` nuestro; ni un `AIMessage` ni un
`Runnable` cruzan hacia `application/`. El override de `mypy` que este paquete necesita
—LangChain no está tipado con el rigor del resto del código— sólo es honesto mientras eso se
cumpla, y hay un test que lo comprueba. Si un tipo de LangChain sube, el override deja de ser
una excepción acotada y pasa a ser un agujero.

El bucle de herramientas vive aquí y no en el caso de uso por el mismo motivo: "el modelo
pidió la herramienta X" es vocabulario del proveedor. Arriba sólo se sabe que se hizo una
pregunta y volvió una respuesta con un coste.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from restaurante.modules.assistant.domain.errors import AssistantProviderError
from restaurante.modules.assistant.domain.ports import (
    EngineReply,
    EngineRequest,
    ToolSpec,
)

logger = logging.getLogger(__name__)

#: Cuántas veces puede el modelo pedir herramientas antes de tener que contestar.
#:
#: Es un tope de GASTO, no de calidad: cada vuelta es otra llamada facturada, y un modelo que
#: se queda pidiendo la carta en bucle nos cuesta dinero por una pregunta que nadie va a leer.
#: Al agotarse se contesta con lo que haya, que es peor respuesta y coste conocido.
MAX_TOOL_ITERATIONS = 4


class LangChainConversationEngine:
    """`ConversationEngine` sobre LangChain. Un cliente por plan, no por petición."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_tool_iterations = max_tool_iterations
        # La caché es por (modelo, techo de salida) —o sea, en la práctica por plan— porque
        # construir el cliente en cada mensaje entrante es montar un pool de conexiones para
        # tirarlo: el plan cambia cuando alguien lo cambia, no cuando llega un WhatsApp.
        self._clients: dict[tuple[str, int, str], ChatOpenAI] = {}

    async def respond(self, request: EngineRequest) -> EngineReply:
        if not self._api_key:
            # Sin credencial no se llama a nadie. Se dice así y no con el error del
            # proveedor, que sería un 401 críptico a tres capas de distancia.
            raise AssistantProviderError(
                "El asistente no tiene credencial de proveedor configurada."
            )

        client = self._client_for(
            request.model, request.max_output_tokens, request.reasoning_effort
        )
        runnable: Any = client
        by_name = {tool.name: tool for tool in request.tools}
        if request.tools:
            runnable = client.bind_tools(
                [_tool_schema(tool) for tool in request.tools]
            )

        messages = _build_messages(request)
        tokens_in = 0
        tokens_out = 0

        try:
            for _ in range(self._max_tool_iterations):
                reply = await runnable.ainvoke(messages)
                used_in, used_out = _usage(reply)
                tokens_in += used_in
                tokens_out += used_out

                calls = list(getattr(reply, "tool_calls", []) or [])
                if not calls:
                    return EngineReply(
                        text=_text_of(reply), tokens_in=tokens_in, tokens_out=tokens_out
                    )

                messages.append(reply)
                for call in calls:
                    messages.append(
                        ToolMessage(
                            content=await _run_tool(by_name, call),
                            tool_call_id=str(call.get("id", "")),
                        )
                    )

            # Se agotaron las vueltas: se pide una respuesta final sin herramientas en vez de
            # devolver un turno vacío. Cuesta una llamada más y evita el silencio.
            final = await client.ainvoke(messages)
            used_in, used_out = _usage(final)
            return EngineReply(
                text=_text_of(final),
                tokens_in=tokens_in + used_in,
                tokens_out=tokens_out + used_out,
            )
        except AssistantProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - la frontera con el proveedor
            # Los tokens ya gastados viajan dentro: se apuntarán en el libro aunque esta
            # llamada acabe en error. Lo que se pagó, se apunta.
            logger.warning("El proveedor falló al responder", exc_info=True)
            raise AssistantProviderError(
                "El asistente no pudo responder en este momento.",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ) from exc

    # --- Interno ------------------------------------------------------------
    def _client_for(
        self, model: str, max_output_tokens: int, reasoning_effort: str
    ) -> ChatOpenAI:
        key = (model, max_output_tokens, reasoning_effort)
        client = self._clients.get(key)
        if client is None:
            # Dos cosas que sólo se ven llamando de verdad:
            #
            # - `temperature` NO se envía (LangChain la deja sin poner): los modelos de
            #   razonamiento rechazan un valor distinto del suyo, así que "ponerla a cero
            #   para que sea determinista" es exactamente el 400.
            # - `reasoning_effort` SÍ se envía, aunque el valor por defecto del cliente sea
            #   "no mandar nada": el modelo trae el suyo del lado del servidor y
            #   `/v1/chat/completions` rechaza las herramientas mientras esté encendido.
            #   Callarse aquí no es neutral, es un 400 en cada llamada con herramientas.
            client = ChatOpenAI(
                model=model,
                api_key=self._api_key,
                max_completion_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                timeout=self._timeout,
                max_retries=1,
            )
            self._clients[key] = client
        return client


def _build_messages(request: EngineRequest) -> list[BaseMessage]:
    """La conversación en vocabulario del proveedor. Se construye aquí y muere aquí."""
    system = request.system_prompt
    if request.passages:
        # El índice hoy no devuelve nada; cuando devuelva, entra como CONTEXTO y no como
        # verdad: lo vivo —stock, ventas, horarios— se contesta con herramientas.
        joined = "\n\n".join(f"[{p.source}] {p.text}" for p in request.passages)
        system = f"{system}\n\nMaterial de referencia:\n{joined}"

    messages: list[BaseMessage] = [SystemMessage(content=system)]
    for turn in request.turns:
        messages.append(
            HumanMessage(content=turn.text)
            if turn.role == "user"
            else AIMessage(content=turn.text)
        )
    messages.append(HumanMessage(content=request.question))
    return messages


def _tool_schema(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


async def _run_tool(by_name: dict[str, ToolSpec], call: dict[str, Any]) -> str:
    """Ejecuta lo que el modelo pidió, si está en SU registro.

    Un nombre que no está en el registro se contesta con un texto, no con una excepción: el
    modelo puede inventarse una herramienta, y eso es un turno malo, no una caída. Que no
    esté es además toda la seguridad del módulo — el registro se construyó con lo que este
    llamador puede hacer.
    """
    tool = by_name.get(str(call.get("name", "")))
    if tool is None:
        return "Esa herramienta no está disponible."
    try:
        return await tool.run(dict(call.get("args", {}) or {}))
    except Exception:  # noqa: BLE001 - un caso de uso que falla no tumba la conversación
        logger.warning("La herramienta %s falló", call.get("name"), exc_info=True)
        return "No se pudo consultar ese dato ahora mismo."


def _usage(message: Any) -> tuple[int, int]:
    """Los tokens que dice el PROVEEDOR. Es la única cifra con la que se audita una factura."""
    usage = getattr(message, "usage_metadata", None) or {}
    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def _text_of(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    # Algunos modelos devuelven la respuesta en trozos; se unen los de texto y se ignora el
    # resto (razonamiento, marcadores), que no es para el cliente.
    parts = [
        str(part.get("text", ""))
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    return "".join(parts)
