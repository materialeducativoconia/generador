from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    supabase_url: str  # https://<ref>.supabase.co
    supabase_service_role_key: str = ""  # Storage; sb_secret_… or the legacy service_role JWT
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_rpm: int = 50
    deepseek_max_inflight: int = 16
    openrouter_api_key: str = ""
    openrouter_image_model: str = "google/gemini-nano-banana-2.1"
    openrouter_review_model: str = "qwen/qwen3.7-flash"  # vision model of the image Reviewer
    openrouter_search_model: str = "perplexity/sonar"  # web search with citations, for official programs
    cloudflare_account_id: str = ""  # Workers AI: the free preview's Illustrator (free daily allowance)
    cloudflare_ai_token: str = ""
    stripe_secret_key: str = ""  # sk_live_… / sk_test_…; empty disables billing
    stripe_webhook_secret: str = ""  # whsec_…, from scripts/stripe_setup.py
    app_url: str = "http://localhost:5173"  # where Stripe sends the user back
    run_worker: bool = False  # run the job loop inside the API process (Render free plan has no workers)

    @property
    def auth_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.auth_issuer}/.well-known/jwks.json"
