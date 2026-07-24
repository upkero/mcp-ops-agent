from pydantic import BaseModel, Field


class InvokeRequest(BaseModel):
    """HTTP-boundary schema for POST /mcp-tools/invoke."""

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="Natural-language instruction for the operations agent.",
    )
