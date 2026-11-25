"""What must never leave this machine or enter the repository: keys, tokens, IP addresses, e-mail addresses.

One list of patterns, used in two places:
  - qa/harness/gate.py scans every file that git would commit (CI and the pre-commit hook);
  - qa/core/llm.py scans every prompt before it is sent to a model (the egress check).

    from qa.core.guard import find_leaks
    find_leaks("my key is sk-proj-...")   # -> [Leak(kind='OpenAI key', ...)]
"""
import ipaddress
import re
from dataclasses import dataclass

SECRET_PATTERNS = {
    "OpenAI key": r"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-|admin-|ant-)?[A-Za-z0-9_\-]{20,}",
    "GitHub token": r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "Slack token": r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "hard-coded credential": r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{16,}['\"]",
}
IPV4 = r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"
EMAIL = r"(?<!\\)[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"   # not right after a backslash: "\n@pytest.mark"

# Addresses that are safe to appear: loopback, "any", and the documentation ranges of RFC 5737.
SAFE_NETWORKS = [ipaddress.ip_network(n) for n in
                 ("127.0.0.0/8", "0.0.0.0/32", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", ".invalid", ".test", ".example",
                      "users.noreply.github.com")   # reserved names (RFC 2606) and GitHub's no-reply addresses

# Files that must never be tracked, whatever they contain.
FORBIDDEN_FILES = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|id_rsa.*|id_ed25519.*|auth\.json|credentials(\.json)?)$")


@dataclass
class Leak:
    kind: str
    text: str
    line: int

    def masked(self):
        """Enough to find it, never enough to use it."""
        return self.text[:6] + "..." if len(self.text) > 8 else "***"


def _safe_ip(s):
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return True                      # 999.1.2.3 is not an address (version numbers and the like)
    return any(ip in n for n in SAFE_NETWORKS)


def find_leaks(text):
    """Every secret, IPv4 address or e-mail address in `text`, with its line number."""
    leaks = []
    for kind, pattern in SECRET_PATTERNS.items():
        for m in re.finditer(pattern, text):
            leaks.append(Leak(kind, m.group(0), text.count("\n", 0, m.start()) + 1))
    for m in re.finditer(IPV4, text):
        if not _safe_ip(m.group(0)):
            leaks.append(Leak("IP address", m.group(0), text.count("\n", 0, m.start()) + 1))
    for m in re.finditer(EMAIL, text):
        if not m.group(0).lower().endswith(SAFE_EMAIL_DOMAINS):
            leaks.append(Leak("e-mail address", m.group(0), text.count("\n", 0, m.start()) + 1))
    return leaks
