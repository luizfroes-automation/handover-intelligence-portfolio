"""Domain exceptions raised at the LLM client boundary."""


class LLMClientError(Exception):
    """Base for failures surfaced by the LLM client."""


class ProviderUnavailableError(LLMClientError):
    """The provider could not be reached or failed to serve the request."""


class InvalidLLMResponseError(LLMClientError):
    """The provider output does not satisfy the handover contract."""


class LLMConfigurationError(LLMClientError):
    """The provider rejected the client or generation configuration."""


class ProviderRateLimitedError(LLMClientError):
    """The provider refused the request for capacity or exhausted quota.

    The refusal is on the provider's side, but it is not a transport failure: the
    request reached the provider and was answered. The status alone does not say
    whether a short window or a daily quota produced it, and no retry is
    configured for it.
    """


class ContentBlockedError(LLMClientError):
    """The provider reported a content block, so no usable assessment is available.

    ``stage`` is where the block was reported ("prompt" or "candidate") and
    ``reason`` is the enum value the provider returned, already restricted to the
    values this service classifies. The message is fixed: the provider's own text
    is never carried by this exception.
    """

    def __init__(self, *, stage: str, reason: str) -> None:
        super().__init__("LLM provider reported a content block")
        self.stage = stage
        self.reason = reason


class TranscriptTooLargeError(Exception):
    """A structurally valid transcript exceeds the total size limit.

    Raised at the endpoint, after request validation and before any provider
    call, so an oversized input costs nothing and is not blamed on the provider.
    """
