import re


def redact(text: str) -> str:
    """Redact credentials before any command is retained in the IR or report."""
    # Keep encryption type so the audit can distinguish cleartext/type 7/hash.
    text = re.sub(
        r"(?i)\b(password|secret)\s+(?:(0|5|7|8|9|plain|simple|cipher|irreversible-cipher)\s+)?\S+.*$",
        lambda m: m[1] + " " + ((m[2] + " ") if m[2] else "") + "[REDACTED]", text,
    )
    text = re.sub(r"(?i)(\bsnmp-server\s+community\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(\bsnmp-agent\s+community\s+(?:read|write)\s+(?:(?:cipher|simple)\s+)?)\S+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(\b(?:key|key-string|pre-shared-key|authentication-key|authentication-keyid|privacy-key)\s+).*", r"\1[REDACTED]", text)
    if re.search(r"(?i)\bsnmp(?:-server|-agent)\s+(?:usm-user|user)\b", text):
        text = re.sub(r"(?i)(\b(?:auth|privacy)\b).*", r"\1 [REDACTED]", text)
    return text
