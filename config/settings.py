"""
Configuration settings for the arbitrage system.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(..., env='DATABASE_URL')

    # Kalshi API
    kalshi_api_key: str = Field(..., env='KALSHI_API_KEY')
    kalshi_api_secret: str = Field(..., env='KALSHI_API_SECRET')
    kalshi_base_url: str = Field(
        default='https://api.elections.kalshi.com/trade-api/v2',
        env='KALSHI_BASE_URL'
    )

    # Polymarket API
    polymarket_api_key: str = Field(..., env='POLYMARKET_API_KEY')
    polymarket_private_key: str = Field(..., env='POLYMARKET_PRIVATE_KEY')
    polymarket_base_url: str = Field(
        default='https://clob.polymarket.com',
        env='POLYMARKET_BASE_URL'
    )

    # Discord
    discord_bot_token: str = Field(..., env='DISCORD_BOT_TOKEN')
    discord_channel_id: int = Field(..., env='DISCORD_CHANNEL_ID')

    # Redis
    redis_url: Optional[str] = Field(default='redis://localhost:6379/0', env='REDIS_URL')

    # Trading Parameters
    paper_trading_mode: bool = Field(default=True, env='PAPER_TRADING_MODE')
    min_arbitrage_threshold: float = Field(default=0.01, env='MIN_ARBITRAGE_THRESHOLD')
    max_trade_size: float = Field(default=1000.0, env='MAX_TRADE_SIZE')
    max_position_per_market: float = Field(default=5000.0, env='MAX_POSITION_PER_MARKET')
    slippage_tolerance: float = Field(default=0.02, env='SLIPPAGE_TOLERANCE')
    order_timeout_seconds: int = Field(default=30, env='ORDER_TIMEOUT_SECONDS')
    cooldown_between_trades: int = Field(default=5, env='COOLDOWN_BETWEEN_TRADES')

    # Paper Trading Parameters
    paper_simulated_slippage: float = Field(default=0.005, env='PAPER_SIMULATED_SLIPPAGE')
    paper_partial_fill_chance: float = Field(default=0.1, env='PAPER_PARTIAL_FILL_CHANCE')
    paper_starting_balance: float = Field(default=10000.0, env='PAPER_STARTING_BALANCE')

    # Monitoring
    price_fetch_interval: int = Field(default=5, env='PRICE_FETCH_INTERVAL')
    max_retry_attempts: int = Field(default=3, env='MAX_RETRY_ATTEMPTS')
    retry_backoff_base: int = Field(default=2, env='RETRY_BACKOFF_BASE')

    # Logging
    log_level: str = Field(default='INFO', env='LOG_LEVEL')
    log_file: str = Field(default='logs/arbitrage.log', env='LOG_FILE')

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False


# Global settings instance
settings = Settings()
