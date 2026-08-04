"""WhatsApp outbound adapters.

`BridgeWhatsAppGateway` talks HTTP to the unofficial bridge. `GuardedWhatsAppGateway`
wraps it and refuses to message anyone who never wrote first. Only the guarded one is
ever exported to the composition root — see `build_whatsapp_gateway`.
"""

from restaurante.modules.messaging.infrastructure.whatsapp.bridge import (
    BridgeWhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.whatsapp.guard import (
    GuardedWhatsAppGateway,
)

__all__ = ["BridgeWhatsAppGateway", "GuardedWhatsAppGateway"]
