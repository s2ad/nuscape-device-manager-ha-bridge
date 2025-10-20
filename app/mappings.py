# Maps domain+property to service+payload merge rules.
# This enables a generic "set properties" API.
from typing import Dict, Any

# For example purposes; extend as needed.
DOMAIN_SERVICE_MAP: Dict[str, Dict[str, Any]] = {
    "light": {
        "on": ("light", "turn_on", lambda v: {} if v else ("light", "turn_off", {})),
        "brightness": ("light", "turn_on", lambda v: {"brightness": int(v)}),
        "color_temp": ("light", "turn_on", lambda v: {"color_temp": int(v)}),
        "hs_color": ("light", "turn_on", lambda v: {"hs_color": v}),
    },
    "switch": {
        "on": ("switch", "turn_on", lambda v: {} if v else ("switch", "turn_off", {})),
    },
    "climate": {
        "hvac_mode": ("climate", "set_hvac_mode", lambda v: {"hvac_mode": v}),
        "temperature": ("climate", "set_temperature", lambda v: {"temperature": float(v)}),
        "fan_mode": ("climate", "set_fan_mode", lambda v: {"fan_mode": v}),
    },
}