from fastapi import APIRouter

from src.app.api.v1.routers.mcp_tools import router as mcp_tools_router

# Aggregator for the public HTTP surface. Unlike the sibling services this one is
# NOT version-prefixed: the agent's public paths are fixed by contract — the MCP
# endpoint is mounted at /mcp and the portfolio frontend calls /mcp-tools/invoke —
# so they are mounted at the root rather than under /api/v1.
api_router = APIRouter()
api_router.include_router(mcp_tools_router)
