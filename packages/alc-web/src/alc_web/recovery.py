"""Bounded automatic recovery for transient provider failures only."""
from collections.abc import Mapping


def transient_provider_failure(error):
    codes, statuses = set(), set()
    requires_input = False
    def walk(value):
        nonlocal requires_input
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"code", "category", "ac_error_code", "llm_code"} and isinstance(item,str):
                    codes.add(item)
                elif key == "http_status" and isinstance(item,int):
                    statuses.add(item)
                elif key == "input_required" and item is True:
                    requires_input = True
                elif isinstance(item,(Mapping,list)):
                    walk(item)
        elif isinstance(value,list):
            for item in value: walk(item)
    walk(error)
    if requires_input or codes & {"authentication", "quota", "credential_required", "runtime_changed", "provider_authentication"}:
        return False
    if statuses & {400,401,402,403,404,405,422}:
        return False
    return bool(statuses & {429,500,502,503,504} or codes & {
        "rate_limit", "provider_rate_limit", "provider_timeout", "timeout",
        "provider_transport", "transport", "provider_circuit_open",
    })
