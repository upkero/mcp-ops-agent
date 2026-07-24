from typing import Literal

# Mirrors ops-core-api's ResourceType. A shared alias (DRY) so the tool argument
# models and the services agree on the allowed values without re-declaring them.
ResourceType = Literal["table", "meeting_room"]
