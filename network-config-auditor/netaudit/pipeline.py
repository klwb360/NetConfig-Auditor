"""Explicit local audit stages; intelligence and AI never replace config evidence."""
from __future__ import annotations

from .ai import explain_report, validate_ai_settings
from .intelligence import analyze_intelligence, load_default_kev
from .parser import parse_config
from .rules import audit


def audit_configuration(text: str, vendor: str = "auto", *, asset=None, kev=None,
                        nvd=None, ai=None) -> dict:
    if asset is not None and not isinstance(asset, dict):
        raise ValueError("设备信息必须为 JSON 对象")
    if kev is not None and not isinstance(kev, dict):
        raise ValueError("KEV 情报必须为 JSON 对象")
    if nvd is not None and not isinstance(nvd, dict):
        raise ValueError("NVD 情报必须为 JSON 对象")
    settings = validate_ai_settings(ai)
    config = parse_config(text, vendor)
    result = audit(config)
    result["intelligence"] = analyze_intelligence(
        config, asset=asset, kev=load_default_kev() if kev is None else kev, nvd=nvd)
    result["ai"] = explain_report(result, settings)
    result["pipeline"] = [
        {"stage": "parser", "status": "completed", "detail":
         f"{config.vendor} · 识别 {config.recognized_lines}/{config.relevant_lines} 行"},
        {"stage": "architecture", "status": "completed", "detail":
         "VLAN / STP / OSPF / ACL / NAT / Management Plane；覆盖范围见各域状态"},
        {"stage": "security", "status": "completed", "detail":
         f"{result['summary']['total']} 项配置发现；保留证据与确认程度"},
        {"stage": "intelligence", "status": result["intelligence"]["status"],
         "detail": result["intelligence"]["message"]},
        {"stage": "ai", "status": result["ai"]["status"], "detail": result["ai"]["message"]},
        {"stage": "reports", "status": "completed", "detail": "JSON / Markdown / HTML"},
    ]
    return result
