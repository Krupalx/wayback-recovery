"""
Configuration and constants.
"""

from dataclasses import dataclass, field
from pathlib import Path


# Rotate through these to look like normal browser traffic.
# Mix of Chrome, Firefox, Safari, Edge on different platforms.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


@dataclass
class RecoveryConfig:
    domain: str
    output_dir: Path = field(default_factory=lambda: Path("output"))
    delay_min: float = 5.0
    delay_max: float = 10.0
    max_retries: int = 3
    timeout: float = 30.0
    use_wayback: bool = True
    use_commoncrawl: bool = True
    use_cdn_detection: bool = True
    resume: bool = True
    limit: int = 0
