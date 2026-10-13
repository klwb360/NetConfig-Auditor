"""Versioned public identity; historical delivery bytes keep their original names."""
import re


def identity(version):
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid application version")
    if tuple(map(int, version.split("."))) >= (1, 1, 1):
        return "NetConfig Auditor", "NetConfig-Auditor"
    return "NetAudit", "NetAudit"


def artifact_name(version, commit):
    return identity(version)[1] + "-windows-x64-" + commit
