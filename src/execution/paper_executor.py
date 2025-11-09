"""
Paper trading executor for simulating trades without real money.
"""
import asyncio
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
from sqlalchemy import select

from src.database import (
    db_manager, VerifiedPair, Order, OrderStatus, OrderSide,
    Exchange, ArbitrageOpportunity
)
from src.arbitrage.detector import ArbitrageStrategy
from config.settings import settings

logger = structlog.get_logger()


class PaperTradingStats:
    """Track paper trading statistics."""

    def __init__(self):
        self.starting_balance = settings.paper_starting_balance
        self.current_balance = settings.paper_starting_balance
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.total_pnl = 0.0
        self.trades_history: List[Dict] = []
        self.session_start = datetime.utcnow()

    def record_trade(
        self,
        pair_id: int,
        strategy: str,
        profit: float,
        success: bool
    ):
        """Record a paper trade."""
        self.total_trades += 1
        if success:
            self.successful_trades += 1
            self.total_pnl += profit
            self.current_balance += profit
        else:
            self.failed_trades += 1

        self.trades_history.append({
            'timestamp': datetime.utcnow(),
            'pair_id': pair_id,
            'strategy': strategy,
            'profit': profit,
            'success': success,
            'balance': self.current_balance
        })

        logger.info(
            "Paper trade recorded",
            pair_id=pair_id,
            profit=profit,
            success=success,
            total_pnl=self.total_pnl,
            balance=self.current_balance
        )

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        win_rate = (
            (self.successful_trades / self.total_trades * 100)
            if self.total_trades > 0
            else 0
        )

        runtime = datetime.utcnow() - self.session_start
        avg_profit = (
            self.total_pnl / self.successful_trades
            if self.successful_trades > 0
            else 0
        )

        return {
            'starting_balance': self.starting_balance,
            'current_balance': self.current_balance,
            'total_pnl': self.total_pnl,
            'total_trades': self.total_trades,
            'successful_trades': self.successful_trades,
            'failed_trades': self.failed_trades,
            'win_rate': win_rate,
            'avg_profit_per_trade': avg_profit,
            'runtime_seconds': runtime.total_seconds(),
            'session_start': self.session_start
        }


class PaperTradingExecutor:
    """
    Simulates arbitrage trades without placing real orders.
    Tracks virtual positions and PnL for testing.
    """

    def __init__(self):
        """Initialize paper trading executor."""
        self.stats = PaperTradingStats()
        self.simulated_slippage = settings.paper_simulated_slippage
        self.partial_fill_chance = settings.paper_partial_fill_chance

    async def execute_arbitrage(
        self,
        pair: VerifiedPair,
        strategy: ArbitrageStrategy,
        opportunity: ArbitrageOpportunity,
        size_usd: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Simulate an arbitrage trade execution.

        Args:
            pair: VerifiedPair object
            strategy: ArbitrageStrategy to execute
            opportunity: ArbitrageOpportunity record
            size_usd: Trade size in USD (defaults to settings.max_trade_size)

        Returns:
            Tuple of (success: bool, message: str)
        """
        if size_usd is None:
            size_usd = settings.max_trade_size

        logger.info(
            "PAPER TRADING: Simulating arbitrage trade",
            pair_id=pair.id,
            opportunity_id=opportunity.id,
            strategy=strategy.strategy_type,
            size_usd=size_usd,
            mode="PAPER"
        )

        try:
            # Check if we have enough balance
            if self.stats.current_balance < size_usd:
                message = f"Insufficient paper trading balance: ${self.stats.current_balance:.2f} < ${size_usd:.2f}"
                logger.warning(message)
                self.stats.record_trade(
                    pair_id=pair.id,
                    strategy=strategy.strategy_type,
                    profit=0.0,
                    success=False
                )
                return False, message

            # Update opportunity to mark execution started
            async with db_manager.session() as session:
                stmt = select(ArbitrageOpportunity).where(
                    ArbitrageOpportunity.id == opportunity.id
                )
                result = await session.execute(stmt)
                opp = result.scalar_one()
                opp.execution_started_at = datetime.utcnow()

            # Simulate order placement on Kalshi
            kalshi_order = await self._simulate_kalshi_order(
                pair=pair,
                opportunity_id=opportunity.id,
                side=strategy.kalshi_side,
                price=strategy.kalshi_price,
                size_usd=size_usd
            )

            # Simulate small delay
            await asyncio.sleep(0.1)

            # Simulate order placement on Polymarket
            polymarket_order = await self._simulate_polymarket_order(
                pair=pair,
                opportunity_id=opportunity.id,
                side=strategy.polymarket_side,
                price=strategy.polymarket_price,
                size_usd=size_usd
            )

            # Simulate fill processing
            await asyncio.sleep(0.2)

            # Calculate simulated results
            success, profit, message = await self._simulate_fills(
                kalshi_order=kalshi_order,
                polymarket_order=polymarket_order,
                strategy=strategy,
                size_usd=size_usd
            )

            # Mark opportunity as executed
            async with db_manager.session() as session:
                stmt = select(ArbitrageOpportunity).where(
                    ArbitrageOpportunity.id == opportunity.id
                )
                result = await session.execute(stmt)
                opp = result.scalar_one()
                opp.executed = True
                opp.execution_completed_at = datetime.utcnow()
                opp.realized_pnl = profit

            # Record trade in stats
            self.stats.record_trade(
                pair_id=pair.id,
                strategy=strategy.strategy_type,
                profit=profit,
                success=success
            )

            logger.info(
                "PAPER TRADING: Trade simulation completed",
                opportunity_id=opportunity.id,
                success=success,
                profit=profit,
                message=message,
                mode="PAPER"
            )

            return success, message

        except Exception as e:
            logger.error(
                "PAPER TRADING: Error simulating trade",
                opportunity_id=opportunity.id,
                error=str(e),
                mode="PAPER"
            )
            return False, f"Simulation error: {str(e)}"

    async def _simulate_kalshi_order(
        self,
        pair: VerifiedPair,
        opportunity_id: int,
        side: str,
        price: float,
        size_usd: float
    ) -> Order:
        """Simulate placing an order on Kalshi."""
        # Generate fake order ID
        order_id = f"PAPER_KALSHI_{datetime.utcnow().timestamp()}"

        # Apply simulated slippage
        slippage_factor = random.uniform(0, self.simulated_slippage)
        actual_price = price * (1 + slippage_factor)

        async with db_manager.session() as session:
            order = Order(
                pair_id=pair.id,
                opportunity_id=opportunity_id,
                exchange=Exchange.KALSHI,
                order_id=order_id,
                side=OrderSide.YES if side == "yes" else OrderSide.NO,
                size=size_usd,
                filled_size=0.0,
                price=actual_price,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.utcnow()
            )
            session.add(order)
            await session.flush()
            await session.refresh(order)

            logger.info(
                "PAPER TRADING: Simulated Kalshi order",
                order_id=order.id,
                side=side,
                price=actual_price,
                slippage=slippage_factor,
                mode="PAPER"
            )

            return order

    async def _simulate_polymarket_order(
        self,
        pair: VerifiedPair,
        opportunity_id: int,
        side: str,
        price: float,
        size_usd: float
    ) -> Order:
        """Simulate placing an order on Polymarket."""
        # Generate fake order ID
        order_id = f"PAPER_POLY_{datetime.utcnow().timestamp()}"

        # Apply simulated slippage
        slippage_factor = random.uniform(0, self.simulated_slippage)
        actual_price = price * (1 + slippage_factor)

        async with db_manager.session() as session:
            order = Order(
                pair_id=pair.id,
                opportunity_id=opportunity_id,
                exchange=Exchange.POLYMARKET,
                order_id=order_id,
                side=OrderSide.YES if side == "BUY" else OrderSide.NO,
                size=size_usd,
                filled_size=0.0,
                price=actual_price,
                status=OrderStatus.SUBMITTED,
                submitted_at=datetime.utcnow()
            )
            session.add(order)
            await session.flush()
            await session.refresh(order)

            logger.info(
                "PAPER TRADING: Simulated Polymarket order",
                order_id=order.id,
                side=side,
                price=actual_price,
                slippage=slippage_factor,
                mode="PAPER"
            )

            return order

    async def _simulate_fills(
        self,
        kalshi_order: Order,
        polymarket_order: Order,
        strategy: ArbitrageStrategy,
        size_usd: float
    ) -> Tuple[bool, float, str]:
        """
        Simulate order fills and calculate PnL.

        Returns:
            Tuple of (success: bool, profit: float, message: str)
        """
        # Determine if we get partial fills
        kalshi_filled = size_usd
        polymarket_filled = size_usd

        # Randomly apply partial fills
        if random.random() < self.partial_fill_chance:
            fill_pct = random.uniform(0.7, 0.95)
            kalshi_filled = size_usd * fill_pct
            logger.info(
                "PAPER TRADING: Simulating partial fill on Kalshi",
                fill_pct=fill_pct,
                mode="PAPER"
            )

        if random.random() < self.partial_fill_chance:
            fill_pct = random.uniform(0.7, 0.95)
            polymarket_filled = size_usd * fill_pct
            logger.info(
                "PAPER TRADING: Simulating partial fill on Polymarket",
                fill_pct=fill_pct,
                mode="PAPER"
            )

        # Update orders with fill information
        async with db_manager.session() as session:
            # Update Kalshi order
            stmt = select(Order).where(Order.id == kalshi_order.id)
            result = await session.execute(stmt)
            k_order = result.scalar_one()
            k_order.filled_size = kalshi_filled
            k_order.avg_fill_price = kalshi_order.price
            k_order.status = OrderStatus.FILLED if kalshi_filled >= size_usd * 0.99 else OrderStatus.PARTIAL
            k_order.filled_at = datetime.utcnow()

            # Update Polymarket order
            stmt = select(Order).where(Order.id == polymarket_order.id)
            result = await session.execute(stmt)
            p_order = result.scalar_one()
            p_order.filled_size = polymarket_filled
            p_order.avg_fill_price = polymarket_order.price
            p_order.status = OrderStatus.FILLED if polymarket_filled >= size_usd * 0.99 else OrderStatus.PARTIAL
            p_order.filled_at = datetime.utcnow()

        # Calculate profit based on filled amounts
        filled_amount = min(kalshi_filled, polymarket_filled)

        # Cost to open both positions
        total_cost = (kalshi_order.price + polymarket_order.price) * filled_amount

        # Payoff is always 1 for binary markets (in paper trading, we assume market resolves correctly)
        guaranteed_payoff = filled_amount

        # Gross profit
        gross_profit = guaranteed_payoff - total_cost

        # Simulate fees (3% total)
        fees = total_cost * 0.03

        # Net profit
        net_profit = gross_profit - fees

        # Check for successful execution
        imbalance = abs(kalshi_filled - polymarket_filled)
        success = imbalance < size_usd * 0.1  # Less than 10% imbalance

        if success:
            message = (
                f"PAPER TRADE SUCCESS: Filled ${filled_amount:.2f} on both sides. "
                f"Profit: ${net_profit:.2f}"
            )
        else:
            # Apply penalty for imbalance in paper trading
            penalty = imbalance * 0.1
            net_profit -= penalty
            message = (
                f"PAPER TRADE PARTIAL: Imbalanced fills "
                f"(K:${kalshi_filled:.2f}, P:${polymarket_filled:.2f}). "
                f"Profit after penalty: ${net_profit:.2f}"
            )

        return success, net_profit, message

    def get_stats(self) -> Dict:
        """Get current paper trading statistics."""
        return self.stats.get_summary()

    def reset_stats(self):
        """Reset paper trading statistics."""
        logger.info("Resetting paper trading statistics", mode="PAPER")
        self.stats = PaperTradingStats()
