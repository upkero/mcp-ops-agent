from abc import ABC, abstractmethod


class OpsCoreHealthChecker(ABC):
    """Abstraction over an ops-core-api reachability probe (for readiness checks)."""

    @abstractmethod
    async def ping(self) -> bool:
        """Return True if ops-core-api answers its health endpoint."""
