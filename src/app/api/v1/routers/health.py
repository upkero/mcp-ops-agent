from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.app.api.v1.dependencies import LLMClientDep, OpsCoreHealthCheckerDep

router = APIRouter(tags=["infra"])


@router.get("/health")
async def health(llm_client: LLMClientDep, ops_core: OpsCoreHealthCheckerDep) -> JSONResponse:
    """Readiness check: the agent can serve only if both upstreams are reachable.

    Reports the LLM provider and ops-core-api independently, and returns 503 when
    either is down so a load balancer stops routing to a broken instance.
    """
    llm_ok = await llm_client.ping()
    ops_core_ok = await ops_core.ping()
    healthy = llm_ok and ops_core_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "llm": llm_ok,
            "ops_core": ops_core_ok,
        },
    )
