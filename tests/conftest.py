import os

# Set before importing anything from src: settings are read at import time and
# then cached. These are throwaway values so importing the container never fails
# on a required field; the tests inject fakes for the things that matter.
os.environ.setdefault("OPS_CORE_API_KEY", "test-ops-core-key-1234567890")
TEST_API_KEY = "test-inbound-key-1234567890"
os.environ.setdefault("SECURITY_API_KEY", TEST_API_KEY)
AUTH = {"X-API-Key": TEST_API_KEY}
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("LLM_MODEL", "stub-model")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# A small cap so the rate-limit test is cheap; well above what any other test sends.
os.environ.setdefault("INVOKE_RATE_LIMIT_PER_MINUTE", "5")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402

from src.app.api.v1.middleware.rate_limit import reset_rate_limit  # noqa: E402
from src.app.core.settings.agent import AgentSettings  # noqa: E402
from src.app.core.settings.app import AppSettings  # noqa: E402
from src.app.core.settings.llm import LLMSettings  # noqa: E402
from src.app.core.settings.logging import LoggingSettings  # noqa: E402
from src.app.core.settings.ops_core import OpsCoreSettings  # noqa: E402
from src.app.core.settings.security import SecuritySettings  # noqa: E402

# A developer's local .env must not change what the tests see (a SECURITY_API_KEY in
# it turns every invoke test into a 401). Environment variables set above still apply.
for _settings in (AgentSettings, AppSettings, LLMSettings, LoggingSettings, OpsCoreSettings, SecuritySettings):
    _settings.model_config["env_file"] = None


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    """The limiter's counters are process-global; keep cases independent."""
    reset_rate_limit()
    yield
    reset_rate_limit()
