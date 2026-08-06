# Nexolú IA Core

Plataforma de inteligencia artificial reutilizable para todo el ecosistema
Nexolú (POS, Spa, EasyTickets, CRM y lo que venga despues). No es "la IA del
POS": es un servicio Python/FastAPI independiente que cualquier producto
puede usar sin acoplarse a el ni a los demas.

## Principios de arquitectura

- **El Core nunca toca una base de datos de negocio.** No ejecuta SQL, no
  conoce columnas ni tablas. Toda la informacion sale de herramientas que
  cada aplicacion expone y autoriza.
- **Laravel (o lo que sea) sigue siendo la unica fuente de verdad.** El
  negocio, los permisos y MySQL siguen del lado de cada producto.
- **Una API key por aplicacion, nunca por usuario final.** El Core no tiene
  sesion de usuario propia: confia en que la app que lo llama (autenticada
  con su API key) ya resolvio quien es el usuario y que puede hacer. Ver
  `TenantContext` en `core/schemas.py`.
- **Las escrituras nunca se ejecutan solas.** Una herramienta de escritura
  (`crear_gasto`, `vender_ticket`, `crear_cita`...) genera un borrador; solo
  se ejecuta de verdad cuando alguien lo confirma explicitamente
  (`POST /v1/drafts/{id}/confirm`).
- **`core/` nunca importa nada de `apps/`.** La dependencia va siempre en un
  solo sentido: `apps/pos`, `apps/spa`, `apps/tickets` dependen del Core, el
  Core no sabe que existen. Agregar un producto nuevo no toca una linea de
  `core/`.

## Estructura

```
nexolu_ia_core/
  main.py            FastAPI app factory
  config.py          Settings (env vars): DB, proveedores, apps registradas
  core/
    schemas.py         DTOs neutrales (ChatTurn, ToolCall, TenantContext...)
    chat/               Orquestador: historial -> loop de herramientas -> respuesta
    agents/             Un agente = personalidad + subconjunto de herramientas
    tools/              Contrato de herramientas, ToolGuard (sanitizacion), registry
    models/             Seleccion de proveedor/modelo por agente
    memory/             Persistencia (SQLAlchemy async) + Alembic
    auth/               Identidad de las apps cliente (API key -> AppIdentity)
    telemetry/          Logging JSON + uso/costo agregado
    rag/ voice/ documents/   Interfaces, sin implementacion (ver mas abajo)
  providers/          OpenRouter, OpenAI, DeepSeek (base OpenAI-compatible
                      compartida), Anthropic (nativo), Null (tests)
  apps/
    pos/  spa/  tickets/    Registro de herramientas + agentes de cada producto
  api/v1/             Endpoints HTTP: chat, conversations, drafts, health
tests/                pytest (guard, registry, proveedores, orquestador, API)
alembic/              Migraciones de esquema
```

## Como correr en local

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env   # y completar al menos NEXOLU_APPS_JSON

alembic upgrade head    # o dejar que arranque solo con SQLite (ver main.py)
uvicorn nexolu_ia_core.main:app --reload
```

Con `DEFAULT_PROVIDER=null` (el valor por defecto) el servicio responde con
el proveedor determinista `NullProvider`, sin gastar tokens reales -- util
para probar el flujo completo (auth, historial, borradores) antes de cargar
API keys.

## Probar el chat

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Authorization: Bearer dev-pos-key" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "cajero",
    "message": "Como esta la caja?",
    "context": {
      "business_id": "biz-1",
      "user_id": "user-1",
      "is_admin": true,
      "permissions": [],
      "features": [],
      "channel": "web"
    }
  }'
```

La app se identifica por la API key (`dev-pos-key` en `.env.example`, mapeada
a `pos` en `NEXOLU_APPS_JSON`), nunca por un campo del body: asi ninguna
aplicacion puede leer las herramientas de otra.

## Tests

```bash
pytest
```

37 tests cubren: `ToolGuard` (claves reservadas, coercion de tipos, rangos de
fecha), `ToolRegistry` (filtro por feature/permiso, admin vs empleado),
`OpenRouterProvider` (payload, parseo, manejo de `arguments` vacios), el
orquestador completo con un proveedor "scripted" (lectura, escritura ->
borrador, argumentos invalidos devueltos al modelo, historial entre
mensajes), y los endpoints HTTP de punta a punta.

## Extender el Core

- **Agregar un proveedor de IA nuevo** (Ollama local, Gemini nativo...):
  escribir una clase en `providers/` (heredando de `OpenAICompatibleProvider`
  si habla ese formato) y una entrada en `providers/registry.py`. Nada mas
  cambia.
- **Agregar una aplicacion nueva** (CRM...): un paquete `apps/<nombre>/` con
  `tools.py` (`Tool`/`WriteTool`) y `agents.py` (`AgentDefinition`), mas una
  rama en `apps/registry.get_app_bundle()` y una entrada en
  `NEXOLU_APPS_JSON`. El Core no cambia.
- **Agregar una herramienta a una app existente**: una entrada mas en su
  `tools.py`. Si es de escritura, usar `WriteTool` para que pase por
  confirmacion humana.
- **RAG, voz, documentos**: las interfaces ya existen en `core/rag`,
  `core/voice`, `core/documents` (ver los docstrings de cada una para el
  razonamiento de por que no tienen implementacion todavia). Implementar un
  proveedor concreto ahi y ofrecerlo como una herramienta mas no requiere
  tocar `core/chat`.

## Conectar el POS real

`apps/pos` define el catalogo de herramientas y agentes con los mismos
nombres que usa `App\Capabilities\Registry` del lado del POS (Laravel,
repo `nexolu-pos-api`). Ese endpoint ya existe:

```
POST {base_url}/api/ai/tools/invoke
Authorization: Bearer <api_key de esa app>
{"tool": "ventas_resumen", "arguments": {...}, "context": {...}}
-> {"data": {...}}  o  {"error": "..."}
```

Apuntar `NEXOLU_APPS_JSON.pos.base_url` al POS real es toda la migracion
necesaria -- no hay que tocar el Core.

`required_permission`/`required_feature` de cada `Tool` en `apps/pos/tools.py`
tienen que coincidir EXACTO con los nombres reales de
`App\Support\PermissionCatalog` y `feature_flags` del lado del POS - son
claves de otro sistema, no vocabulario propio de este repo, asi que un typo
aca no lo detecta ningun test local (silenciosamente esconde o expone mal
una herramienta). Los nombres de las herramientas (`ventas_resumen`,
`crear_gasto`, ...) sí son el contrato compartido y viajan en español a
proposito en los dos lados, aunque las clases que las implementan en el POS
esten en ingles (convencion de codigo de ese repo, no del contrato).
