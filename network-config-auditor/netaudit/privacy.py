import re


def redact(text: str) -> str:
    """Redact credentials before any command is retained in the IR or report."""
    # Scope is not a password: retain the explicitly configured privilege level
    # or role so later suggestions cannot accidentally target the default
    # enable credential. Never retain anything following the credential value.
    enable = re.fullmatch(
        r"(?i)(\s*enable\s+(?:password|secret))"
        r"(?:(\s+level\s+\d+)|(\s+role\s+[A-Za-z0-9_.:/-]+))?\s+"
        r"(?:(0|5|7|8|9|plain|simple|cipher|irreversible-cipher)\s+)?\S+.*",
        text,
    )
    if enable:
        return enable[1] + (enable[2] or enable[3] or "") + " " + ((enable[4] + " ") if enable[4] else "") + "[REDACTED]"
    # RGOS/Cisco may place an encryption selector before the community. Mask
    # the value, not its selector, and preserve read/write/access metadata.
    # Handle this before generic "secret" matching can eat the remaining flags.
    community = re.fullmatch(
        r"(?i)(\s*snmp-server\s+community\s+)"
        r"(?:(0|7|secret(?:\s+(?:0|8))?)\s+)?\S+(.*)", text,
    )
    if community:
        return community[1] + ((community[2] + " ") if community[2] else "") + "[REDACTED]" + community[3]
    # Keep encryption type so the audit can distinguish cleartext/type 7/hash.
    text = re.sub(
        r"(?i)\b(password|secret)\s+(?:(0|5|7|8|9|plain|simple|cipher|irreversible-cipher)\s+)?\S+.*$",
        lambda m: m[1] + " " + ((m[2] + " ") if m[2] else "") + "[REDACTED]", text,
    )
    text = re.sub(
        r"(?i)(\bsnmp-server\s+community\s+)(?:(0|7|secret(?:\s+(?:0|8))?)\s+)?\S+",
        lambda m: m[1] + ((m[2] + " ") if m[2] else "") + "[REDACTED]", text,
    )
    text = re.sub(r"(?i)(\bsnmp-agent\s+community\s+(?:read|write)\s+(?:(?:cipher|simple)\s+)?)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(\b(?:key|key-string|pre-shared-key|authentication-key|authentication-keyid|privacy-key)\s+).*", r"\1[REDACTED]", text)
    if re.search(r"(?i)\bsnmp(?:-server|-agent)\s+(?:usm-user|user)\b", text):
        text = re.sub(r"(?i)(\b(?:auth|privacy)\b).*", r"\1 [REDACTED]", text)
    return text
