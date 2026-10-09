"""DNS 拨测核心。

纯逻辑模块，不依赖任何 UI 组件，便于独立测试与复用：

- 记录类型枚举（全部公共可查询类型，常用类型优先）
- 目标输入校验（域名 / IPv4 / IPv6）
- DNS 服务器解析（Do53 / DoT / DoH，支持多台）
- 单类型 / 全类型并发拨测
- 反向解析（IP -> PTR）
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import dns.exception
import dns.name
import dns.nameserver
import dns.resolver
import dns.reversename
import dns.rdatatype

#: 「全部记录」在下拉框中的显示标签
ALL_TYPES_LABEL = "全部记录"

#: 全量查询并发线程数上限
MAX_WORKERS = 16

#: EDNS0 UDP payload 大小（DNS Flag Day 2020 建议值）
EDNS_PAYLOAD = 1232

_LABEL = r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?"
_DOMAIN_RE = re.compile(rf"^(?:{_LABEL})(?:\.{_LABEL})*\.?$")

#: 「全部记录」模式下优先展示的常用类型
_PRIORITY_TYPES = (
    "A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "PTR", "SRV", "CAA",
    "SVCB", "HTTPS", "DS", "DNSKEY", "RRSIG", "NSEC", "NSEC3", "TLSA",
)


def queryable_types() -> list[str]:
    """返回全部公共可查询的记录类型名（常用优先，其余按字母序）。

    排除元类型（OPT / TKEY / TSIG / AXFR / IXFR / ANY 等）、
    占位类型 TYPE0 与伪类型 NONE。
    """
    skip = {dns.rdatatype.RdataType.TYPE0, dns.rdatatype.RdataType.NONE}
    names = [
        rdtype.name
        for rdtype in dns.rdatatype.RdataType
        if not dns.rdatatype.is_metatype(rdtype) and rdtype not in skip
    ]
    priority = [t for t in _PRIORITY_TYPES if t in names]
    rest = sorted(t for t in names if t not in _PRIORITY_TYPES)
    return priority + rest


def common_types() -> list[str]:
    """常用记录类型（UI 下拉框默认展示集，完整类型见 queryable_types）。"""
    return list(_PRIORITY_TYPES)


def is_ip_address(text: str) -> bool:
    """判断输入是否为合法 IPv4 / IPv6 地址。"""
    try:
        ipaddress.ip_address(text.strip())
        return True
    except ValueError:
        return False


def validate_target(raw: str) -> tuple[str, bool]:
    """校验拨测目标，返回 (目标文本, 是否 IP)。不合法时抛 ValueError。"""
    text = (raw or "").strip().rstrip(".")
    if not text:
        raise ValueError("请输入域名或 IP 地址")
    try:
        ipaddress.ip_address(text)
        return text, True
    except ValueError:
        pass
    if len(text) > 253:
        raise ValueError("域名长度超过 253 字符上限")
    if not _DOMAIN_RE.match(text):
        raise ValueError(
            "目标格式不合法：仅支持常规域名（字母 / 数字 / 连字符 / 下划线）或 IPv4 / IPv6 地址"
        )
    return text, False


# ---------------------------------------------------------------------------
# DNS 服务器解析
# ---------------------------------------------------------------------------

def _ensure_host(host: str) -> None:
    """DoT 主机允许 IP 或域名，此处仅做格式防呆。"""
    if not host:
        raise ValueError("服务器地址不能为空")
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    if len(host) > 253 or not _DOMAIN_RE.match(host):
        raise ValueError(f"服务器地址格式不正确：{host}")


def _split_host_port(text: str, default_port: int) -> tuple[str, int]:
    """拆分 ``host[:port]`` / ``[v6](:port)``，返回 (host, port)。"""
    if text.startswith("["):
        match = re.match(r"^\[([0-9A-Fa-f:.]+)\](?::(\d+))?$", text)
        if not match:
            raise ValueError(f"IPv6 地址格式不正确：{text}")
        host, port_text = match.group(1), match.group(2)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            raise ValueError(f"IPv6 地址格式不正确：{text}") from None
        port = int(port_text) if port_text else default_port
        if not 1 <= port <= 65535:
            raise ValueError(f"端口不合法：{text}")
        return host, port
    try:
        ipaddress.ip_address(text)
        return text, default_port
    except ValueError:
        pass
    if text.count(":") > 1:
        raise ValueError(f"IPv6 地址带端口请使用 [IPv6]:端口 格式：{text}")
    if ":" in text:
        host, _, port_text = text.partition(":")
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise ValueError(f"端口不合法：{text}")
        return host, int(port_text)
    return text, default_port


def _format_host_port(host: str, port: int) -> str:
    """IPv6 地址展示时加方括号，避免与端口混淆。"""
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _parse_single_server(part: str) -> tuple[object, str]:
    """解析单个服务器条目，返回 (nameserver 实例, 展示文本)。"""
    lower = part.lower()
    if lower.startswith("https://"):
        parsed = urlparse(part)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"DoH 地址格式不正确：{part}")
        return dns.nameserver.DoHNameserver(part), f"{part}（DoH）"
    if lower.startswith(("tls://", "dot://")):
        host, port = _split_host_port(part[6:], 853)
        _ensure_host(host)
        return (
            dns.nameserver.DoTNameserver(host, port),
            f"{_format_host_port(host, port)}（DoT）",
        )
    if lower.startswith(("quic://", "doq://")):
        raise ValueError("暂不支持 DoQ 服务器（需额外安装 dnspython[doq] 依赖）")
    if lower.startswith("http://"):
        raise ValueError("DoH 仅支持 https:// 地址")
    if "://" in part:
        raise ValueError(f"无法识别的服务器格式：{part}")
    host, port = _split_host_port(part, 53)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(
            f"普通 DNS 服务器须为 IP 地址：{part}（域名形式请改用 tls:// 或 https://）"
        ) from None
    return (
        dns.nameserver.Do53Nameserver(host, port),
        f"{_format_host_port(host, port)}（Do53）",
    )


def parse_server(raw: str) -> tuple[list, str]:
    """解析 DNS 服务器输入，返回 (nameserver 实例列表, 展示文本)。

    支持格式（多台服务器用空格 / 逗号 / 分号分隔）：

    - ``223.5.5.5``               普通 DNS（Do53，UDP+TCP，53 端口）
    - ``223.5.5.5:5353``          Do53 指定端口
    - ``[2001:db8::1]:53``        IPv6 带端口（必须方括号）
    - ``tls://223.5.5.5:853``     DoT
    - ``https://host/dns-query``  DoH

    输入为空时返回 ([], "系统默认 DNS")；格式不合法时抛 ValueError。
    """
    text = (raw or "").strip()
    if not text:
        return [], "系统默认 DNS"
    servers: list = []
    descs: list[str] = []
    for part in re.split(r"[,;\s]+", text):
        if not part:
            continue
        server, desc = _parse_single_server(part)
        servers.append(server)
        descs.append(desc)
    if not servers:
        return [], "系统默认 DNS"
    return servers, " / ".join(descs)


# ---------------------------------------------------------------------------
# 查询结果数据结构
# ---------------------------------------------------------------------------

@dataclass
class TypeResult:
    """单个记录类型的查询结果。"""

    rdtype: str
    records: list[str] = field(default_factory=list)
    ttl: int | None = None
    cname_note: str | None = None
    error: str | None = None
    #: nxdomain / timeout / server / other，正常时为 None
    error_kind: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class LookupResult:
    """一次拨测的完整结果。"""

    target: str
    query_name: str
    is_ip: bool
    rdtype_label: str
    server_display: str
    results: list[TypeResult] = field(default_factory=list)
    elapsed_ms: float = 0.0
    fatal_error: str | None = None

    @property
    def found_results(self) -> list[TypeResult]:
        return [r for r in self.results if r.records]

    @property
    def error_results(self) -> list[TypeResult]:
        return [r for r in self.results if r.error]

    @property
    def empty_count(self) -> int:
        return len(self.results) - len(self.found_results) - len(self.error_results)

    @property
    def all_nxdomain(self) -> bool:
        """所有类型均 NXDOMAIN，可判定域名不存在。"""
        return bool(self.results) and all(r.error_kind == "nxdomain" for r in self.results)


@dataclass
class LookupParams:
    """拨测参数。"""

    target: str
    rdtype: str = ALL_TYPES_LABEL
    server: str = ""
    timeout: float = 3.0


# ---------------------------------------------------------------------------
# 拨测执行
# ---------------------------------------------------------------------------

def _build_resolver(server_raw: str, timeout: float) -> dns.resolver.Resolver:
    """按参数构建 Resolver：关闭 search、开 EDNS0、设超时。"""
    if server_raw.strip():
        nameservers, _ = parse_server(server_raw)
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = nameservers
    else:
        resolver = dns.resolver.Resolver(configure=True)
    resolver.search = []
    resolver.lifetime = timeout
    resolver.edns = 0
    resolver.payload = EDNS_PAYLOAD
    return resolver


def _query_type(
    rdtype_name: str,
    qname: dns.name.Name,
    server_raw: str,
    timeout: float,
) -> TypeResult:
    """查询单个记录类型，任何异常都转化为结果对象，不向调用方抛出。"""
    start = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - start) * 1000

    def fail(message: str, kind: str) -> TypeResult:
        return TypeResult(
            rdtype=rdtype_name, error=message, error_kind=kind, elapsed_ms=elapsed()
        )

    try:
        resolver = _build_resolver(server_raw, timeout)
        answer = resolver.resolve(qname, rdtype_name, raise_on_no_answer=False, search=False)
    except dns.resolver.NXDOMAIN:
        return fail("域名不存在（NXDOMAIN）", "nxdomain")
    except dns.exception.Timeout:
        return fail("查询超时", "timeout")
    except dns.resolver.NoNameservers as exc:
        return fail(f"服务器无响应或拒绝查询（{str(exc)[:120]}）", "server")
    except (dns.exception.DNSException, ValueError, OSError) as exc:
        return fail(f"查询失败：{type(exc).__name__}", "other")
    except Exception as exc:  # 网络栈等意外错误兜底
        return fail(f"查询失败：{type(exc).__name__}", "other")

    rrset = answer.rrset
    if rrset is None or len(rrset) == 0:
        return TypeResult(rdtype=rdtype_name, elapsed_ms=elapsed())

    records = [rdata.to_text() for rdata in rrset]
    cname_note = None
    try:
        if answer.canonical_name != answer.qname:
            cname_note = f"经 CNAME 指向 {answer.canonical_name}"
    except Exception:
        cname_note = None
    return TypeResult(
        rdtype=rdtype_name,
        records=records,
        ttl=int(rrset.ttl),
        cname_note=cname_note,
        elapsed_ms=elapsed(),
    )


def _resolve_type_names(rdtype_label: str, is_ip: bool) -> list[str]:
    """确定本次拨测要查询的记录类型列表。"""
    if rdtype_label == ALL_TYPES_LABEL:
        if is_ip:
            return ["PTR"]
        # 域名输入时全量查询不包含 PTR（PTR 仅对 IP 有意义，走反向解析）
        return [t for t in queryable_types() if t != "PTR"]
    return [rdtype_label]


def run_lookup(params: LookupParams) -> LookupResult:
    """执行一次拨测。单类型直接查询，全量模式并发查询。"""
    start = time.perf_counter()
    target = params.target.strip()
    display_server = params.server.strip() or "系统默认 DNS"

    try:
        is_ip = is_ip_address(target)
        if is_ip:
            qname = dns.reversename.from_address(target)
        else:
            qname = dns.name.from_text(target)
        _, display_server = parse_server(params.server)
        type_names = _resolve_type_names(params.rdtype, is_ip)
    except ValueError as exc:
        return LookupResult(
            target=params.target,
            query_name=target,
            is_ip=False,
            rdtype_label=params.rdtype,
            server_display=display_server,
            fatal_error=str(exc),
        )
    except Exception as exc:
        return LookupResult(
            target=params.target,
            query_name=target,
            is_ip=False,
            rdtype_label=params.rdtype,
            server_display=display_server,
            fatal_error=f"拨测初始化失败：{type(exc).__name__}",
        )

    if len(type_names) == 1:
        results = [_query_type(type_names[0], qname, params.server, params.timeout)]
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS, len(type_names)),
            thread_name_prefix="dns-lookup",
        ) as pool:
            futures = [
                pool.submit(_query_type, name, qname, params.server, params.timeout)
                for name in type_names
            ]
            results = [future.result() for future in futures]

    return LookupResult(
        target=target,
        query_name=str(qname),
        is_ip=is_ip,
        rdtype_label=params.rdtype,
        server_display=display_server,
        results=results,
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )
