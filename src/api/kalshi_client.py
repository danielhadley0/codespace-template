"""
Kalshi API client for market data and order execution.
"""
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog
import hashlib
import hmac
import base64
from urllib.parse import urlencode

from config.settings import settings
from src.utils.retry import retry_with_backoff

logger = structlog.get_logger()


class KalshiClient:
    """
    Async client for Kalshi API.
    Handles authentication, market data fetching, and order execution.
    """

    def __init__(self):
        self.base_url = settings.kalshi_base_url
        self.api_key = settings.kalshi_api_key
        self.api_secret = settings.kalshi_api_secret
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def initialize(self):
        """Initialize HTTP session and authenticate."""
        self.session = aiohttp.ClientSession()
        await self.authenticate()
        logger.info("Kalshi client initialized")

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            logger.info("Kalshi client closed")

    async def authenticate(self):
        """Authenticate with Kalshi and obtain access token."""
        # Skip authentication in paper trading mode
        if settings.paper_trading_mode:
            logger.info("Kalshi client in paper trading mode - skipping authentication")
            self.auth_token = "PAPER_TRADING_MODE"
            return

        try:
            # Updated endpoint for Kalshi API v2
            url = f"{self.base_url}/log_in"
            payload = {
                "email": self.api_key,
                "password": self.api_secret
            }

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get('token')
                    logger.info("Kalshi authentication successful")
                else:
                    error_text = await response.text()
                    logger.error("Kalshi authentication failed",
                               status=response.status,
                               error=error_text)
                    raise Exception(f"Authentication failed: {error_text}")

        except Exception as e:
            logger.error("Kalshi authentication error", error=str(e))
            raise

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    @retry_with_backoff(max_retries=3)
    async def get_markets(self, status: str = "open") -> List[Dict[str, Any]]:
        """
        Fetch all active markets from Kalshi.

        Args:
            status: Market status filter (open, closed, settled)

        Returns:
            List of market dictionaries
        """
        # Return mock data in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock Kalshi markets")
            return self._get_mock_markets()

        try:
            url = f"{self.base_url}/markets"
            params = {
                "status": status,
                "limit": 200
            }

            async with self.session.get(
                url,
                headers=self._get_headers(),
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data.get('markets', [])
                    logger.debug("Fetched Kalshi markets", count=len(markets))
                    return markets
                else:
                    error_text = await response.text()
                    logger.error("Failed to fetch Kalshi markets",
                               status=response.status,
                               error=error_text)
                    return []

        except Exception as e:
            logger.error("Error fetching Kalshi markets", error=str(e))
            return []

    def _get_mock_markets(self) -> List[Dict[str, Any]]:
        """Return mock market data for paper trading."""
        return [
            # Crypto markets
            {'ticker': 'BTC-DEC25-70K', 'title': 'Will Bitcoin be above $70,000 on Dec 31, 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 55, 'no_bid': 45, 'volume': 50000, 'status': 'open'},
            {'ticker': 'ETH-DEC25-5K', 'title': 'Will Ethereum reach $5,000 by end of 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 48, 'no_bid': 52, 'volume': 35000, 'status': 'open'},
            {'ticker': 'BTC-JUN25-100K', 'title': 'Will Bitcoin hit $100,000 before July 2025?',
             'close_time': '2025-06-30T23:59:00Z', 'yes_bid': 35, 'no_bid': 65, 'volume': 80000, 'status': 'open'},
            {'ticker': 'SOL-2025-500', 'title': 'Will Solana trade above $500 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 42, 'no_bid': 58, 'volume': 25000, 'status': 'open'},

            # Stock market indices
            {'ticker': 'SPX-2025-6000', 'title': 'Will the S&P 500 end 2025 above 6000?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 62, 'no_bid': 38, 'volume': 75000, 'status': 'open'},
            {'ticker': 'SPX-2025-6500', 'title': 'Will S&P 500 reach 6500 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 45, 'no_bid': 55, 'volume': 60000, 'status': 'open'},
            {'ticker': 'NASDAQ-2025-20K', 'title': 'Will NASDAQ hit 20,000 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 51, 'no_bid': 49, 'volume': 45000, 'status': 'open'},
            {'ticker': 'DOW-2025-45K', 'title': 'Will Dow Jones reach 45,000 by end of 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 58, 'no_bid': 42, 'volume': 40000, 'status': 'open'},

            # Tech stocks
            {'ticker': 'TSLA-2025-500', 'title': 'Will Tesla stock hit $500 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 38, 'no_bid': 62, 'volume': 90000, 'status': 'open'},
            {'ticker': 'NVDA-2025-200', 'title': 'Will NVIDIA reach $200 per share in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 65, 'no_bid': 35, 'volume': 85000, 'status': 'open'},
            {'ticker': 'AAPL-2025-250', 'title': 'Will Apple stock trade above $250 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 52, 'no_bid': 48, 'volume': 70000, 'status': 'open'},
            {'ticker': 'MSFT-2025-500', 'title': 'Will Microsoft reach $500 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 48, 'no_bid': 52, 'volume': 65000, 'status': 'open'},

            # Politics - US
            {'ticker': 'PRES-2028-DEM', 'title': 'Will a Democrat win the 2028 Presidential election?',
             'close_time': '2028-11-08T23:59:00Z', 'yes_bid': 50, 'no_bid': 50, 'volume': 120000, 'status': 'open'},
            {'ticker': 'HOUSE-2026-GOP', 'title': 'Will Republicans control House in 2026?',
             'close_time': '2026-11-04T23:59:00Z', 'yes_bid': 54, 'no_bid': 46, 'volume': 75000, 'status': 'open'},
            {'ticker': 'SENATE-2026-DEM', 'title': 'Will Democrats control Senate after 2026 midterms?',
             'close_time': '2026-11-04T23:59:00Z', 'yes_bid': 47, 'no_bid': 53, 'volume': 68000, 'status': 'open'},

            # Economy
            {'ticker': 'FED-2025-CUTS', 'title': 'Will Fed cut rates at least 3 times in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 41, 'no_bid': 59, 'volume': 55000, 'status': 'open'},
            {'ticker': 'RECESSION-2025', 'title': 'Will US enter recession in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 28, 'no_bid': 72, 'volume': 90000, 'status': 'open'},
            {'ticker': 'CPI-2025-3PCT', 'title': 'Will inflation fall below 3% in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 60, 'no_bid': 40, 'volume': 45000, 'status': 'open'},
            {'ticker': 'GOLD-2025-3000', 'title': 'Will gold reach $3,000 per ounce in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 44, 'no_bid': 56, 'volume': 35000, 'status': 'open'},
            {'ticker': 'OIL-2025-100', 'title': 'Will oil hit $100/barrel in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 36, 'no_bid': 64, 'volume': 42000, 'status': 'open'},

            # Sports
            {'ticker': 'NFL-2026-KC', 'title': 'Will Kansas City Chiefs win Super Bowl 2026?',
             'close_time': '2026-02-15T23:59:00Z', 'yes_bid': 18, 'no_bid': 82, 'volume': 95000, 'status': 'open'},
            {'ticker': 'NBA-2025-BOS', 'title': 'Will Boston Celtics win 2025 NBA Championship?',
             'close_time': '2025-06-30T23:59:00Z', 'yes_bid': 24, 'no_bid': 76, 'volume': 70000, 'status': 'open'},
            {'ticker': 'MLB-2025-NYY', 'title': 'Will Yankees win 2025 World Series?',
             'close_time': '2025-11-01T23:59:00Z', 'yes_bid': 15, 'no_bid': 85, 'volume': 60000, 'status': 'open'},

            # Tech & AI
            {'ticker': 'GPT5-2025', 'title': 'Will OpenAI release GPT-5 in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 55, 'no_bid': 45, 'volume': 110000, 'status': 'open'},
            {'ticker': 'TESLA-FSD-2025', 'title': 'Will Tesla achieve full self-driving in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 22, 'no_bid': 78, 'volume': 85000, 'status': 'open'},
            {'ticker': 'APPLE-AR-2025', 'title': 'Will Apple release AR glasses in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 32, 'no_bid': 68, 'volume': 65000, 'status': 'open'},

            # Weather & Climate
            {'ticker': 'TEMP-2025-RECORD', 'title': 'Will 2025 be hottest year on record?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 58, 'no_bid': 42, 'volume': 28000, 'status': 'open'},
            {'ticker': 'HURRICANE-2025', 'title': 'Will Atlantic see Category 5 hurricane in 2025?',
             'close_time': '2025-11-30T23:59:00Z', 'yes_bid': 42, 'no_bid': 58, 'volume': 22000, 'status': 'open'},

            # International
            {'ticker': 'CHINA-GDP-2025', 'title': 'Will China GDP grow over 5% in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 51, 'no_bid': 49, 'volume': 38000, 'status': 'open'},
            {'ticker': 'UK-ELECTION-2025', 'title': 'Will UK hold general election in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 35, 'no_bid': 65, 'volume': 45000, 'status': 'open'},

            # Entertainment
            {'ticker': 'OSCARS-2026-DRAMA', 'title': 'Will a drama win Best Picture at 2026 Oscars?',
             'close_time': '2026-03-01T23:59:00Z', 'yes_bid': 62, 'no_bid': 38, 'volume': 18000, 'status': 'open'},
            {'ticker': 'STREAMING-2025', 'title': 'Will Netflix add 20M+ subscribers in 2025?',
             'close_time': '2025-12-31T23:59:00Z', 'yes_bid': 48, 'no_bid': 52, 'volume': 35000, 'status': 'open'},
        ]

    @retry_with_backoff(max_retries=3)
    async def get_market(self, market_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details for a specific market.

        Args:
            market_ticker: Market ticker symbol

        Returns:
            Market details dictionary or None
        """
        # Return mock data in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock market data",
                        ticker=market_ticker)
            # Find and return the mock market that matches this ticker
            mock_markets = self._get_mock_markets()
            for market in mock_markets:
                if market.get('ticker') == market_ticker:
                    return market
            # If not found, return the first mock market as fallback
            return mock_markets[0] if mock_markets else None

        try:
            url = f"{self.base_url}/markets/{market_ticker}"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('market')
                else:
                    logger.error("Failed to fetch Kalshi market",
                               ticker=market_ticker,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error fetching Kalshi market",
                        ticker=market_ticker,
                        error=str(e))
            return None

    @retry_with_backoff(max_retries=3)
    async def get_orderbook(self, market_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get current orderbook for a market.

        Args:
            market_ticker: Market ticker symbol

        Returns:
            Orderbook data with bids and asks
        """
        # Return mock orderbook in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock orderbook",
                        ticker=market_ticker)
            # Orderbook format: list of [price_in_cents, size]
            return {
                'yes': [
                    [55, 100],  # 55 cents, 100 contracts
                    [54, 200],
                    [53, 500]
                ],
                'no': [
                    [45, 100],  # 45 cents, 100 contracts
                    [44, 200],
                    [43, 500]
                ]
            }

        try:
            url = f"{self.base_url}/markets/{market_ticker}/orderbook"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('orderbook')
                else:
                    logger.error("Failed to fetch orderbook",
                               ticker=market_ticker,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error fetching orderbook",
                        ticker=market_ticker,
                        error=str(e))
            return None

    async def place_order(
        self,
        market_ticker: str,
        side: str,
        quantity: int,
        price: int,
        order_type: str = "limit"
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order on Kalshi.

        Args:
            market_ticker: Market ticker symbol
            side: "yes" or "no"
            quantity: Number of contracts (in cents, so 100 = $1)
            price: Price in cents (1-99)
            order_type: "limit" or "market"

        Returns:
            Order response dictionary or None
        """
        try:
            url = f"{self.base_url}/portfolio/orders"
            payload = {
                "ticker": market_ticker,
                "action": "buy",
                "side": side,
                "count": quantity,
                "type": order_type,
            }

            if order_type == "limit":
                payload["yes_price"] = price if side == "yes" else None
                payload["no_price"] = price if side == "no" else None

            async with self.session.post(
                url,
                headers=self._get_headers(),
                json=payload
            ) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    order = data.get('order')
                    logger.info("Kalshi order placed",
                              order_id=order.get('order_id'),
                              ticker=market_ticker,
                              side=side)
                    return order
                else:
                    error_text = await response.text()
                    logger.error("Failed to place Kalshi order",
                               status=response.status,
                               error=error_text)
                    return None

        except Exception as e:
            logger.error("Error placing Kalshi order", error=str(e))
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/portfolio/orders/{order_id}"

            async with self.session.delete(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    logger.info("Kalshi order cancelled", order_id=order_id)
                    return True
                else:
                    logger.error("Failed to cancel Kalshi order",
                               order_id=order_id,
                               status=response.status)
                    return False

        except Exception as e:
            logger.error("Error cancelling Kalshi order",
                        order_id=order_id,
                        error=str(e))
            return False

    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of an order.

        Args:
            order_id: Order ID

        Returns:
            Order status dictionary or None
        """
        try:
            url = f"{self.base_url}/portfolio/orders/{order_id}"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('order')
                else:
                    logger.error("Failed to get Kalshi order status",
                               order_id=order_id,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error getting Kalshi order status",
                        order_id=order_id,
                        error=str(e))
            return None

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        try:
            url = f"{self.base_url}/portfolio/positions"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('positions', [])
                else:
                    logger.error("Failed to fetch Kalshi positions",
                               status=response.status)
                    return []

        except Exception as e:
            logger.error("Error fetching Kalshi positions", error=str(e))
            return []

    def parse_market_to_event(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Kalshi market data to standardized event format.

        Args:
            market: Raw market data from Kalshi API

        Returns:
            Standardized event dictionary
        """
        # Parse close_time and remove timezone info for database compatibility
        close_time = None
        if market.get('close_time'):
            try:
                # Parse and convert to naive datetime
                dt = datetime.fromisoformat(
                    market.get('close_time', '').replace('Z', '+00:00')
                )
                close_time = dt.replace(tzinfo=None)  # Remove timezone
            except:
                pass

        return {
            'event_id': market.get('ticker'),
            'title': market.get('title', ''),
            'url': f"https://kalshi.com/markets/{market.get('ticker')}",
            'close_time': close_time,
            'yes_price': market.get('yes_bid', 0) / 100.0,  # Convert cents to decimal
            'no_price': market.get('no_bid', 0) / 100.0,
            'liquidity': market.get('volume', 0),
        }
