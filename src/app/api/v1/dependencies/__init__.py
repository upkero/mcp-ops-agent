from typing import Annotated

from fastapi import Depends, Request

from src.app.bootstrap.container import ApplicationContainer
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.services.orchestrator import OrchestratorService


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.container.llm_client  # type: ignore[no-any-return]


def get_orchestrator(request: Request) -> OrchestratorService:
    return request.app.state.container.orchestrator  # type: ignore[no-any-return]


# Depends helpers exposed as annotated aliases (used directly as param types in
# routers, e.g. `orchestrator: OrchestratorDep`).
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
OrchestratorDep = Annotated[OrchestratorService, Depends(get_orchestrator)]
