import inspect
from functools import cached_property

import httpx

from src.app.core.settings.agent import get_agent_settings
from src.app.core.settings.llm import get_llm_settings
from src.app.core.settings.ops_core import get_ops_core_settings
from src.app.gateways.agent.mcp_tool_gateway import McpToolGateway
from src.app.gateways.notifications.simulated_channel import SimulatedNotificationChannel
from src.app.gateways.ops_core.availability_gateway import OpsCoreAvailabilityGateway
from src.app.gateways.ops_core.client import create_ops_core_http_client
from src.app.gateways.ops_core.customer_gateway import OpsCoreCustomerGateway
from src.app.gateways.ops_core.health_probe import OpsCoreHealthProbe
from src.app.gateways.ops_core.pricing_gateway import OpsCorePricingGateway
from src.app.interfaces.agent.tool_gateway import ToolGateway
from src.app.interfaces.llm.llm_client import LLMClient
from src.app.interfaces.notifications.channel import NotificationChannel
from src.app.interfaces.ops_core.availability import AvailabilityGateway
from src.app.interfaces.ops_core.customers import CustomerGateway
from src.app.interfaces.ops_core.health import OpsCoreHealthChecker
from src.app.interfaces.ops_core.pricing import PricingGateway
from src.app.llm.factory import create_llm_client
from src.app.services.availability import AvailabilityService
from src.app.services.customer import CustomerService
from src.app.services.notification import NotificationService
from src.app.services.orchestrator import OrchestratorService
from src.app.services.pricing import PricingService


class ApplicationContainer:
    """Manual DI container.

    Each dependency is a lazily-built, memoized ``cached_property``; return types
    are interfaces (not concretes), so the wiring reads as a composition of
    abstractions. Built once on first access and closed on lifespan shutdown.
    This service has no database — the only pooled resource is one shared httpx
    client to ops-core-api, injected into every ops-core adapter.
    """

    @cached_property
    def llm_client(self) -> LLMClient:
        return create_llm_client(get_llm_settings())

    @cached_property
    def _ops_core_client(self) -> httpx.AsyncClient:
        return create_ops_core_http_client(get_ops_core_settings())

    @cached_property
    def availability_gateway(self) -> AvailabilityGateway:
        return OpsCoreAvailabilityGateway(
            client=self._ops_core_client,
            max_attempts=get_ops_core_settings().max_attempts,
        )

    @cached_property
    def customer_gateway(self) -> CustomerGateway:
        return OpsCoreCustomerGateway(
            client=self._ops_core_client,
            max_attempts=get_ops_core_settings().max_attempts,
        )

    @cached_property
    def pricing_gateway(self) -> PricingGateway:
        return OpsCorePricingGateway(
            client=self._ops_core_client,
            max_attempts=get_ops_core_settings().max_attempts,
        )

    @cached_property
    def ops_core_health_probe(self) -> OpsCoreHealthChecker:
        return OpsCoreHealthProbe(client=self._ops_core_client)

    @cached_property
    def notification_channel(self) -> NotificationChannel:
        return SimulatedNotificationChannel()

    @cached_property
    def tool_gateway(self) -> ToolGateway:
        return McpToolGateway(settings=get_agent_settings())

    @cached_property
    def availability_service(self) -> AvailabilityService:
        return AvailabilityService(availability=self.availability_gateway)

    @cached_property
    def customer_service(self) -> CustomerService:
        return CustomerService(customers=self.customer_gateway)

    @cached_property
    def pricing_service(self) -> PricingService:
        return PricingService(pricing=self.pricing_gateway)

    @cached_property
    def notification_service(self) -> NotificationService:
        return NotificationService(channel=self.notification_channel)

    @cached_property
    def orchestrator(self) -> OrchestratorService:
        return OrchestratorService(
            llm_client=self.llm_client,
            tool_gateway=self.tool_gateway,
            settings=get_agent_settings(),
        )

    async def close(self) -> None:
        # Generic teardown: close every instantiated dependency exposing close(),
        # de-duplicated by identity (services share client instances).
        closed_dependency_ids: set[int] = set()
        for dependency in tuple(self.__dict__.values()):
            dependency_id = id(dependency)
            if dependency_id in closed_dependency_ids:
                continue
            close = getattr(dependency, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result
            closed_dependency_ids.add(dependency_id)

        # httpx.AsyncClient exposes aclose(), not close(), so dispose it explicitly.
        if "_ops_core_client" in self.__dict__:
            await self._ops_core_client.aclose()
