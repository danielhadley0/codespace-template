"""
Polymarket API client for market data and order execution.
"""
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog
import json

from config.settings import settings
from src.utils.retry import retry_with_backoff

logger = structlog.get_logger()


class PolymarketClient:
    """
    Async client for Polymarket CLOB API.
    Handles market data fetching and order execution.
    """

    def __init__(self):
        self.base_url = settings.polymarket_base_url
        self.api_key = settings.polymarket_api_key
        self.private_key = settings.polymarket_private_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def initialize(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession()
        if settings.paper_trading_mode:
            logger.info("Polymarket client initialized in paper trading mode")
        else:
            logger.info("Polymarket client initialized")

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            logger.info("Polymarket client closed")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @retry_with_backoff(max_retries=3)
    async def get_markets(self, closed: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch all markets from Polymarket.

        Args:
            closed: Whether to include closed markets

        Returns:
            List of market dictionaries
        """
        # Return mock data in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock Polymarket markets")
            return self._get_mock_markets()

        try:
            url = f"{self.base_url}/markets"
            params = {
                "closed": str(closed).lower(),
                "limit": 200
            }

            async with self.session.get(
                url,
                headers=self._get_headers(),
                params=params
            ) as response:
                if response.status == 200:
                    markets = await response.json()
                    logger.debug("Fetched Polymarket markets", count=len(markets))
                    return markets
                else:
                    error_text = await response.text()
                    logger.error("Failed to fetch Polymarket markets",
                               status=response.status,
                               error=error_text)
                    return []

        except Exception as e:
            logger.error("Error fetching Polymarket markets", error=str(e))
            return []

    def _get_mock_markets(self) -> List[Dict[str, Any]]:
        """Return mock market data for paper trading."""
        return [
            # Crypto markets (matching Kalshi)
            {'condition_id': 'BTC-70K-DEC2025', 'question': 'Will Bitcoin trade above $70,000 on December 31, 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.52, 0.48],
             'outcomes': [{'token_id': 'btc70k-yes'}, {'token_id': 'btc70k-no'}], 'volume': 55000},
            {'condition_id': 'ETH-5K-2025', 'question': 'Will Ethereum hit $5,000 by end of 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.50, 0.50],
             'outcomes': [{'token_id': 'eth5k-yes'}, {'token_id': 'eth5k-no'}], 'volume': 38000},
            {'condition_id': 'BTC-100K-JUN25', 'question': 'Will Bitcoin reach $100,000 before July 2025?',
             'end_date_iso': '2025-06-30T23:59:00Z', 'outcomePrices': [0.33, 0.67],
             'outcomes': [{'token_id': 'btc100k-yes'}, {'token_id': 'btc100k-no'}], 'volume': 85000},
            {'condition_id': 'SOL-500-2025', 'question': 'Will Solana be above $500 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.40, 0.60],
             'outcomes': [{'token_id': 'sol500-yes'}, {'token_id': 'sol500-no'}], 'volume': 28000},

            # Stock indices (matching Kalshi)
            {'condition_id': 'SPX-6000-2025', 'question': 'Will S&P 500 close 2025 above 6000?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.60, 0.40],
             'outcomes': [{'token_id': 'spx6k-yes'}, {'token_id': 'spx6k-no'}], 'volume': 80000},
            {'condition_id': 'SPX-6500-2025', 'question': 'Will S&P 500 hit 6500 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.43, 0.57],
             'outcomes': [{'token_id': 'spx6500-yes'}, {'token_id': 'spx6500-no'}], 'volume': 62000},
            {'condition_id': 'NASDAQ-20K-2025', 'question': 'Will NASDAQ reach 20,000 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.49, 0.51],
             'outcomes': [{'token_id': 'ndaq20k-yes'}, {'token_id': 'ndaq20k-no'}], 'volume': 48000},
            {'condition_id': 'DOW-45K-2025', 'question': 'Will Dow Jones hit 45,000 by December 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.56, 0.44],
             'outcomes': [{'token_id': 'dow45k-yes'}, {'token_id': 'dow45k-no'}], 'volume': 42000},

            # Tech stocks (matching Kalshi)
            {'condition_id': 'TSLA-500-2025', 'question': 'Will Tesla stock reach $500 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.36, 0.64],
             'outcomes': [{'token_id': 'tsla500-yes'}, {'token_id': 'tsla500-no'}], 'volume': 95000},
            {'condition_id': 'NVDA-200-2025', 'question': 'Will NVIDIA hit $200 per share in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.63, 0.37],
             'outcomes': [{'token_id': 'nvda200-yes'}, {'token_id': 'nvda200-no'}], 'volume': 88000},
            {'condition_id': 'AAPL-250-2025', 'question': 'Will Apple stock be above $250 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.50, 0.50],
             'outcomes': [{'token_id': 'aapl250-yes'}, {'token_id': 'aapl250-no'}], 'volume': 72000},
            {'condition_id': 'MSFT-500-2025', 'question': 'Will Microsoft stock reach $500 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.46, 0.54],
             'outcomes': [{'token_id': 'msft500-yes'}, {'token_id': 'msft500-no'}], 'volume': 68000},

            # Politics (matching Kalshi)
            {'condition_id': 'PRES2028-DEM', 'question': 'Will Democrats win Presidential election in 2028?',
             'end_date_iso': '2028-11-08T23:59:00Z', 'outcomePrices': [0.48, 0.52],
             'outcomes': [{'token_id': 'pres28d-yes'}, {'token_id': 'pres28d-no'}], 'volume': 125000},
            {'condition_id': 'HOUSE2026-GOP', 'question': 'Will GOP control House after 2026 midterms?',
             'end_date_iso': '2026-11-04T23:59:00Z', 'outcomePrices': [0.52, 0.48],
             'outcomes': [{'token_id': 'house26r-yes'}, {'token_id': 'house26r-no'}], 'volume': 78000},
            {'condition_id': 'SENATE2026-DEM', 'question': 'Will Democrats control Senate in 2026?',
             'end_date_iso': '2026-11-04T23:59:00Z', 'outcomePrices': [0.45, 0.55],
             'outcomes': [{'token_id': 'sen26d-yes'}, {'token_id': 'sen26d-no'}], 'volume': 70000},

            # Economy (matching Kalshi)
            {'condition_id': 'FED-CUTS-2025', 'question': 'Will Federal Reserve cut rates 3+ times in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.39, 0.61],
             'outcomes': [{'token_id': 'fedcut3-yes'}, {'token_id': 'fedcut3-no'}], 'volume': 58000},
            {'condition_id': 'RECESSION-US-2025', 'question': 'Will US economy enter recession in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.26, 0.74],
             'outcomes': [{'token_id': 'recess25-yes'}, {'token_id': 'recess25-no'}], 'volume': 92000},
            {'condition_id': 'INFLATION-3PCT-2025', 'question': 'Will US inflation drop below 3% in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.58, 0.42],
             'outcomes': [{'token_id': 'cpi3-yes'}, {'token_id': 'cpi3-no'}], 'volume': 47000},
            {'condition_id': 'GOLD-3000-2025', 'question': 'Will gold hit $3,000/oz in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.42, 0.58],
             'outcomes': [{'token_id': 'gold3k-yes'}, {'token_id': 'gold3k-no'}], 'volume': 38000},
            {'condition_id': 'OIL-100-2025', 'question': 'Will crude oil reach $100 per barrel in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.34, 0.66],
             'outcomes': [{'token_id': 'oil100-yes'}, {'token_id': 'oil100-no'}], 'volume': 44000},

            # Sports (matching Kalshi)
            {'condition_id': 'SB2026-CHIEFS', 'question': 'Will KC Chiefs win 2026 Super Bowl?',
             'end_date_iso': '2026-02-15T23:59:00Z', 'outcomePrices': [0.16, 0.84],
             'outcomes': [{'token_id': 'sb26kc-yes'}, {'token_id': 'sb26kc-no'}], 'volume': 98000},
            {'condition_id': 'NBA2025-CELTICS', 'question': 'Will Celtics win 2025 NBA title?',
             'end_date_iso': '2025-06-30T23:59:00Z', 'outcomePrices': [0.22, 0.78],
             'outcomes': [{'token_id': 'nba25bos-yes'}, {'token_id': 'nba25bos-no'}], 'volume': 73000},
            {'condition_id': 'WS2025-YANKEES', 'question': 'Will NY Yankees win 2025 World Series?',
             'end_date_iso': '2025-11-01T23:59:00Z', 'outcomePrices': [0.13, 0.87],
             'outcomes': [{'token_id': 'ws25nyy-yes'}, {'token_id': 'ws25nyy-no'}], 'volume': 62000},

            # Tech & AI (matching Kalshi)
            {'condition_id': 'GPT5-RELEASE-2025', 'question': 'Will OpenAI launch GPT-5 in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.53, 0.47],
             'outcomes': [{'token_id': 'gpt5-yes'}, {'token_id': 'gpt5-no'}], 'volume': 115000},
            {'condition_id': 'TESLA-FSD-2025', 'question': 'Will Tesla have full self-driving in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.20, 0.80],
             'outcomes': [{'token_id': 'fsd25-yes'}, {'token_id': 'fsd25-no'}], 'volume': 88000},
            {'condition_id': 'APPLE-AR-2025', 'question': 'Will Apple launch AR glasses in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.30, 0.70],
             'outcomes': [{'token_id': 'applegar-yes'}, {'token_id': 'applegar-no'}], 'volume': 68000},

            # Weather (matching Kalshi)
            {'condition_id': 'TEMP-RECORD-2025', 'question': 'Will 2025 set global temperature record?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.56, 0.44],
             'outcomes': [{'token_id': 'temp25-yes'}, {'token_id': 'temp25-no'}], 'volume': 30000},
            {'condition_id': 'HURRICANE-CAT5-2025', 'question': 'Will Category 5 hurricane hit Atlantic in 2025?',
             'end_date_iso': '2025-11-30T23:59:00Z', 'outcomePrices': [0.40, 0.60],
             'outcomes': [{'token_id': 'hurr25-yes'}, {'token_id': 'hurr25-no'}], 'volume': 24000},

            # International (matching Kalshi)
            {'condition_id': 'CHINA-GDP-5PCT-2025', 'question': 'Will China economy grow 5%+ in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.49, 0.51],
             'outcomes': [{'token_id': 'cngdp5-yes'}, {'token_id': 'cngdp5-no'}], 'volume': 40000},
            {'condition_id': 'UK-GE-2025', 'question': 'Will United Kingdom hold election in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.33, 0.67],
             'outcomes': [{'token_id': 'ukge25-yes'}, {'token_id': 'ukge25-no'}], 'volume': 47000},

            # Entertainment (matching Kalshi)
            {'condition_id': 'OSCARS2026-DRAMA', 'question': 'Will drama win Best Picture Oscar 2026?',
             'end_date_iso': '2026-03-01T23:59:00Z', 'outcomePrices': [0.60, 0.40],
             'outcomes': [{'token_id': 'osc26dr-yes'}, {'token_id': 'osc26dr-no'}], 'volume': 20000},
            {'condition_id': 'NETFLIX-SUBS-2025', 'question': 'Will Netflix gain 20M+ subscribers in 2025?',
             'end_date_iso': '2025-12-31T23:59:00Z', 'outcomePrices': [0.46, 0.54],
             'outcomes': [{'token_id': 'nflx20m-yes'}, {'token_id': 'nflx20m-no'}], 'volume': 37000},
        ]

    @retry_with_backoff(max_retries=3)
    async def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details for a specific market.

        Args:
            condition_id: Market condition ID

        Returns:
            Market details dictionary or None
        """
        # Return mock data in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock market data",
                        condition_id=condition_id)
            # Find and return the mock market that matches this condition_id
            mock_markets = self._get_mock_markets()
            for market in mock_markets:
                if market.get('condition_id') == condition_id:
                    return market
            # If not found, return the first mock market as fallback
            return mock_markets[0] if mock_markets else None

        try:
            url = f"{self.base_url}/markets/{condition_id}"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("Failed to fetch Polymarket market",
                               condition_id=condition_id,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error fetching Polymarket market",
                        condition_id=condition_id,
                        error=str(e))
            return None

    @retry_with_backoff(max_retries=3)
    async def get_orderbook(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current orderbook for a market.

        Args:
            token_id: Token ID (outcome)

        Returns:
            Orderbook data with bids and asks
        """
        # Return mock orderbook in paper trading mode
        if settings.paper_trading_mode:
            logger.debug("Paper trading mode - returning mock orderbook",
                        token_id=token_id)
            # Orderbook format: list of [price, size]
            return {
                'bids': [
                    [0.48, 1000],  # Price 0.48, size 1000
                    [0.47, 2000],
                    [0.46, 5000]
                ],
                'asks': [
                    [0.52, 1000],  # Price 0.52, size 1000
                    [0.53, 2000],
                    [0.54, 5000]
                ]
            }

        try:
            url = f"{self.base_url}/book"
            params = {"token_id": token_id}

            async with self.session.get(
                url,
                headers=self._get_headers(),
                params=params
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("Failed to fetch Polymarket orderbook",
                               token_id=token_id,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error fetching Polymarket orderbook",
                        token_id=token_id,
                        error=str(e))
            return None

    @retry_with_backoff(max_retries=3)
    async def get_prices(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current prices for a token.

        Args:
            token_id: Token ID

        Returns:
            Price data dictionary
        """
        try:
            url = f"{self.base_url}/price"
            params = {"token_id": token_id}

            async with self.session.get(
                url,
                headers=self._get_headers(),
                params=params
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("Failed to fetch Polymarket prices",
                               token_id=token_id,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error fetching Polymarket prices",
                        token_id=token_id,
                        error=str(e))
            return None

    async def place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float,
        order_type: str = "GTC"
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order on Polymarket.

        Args:
            token_id: Token ID to trade
            side: "BUY" or "SELL"
            size: Order size (in dollars)
            price: Limit price (0-1)
            order_type: "GTC" (Good Till Cancel) or "FOK" (Fill or Kill)

        Returns:
            Order response dictionary or None
        """
        try:
            url = f"{self.base_url}/order"

            # Note: In production, this would require proper signing with private key
            payload = {
                "tokenID": token_id,
                "side": side.upper(),
                "size": str(size),
                "price": str(price),
                "orderType": order_type,
                "maker": self.api_key  # Wallet address
            }

            # TODO: Sign the order with private key
            # This is a simplified version - production needs proper EIP-712 signing

            async with self.session.post(
                url,
                headers=self._get_headers(),
                json=payload
            ) as response:
                if response.status in [200, 201]:
                    data = await response.json()
                    logger.info("Polymarket order placed",
                              order_id=data.get('orderID'),
                              token_id=token_id,
                              side=side)
                    return data
                else:
                    error_text = await response.text()
                    logger.error("Failed to place Polymarket order",
                               status=response.status,
                               error=error_text)
                    return None

        except Exception as e:
            logger.error("Error placing Polymarket order", error=str(e))
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
            url = f"{self.base_url}/order"
            payload = {"orderID": order_id}

            async with self.session.delete(
                url,
                headers=self._get_headers(),
                json=payload
            ) as response:
                if response.status == 200:
                    logger.info("Polymarket order cancelled", order_id=order_id)
                    return True
                else:
                    logger.error("Failed to cancel Polymarket order",
                               order_id=order_id,
                               status=response.status)
                    return False

        except Exception as e:
            logger.error("Error cancelling Polymarket order",
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
            url = f"{self.base_url}/order/{order_id}"

            async with self.session.get(
                url,
                headers=self._get_headers()
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error("Failed to get Polymarket order status",
                               order_id=order_id,
                               status=response.status)
                    return None

        except Exception as e:
            logger.error("Error getting Polymarket order status",
                        order_id=order_id,
                        error=str(e))
            return None

    def parse_market_to_event(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Polymarket market data to standardized event format.

        Args:
            market: Raw market data from Polymarket API

        Returns:
            Standardized event dictionary
        """
        # Polymarket markets typically have multiple outcomes
        # For binary markets, we'll use the first two outcomes
        outcomes = market.get('outcomes', [])

        # Get current prices
        outcome_prices = market.get('outcomePrices', [])
        yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
        no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else (1 - yes_price)

        # Parse close_time and remove timezone info for database compatibility
        close_time = None
        if market.get('end_date_iso'):
            try:
                # Parse and convert to naive datetime
                dt = datetime.fromisoformat(
                    market.get('end_date_iso', '').replace('Z', '+00:00')
                )
                close_time = dt.replace(tzinfo=None)  # Remove timezone
            except:
                pass

        return {
            'event_id': market.get('condition_id', market.get('id')),
            'title': market.get('question', market.get('title', '')),
            'url': f"https://polymarket.com/market/{market.get('slug', '')}",
            'close_time': close_time,
            'yes_price': yes_price,
            'no_price': no_price,
            'liquidity': float(market.get('volume', 0)),
            'token_ids': [outcome.get('token_id') for outcome in outcomes]
        }
