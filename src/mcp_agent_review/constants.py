import os
from fnmatch import fnmatch

SENSITIVE_PATTERNS = [
    ".env", ".env.*",
    "*.pem", "*.key", "*.p12", "*.pfx",
    "*.jks", "*.keystore",
    "id_rsa", "id_ed25519", "id_ecdsa",
    "credentials.json", "service-account*.json",
    ".netrc", ".pgpass", ".my.cnf",
    "*.secret", "secrets.*",
]


def is_sensitive(path: str) -> bool:
    basename = os.path.basename(path)
    return any(fnmatch(basename, pat) for pat in SENSITIVE_PATTERNS)
