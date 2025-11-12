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
        try:
            url = f"{self.base_url}/markets"
            params = {
                "closed": str(closed).lower(),
                "limit": 200
            }

            logger.debug("Fetching Polymarket markets", url=url, params=params)

            async with self.session.get(
                url,
                headers=self._get_headers(),
                params=params
            ) as response:
                response_text = await response.text()
                logger.debug("Polymarket API response",
                           status=response.status,
                           response_length=len(response_text),
                           response_preview=response_text[:500])

                if response.status == 200:
                    try:
                        import json
                        markets = json.loads(response_text)
                        logger.info("Successfully fetched Polymarket markets", count=len(markets))
                        return markets
                    except Exception as json_error:
                        logger.error("Failed to parse Polymarket JSON response",
                                   error=str(json_error),
                                   response=response_text[:500])
                        return []
                else:
                    logger.error("Failed to fetch Polymarket markets",
                               status=response.status,
                               url=url,
                               error=response_text[:500])
                    return []

        except Exception as e:
            logger.error("Error fetching Polymarket markets",
                        error=str(e),
                        url=f"{self.base_url}/markets")
            return []

    @retry_with_backoff(max_retries=3)
    async def get_market(self, condition_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details for a specific market.

        Args:
            condition_id: Market condition ID

        Returns:
            Market details dictionary or None
        """
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
