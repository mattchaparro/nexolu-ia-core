"""Redaccion de una sola pasada, sin conversacion ni herramientas.

Existe para casos como los insights embebidos del POS (ver
`App\\Services\\Ai\\Contracts\\AiInsightDefinition`): la app ya calculo sus
propios numeros de forma deterministica y solo necesita que el modelo los
redacte en 1-2 frases, con un system+user prompt propio que ella misma
arma. `/v1/chat` no encaja aca -- persiste conversacion, arma un loop de
herramientas y ata la respuesta a un `conversation_id`, nada de lo cual
aplica a un texto que se cachea aparte (`ai_insights` del lado del POS) y no
es parte de ningun hilo de chat.

Igual que en el chat, el uso/costo se registra siempre (ver
`ChatOrchestrator`): la comercializacion de este endpoint es la misma que la
del chat, solo cambia la forma del prompt.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexolu_ia_core.core.agents.base import AgentDefinition
from nexolu_ia_core.core.auth.apps import AppIdentity
from nexolu_ia_core.core.auth.dependencies import get_current_app
from nexolu_ia_core.core.memory.db import get_session
from nexolu_ia_core.core.memory.repository import ConversationRepository
from nexolu_ia_core.core.models.router import ModelRouter
from nexolu_ia_core.core.schemas import ChatRequest, ChatTurn, CompletionIn, CompletionOut
from nexolu_ia_core.providers.registry import get_provider_registry

router = APIRouter(prefix="/v1", tags=["completions"])

# Sin instrucciones ni herramientas propias: el system/user prompt completo
# lo trae la app llamante. Solo sirve para que ModelRouter resuelva
# proveedor/modelo con la misma precedencia que un agente de chat (override
# de agente > override de la app > default global) - aca no hay override de
# agente, asi que en la practica es "override de la app > default global".
_AGENT = AgentDefinition(name="completion", display_name="Completion", instructions="")


@router.post("/completions", response_model=CompletionOut)
async def create_completion(
    payload: CompletionIn,
    app: AppIdentity = Depends(get_current_app),
    session: AsyncSession = Depends(get_session),
) -> CompletionOut:
    selection = ModelRouter().resolve(_AGENT, app)
    provider = get_provider_registry().resolve(selection.provider, selection.model, selection.api_key_override)

    result = await provider.chat(
        ChatRequest(system=payload.system, messages=[ChatTurn.user(payload.user)], max_tokens=payload.max_tokens)
    )

    cost_micros = (
        result.cost_micros
        if result.cost_micros is not None
        else provider.estimate_cost_micros(result.input_tokens, result.output_tokens)
    )

    await ConversationRepository(session).record_usage(
        app_id=app.app_id,
        business_id=payload.context.resolved(app.app_id).business_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_micros=cost_micros,
    )
    await session.commit()

    return CompletionOut(
        text=result.text or "",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model=result.model,
        cost_micros=cost_micros,
    )
