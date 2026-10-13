"""Local, evidence-limited CVE / CISA KEV correlation.

Loading and analysis never access the network. Only ``fetch_official_kev`` does,
and it sends no configuration, asset identifiers, or model prompts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .branding import APPLICATION_NAME

MAX_INTELLIGENCE_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 50000
KEV_URL = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json"
KEV_CATALOG_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
NVD_URL = "https://nvd.nist.gov/vuln/data-feeds"
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,19}\Z")


class IntelligenceDocument(dict):
    """A JSON-compatible document with trusted loader provenance off the wire."""

    def __init__(self, data: dict, metadata: dict | None = None):
        super().__init__(data)
        self.metadata = metadata or {}


def _text(value: object, limit: int = 3000) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _cve_id(value: object) -> str:
    if not isinstance(value, str) or not CVE_PATTERN.fullmatch(value.upper()):
        raise ValueError("情报包含无效 CVE 编号；应使用 CVE-YYYY-NNNN 格式。")
    return value.upper()


def _json_document(data: bytes) -> dict:
    if len(data) > MAX_INTELLIGENCE_BYTES:
        raise ValueError("情报文件超过 16 MiB；请导入相关产品的 NVD 子集。")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("重复 JSON 键。")
            value[key] = item
        return value
    def invalid_constant(value):
        raise ValueError(f"非法 JSON 常量 {value}。")
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("情报文件不是有效的 UTF-8 JSON 对象。") from exc
    if not isinstance(value, dict):
        raise ValueError("情报 JSON 顶层必须为对象。")
    return value


def _validate_document_size(value: object) -> None:
    try:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError) as exc:
        raise ValueError("情报不是有效 JSON 数据。") from exc
    if len(data) > MAX_INTELLIGENCE_BYTES:
        raise ValueError("情报超过 16 MiB；请导入相关产品的 NVD 子集。")


def normalize_kev(value: dict) -> dict:
    _validate_document_size(value)
    if not isinstance(value, dict) or not isinstance(value.get("vulnerabilities"), list):
        raise ValueError("KEV 文件须包含 CISA vulnerabilities 列表。")
    records = value["vulnerabilities"]
    if len(records) > MAX_RECORDS:
        raise ValueError("KEV 条目过多。")
    if "count" in value and (type(value["count"]) is not int or value["count"] != len(records)):
        raise ValueError("KEV count 与条目数量不一致。")
    seen: set[str] = set()
    cleaned = []
    fields = ("vendorProject", "product", "vulnerabilityName", "shortDescription", "requiredAction", "notes", "knownRansomwareCampaignUse")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("KEV 条目必须为对象。")
        cve_id = _cve_id(record.get("cveID"))
        if cve_id in seen:
            raise ValueError(f"KEV 存在重复条目 {cve_id}。")
        seen.add(cve_id)
        item = {"cveID": cve_id, **{key: _text(record.get(key)) for key in fields}}
        for key in ("dateAdded", "dueDate"):
            text = _text(record.get(key), 32)
            if text:
                try:
                    date.fromisoformat(text)
                except ValueError as exc:
                    raise ValueError(f"KEV {cve_id} 的 {key} 日期无效。") from exc
            item[key] = text
        cleaned.append(item)
    return IntelligenceDocument({"catalogVersion": _text(value.get("catalogVersion"), 128), "dateReleased": _text(value.get("dateReleased"), 128), "count": len(cleaned), "vulnerabilities": cleaned}, getattr(value, "metadata", None))


def _validate_nodes(nodes: object, depth: int = 0) -> None:
    if not isinstance(nodes, list) or depth > 16:
        raise ValueError("NVD 配置节点无效或嵌套超过 16 层。")
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("NVD 配置节点必须为对象。")
        if "negate" in node and type(node["negate"]) is not bool:
            raise ValueError("NVD negate 必须为布尔值。")
        if "operator" in node and not isinstance(node["operator"], str):
            raise ValueError("NVD operator 必须为字符串。")
        if "cpeMatch" in node:
            if not isinstance(node["cpeMatch"], list):
                raise ValueError("NVD cpeMatch 必须为列表。")
            for match in node["cpeMatch"]:
                if not isinstance(match, dict) or not isinstance(match.get("criteria"), str) or type(match.get("vulnerable")) is not bool:
                    raise ValueError("NVD CPE 匹配项须包含 criteria 字符串与 vulnerable 布尔值。")
                if len(match["criteria"]) > 2048:
                    raise ValueError("NVD CPE 长度超过限制。")
                if _parse_cpe(match["criteria"]) is None:
                    raise ValueError("NVD criteria 须采用有效 CPE 2.3 格式。")
                for key in ("versionStartIncluding", "versionStartExcluding", "versionEndIncluding", "versionEndExcluding"):
                    if key in match and (not isinstance(match[key], str) or len(match[key]) > 128):
                        raise ValueError("NVD 版本边界无效。")
        for key in ("nodes", "children"):
            if key in node:
                _validate_nodes(node[key], depth + 1)


def normalize_nvd(value: dict) -> dict:
    _validate_document_size(value)
    if not isinstance(value, dict) or not isinstance(value.get("vulnerabilities"), list):
        raise ValueError("NVD 文件须采用 CVE API 2.0 vulnerabilities 格式。")
    if value.get("format", "NVD_CVE") != "NVD_CVE" or value.get("version", "2.0") != "2.0":
        raise ValueError("仅支持 NVD CVE 2.0 格式。")
    records = value["vulnerabilities"]
    if len(records) > MAX_RECORDS:
        raise ValueError("NVD 条目过多；请导入相关产品子集。")
    seen: set[str] = set()
    cleaned = []
    for wrapped in records:
        if not isinstance(wrapped, dict) or not isinstance(wrapped.get("cve"), dict):
            raise ValueError("NVD 条目须包含 cve 对象。")
        cve = wrapped["cve"]
        cve_id = _cve_id(cve.get("id"))
        if cve_id in seen:
            raise ValueError(f"NVD 存在重复条目 {cve_id}。")
        seen.add(cve_id)
        configurations = cve.get("configurations", [])
        _validate_nodes(configurations)
        descriptions = cve.get("descriptions", [])
        references = cve.get("references", [])
        metrics = cve.get("metrics", {})
        if not isinstance(descriptions, list) or not isinstance(references, list) or not isinstance(metrics, dict):
            raise ValueError("NVD descriptions / references / metrics 格式无效。")
        cleaned.append({"cve": {"id": cve_id, "published": _text(cve.get("published"), 128), "lastModified": _text(cve.get("lastModified"), 128), "vulnStatus": _text(cve.get("vulnStatus"), 128), "descriptions": descriptions, "references": references, "metrics": metrics, "configurations": configurations}})
    return IntelligenceDocument({"format": "NVD_CVE", "version": "2.0", "timestamp": _text(value.get("timestamp"), 128), "vulnerabilities": cleaned}, getattr(value, "metadata", None))


def load_intelligence_file(path: str | Path, kind: str) -> dict:
    if kind not in ("kev", "nvd"):
        raise ValueError("情报类型必须为 kev 或 nvd。")
    source = Path(path)
    with source.open("rb") as stream:
        data = stream.read(MAX_INTELLIGENCE_BYTES + 1)
    result = (normalize_kev if kind == "kev" else normalize_nvd)(_json_document(data))
    result.metadata = {"origin": "user-import", "sha256": hashlib.sha256(data).hexdigest(), "source_url": KEV_CATALOG_URL if kind == "kev" else NVD_URL}
    return result


def load_default_kev() -> dict:
    directory = Path(__file__).with_name("data")
    source = directory / "kev.json"
    manifest = _json_document((directory / "kev-source.json").read_bytes())
    with source.open("rb") as stream:
        data = stream.read(MAX_INTELLIGENCE_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != manifest.get("sha256"):
        raise ValueError("内置 KEV 快照校验失败；请重新获取完整发行包。")
    result = normalize_kev(_json_document(data))
    result.metadata = {**manifest, "origin": "bundled-official-snapshot"}
    return result


def fetch_official_kev(destination: str | Path | None = None) -> dict:
    """Explicit official-data download; never called by analysis or startup."""
    request = urllib.request.Request(KEV_URL, headers={"User-Agent": f"{APPLICATION_NAME} intelligence updater", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.geturl() != KEV_URL:
                raise ValueError("官方 KEV 下载发生非预期重定向。")
            data = response.read(MAX_INTELLIGENCE_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"无法下载官方 KEV：{type(exc).__name__}；仍可使用内置快照或本地导入。") from exc
    result = normalize_kev(_json_document(data))
    result.metadata = {"origin": "official-download", "source_url": KEV_URL, "sha256": hashlib.sha256(data).hexdigest(), "retrieved_at": datetime.now(timezone.utc).isoformat(), "license": "CC0-1.0"}
    if destination is not None:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".netaudit-kev-", dir=target.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(data)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
    return result


def _source(document: dict, kind: str) -> dict:
    metadata = getattr(document, "metadata", {})
    released = document.get("dateReleased", "") if kind == "kev" else document.get("timestamp", "")
    age: int | None = None
    try:
        day = datetime.fromisoformat(released.replace("Z", "+00:00")).date()
        age = (datetime.now(timezone.utc).date() - day).days
    except (ValueError, TypeError, AttributeError):
        pass
    return {"kind": kind, "name": "CISA KEV" if kind == "kev" else "NVD CVE 2.0", "source_url": metadata.get("source_url", KEV_CATALOG_URL if kind == "kev" else NVD_URL), "catalog_version": document.get("catalogVersion", ""), "date_released": released, "sha256": metadata.get("sha256", ""), "origin": metadata.get("origin", "caller-provided-unverified"), "age_days": age, "stale": age is None or age > 30 or age < -1, "count": len(document.get("vulnerabilities", [])), "license": metadata.get("license", "CC0-1.0 (CISA official catalog)" if kind == "kev" else "NVD/NIST data terms")}


def _parse_cpe(value: object) -> list[str] | None:
    if not isinstance(value, str) or len(value) > 2048 or not value.startswith("cpe:2.3:") or any(ord(char) < 32 or char.isspace() for char in value):
        return None
    parts: list[str] = []
    current = ""
    escaped = False
    for char in value:
        if char == ":" and not escaped:
            parts.append(current)
            current = ""
        else:
            current += char
        escaped = char == "\\" and not escaped
    parts.append(current)
    if len(parts) != 13 or parts[2] not in ("a", "o", "h") or any(not part for part in parts[2:]):
        return None
    return [part.casefold() for part in parts[2:]]


def _identity_known(cpe: list[str]) -> bool:
    return len(cpe) == 11 and cpe[0] in ("a", "o", "h") and all(value not in ("*", "-") and not any(char in value for char in ("?", "*", "\\")) for value in cpe[1:3])


def _product_related(asset: list[str], criteria: object) -> bool:
    target = _parse_cpe(criteria)
    return _identity_known(asset) and target is not None and _identity_known(target) and asset[:3] == target[:3]


def _version_tuple(value: str) -> tuple[int, ...] | None:
    if len(value) > 128 or not re.fullmatch(r"\d{1,16}(?:\.\d{1,16}){0,15}", value):
        return None
    parts = [int(piece) for piece in value.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _cpe_matches(asset: list[str], match: dict) -> bool | None:
    supported = {"vulnerable", "criteria", "matchCriteriaId", "versionStartIncluding", "versionStartExcluding", "versionEndIncluding", "versionEndExcluding"}
    if set(match) - supported:
        return None
    target = _parse_cpe(match.get("criteria"))
    if target is None or not _identity_known(asset) or not _identity_known(target):
        return None
    if asset[:3] != target[:3]:
        return False
    if asset[3] in ("*", "-") or any(char in asset[3] for char in ("?", "\\", "*")):
        return None
    unknown = False
    for index, (actual, required) in enumerate(zip(asset, target)):
        if required == "*":
            continue
        if required == actual:
            continue
        if actual == "*" or any(char in required for char in ("?", "*", "\\")):
            unknown = True
            continue
        return False
    lower = [key for key in ("versionStartIncluding", "versionStartExcluding") if key in match]
    upper = [key for key in ("versionEndIncluding", "versionEndExcluding") if key in match]
    if len(lower) > 1 or len(upper) > 1:
        return None
    if lower or upper:
        actual_version = _version_tuple(asset[3])
        if actual_version is None:
            return None
        for key in lower + upper:
            boundary = _version_tuple(match[key])
            if boundary is None:
                return None
            width = max(len(actual_version), len(boundary))
            left = actual_version + (0,) * (width - len(actual_version))
            right = boundary + (0,) * (width - len(boundary))
            comparison = {"versionStartIncluding": left >= right, "versionStartExcluding": left > right, "versionEndIncluding": left <= right, "versionEndExcluding": left < right}[key]
            if not comparison:
                return False
    return None if unknown else True


def _flatten_matches(nodes: list[dict]):
    for node in nodes:
        yield from node.get("cpeMatch", [])
        for key in ("nodes", "children"):
            yield from _flatten_matches(node.get(key, []))


def _configuration_result(nodes: list[dict], asset: list[str]) -> bool | None:
    """Only OR paths are proven; AND, negation and environmental CPEs defer."""
    if not nodes:
        return None
    results: list[bool | None] = []
    for node in nodes:
        if set(node) - {"operator", "negate", "cpeMatch", "nodes", "children"} or node.get("negate", False) or node.get("operator", "OR").upper() != "OR" or ("cpeMatch" in node and "operator" not in node):
            results.append(None)
            continue
        values: list[bool | None] = []
        for match in node.get("cpeMatch", []):
            if match.get("vulnerable") is not True:
                values.append(None)
            else:
                values.append(_cpe_matches(asset, match))
        for key in ("nodes", "children"):
            if key in node:
                values.append(_configuration_result(node[key], asset))
        results.append(True if True in values else None if None in values or not values else False)
    return True if True in results else None if None in results else False


def _description(cve: dict) -> str:
    descriptions = [item for item in cve.get("descriptions", []) if isinstance(item, dict)]
    preferred = next((item for item in descriptions if item.get("lang") in ("zh", "zh-CN")), None)
    preferred = preferred or next((item for item in descriptions if item.get("lang") == "en"), None)
    return _text(preferred.get("value")) if preferred else ""


def _severity(cve: dict) -> str:
    metrics = cve.get("metrics", {})
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        rows = metrics.get(key, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            data = row.get("cvssData", {})
            severity = (data.get("baseSeverity", row.get("baseSeverity", "")) if isinstance(data, dict) else "")
            if isinstance(severity, str) and severity.lower() in ("critical", "high", "medium", "low", "none"):
                return severity.lower()
    return "unknown"


def _item(cve_id: str, cve: dict | None, kev: dict | None, confidence: str, basis: str) -> dict:
    description = _description(cve) if cve else _text((kev or {}).get("shortDescription"))
    references = []
    for reference in (cve or {}).get("references", []):
        if isinstance(reference, dict) and isinstance(reference.get("url"), str) and reference["url"].startswith(("https://", "http://")):
            references.append({"url": _text(reference["url"], 2048), "source": _text(reference.get("source"), 256)})
    return {"cve_id": cve_id, "title": _text((kev or {}).get("vulnerabilityName"), 256) or description[:160] or cve_id, "description": description, "severity": _severity(cve) if cve else "unknown", "known_exploited": kev is not None, "confidence": confidence, "match_basis": basis, "source_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}", "references": references, "kev": {key: kev.get(key, "") for key in ("dateAdded", "dueDate", "requiredAction", "knownRansomwareCampaignUse", "notes")} if kev else None}


def analyze_intelligence(config, asset: dict | None = None, kev: dict | None = None, nvd: dict | None = None) -> dict:
    """Correlate explicit asset facts, never guess firmware from vendor/hostname."""
    if asset is None:
        asset = {}
    if not isinstance(asset, dict):
        raise ValueError("资产元数据必须为对象。")
    cpe_text = asset.get("cpe", "")
    if not isinstance(cpe_text, str):
        raise ValueError("资产 cpe 必须为 CPE 2.3 字符串。")
    cpe = _parse_cpe(cpe_text) if cpe_text else None
    if cpe_text and cpe is None:
        raise ValueError("资产须采用有效 CPE 2.3 格式，并使用 a、o 或 h 作为 part。")
    identifiers = asset.get("cve_ids", [])
    if not isinstance(identifiers, list) or len(identifiers) > 256:
        raise ValueError("资产 cve_ids 须为不超过 256 个编号的列表。")
    explicit = {_cve_id(value) for value in identifiers}
    kev_document = normalize_kev(kev) if kev is not None else load_default_kev()
    nvd_document = normalize_nvd(nvd) if nvd is not None else None
    sources = [_source(kev_document, "kev")]
    if nvd_document is not None:
        sources.append(_source(nvd_document, "nvd"))
    result = {"status": "not-configured", "message": "KEV 已载入；请提供设备 CPE 与 NVD 2.0 情报，才能判断版本适用性。", "asset": {"cpe": cpe_text, "cve_ids": sorted(explicit)}, "sources": sources, "matches": [], "candidates": [], "limitations": ["配置文件中的厂商品牌不能证明型号、固件版本或 CVE 适用性。", "CISA KEV 表示该漏洞已有真实利用记录，不表示当前设备已被攻陷。", "CPE/版本命中仍需结合实际型号、固件、厂商公告和启用功能复核。", "情报未命中不能证明设备安全；当前分析仅覆盖载入的快照或 NVD 子集。", "KEV dueDate 为美国联邦机构指令适用日期，不是本工具给用户设定的整改期限。"]}
    for source in sources:
        if source["stale"]:
            result["limitations"].append(f"{source['name']} 快照超过 30 天、日期未知或存在时钟偏差，请核对其时效。")
        if source["origin"] in ("caller-provided-unverified", "user-import"):
            result["limitations"].append(f"{source['name']} 为用户提供数据，格式校验与 SHA-256 不等同于来源认证。")
    kev_index = {item["cveID"]: item for item in kev_document["vulnerabilities"]}
    considered: set[str] = set()
    for wrapped in (nvd_document or {}).get("vulnerabilities", []):
        cve = wrapped["cve"]
        cve_id = cve["id"]
        considered.add(cve_id)
        configurations = cve["configurations"]
        related = cpe is not None and any(_product_related(cpe, match["criteria"]) for match in _flatten_matches(configurations))
        if cve_id not in explicit and not related:
            continue
        if cve.get("vulnStatus", "").lower() == "rejected":
            if cve_id in explicit:
                result["candidates"].append(_item(cve_id, cve, kev_index.get(cve_id), "needs-review", "用户提供候选，但 NVD 已标记 REJECTED；不得作为有效漏洞结论。"))
            continue
        applicability = _configuration_result(configurations, cpe) if cpe is not None else None
        if applicability is True:
            result["matches"].append(_item(cve_id, cve, kev_index.get(cve_id), "cpe-version-match", "用户提供的明确 CPE 和版本符合 NVD 简单 OR 适用条件；仍需厂商公告复核。"))
        elif applicability is None:
            result["candidates"].append(_item(cve_id, cve, kev_index.get(cve_id), "needs-review" if related else "user-provided-candidate", "缺少明确版本、NVD 适用条件，或包含复杂 AND/否定/环境条件与不支持的版本比较；无法确认设备受影响。"))
        elif cve_id in explicit:
            result["candidates"].append(_item(cve_id, cve, kev_index.get(cve_id), "user-provided-candidate", "用户提供的 CVE 候选与当前 CPE/版本条件不匹配；该编号不是设备受影响的证明。"))
    for cve_id in sorted(explicit - considered):
        result["candidates"].append(_item(cve_id, None, kev_index.get(cve_id), "user-provided-candidate", "用户提供 CVE 候选，未载入该 CVE 的 NVD 产品/版本适用条件；无法确认设备受影响。"))
    result["matches"].sort(key=lambda item: item["cve_id"])
    result["candidates"].sort(key=lambda item: item["cve_id"])
    if result["matches"]:
        result["status"] = "matched"
        result["message"] = f"{len(result['matches'])} 项 CPE/版本符合已载入 NVD 条件，{len(result['candidates'])} 项候选待复核。"
    elif result["candidates"]:
        result["status"] = "needs-review"
        result["message"] = f"{len(result['candidates'])} 项 CVE 候选待人工复核，尚未确认设备受影响。"
    elif cpe is not None and not _identity_known(cpe):
        result["status"] = "needs-review"
        result["message"] = "设备 CPE 的厂商或产品未知；请提供明确标识，尚未确认任何 CVE 适用性。"
    elif nvd_document is not None and cpe is not None:
        result["status"] = "no-matches"
        result["message"] = "已载入情报未发现明确 CPE/版本命中；这不等同于设备安全。"
    return result
