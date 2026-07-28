from fastapi import APIRouter

from src.app.api.v1.routers.invoke import router as invoke_router

# Aggregator for the public HTTP surface, versioned at /api/v1 like every sibling
# service. The MCP endpoint is NOT part of it: /mcp is an external contract that
# Claude Desktop and MCP Inspector depend on, and it is mounted in `main` as its
# own ASGI app.
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(invoke_router)
