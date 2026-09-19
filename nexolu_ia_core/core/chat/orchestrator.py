"""Orquestador del chat: historial -> loop de herramientas -> respuesta.

Equivale a `App\\Services\\Ai\\AiChatService::enviarMensaje()` en el POS. No
conoce nada de POS, Spa ni EasyTickets: recibe ya resueltos el `ToolRegistry`
y el `AgentDefinition` de la aplicacion que llama, y un `AppToolClient` para
devolverle la ejecucion de herramientas a esa misma aplicacion. Por eso este
modulo NUNCA importa nada de `nexolu_ia_core.apps.*` -- esa dependencia va en
el sentido contrario, y es justamente lo que mantiene al Core reutilizable.

Las cuotas comerciales (mensajes gratis, plan mensual) no se validan aca: esa
es una decision de negocio de cada producto, tomada ANTES de llamar al Core.
Lo que si hace siempre el orquestador es registrar uso/costo por tenant, para
que cualquier producto pueda facturar sobre esos datos.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.chat.system_prompt import SystemPromptBuilder
from nexolu_ia_core.core.memory.entities import Message
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.models.router import ModelRouter
from nexolu_ia_core.core.schemas import (
    ChatMessageOut,
    ChatRequest,
    ChatResult,
    ChatStreamChunk,
    ChatStreamEvent,
    ChatTurn,
    DraftOut,
    Role,
    TenantContext,
    ToolCall,
    ToolDefinition,
)
from nexolu_ia_core.core.tools.dispatch_client import AppToolClient, ToolDispatchError
from nexolu_ia_core.core.tools.exceptions import ToolInputException, ToolNotAllowedException
from nexolu_ia_core.core.tools.guard import MAX_TOOL_CALLS_PER_MESSAGE, ToolGuard
from nexolu_ia_core.core.tools.registry import ToolRegistry
from nexolu_ia_core.providers.base import ChatProvider
from nexolu_ia_core.providers.registry import ProviderRegistry

logger = logging.getLogger("nexolu_ia_core.chat")

MAX_USER_MESSAGE_CHARS = 1000


class ChatOrchestrator:
    def __init__(
        self,
        *,
        repository: ConversationRepository,
        provider_registry: ProviderRegistry,
        model_router: ModelRouter,
        guard: ToolGuard | None = None,
        prompt_builder: SystemPromptBuilder | None = None,
    ) -> None:
        self._repo = repository
        self._providers = provider_registry
        self._router = model_router
        self._guard = guard or ToolGuard()
        self._prompts = prompt_builder or SystemPromptBuilder()

    async def send_message(
        self,
        *,
        app_identity: AppIdentity,
        app_display_name: str,
        tool_registry: ToolRegistry,
        agent: AgentDefinition,
        context: TenantContext,
        message: str,
        conversation_id: str | None,
    ) -> ChatMessageOut:
        text = message.strip()
        if not text:
            raise ValueError("El mensaje esta vacio.")
        if len(text) > MAX_USER_MESSAGE_CHARS:
            raise ValueError(f"El mensaje no puede superar {MAX_USER_MESSAGE_CHARS} caracteres.")

        conversation = await self._repo.get_or_create(
            app_id=app_identity.app_id,
            context=context,
            agent=agent.name,
            conversation_id=conversation_id,
            first_text=text,
        )

        await self._repo.add_message(
            conversation_id=conversation.id,
            app_id=app_identity.app_id,
            business_id=context.business_id,
            user_id=context.user_id,
            role="user",
            channel=context.channel,
            content=text,
        )

        tools = self._tools_for_agent(tool_registry, agent, context)
        definitions = [
            ToolDefinition(name=t.name, description=t.description, parameters=t.parameters_for(context))
            for t in tools.values()
        ]

        selection = self._router.resolve(agent, app_identity)
        provider = self._providers.resolve(
            selection.provider,
            selection.model,
            selection.api_key_override,
            selection.site_url,
            selection.site_name,
            selection.provider_preferences,
        )
        client = AppToolClient(app_identity)

        turns = await self._build_turns(conversation.id, context)

        tools_used: list[str] = []
        drafts_created: list[DraftOut] = []
        input_tokens = 0
        output_tokens = 0
        cost_reported: int | None = None
        final_text: str | None = None
        system_prompt = self._prompts.build(app_name=app_display_name, agent=agent, context=context)

        for _ in range(MAX_TOOL_CALLS_PER_MESSAGE):
            started = time.monotonic()
            result = await provider.chat(
                ChatRequest(system=system_prompt, messages=turns, tools=definitions, max_tokens=1500)
            )
            latency_ms = round((time.monotonic() - started) * 1000)

            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            if result.cost_micros is not None:
                cost_reported = (cost_reported or 0) + result.cost_micros

            if not result.wants_tools():
                final_text = result.text or "No pude generar una respuesta. Intentalo de nuevo."
                error_tag = None if result.text else "respuesta_vacia"

                await self._repo.add_message(
                    conversation_id=conversation.id,
                    app_id=app_identity.app_id,
                    business_id=context.business_id,
                    user_id=None,
                    role="assistant",
                    channel=context.channel,
                    content=final_text,
                    provider=provider.name(),
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=latency_ms,
                    error=error_tag,
                )
                break

            await self._repo.add_message(
                conversation_id=conversation.id,
                app_id=app_identity.app_id,
                business_id=context.business_id,
                user_id=None,
                role="assistant",
                channel=context.channel,
                content=result.text,
                tool_calls=[c.model_dump() for c in result.tool_calls],
                provider=provider.name(),
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency_ms,
            )

            turns.append(ChatTurn.assistant(result.text, result.tool_calls))

            for call in result.tool_calls:
                output = await self._execute_tool(
                    tool_registry=tool_registry,
                    client=client,
                    context=context,
                    app_id=app_identity.app_id,
                    conversation_id=conversation.id,
                    user_id=context.user_id,
                    call=call,
                    drafts_created=drafts_created,
                )
                tools_used.append(call.name)

                await self._repo.add_message(
                    conversation_id=conversation.id,
                    app_id=app_identity.app_id,
                    business_id=context.business_id,
                    user_id=None,
                    role="tool",
                    channel=context.channel,
                    content=output,
                    tool_name=call.name,
                )

                turns.append(ChatTurn.tool_result(call.id, call.name, output))

        if final_text is None:
            final_text = (
                "La consulta resulto demasiado compleja. Intenta preguntar algo mas "
                "concreto, por ejemplo acotando un periodo de fechas."
            )
            await self._repo.add_message(
                conversation_id=conversation.id,
                app_id=app_identity.app_id,
                business_id=context.business_id,
                user_id=None,
                role="assistant",
                channel=context.channel,
                content=final_text,
                provider=provider.name(),
                model=provider.model(),
                error="max_tool_calls_alcanzado",
            )

        await self._repo.record_usage(
            app_id=app_identity.app_id,
            business_id=context.business_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_micros=cost_reported if cost_reported is not None else provider.estimate_cost_micros(
                input_tokens, output_tokens
            ),
        )
        await self._repo.touch(conversation)

        return ChatMessageOut(
            conversation_id=conversation.id,
            text=final_text,
            tools_used=list(dict.fromkeys(tools_used)),
            drafts=drafts_created,
        )

    async def send_message_stream(
        self,
        *,
        app_identity: AppIdentity,
        app_display_name: str,
        tool_registry: ToolRegistry,
        agent: AgentDefinition,
        context: TenantContext,
        message: str,
        conversation_id: str | None,
    ) -> AsyncIterator[ChatStreamChunk]:
        """Igual que `send_message`, pero entregando el texto del modelo en
        deltas conforme llegan (SSE), en vez de esperar la respuesta
        completa. La ejecucion de herramientas NO se transmite token a
        token (no tiene sentido streamear JSON intermedio): cada turno del
        loop se streamea, y si ese turno pide herramientas, se ejecutan de
        forma sincrona antes de streamear el turno siguiente."""
        text = message.strip()
        if not text:
            raise ValueError("El mensaje esta vacio.")
        if len(text) > MAX_USER_MESSAGE_CHARS:
            raise ValueError(f"El mensaje no puede superar {MAX_USER_MESSAGE_CHARS} caracteres.")

        conversation = await self._repo.get_or_create(
            app_id=app_identity.app_id,
            context=context,
            agent=agent.name,
            conversation_id=conversation_id,
            first_text=text,
        )

        await self._repo.add_message(
            conversation_id=conversation.id,
            app_id=app_identity.app_id,
            business_id=context.business_id,
            user_id=context.user_id,
            role="user",
            channel=context.channel,
            content=text,
        )

        tools = self._tools_for_agent(tool_registry, agent, context)
        definitions = [
            ToolDefinition(name=t.name, description=t.description, parameters=t.parameters_for(context))
            for t in tools.values()
        ]

        selection = self._router.resolve(agent, app_identity)
        provider = self._providers.resolve(
            selection.provider,
            selection.model,
            selection.api_key_override,
            selection.site_url,
            selection.site_name,
            selection.provider_preferences,
        )
        client = AppToolClient(app_identity)

        turns = await self._build_turns(conversation.id, context)

        tools_used: list[str] = []
        drafts_created: list[DraftOut] = []
        input_tokens = 0
        output_tokens = 0
        cost_reported: int | None = None
        final_text: str | None = None
        system_prompt = self._prompts.build(app_name=app_display_name, agent=agent, context=context)

        for _ in range(MAX_TOOL_CALLS_PER_MESSAGE):
            started = time.monotonic()
            result: ChatResult | None = None

            async for event in self._run_turn(
                provider, ChatRequest(system=system_prompt, messages=turns, tools=definitions, max_tokens=1500)
            ):
                if event.delta:
                    yield ChatStreamChunk(delta=event.delta)
                if event.done:
                    result = event.result

            assert result is not None  # _run_turn siempre emite un evento done con result
            latency_ms = round((time.monotonic() - started) * 1000)

            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            if result.cost_micros is not None:
                cost_reported = (cost_reported or 0) + result.cost_micros

            if not result.wants_tools():
                final_text = result.text or "No pude generar una respuesta. Intentalo de nuevo."
                error_tag = None if result.text else "respuesta_vacia"
                if not result.text:
                    # No se streameo nada para este turno (respuesta vacia del
                    # modelo): el cliente no debe quedarse sin texto alguno.
                    yield ChatStreamChunk(delta=final_text)

                await self._repo.add_message(
                    conversation_id=conversation.id,
                    app_id=app_identity.app_id,
                    business_id=context.business_id,
                    user_id=None,
                    role="assistant",
                    channel=context.channel,
                    content=final_text,
                    provider=provider.name(),
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=latency_ms,
                    error=error_tag,
                )
                break

            await self._repo.add_message(
                conversation_id=conversation.id,
                app_id=app_identity.app_id,
                business_id=context.business_id,
                user_id=None,
                role="assistant",
                channel=context.channel,
                content=result.text,
                tool_calls=[c.model_dump() for c in result.tool_calls],
                provider=provider.name(),
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=latency_ms,
            )

            turns.append(ChatTurn.assistant(result.text, result.tool_calls))

            for call in result.tool_calls:
                output = await self._execute_tool(
                    tool_registry=tool_registry,
                    client=client,
                    context=context,
                    app_id=app_identity.app_id,
                    conversation_id=conversation.id,
                    user_id=context.user_id,
                    call=call,
                    drafts_created=drafts_created,
                )
                tools_used.append(call.name)

                await self._repo.add_message(
                    conversation_id=conversation.id,
                    app_id=app_identity.app_id,
                    business_id=context.business_id,
                    user_id=None,
                    role="tool",
                    channel=context.channel,
                    content=output,
                    tool_name=call.name,
                )

                turns.append(ChatTurn.tool_result(call.id, call.name, output))

        if final_text is None:
            final_text = (
                "La consulta resulto demasiado compleja. Intenta preguntar algo mas "
                "concreto, por ejemplo acotando un periodo de fechas."
            )
            yield ChatStreamChunk(delta=final_text)
            await self._repo.add_message(
                conversation_id=conversation.id,
                app_id=app_identity.app_id,
                business_id=context.business_id,
                user_id=None,
                role="assistant",
                channel=context.channel,
                content=final_text,
                provider=provider.name(),
                model=provider.model(),
                error="max_tool_calls_alcanzado",
            )

        await self._repo.record_usage(
            app_id=app_identity.app_id,
            business_id=context.business_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_micros=cost_reported if cost_reported is not None else provider.estimate_cost_micros(
                input_tokens, output_tokens
            ),
        )
        await self._repo.touch(conversation)

        yield ChatStreamChunk(
            done=True,
            conversation_id=conversation.id,
            text=final_text,
            tools_used=list(dict.fromkeys(tools_used)),
            drafts=drafts_created,
        )

    async def _run_turn(self, provider: ChatProvider, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        """Normaliza `chat()` y `chat_stream()` a la misma secuencia de
        eventos: deltas de texto (si hay) seguidos de un evento final con el
        `ChatResult` completo. Los proveedores sin streaming (ver
        `ChatProvider.supports_streaming`) igual funcionan aca, solo que
        entregan todo el texto de una vez como un unico delta."""
        if not provider.supports_streaming():
            result = await provider.chat(request)
            if result.text:
                yield ChatStreamEvent(delta=result.text)
            yield ChatStreamEvent(done=True, result=result)
            return

        async for event in provider.chat_stream(request):
            yield event

    def _tools_for_agent(self, tool_registry: ToolRegistry, agent: AgentDefinition, context: TenantContext):
        available = tool_registry.available_for(context)
        if agent.tool_names is None:
            return available
        return {name: tool for name, tool in available.items() if name in agent.tool_names}

    async def _build_turns(self, conversation_id: str, context: TenantContext) -> list[ChatTurn]:
        from nexolu_ia_core.config import get_settings

        limit = get_settings().ai_history_turns
        messages = await self._repo.recent_messages(conversation_id, limit)
        turns = self._turns_from_messages(messages)

        if turns and turns[-1].role == Role.USER:
            # Si la zona no se puede resolver, el reloj cae a UTC -- pero la
            # etiqueta tiene que caer con el. Decirle al modelo "hoy es
            # 2026-09-11 02:39 (America/Bogota)" a las 9 de la noche del 10 en
            # Bogota es peor que no decirle la zona: el modelo fecha "hoy"
            # manana y la escritura queda con el dia corrido, sin que nada
            # falle a la vista. (Pasa en Windows sin el paquete `tzdata`.)
            try:
                now = datetime.now(ZoneInfo(context.timezone))
                zona = context.timezone
            except Exception:  # noqa: BLE001 - un timezone invalido no debe tumbar el chat
                logger.warning(
                    "No se pudo resolver la zona horaria '%s'; el contexto de fecha cae a UTC.",
                    context.timezone,
                )
                now = datetime.now(UTC)
                zona = "UTC"
            stamp = now.strftime("%Y-%m-%d %H:%M")
            turns[-1] = ChatTurn.user(f"[Contexto: hoy es {stamp} ({zona})]\n\n{turns[-1].content}")

        return turns

    def _turns_from_messages(self, messages: list[Message]) -> list[ChatTurn]:
        turns: list[ChatTurn] = []
        i = 0
        total = len(messages)

        while i < total:
            msg = messages[i]

            if msg.role == "user":
                turns.append(ChatTurn.user(msg.content or ""))
                i += 1
                continue

            if msg.role == "tool":
                # Huerfano: su assistant quedo fuera de la ventana del historial.
                i += 1
                continue

            if msg.error is not None:
                # Texto nuestro de contingencia, no una respuesta real del
                # modelo: reenviarlo como historial le enseñaria a imitarlo.
                i += 1
                continue

            calls = self._tool_calls_from(msg)

            if not calls:
                if msg.content:
                    turns.append(ChatTurn.assistant(msg.content))
                i += 1
                continue

            results = []
            j = i + 1
            while j < total and messages[j].role == "tool" and len(results) < len(calls):
                results.append(messages[j])
                j += 1

            if len(results) != len(calls):
                # Grupo cortado por el limite de la ventana: un tool_calls sin
                # todos sus resultados es invalido para casi todo proveedor.
                if msg.content:
                    turns.append(ChatTurn.assistant(msg.content))
                i = j
                continue

            turns.append(ChatTurn.assistant(msg.content, calls))
            for call, result_msg in zip(calls, results):
                turns.append(
                    ChatTurn.tool_result(call.id, call.name, self._compact_tool_result(result_msg.content or ""))
                )
            i = j

        return turns

    def _tool_calls_from(self, msg: Message) -> list[ToolCall]:
        raw = msg.tool_calls
        if not raw:
            return []
        try:
            return [ToolCall(id=c["id"], name=c["name"], arguments=c.get("arguments") or {}) for c in raw]
        except (KeyError, TypeError):
            return []

    def _compact_tool_result(self, content: str) -> str:
        """Reduce un resultado historico antes de reenviarlo: evita pesar
        cada mensaje siguiente con datos ya viejos que el modelo podria citar
        como si fueran actuales."""
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content[:200]

        if not isinstance(data, dict):
            return content[:200]

        if "error" in data:
            return json.dumps({"error": data["error"]}, ensure_ascii=False)

        if data.get("estado") == "borrador_pendiente_de_confirmacion":
            return json.dumps(
                {"estado": data["estado"], "resumen": data.get("resumen")}, ensure_ascii=False
            )

        return json.dumps(
            {
                # Pasó en producción con un catálogo real: al quinto mensaje
                # el modelo ya no tenía los precios y se inventó tres
                # servicios que no existen, con sus valores. Una nota suave
                # ("si necesitas cifras exactas...") deja abierta la puerta
                # a completar el hueco de memoria; esta la cierra.
                "nota": "RESULTADO DESCARTADO por antiguedad. Los datos que estaban aqui "
                "YA NO ESTAN: no cites de memoria precios, horas, duraciones ni nombres "
                "que vinieron de esta llamada. Si los necesitas, vuelve a llamar la "
                "herramienta."
            },
            ensure_ascii=False,
        )

    async def _execute_tool(
        self,
        *,
        tool_registry: ToolRegistry,
        client: AppToolClient,
        context: TenantContext,
        app_id: str,
        conversation_id: str,
        user_id: str,
        call: ToolCall,
        drafts_created: list[DraftOut],
    ) -> str:
        try:
            tool = tool_registry.resolve_for(context, call.name)
            arguments = self._guard.sanitize(tool, context, call.arguments)

            if tool.is_write():
                summary = tool.summarize(arguments)  # type: ignore[attr-defined]
                fields = tool.fields_for(context)  # type: ignore[attr-defined]
                draft = await self._repo.create_draft(
                    conversation_id=conversation_id,
                    app_id=app_id,
                    business_id=context.business_id,
                    user_id=user_id,
                    draft_type=tool.draft_type,  # type: ignore[attr-defined]
                    tool_name=tool.name,
                    payload=arguments,
                    summary=summary,
                )
                drafts_created.append(
                    DraftOut(
                        id=draft.id,
                        tool_type=draft.draft_type,
                        status=draft.status,
                        summary=summary,
                        fields=fields,
                        values=arguments,
                    )
                )
                return json.dumps(
                    {
                        "estado": "borrador_pendiente_de_confirmacion",
                        "resumen": summary,
                        "instruccion": (
                            "La tarjeta con los datos YA se le mostro al usuario y puede editarla ahi. "
                            "Responde con UNA frase corta invitandolo a revisar y confirmar. No repitas "
                            "los valores ni afirmes que quedo registrado: hasta que confirme, no existe."
                        ),
                    },
                    ensure_ascii=False,
                )

            data = await client.invoke(tool.name, arguments, context)
            await self._repo.log_tool_invocation(
                conversation_id=conversation_id,
                app_id=app_id,
                business_id=context.business_id,
                tool_name=tool.name,
                arguments=arguments,
                status="ok",
                result_summary=json.dumps(data, ensure_ascii=False)[:500],
                context=context.model_dump(),
            )
            return json.dumps(data, ensure_ascii=False)

        except ToolInputException as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        except ToolNotAllowedException as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        except ToolDispatchError as exc:
            logger.error("Fallo al despachar herramienta '%s': %s", call.name, exc)
            await self._repo.log_tool_invocation(
                conversation_id=conversation_id,
                app_id=app_id,
                business_id=context.business_id,
                tool_name=call.name,
                arguments=call.arguments,
                status="error",
                result_summary=str(exc)[:500],
                context=context.model_dump(),
            )
            return json.dumps({"error": "No se pudo consultar ese dato en este momento."}, ensure_ascii=False)
        except Exception:
            logger.exception("Fallo inesperado ejecutando herramienta '%s'", call.name)
            return json.dumps({"error": "No se pudo consultar ese dato en este momento."}, ensure_ascii=False)
