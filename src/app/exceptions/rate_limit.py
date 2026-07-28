from src.app.exceptions.base import BaseAppException


class RateLimitExceededError(BaseAppException):
    """Raised when a client exceeds the configured request rate.

    One invoke request drives an agent loop of up to ``AGENT_MAX_STEPS`` LLM
    calls, so the cap is a cost control as much as an abuse control.
    """

    status_code = 429
    error_code = "rate_limit_exceeded"
    default_detail = "Too many requests. Please slow down and retry shortly."
