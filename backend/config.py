import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    demo_mode: bool = os.getenv('DEMO_MODE', 'false').lower() == 'true'
    database_url: str = os.getenv(
        "DATABASE_URL", "sqlite:///" + str(ROOT / "honeychain.db")
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    token_minutes: int = int(os.getenv("TOKEN_MINUTES", "60"))
    environment: str = os.getenv("APP_ENV", "local")
    public_url: str = os.getenv("FRONTEND_URL", os.getenv("PUBLIC_URL", "http://127.0.0.1:8000"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://127.0.0.1:8000")
    normal_temp_min: float = float(os.getenv("NORMAL_TEMP_MIN", "30"))
    normal_temp_max: float = float(os.getenv("NORMAL_TEMP_MAX", "37"))
    temp_warning: float = float(os.getenv("TEMP_WARNING_THRESHOLD", "38"))
    humidity_min: float = float(os.getenv("HUMIDITY_MIN", "30"))
    humidity_max: float = float(os.getenv("HUMIDITY_MAX", "85"))
    stress_minutes: int = int(os.getenv("STRESS_MINUTES", "30"))
    swarm_minutes: int = int(os.getenv("SWARM_WINDOW_MINUTES", "30"))
    weight_drop: float = float(os.getenv("WEIGHT_DROP_THRESHOLD", "2"))
    sensor_jump: float = float(os.getenv("SENSOR_JUMP_KG", "15"))
    harvest_target: float = float(os.getenv("HARVEST_WEIGHT_TARGET", "40"))
    harvest_gain: float = float(os.getenv("HARVEST_GAIN_KG", "5"))
    harvest_hours: int = int(os.getenv("HARVEST_STABILITY_HOURS", "48"))
    harvest_tolerance: float = float(os.getenv("HARVEST_TOLERANCE_KG", "0.5"))
    max_gap_minutes: int = int(os.getenv("MAX_GAP_MINUTES", "65"))
    regional_percentage: float = float(os.getenv("REGIONAL_ALERT_PERCENTAGE", "15"))
    regional_hours: int = int(os.getenv("REGIONAL_WINDOW_HOURS", "48"))
    regional_min_monitored: int = int(os.getenv("REGIONAL_MIN_MONITORED", "4"))
    regional_min_affected: int = int(os.getenv("REGIONAL_MIN_AFFECTED", "2"))
    offline_minutes: int = int(os.getenv("DEVICE_OFFLINE_MINUTES", "15"))
    max_age_days: int = int(os.getenv("MAX_TELEMETRY_AGE_DAYS", "30"))
    rule_version: str = "sih-rules-1.0"

    def validate_deployment(self):
        if self.environment != "production":
            return
        from urllib.parse import urlsplit
        import ipaddress
        origins = [self.public_url] + [x.strip() for x in self.cors_origins.split(",")]
        for origin in origins:
            u = urlsplit(origin)
            if u.scheme != "https" or not u.hostname or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
                raise RuntimeError("Production frontend and CORS require explicit HTTPS origins")
            if u.hostname in ("localhost", "v0.app") or u.hostname.endswith((".localhost", ".v0.app")):
                raise RuntimeError("Production requires a public frontend domain")
            try:
                address = ipaddress.ip_address(u.hostname)
            except ValueError:
                address = None
            if address and not address.is_global:
                raise RuntimeError("Production cannot use local IP addresses")
        if self.public_url.rstrip("/") not in [x.strip().rstrip("/") for x in self.cors_origins.split(",")]:
            raise RuntimeError("CORS_ORIGINS must include FRONTEND_URL")
