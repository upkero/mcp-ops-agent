import secrets
from typing import Annotated

from fastapi import Depends, Header, Request

from src.app.bootstrap.container import ApplicationContainer
from src.app.core.settings.security import SecuritySettings, get_security_settings
from src.app.exceptions.auth import UnauthorizedError
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.interfaces.ops_core.health import OpsCoreHealthChecker
from src.app.services.orchestrator import OrchestratorService


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.container.llm_client  # type: ignore[no-any-return]


def get_orchestrator(request: Request) -> OrchestratorService:
    return request.app.state.container.orchestrator  # type: ignore[no-any-return]


def get_ops_core_health_checker(request: Request) -> OpsCoreHealthChecker:
    return request.app.state.container.ops_core_health_probe  # type: ignore[no-any-return]


def require_api_key(
    settings: Annotated[SecuritySettings, Depends(get_security_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Guard: enforce X-API-Key only when SECURITY_API_KEY is configured.

    Left open by default so the demo and MCP clients work without a key; set the
    env var to require it. Uses a constant-time comparison.
    """
    if settings.api_key is None:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise UnauthorizedError()


# Depends helpers exposed as annotated aliases (used directly as param types in
# routers, e.g. `orchestrator: OrchestratorDep`).
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
OrchestratorDep = Annotated[OrchestratorService, Depends(get_orchestrator)]
OpsCoreHealthCheckerDep = Annotated[OpsCoreHealthChecker, Depends(get_ops_core_health_checker)]
