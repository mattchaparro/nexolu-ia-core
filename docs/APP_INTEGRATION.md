# Integrar una aplicacion nueva al Nexolu IA Core

Esta guia es la referencia rapida para conectar una app nueva (Spa, EasyTickets,
lo que venga) al Core, basada en la integracion real ya hecha con el POS
(`nexolu-pos-api`). Si la seguis al pie de la letra, conectar una app nueva es
horas, no dias: nada de esto requiere tocar `core/` del Core.

Ver tambien:
- Swagger interactivo del contrato que la app debe **implementar**:
  `GET /docs/app-contract` del servicio corriendo (o `docs/openapi/app-contract.json`
  en este repo, sin levantar nada).
- Swagger autogenerado de lo que la app debe **consumir**: `GET /docs` del
  servicio corriendo (FastAPI lo genera solo a partir de las rutas reales).

## 1. Arquitectura en una frase

El Core nunca toca la base de datos de tu app. Vos le decis que herramientas
existen (metadata: nombre, descripcion, JSON Schema, permiso/feature) y el
Core, cuando el modelo decide usar una, te llama de vuelta a un unico
endpoint tuyo para que la ejecutes con tu propia logica de negocio.

```
Usuario final → tu app (Laravel/Node/lo que sea) → POST /v1/chat (Core)
                                                        │
                                          Core decide llamar una tool
                                                        │
                                                        ▼
                                     POST {tu base_url}/api/ai/tools/invoke
                                                        │
                                          tu app ejecuta con SU logica
                                                        │
                                                        ▼
                                              Core arma la respuesta final
```

## 2. Que debe IMPLEMENTAR tu app (2 endpoints)

Ver el contrato formal completo en `docs/openapi/app-contract.json`
(Swagger en `/docs/app-contract`). Resumen:

### `POST {base_url}/api/ai/tools/invoke` (obligatorio)

Unico endpoint de despacho. Body: `{"tool": "...", "arguments": {...}, "context": {...}}`.
Responde `{"data": {...}}` (200) o `{"error": "..."}` (4xx/5xx).

Checklist de lo que tu implementacion debe hacer, en orden:

1. **Autenticar** el request: `Authorization: Bearer <api_key>` debe coincidir
   con la que te devolvio el Core al registrar tu app con
   `POST /v1/admin/apps` (ver la seccion de administracion mas abajo). Nunca
   uses el sistema de sesion/tokens de usuario para esto - es una API key de
   aplicacion, estatica, distinta de eso.
2. **Resolver el `context`** (`business_id`, `user_id`) contra tu propia base
   de datos. NUNCA confies en el a ciegas solo porque la llamada viene
   autenticada: verifica que el usuario exista, este activo y pertenezca a
   ese negocio. Referencia real: `AiToolInvokeController::invoke()` en
   `nexolu-pos-api` hace exactamente esto antes de tocar nada mas.
3. **Resolver `tool`** contra tu propio registro interno de capacidades
   (nombre → clase/funcion). 404 si no existe.
4. **Revalidar permiso/feature** con tu propio sistema de autorizacion -
   nunca confies en que el Core ya filtro bien lo que le ofrecio al modelo.
   Un modelo puede alucinar un nombre de herramienta que nunca se le paso.
5. **Revalidar `arguments`**: el Core ya los paso por su `ToolGuard` (tipos
   coercionados, claves reservadas como `business_id`/`sql`/`query`
   rechazadas), pero eso es defensa del lado del Core, no del tuyo. Tu
   implementacion define sus propias reglas.
6. **Ejecutar reusando tu logica de negocio existente** (Services, no
   Eloquent/ORM directo, no una reimplementacion paralela de lo que ya hace
   tu API HTTP normal para esa misma accion).
7. **Las escrituras se ejecutan de inmediato aca**, sin preview propio de tu
   lado: la confirmacion humana ya paso por el Core (ver seccion 4) antes de
   que esta llamada exista.

### `GET {base_url}/api/ai/tools/catalog` (recomendado, no obligatorio)

Devuelve el permiso/feature REAL que protege cada herramienta:

```json
{"tools": {"ventas_resumen": {"required_permission": "reports.sales", "required_feature": null}}}
```

El Core lo consulta y cachea ~24h (`TOOL_CATALOG_TTL_SECONDS`, ver
`core/tools/remote_catalog.py`) para no tener que redeployarse cada vez que
renombras un permiso. Sin este endpoint, el Core usa los valores que hayas
declarado a mano en `apps/<tu_app>/tools.py` de este repo - funciona, pero se
puede desalinear en silencio (nos paso una vez con el POS).

## 3. Que debe CONSUMIR tu app (lo que el Core expone)

Todo esto ya existe y tiene Swagger autogenerado en `/docs` del servicio
corriendo. Los mas relevantes:

- `POST /v1/chat` - manda un mensaje de un usuario ya autenticado en TU app.
  Tu backend resuelve el `TenantContext` (ver seccion 5) y llama esto,
  firmado con tu API key.
- `POST /v1/drafts/{id}/confirm` / `POST /v1/drafts/{id}/discard` - tu
  frontend llama esto cuando el usuario confirma o descarta una tarjeta de
  "borrador pendiente" que vino en la respuesta de `/v1/chat`.
- `GET /v1/conversations/{id}` - historial de una conversacion.
- `GET /v1/usage/summary` / `GET /v1/usage/daily` - cuanto ha gastado TU app
  (opcionalmente filtrado por `business_id`), autenticado con tu propia API
  key. Ver seccion 6.

## 4. El flujo de escritura: nunca se ejecuta sola

Una herramienta de escritura (`WriteTool` en `core/tools/base.py`) nunca
llama a tu `/api/ai/tools/invoke` directo cuando el modelo la invoca: el
orquestador arma un **borrador** (guardado en la base del Core, no en la
tuya) y le devuelve al usuario una tarjeta con los valores para revisar. Solo
cuando alguien confirma explicitamente (`POST /v1/drafts/{id}/confirm`) el
Core te llama de verdad. Vos como app integradora no implementas nada de
este flujo - ya vive en `core/chat/orchestrator.py` y `api/v1/drafts.py`, es
igual para cualquier app.

## 5. TenantContext: quien esta preguntando

Tu backend arma esto ANTES de llamar `POST /v1/chat`, a partir de tu propia
sesion de usuario autenticado - nunca lo recibe del cliente/frontend:

```json
{
  "business_id": "42",
  "user_id": "7",
  "is_admin": false,
  "permissions": ["reports.sales", "cash_shift.manage"],
  "features": ["expenses", "clients"],
  "channel": "web",
  "timezone": "America/Bogota",
  "locale": "es"
}
```

`permissions` son los EFECTIVOS del usuario (heredados por rol incluidos, no
solo los directos), en el vocabulario real de tu app. `features` son los
feature flags realmente habilitados para ese negocio. Referencia real:
`AiChatController::send()` en `nexolu-pos-api` arma exactamente esto.

## 6. Costos y uso: por que existen dos niveles

El Core registra uso/costo por `app_id` + `business_id` + dia, SIEMPRE, sin
condicionarlo a ningun plan comercial (ver `UsageDaily` en
`core/memory/entities.py`). Dos consumidores distintos de ese mismo dato:

- **Tu propia app** (autenticada con TU API key) puede consultar
  `GET /v1/usage/summary`/`GET /v1/usage/daily`, opcionalmente filtrado por
  `business_id` - asi el dueño de un negocio dentro de tu app ve cuanto gasta
  SU IA, y vos como dueño de la app ves el total agregado de todos tus
  negocios.
- **Nexolu como plataforma** (autenticada con `NEXOLU_PLATFORM_API_KEY`, una
  key aparte, cross-app) consulta `GET /v1/platform/usage`, agrupado por
  `app_id` - cuanto gasta el POS en total, cuanto el Spa, etc. Esta key nunca
  se le entrega a una app integradora.

## 7. Modelo/proveedor por app: workspaces de OpenRouter independientes

Cada app puede tener su propio proveedor, modelo y API key de IA, para que
las estadisticas y el costo queden segregados por app en el dashboard del
proveedor (p.ej. un workspace de OpenRouter por app, no uno solo compartido).
Se declara al crear o actualizar la app con el API de administracion (ver
seccion 8), `Authorization: Bearer <NEXOLU_PLATFORM_API_KEY>`:

```bash
curl -X PATCH https://ia.nexolu.co/v1/admin/apps/pos \
  -H "Authorization: Bearer $NEXOLU_PLATFORM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "site_url": "https://pos.nexolu.co", "site_name": "Nexolu POS",
    "provider": "openrouter", "model": "deepseek/deepseek-chat",
    "provider_api_key": "sk-or-v1-<workspace del POS>",
    "provider_preferences": {"order": ["DeepSeek"], "allow_fallbacks": true}
  }'
```

`site_url`/`site_name` viajan como los headers `HTTP-Referer`/`X-Title` en
cada llamada a OpenRouter (asi el dashboard distingue el trafico de cada app
aunque compartan API key global), y `provider_preferences` se inyecta tal
cual en el campo `provider` del payload de `chat/completions` -- ver
[la documentacion de OpenRouter](https://openrouter.ai/docs/quickstart) para
las claves soportadas (`order`, `allow_fallbacks`, `data_collection`, etc).

Precedencia (mas especifico gana): override de agente puntual
(`AgentDefinition.provider`/`.model` en `apps/<app>/agents.py`) > override de
la app (`provider`/`model`/`provider_api_key` arriba) > default global
(`DEFAULT_PROVIDER`/`DEFAULT_MODEL`). `provider_api_key` solo se usa si el
proveedor resuelto coincide con el `provider` declarado de la app - si un
agente puntual fuerza OTRO proveedor, se usa la API key global de ese
proveedor, no la de la app.

**Crear el workspace en OpenRouter es un paso manual tuyo** (dashboard de
OpenRouter → crear un workspace/API key nuevo por app): este repo solo
soporta que cada app use uno distinto, no los crea.

## 8. Checklist para integrar una app nueva

1. Crear `nexolu_ia_core/apps/<tu_app>/tools.py` (`Tool`/`WriteTool`,
   mismos nombres que va a implementar tu `/api/ai/tools/invoke`) y
   `agents.py` (`AgentDefinition` por cada personalidad del chat).
2. Agregar una rama en `apps/registry.py::get_app_bundle()`.
3. Darla de alta con `POST /v1/admin/apps` (`base_url`, y opcionalmente
   `site_url`/`site_name`/`provider`/`model`/`provider_api_key`/
   `provider_preferences` - ver seccion 7). Guardar la `api_key` que devuelve:
   no se vuelve a mostrar (aunque se puede rotar con
   `POST /v1/admin/apps/{app_id}/regenerate-key`).
4. Del lado de tu app: implementar `POST /api/ai/tools/invoke` (obligatorio)
   y `GET /api/ai/tools/catalog` (recomendado) - ver seccion 2.
5. Del lado de tu app: un endpoint que reciba el mensaje del usuario, arme el
   `TenantContext` (seccion 5) y llame `POST /v1/chat` del Core.
6. Probar de punta a punta con `DEFAULT_PROVIDER=null` (respuesta
   determinista, sin gastar tokens) antes de cargar una API key real.

`core/` no cambia en ningun paso de esta lista.
