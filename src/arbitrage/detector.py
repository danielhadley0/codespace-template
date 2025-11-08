"""
Arbitrage detection engine for identifying profitable opportunities.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import structlog
from sqlalchemy import select

from src.database import db_manager, VerifiedPair, ArbitrageOpportunity, Event, Exchange
from src.api import KalshiClient, PolymarketClient
from config.settings import settings

logger = structlog.get_logger()


@dataclass
class ArbitrageStrategy:
    """Represents an arbitrage strategy."""
    strategy_type: str  # "kalshi_yes_polymarket_no" or "kalshi_no_polymarket_yes"
    kalshi_side: str  # "yes" or "no"
    polymarket_side: str  # "BUY" or "SELL"
    kalshi_price: float
    polymarket_price: float
    spread: float
    expected_profit: float


class ArbitrageDetector:
    """
    Detects arbitrage opportunities between verified event pairs.
    """

    def __init__(
        self,
        kalshi_client: KalshiClient,
        polymarket_client: PolymarketClient
    ):
        """
        Initialize arbitrage detector.

        Args:
            kalshi_client: Kalshi API client
            polymarket_client: Polymarket API client
        """
        self.kalshi_client = kalshi_client
        self.polymarket_client = polymarket_client
        self.min_threshold = settings.min_arbitrage_threshold
        self.price_cache: Dict[int, Dict] = {}  # pair_id -> price data

    async def detect_arbitrage(
        self,
        pair: VerifiedPair
    ) -> Optional[ArbitrageStrategy]:
        """
        Check for arbitrage opportunity in a verified pair.

        Args:
            pair: VerifiedPair object with kalshi and polymarket events

        Returns:
            ArbitrageStrategy if opportunity exists, None otherwise
        """
        try:
            # Fetch current prices for both markets
            kalshi_prices, polymarket_prices = await asyncio.gather(
                self._get_kalshi_prices(pair.kalshi_event.event_id),
                self._get_polymarket_prices(pair.polymarket_event.event_id)
            )

            if not kalshi_prices or not polymarket_prices:
                logger.debug(
                    "Failed to fetch prices for pair",
                    pair_id=pair.id
                )
                return None

            # Cache prices
            self.price_cache[pair.id] = {
                'kalshi': kalshi_prices,
                'polymarket': polymarket_prices,
                'timestamp': datetime.utcnow()
            }

            # Calculate arbitrage opportunities
            # Strategy 1: Buy YES on Kalshi, Buy NO on Polymarket
            strategy1 = self._calculate_strategy(
                "kalshi_yes_polymarket_no",
                kalshi_prices['yes'],
                polymarket_prices['no'],
                "yes",
                "BUY"
            )

            # Strategy 2: Buy NO on Kalshi, Buy YES on Polymarket
            strategy2 = self._calculate_strategy(
                "kalshi_no_polymarket_yes",
                kalshi_prices['no'],
                polymarket_prices['yes'],
                "no",
                "BUY"
            )

            # Choose the better strategy
            best_strategy = None
            if strategy1 and strategy2:
                best_strategy = strategy1 if strategy1.spread > strategy2.spread else strategy2
            elif strategy1:
                best_strategy = strategy1
            elif strategy2:
                best_strategy = strategy2

            if best_strategy and best_strategy.spread >= self.min_threshold:
                logger.info(
                    "Arbitrage opportunity detected",
                    pair_id=pair.id,
                    strategy=best_strategy.strategy_type,
                    spread=best_strategy.spread,
                    expected_profit=best_strategy.expected_profit
                )
                return best_strategy

            return None

        except Exception as e:
            logger.error(
                "Error detecting arbitrage",
                pair_id=pair.id,
                error=str(e)
            )
            return None

    def _calculate_strategy(
        self,
        strategy_type: str,
        kalshi_price: float,
        polymarket_price: float,
        kalshi_side: str,
        polymarket_side: str
    ) -> Optional[ArbitrageStrategy]:
        """
        Calculate arbitrage metrics for a strategy.

        The arbitrage condition for binary markets:
        - Buy YES on Kalshi + Buy NO on Polymarket = guaranteed profit if total cost < 1
        - Buy NO on Kalshi + Buy YES on Polymarket = guaranteed profit if total cost < 1

        Args:
            strategy_type: Strategy identifier
            kalshi_price: Price on Kalshi (0-1)
            polymarket_price: Price on Polymarket (0-1)
            kalshi_side: Side to trade on Kalshi
            polymarket_side: Side to trade on Polymarket

        Returns:
            ArbitrageStrategy if profitable, None otherwise
        """
        # Total cost to open both positions
        total_cost = kalshi_price + polymarket_price

        # Payoff is always 1 for binary markets (one side pays out 1, other pays 0)
        guaranteed_payoff = 1.0

        # Profit before fees
        gross_profit = guaranteed_payoff - total_cost

        # Estimate fees (typically 2-3% per side, total ~5%)
        # Kalshi: ~1% fee, Polymarket: ~2% fee
        estimated_fees = 0.03 * total_cost

        # Net profit after fees
        net_profit = gross_profit - estimated_fees

        # Spread as percentage
        spread = net_profit / total_cost if total_cost > 0 else 0

        # Expected profit on $100 position
        expected_profit_usd = net_profit * settings.max_trade_size

        if spread > 0:  # Any positive spread is theoretically profitable
            return ArbitrageStrategy(
                strategy_type=strategy_type,
                kalshi_side=kalshi_side,
                polymarket_side=polymarket_side,
                kalshi_price=kalshi_price,
                polymarket_price=polymarket_price,
                spread=spread,
                expected_profit=expected_profit_usd
            )

        return None

    async def _get_kalshi_prices(self, market_ticker: str) -> Optional[Dict[str, float]]:
        """
        Get current prices from Kalshi market.

        Args:
            market_ticker: Kalshi market ticker

        Returns:
            Dictionary with 'yes' and 'no' prices or None
        """
        try:
            orderbook = await self.kalshi_client.get_orderbook(market_ticker)
            if not orderbook:
                return None

            # Get best bid prices
            yes_bids = orderbook.get('yes', [])
            no_bids = orderbook.get('no', [])

            yes_price = yes_bids[0][0] / 100.0 if yes_bids else 0.5
            no_price = no_bids[0][0] / 100.0 if no_bids else 0.5

            return {
                'yes': yes_price,
                'no': no_price
            }

        except Exception as e:
            logger.error(
                "Error fetching Kalshi prices",
                ticker=market_ticker,
                error=str(e)
            )
            return None

    async def _get_polymarket_prices(self, condition_id: str) -> Optional[Dict[str, float]]:
        """
        Get current prices from Polymarket market.

        Args:
            condition_id: Polymarket condition ID

        Returns:
            Dictionary with 'yes' and 'no' prices or None
        """
        try:
            market = await self.polymarket_client.get_market(condition_id)
            if not market:
                return None

            # Get outcome prices
            outcome_prices = market.get('outcomePrices', [])

            yes_price = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
            no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else (1 - yes_price)

            return {
                'yes': yes_price,
                'no': no_price
            }

        except Exception as e:
            logger.error(
                "Error fetching Polymarket prices",
                condition_id=condition_id,
                error=str(e)
            )
            return None

    async def monitor_pairs(self, pairs: List[VerifiedPair]) -> List[Tuple[VerifiedPair, ArbitrageStrategy]]:
        """
        Monitor multiple pairs for arbitrage opportunities.

        Args:
            pairs: List of verified pairs to monitor

        Returns:
            List of tuples (pair, strategy) for detected opportunities
        """
        opportunities = []

        # Check all pairs concurrently
        tasks = [self.detect_arbitrage(pair) for pair in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pair, result in zip(pairs, results):
            if isinstance(result, Exception):
                logger.error(
                    "Error monitoring pair",
                    pair_id=pair.id,
                    error=str(result)
                )
                continue

            if result is not None:  # ArbitrageStrategy found
                opportunities.append((pair, result))

        return opportunities

    async def log_opportunity(
        self,
        pair: VerifiedPair,
        strategy: ArbitrageStrategy,
        executed: bool = False
    ) -> ArbitrageOpportunity:
        """
        Log an arbitrage opportunity to the database.

        Args:
            pair: VerifiedPair object
            strategy: ArbitrageStrategy object
            executed: Whether the opportunity was executed

        Returns:
            Created ArbitrageOpportunity object
        """
        async with db_manager.session() as session:
            # Get cached prices
            cached_prices = self.price_cache.get(pair.id, {})
            kalshi_prices = cached_prices.get('kalshi', {'yes': 0, 'no': 0})
            polymarket_prices = cached_prices.get('polymarket', {'yes': 0, 'no': 0})

            opportunity = ArbitrageOpportunity(
                pair_id=pair.id,
                timestamp=datetime.utcnow(),
                kalshi_yes_price=kalshi_prices['yes'],
                kalshi_no_price=kalshi_prices['no'],
                polymarket_yes_price=polymarket_prices['yes'],
                polymarket_no_price=polymarket_prices['no'],
                spread=strategy.spread,
                strategy=strategy.strategy_type,
                expected_profit=strategy.expected_profit,
                executed=executed
            )

            session.add(opportunity)
            await session.flush()
            await session.refresh(opportunity)

            logger.info(
                "Arbitrage opportunity logged",
                opportunity_id=opportunity.id,
                pair_id=pair.id,
                strategy=strategy.strategy_type
            )

            return opportunity
