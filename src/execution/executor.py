"""
Trade execution engine for placing and managing orders.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import structlog
from sqlalchemy import select

from src.database import (
    db_manager, VerifiedPair, Order, OrderStatus, OrderSide,
    Exchange, ArbitrageOpportunity
)
from src.api import KalshiClient, PolymarketClient
from src.arbitrage.detector import ArbitrageStrategy
from config.settings import settings

logger = structlog.get_logger()


class TradeExecutor:
    """
    Executes arbitrage trades across both platforms with partial fill management.
    """

    def __init__(
        self,
        kalshi_client: KalshiClient,
        polymarket_client: PolymarketClient
    ):
        """
        Initialize trade executor.

        Args:
            kalshi_client: Kalshi API client
            polymarket_client: Polymarket API client
        """
        self.kalshi_client = kalshi_client
        self.polymarket_client = polymarket_client
        self.active_orders: Dict[int, List[Order]] = {}  # opportunity_id -> orders

    async def execute_arbitrage(
        self,
        pair: VerifiedPair,
        strategy: ArbitrageStrategy,
        opportunity: ArbitrageOpportunity,
        size_usd: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Execute an arbitrage trade across both platforms.

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
            "Executing arbitrage trade",
            pair_id=pair.id,
            opportunity_id=opportunity.id,
            strategy=strategy.strategy_type,
            size_usd=size_usd
        )

        try:
            # Update opportunity to mark execution started
            async with db_manager.session() as session:
                stmt = select(ArbitrageOpportunity).where(
                    ArbitrageOpportunity.id == opportunity.id
                )
                result = await session.execute(stmt)
                opp = result.scalar_one()
                opp.execution_started_at = datetime.utcnow()

            # Phase 1: Place order on better liquidity side (typically Kalshi first)
            kalshi_order = await self._place_kalshi_order(
                pair=pair,
                opportunity_id=opportunity.id,
                side=strategy.kalshi_side,
                price=strategy.kalshi_price,
                size_usd=size_usd
            )

            if not kalshi_order:
                return False, "Failed to place Kalshi order"

            # Wait a moment for fill
            await asyncio.sleep(1)

            # Check fill status
            kalshi_status = await self.kalshi_client.get_order_status(
                kalshi_order.order_id
            )

            if not kalshi_status:
                await self._cancel_order(kalshi_order)
                return False, "Failed to get Kalshi order status"

            # Update order with fill information
            await self._update_order_status(kalshi_order, kalshi_status)

            # Phase 2: Place hedge order on Polymarket
            polymarket_order = await self._place_polymarket_order(
                pair=pair,
                opportunity_id=opportunity.id,
                side=strategy.polymarket_side,
                price=strategy.polymarket_price,
                size_usd=size_usd
            )

            if not polymarket_order:
                # Failed to place hedge - need to unwind Kalshi position
                logger.error(
                    "Failed to place Polymarket order, unwinding Kalshi position",
                    kalshi_order_id=kalshi_order.id
                )
                await self._unwind_position(kalshi_order)
                return False, "Failed to place Polymarket hedge order"

            # Wait for Polymarket fill
            await asyncio.sleep(1)

            # Check Polymarket fill status
            polymarket_status = await self.polymarket_client.get_order_status(
                polymarket_order.order_id
            )

            if polymarket_status:
                await self._update_order_status(polymarket_order, polymarket_status)

            # Manage partial fills
            success = await self._manage_partial_fills(
                kalshi_order=kalshi_order,
                polymarket_order=polymarket_order,
                target_size=size_usd
            )

            if success:
                # Mark opportunity as executed
                async with db_manager.session() as session:
                    stmt = select(ArbitrageOpportunity).where(
                        ArbitrageOpportunity.id == opportunity.id
                    )
                    result = await session.execute(stmt)
                    opp = result.scalar_one()
                    opp.executed = True
                    opp.execution_completed_at = datetime.utcnow()

                logger.info(
                    "Arbitrage trade executed successfully",
                    opportunity_id=opportunity.id
                )
                return True, "Trade executed successfully"
            else:
                return False, "Partial fill management failed"

        except Exception as e:
            logger.error(
                "Error executing arbitrage trade",
                opportunity_id=opportunity.id,
                error=str(e)
            )
            return False, f"Execution error: {str(e)}"

    async def _place_kalshi_order(
        self,
        pair: VerifiedPair,
        opportunity_id: int,
        side: str,
        price: float,
        size_usd: float
    ) -> Optional[Order]:
        """Place an order on Kalshi."""
        try:
            # Convert USD to contracts (Kalshi uses cents)
            # If buying at price P, you get 1 contract for P dollars
            # So for size_usd dollars, you can buy size_usd/price contracts
            quantity_contracts = int((size_usd / price) * 100)  # Convert to cents

            # Place order via API
            response = await self.kalshi_client.place_order(
                market_ticker=pair.kalshi_event.event_id,
                side=side,
                quantity=quantity_contracts,
                price=int(price * 100)  # Convert to cents
            )

            if not response:
                return None

            # Create order record
            async with db_manager.session() as session:
                order = Order(
                    pair_id=pair.id,
                    opportunity_id=opportunity_id,
                    exchange=Exchange.KALSHI,
                    order_id=response.get('order_id'),
                    side=OrderSide.YES if side == "yes" else OrderSide.NO,
                    size=size_usd,
                    filled_size=0.0,
                    price=price,
                    status=OrderStatus.SUBMITTED,
                    submitted_at=datetime.utcnow()
                )
                session.add(order)
                await session.flush()
                await session.refresh(order)

                logger.info(
                    "Kalshi order placed",
                    order_id=order.id,
                    exchange_order_id=order.order_id
                )

                return order

        except Exception as e:
            logger.error(
                "Error placing Kalshi order",
                error=str(e)
            )
            return None

    async def _place_polymarket_order(
        self,
        pair: VerifiedPair,
        opportunity_id: int,
        side: str,
        price: float,
        size_usd: float
    ) -> Optional[Order]:
        """Place an order on Polymarket."""
        try:
            # Get token ID for the market
            # This is simplified - in production you'd need to track token IDs
            token_id = pair.polymarket_event.event_id

            # Place order via API
            response = await self.polymarket_client.place_order(
                token_id=token_id,
                side=side,
                size=size_usd,
                price=price
            )

            if not response:
                return None

            # Create order record
            async with db_manager.session() as session:
                order = Order(
                    pair_id=pair.id,
                    opportunity_id=opportunity_id,
                    exchange=Exchange.POLYMARKET,
                    order_id=response.get('orderID'),
                    side=OrderSide.YES if side == "BUY" else OrderSide.NO,
                    size=size_usd,
                    filled_size=0.0,
                    price=price,
                    status=OrderStatus.SUBMITTED,
                    submitted_at=datetime.utcnow()
                )
                session.add(order)
                await session.flush()
                await session.refresh(order)

                logger.info(
                    "Polymarket order placed",
                    order_id=order.id,
                    exchange_order_id=order.order_id
                )

                return order

        except Exception as e:
            logger.error(
                "Error placing Polymarket order",
                error=str(e)
            )
            return None

    async def _update_order_status(
        self,
        order: Order,
        status_data: Dict
    ):
        """Update order with fill information from exchange."""
        try:
            async with db_manager.session() as session:
                stmt = select(Order).where(Order.id == order.id)
                result = await session.execute(stmt)
                db_order = result.scalar_one()

                # Parse status based on exchange
                if order.exchange == Exchange.KALSHI:
                    filled_qty = status_data.get('filled_count', 0)
                    total_qty = status_data.get('count', 0)
                    fill_price = status_data.get('filled_price', 0) / 100.0

                    db_order.filled_size = (filled_qty / total_qty) * order.size if total_qty > 0 else 0
                    db_order.avg_fill_price = fill_price

                    if filled_qty == total_qty:
                        db_order.status = OrderStatus.FILLED
                        db_order.filled_at = datetime.utcnow()
                    elif filled_qty > 0:
                        db_order.status = OrderStatus.PARTIAL
                    else:
                        db_order.status = OrderStatus.PENDING

                elif order.exchange == Exchange.POLYMARKET:
                    filled_size = float(status_data.get('sizeFilled', 0))
                    total_size = float(status_data.get('size', 0))
                    fill_price = float(status_data.get('price', 0))

                    db_order.filled_size = filled_size
                    db_order.avg_fill_price = fill_price

                    if filled_size >= total_size * 0.99:  # Allow 1% tolerance
                        db_order.status = OrderStatus.FILLED
                        db_order.filled_at = datetime.utcnow()
                    elif filled_size > 0:
                        db_order.status = OrderStatus.PARTIAL
                    else:
                        db_order.status = OrderStatus.PENDING

                logger.debug(
                    "Order status updated",
                    order_id=order.id,
                    status=db_order.status,
                    filled_size=db_order.filled_size
                )

        except Exception as e:
            logger.error(
                "Error updating order status",
                order_id=order.id,
                error=str(e)
            )

    async def _manage_partial_fills(
        self,
        kalshi_order: Order,
        polymarket_order: Order,
        target_size: float
    ) -> bool:
        """
        Manage partial fills and attempt to balance positions.

        Args:
            kalshi_order: Kalshi order
            polymarket_order: Polymarket order
            target_size: Target position size

        Returns:
            True if positions are balanced, False otherwise
        """
        timeout = datetime.utcnow() + timedelta(seconds=settings.order_timeout_seconds)

        while datetime.utcnow() < timeout:
            # Refresh order statuses
            async with db_manager.session() as session:
                # Get latest Kalshi order
                stmt = select(Order).where(Order.id == kalshi_order.id)
                result = await session.execute(stmt)
                k_order = result.scalar_one()

                # Get latest Polymarket order
                stmt = select(Order).where(Order.id == polymarket_order.id)
                result = await session.execute(stmt)
                p_order = result.scalar_one()

                # Check if both are fully filled
                if (k_order.status == OrderStatus.FILLED and
                    p_order.status == OrderStatus.FILLED):
                    logger.info(
                        "Both orders fully filled",
                        kalshi_order_id=k_order.id,
                        polymarket_order_id=p_order.id
                    )
                    return True

                # Check for imbalance
                fill_diff = abs(k_order.filled_size - p_order.filled_size)
                if fill_diff > target_size * 0.1:  # More than 10% imbalance
                    logger.warning(
                        "Order fill imbalance detected",
                        kalshi_filled=k_order.filled_size,
                        polymarket_filled=p_order.filled_size,
                        difference=fill_diff
                    )

                    # Attempt to fill the lagging side
                    # This is simplified - production would place additional orders
                    await asyncio.sleep(2)
                else:
                    # Acceptable imbalance, continue monitoring
                    await asyncio.sleep(1)

        # Timeout reached
        logger.error(
            "Order timeout reached with partial fills",
            kalshi_order_id=kalshi_order.id,
            polymarket_order_id=polymarket_order.id
        )

        # Cancel any unfilled portions
        await self._cancel_order(kalshi_order)
        await self._cancel_order(polymarket_order)

        return False

    async def _cancel_order(self, order: Order) -> bool:
        """Cancel an order on the exchange."""
        try:
            if order.exchange == Exchange.KALSHI:
                success = await self.kalshi_client.cancel_order(order.order_id)
            elif order.exchange == Exchange.POLYMARKET:
                success = await self.polymarket_client.cancel_order(order.order_id)
            else:
                return False

            if success:
                async with db_manager.session() as session:
                    stmt = select(Order).where(Order.id == order.id)
                    result = await session.execute(stmt)
                    db_order = result.scalar_one()
                    db_order.status = OrderStatus.CANCELLED
                    db_order.cancelled_at = datetime.utcnow()

                logger.info("Order cancelled", order_id=order.id)

            return success

        except Exception as e:
            logger.error(
                "Error cancelling order",
                order_id=order.id,
                error=str(e)
            )
            return False

    async def _unwind_position(self, order: Order):
        """
        Unwind a position by placing an offsetting order.

        Args:
            order: Original order to unwind
        """
        logger.warning("Unwinding position", order_id=order.id)

        # This is simplified - production would place offsetting orders
        # to close the position at market price
        await self._cancel_order(order)
