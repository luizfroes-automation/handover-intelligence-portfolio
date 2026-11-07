"""Domain exceptions raised at the LLM client boundary."""


class LLMClientError(Exception):
    """Base for failures surfaced by the LLM client."""


class ProviderUnavailableError(LLMClientError):
    """The provider could not be reached or failed to serve the request."""


class InvalidLLMResponseError(LLMClientError):
    """The provider output does not satisfy the handover contract."""


class LLMConfigurationError(LLMClientError):
    """The provider rejected the client or generation configuration."""


class TranscriptTooLargeError(Exception):
    """A structurally valid transcript exceeds the total size limit.

    Raised at the endpoint, after request validation and before any provider
    call, so an oversized input costs nothing and is not blamed on the provider.
    """
