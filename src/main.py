from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.api.v1.exception_handlers import register_exception_handlers
from src.app.api.v1.middleware.request_id import register_request_id_middleware
from src.app.api.v1.router import api_router
from src.app.api.v1.routers.health import router as health_router
from src.app.bootstrap.container import ApplicationContainer
from src.app.core.logging import setup_logging
from src.app.core.settings.app import get_app_settings
from src.app.core.settings.logging import get_logging_settings
from src.app.mcp.v1.server import build_mcp_server


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    setup_logging(get_logging_settings())

    # The container is created here (not in the lifespan) because the MCP ASGI app
    # must be mounted before startup. `container` can be injected for tests.
    container = container or ApplicationContainer()

    # Build the MCP server from the SAME container the HTTP layer uses, so tools
    # and services share one set of dependencies. Its Streamable HTTP ASGI app is
    # mounted at /mcp; streamable_http_path="/" keeps the endpoint exactly /mcp.
    mcp_server = build_mcp_server(container)
    mcp_app = mcp_server.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Mounted sub-apps do not receive Starlette lifespan events, so the MCP
        # session manager must be run here for the /mcp endpoint to serve requests.
        async with mcp_server.session_manager.run():
            try:
                yield
            finally:
                await container.close()

    app = FastAPI(title="MCP Ops Agent", version="0.1.0", lifespan=lifespan)
    # Set on state here (not only in the lifespan) so the app is usable under an
    # ASGI transport that does not run the lifespan (e.g. httpx.ASGITransport tests).
    app.state.container = container

    settings = get_app_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials="*" not in settings.cors_allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_request_id_middleware(app)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router)
    # Mount the real MCP server: both Claude Desktop and the internal orchestrator
    # reach the tools only through this endpoint, over genuine MCP JSON-RPC.
    app.mount("/mcp", mcp_app)

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
