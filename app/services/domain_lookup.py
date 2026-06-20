import json
import re
import socket
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import dns.exception
    import dns.resolver
except ImportError:  # pragma: no cover - dependency is installed in the app image
    dns = None


DOMAIN_PATTERN = re.compile(r"^(?=.{1,253}$)(?!-)(?:[a-z0-9-]{1,63}\.)+[a-z]{2,63}$", re.IGNORECASE)
DNS_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT"]


def normalize_domain(value: str) -> str:
    domain = value.strip().lower().rstrip(".")
    domain = domain.removeprefix("http://").removeprefix("https://").split("/")[0].split(":")[0]
    if not DOMAIN_PATTERN.match(domain):
        raise ValueError("Enter a valid domain name.")
    return domain


def parse_rdap_date(value: str | None) -> datetime | None:
    if not value:
        return None
    clean = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(clean).replace(tzinfo=None)
    except ValueError:
        return None


def rdap_event_date(data: dict, actions: set[str]) -> datetime | None:
    for event in data.get("events", []):
        if event.get("eventAction") in actions:
            parsed = parse_rdap_date(event.get("eventDate"))
            if parsed:
                return parsed
    return None


def entity_name(entity: dict) -> str | None:
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2:
        return None
    for item in vcard[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == "fn":
            value = str(item[3]).strip()
            if value:
                return value
    return None


def registrar_from_rdap(data: dict) -> str | None:
    for entity in data.get("entities", []):
        roles = set(entity.get("roles", []))
        if "registrar" in roles:
            return entity_name(entity)
    return None


def nameservers_from_rdap(data: dict) -> list[str]:
    nameservers = []
    for row in data.get("nameservers", []):
        name = str(row.get("ldhName") or row.get("unicodeName") or "").strip().lower().rstrip(".")
        if name and name not in nameservers:
            nameservers.append(name)
    return nameservers


def infer_dns_provider(nameservers: list[str]) -> str | None:
    if not nameservers:
        return None
    parts = nameservers[0].split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return nameservers[0]


def lookup_rdap(domain: str) -> dict:
    request = Request(f"https://rdap.org/domain/{domain}", headers={"Accept": "application/rdap+json, application/json"})
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def lookup_dns(domain: str) -> dict[str, list[str]]:
    if dns is None:
        raise RuntimeError("DNS lookup dependency is not installed.")
    resolver = dns.resolver.Resolver()
    resolver.timeout = 3
    resolver.lifetime = 5
    records: dict[str, list[str]] = {}
    for record_type in DNS_TYPES:
        try:
            answers = resolver.resolve(domain, record_type)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            records[record_type] = []
            continue
        except (dns.exception.DNSException, socket.timeout) as exc:
            records[record_type] = [f"Lookup failed: {exc}"]
            continue
        records[record_type] = [answer.to_text().strip('"') for answer in answers]
    return records


def lookup_domain(domain: str) -> dict:
    clean_domain = normalize_domain(domain)
    errors = []
    rdap_data: dict = {}
    dns_records: dict[str, list[str]] = {}

    try:
        rdap_data = lookup_rdap(clean_domain)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        errors.append(f"RDAP lookup failed: {exc}")

    try:
        dns_records = lookup_dns(clean_domain)
    except Exception as exc:  # noqa: BLE001 - lookup failures should be stored, not raised to users
        errors.append(f"DNS lookup failed: {exc}")

    nameservers = nameservers_from_rdap(rdap_data)
    if not nameservers:
        nameservers = dns_records.get("NS", [])

    status_values = rdap_data.get("status") or []
    return {
        "name": clean_domain,
        "registrar": registrar_from_rdap(rdap_data),
        "dns_provider": infer_dns_provider(nameservers),
        "status": ", ".join(status_values) if status_values else None,
        "expires_at": rdap_event_date(rdap_data, {"expiration", "expiry"}),
        "nameservers": nameservers,
        "dns_records": dns_records,
        "lookup_error": "\n".join(errors) or None,
        "last_lookup_at": datetime.utcnow(),
    }
