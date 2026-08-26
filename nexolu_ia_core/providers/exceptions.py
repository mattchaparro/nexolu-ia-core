class AiProviderError(RuntimeError):
    """Fallo al hablar con un proveedor de IA (config invalida, HTTP, parseo)."""


class AiProviderRetryableError(AiProviderError):
    """Fallo transitorio (429 rate limit, 5xx) -- vale la pena reintentar con
    backoff exponencial (ver `providers/openai_compatible.py::_post`).
    Errores de cliente (400/401/403/404) NO usan esta subclase: reintentarlos
    no cambia el resultado, solo demora el error."""
