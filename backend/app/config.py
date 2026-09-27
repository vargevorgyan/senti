"""Backend settings from environment variables (see docker-compose.yml / .env.example)."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_INSTALLER = "https://raw.githubusercontent.com/vargevorgyan/senti/main/engine/install.sh"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTI_", env_file=".env", extra="ignore")

    data_dir: str = "./data"
    database_url: str = ""  # default: sqlite in data_dir
    secret_key: str = "change-me-in-production"
    admin_email: str = "admin@senti.local"
    admin_password: str = "senti-admin"
    org_name: str = "Acme Corp"
    demo_enroll_code: str = ""  # set SENTI_DEMO_ENROLL_CODE for demos only (20 uses, 7 days)
    # Shared (multi-use, not tied to a person) enrollment codes: off. Admins invite people instead (personal, one-time keys).
    allow_shared_codes: bool = False
    invite_ttl_hours: int = 48
    # Per-device limits on the device API (requests per minute), so a leaked or rogue device can't burn the corporate model
    judge_rpm: int = 60
    approvals_rpm: int = 20
    # Server gateway (MCP): the folder and SQLite database agents may reach, only through the gateway
    gateway_root: str = ""        # default: <data_dir>/server-files
    gateway_db: str = ""          # default: <data_dir>/server.db
    gateway_rpm: int = 120        # per agent token
    gateway_cmd_timeout_s: float = 10.0
    # Model that turns the plain-English policy into rules (default: the corporate model). Use a strong one; it runs rarely.
    policy_model_url: str = ""
    policy_model: str = ""
    policy_model_api_key: str = ""
    # The admin panel and the device API are served from the same origin: no cross-origin browser access by default
    cors_origins: str = ""
    # Who may reach the admin API and admin sign-in (comma-separated IPs/CIDRs, or "any"). Macs, bots and the join
    # endpoint stay reachable from anywhere; the admin side defaults to this computer and private networks (office, VPN).
    admin_allow: str = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
    # Failed sign-ins: an account is locked for lockout_minutes after login_max_failures; an IP after 4x that
    login_max_failures: int = 5
    lockout_minutes: int = 15
    enroll_rpm_per_ip: int = 10   # join attempts and invite look-ups per IP per minute
    # Device requests must be signed with the Mac's device key; allowed clock difference in seconds
    device_sig_window_s: int = 300
    # The address Macs use (goes into invite links), e.g. https://senti.acme.com:8443. Empty: the admin panel's own address.
    public_url: str = ""
    # public_url is served with a publicly trusted certificate (e.g. Let's Encrypt on a reverse proxy in front of Senti):
    # invites then carry no fingerprint and Macs verify the server the normal way instead of pinning Senti's own CA
    public_tls: bool = False
    # Join page for invite links. Empty: the /join page of this server's admin panel.
    join_page: str = ""
    # The Mac installer script. Servers with Senti's own certificate need it from a publicly trusted address (it then
    # checks this server against the invite's fingerprint); servers with a public certificate serve their own /install.sh.
    installer_url: str = DEFAULT_INSTALLER
    # Gateway tools run in the isolated runner container (Unix socket). Running them inside the backend process, next to
    # the signing key and the database, is only for tests and development and must be switched on explicitly.
    gateway_runner: str = ""
    gateway_in_process: bool = False
    tls_ca: str = ""         # path to the organization's own TLS CA certificate (self-signed deployments)
    # corporate model (OpenAI-compatible chat completions endpoint, e.g. Ollama)
    corp_model_url: str = "http://localhost:11434/v1"
    corp_model: str = "qwen2.5:3b"
    corp_model_api_key: str = ""
    corp_model_enabled: bool = True  # false: no company AI yet; unclear actions are asked about or blocked
    corp_timeout_s: float = 25.0
    token_ttl_hours: int = 8
    tls_cert: str = ""       # path to the TLS certificate served by the admin container
    https_port: int = 8443

    @field_validator("installer_url")
    @classmethod
    def _installer_default(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return DEFAULT_INSTALLER  # an empty SENTI_INSTALLER_URL= line in .env means "the default"
        if not v.startswith("https://"):
            raise ValueError("SENTI_INSTALLER_URL must be an https:// address")
        return v

    @property
    def gateway_root_path(self) -> str:
        return self.gateway_root or f"{self.data_dir}/server-files"

    @property
    def gateway_db_path(self) -> str:
        return self.gateway_db or f"{self.data_dir}/server.db"

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir}/senti.db"


settings = Settings()
