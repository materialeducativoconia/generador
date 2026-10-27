from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    supabase_url: str  # https://<ref>.supabase.co
    supabase_service_role_key: str = ""  # Storage; sb_secret_… or the legacy service_role JWT
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_rpm: int = 50
    deepseek_max_inflight: int = 16

    @property
    def auth_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.auth_issuer}/.well-known/jwks.json"
