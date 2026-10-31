from typing import Literal

# Mirrors ops-core-api's ResourceType. One alias, so the tool arguments and the
# services cannot drift apart on the allowed values.
ResourceType = Literal["table", "meeting_room", "treatment_room"]
