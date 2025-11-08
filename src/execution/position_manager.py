"""
Position and PnL tracking.
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import structlog
from sqlalchemy import select, and_

from src.database import db_manager, Position, Order, OrderStatus, OrderSide, Exchange

logger = structlog.get_logger()


class PositionManager:
    """
    Manages positions and tracks PnL across both exchanges.
    """

    def __init__(self):
        """Initialize position manager."""
        self.positions_cache: Dict[str, Position] = {}  # (exchange, event_id, side) -> Position

    async def update_position_from_order(self, order: Order):
        """
        Update position based on a filled order.

        Args:
            order: Filled order to process
        """
        if order.status not in [OrderStatus.FILLED, OrderStatus.PARTIAL]:
            logger.debug(
                "Skipping position update for non-filled order",
                order_id=order.id,
                status=order.status
            )
            return

        try:
            async with db_manager.session() as session:
                # Find or create position
                stmt = select(Position).where(
                    and_(
                        Position.exchange == order.exchange,
                        Position.event_id == order.pair.kalshi_event_id
                        if order.exchange == Exchange.KALSHI
                        else order.pair.polymarket_event_id,
                        Position.side == order.side
                    )
                )
                result = await session.execute(stmt)
                position = result.scalar_one_or_none()

                if not position:
                    # Create new position
                    position = Position(
                        exchange=order.exchange,
                        event_id=(
                            order.pair.kalshi_event_id
                            if order.exchange == Exchange.KALSHI
                            else order.pair.polymarket_event_id
                        ),
                        side=order.side,
                        quantity=0.0,
                        avg_price=0.0,
                        realized_pnl=0.0,
                        unrealized_pnl=0.0,
                        opened_at=datetime.utcnow()
                    )
                    session.add(position)

                # Update position with order fill
                filled_qty = order.filled_size
                fill_price = order.avg_fill_price or order.price

                # Calculate new average price
                total_qty = position.quantity + filled_qty
                if total_qty > 0:
                    position.avg_price = (
                        (position.quantity * position.avg_price + filled_qty * fill_price)
                        / total_qty
                    )
                    position.quantity = total_qty
                else:
                    position.quantity = filled_qty
                    position.avg_price = fill_price

                position.updated_at = datetime.utcnow()

                logger.info(
                    "Position updated",
                    exchange=order.exchange.value,
                    event_id=position.event_id,
                    side=order.side.value,
                    quantity=position.quantity,
                    avg_price=position.avg_price
                )

        except Exception as e:
            logger.error(
                "Error updating position",
                order_id=order.id,
                error=str(e)
            )

    async def get_positions(
        self,
        exchange: Optional[Exchange] = None,
        active_only: bool = True
    ) -> List[Position]:
        """
        Get current positions.

        Args:
            exchange: Filter by exchange (None for all)
            active_only: Only return positions with quantity > 0

        Returns:
            List of Position objects
        """
        try:
            async with db_manager.session() as session:
                stmt = select(Position)

                if exchange:
                    stmt = stmt.where(Position.exchange == exchange)

                if active_only:
                    stmt = stmt.where(Position.quantity > 0)

                result = await session.execute(stmt)
                positions = result.scalars().all()

                return list(positions)

        except Exception as e:
            logger.error("Error getting positions", error=str(e))
            return []

    async def calculate_unrealized_pnl(
        self,
        position: Position,
        current_price: float
    ) -> float:
        """
        Calculate unrealized PnL for a position.

        Args:
            position: Position object
            current_price: Current market price

        Returns:
            Unrealized PnL amount
        """
        # For binary markets:
        # If holding YES at avg_price, current value is current_price per unit
        # PnL = (current_price - avg_price) * quantity
        unrealized_pnl = (current_price - position.avg_price) * position.quantity

        # Update position
        async with db_manager.session() as session:
            stmt = select(Position).where(Position.id == position.id)
            result = await session.execute(stmt)
            db_position = result.scalar_one()
            db_position.unrealized_pnl = unrealized_pnl
            db_position.updated_at = datetime.utcnow()

        return unrealized_pnl

    async def close_position(
        self,
        position: Position,
        close_price: float,
        quantity: Optional[float] = None
    ):
        """
        Close a position (fully or partially).

        Args:
            position: Position to close
            close_price: Price at which position is closed
            quantity: Quantity to close (None for full position)
        """
        close_qty = quantity if quantity is not None else position.quantity

        if close_qty > position.quantity:
            logger.error(
                "Cannot close more than position quantity",
                position_id=position.id,
                position_qty=position.quantity,
                close_qty=close_qty
            )
            return

        # Calculate realized PnL
        realized_pnl = (close_price - position.avg_price) * close_qty

        async with db_manager.session() as session:
            stmt = select(Position).where(Position.id == position.id)
            result = await session.execute(stmt)
            db_position = result.scalar_one()

            db_position.quantity -= close_qty
            db_position.realized_pnl += realized_pnl
            db_position.updated_at = datetime.utcnow()

            if db_position.quantity <= 0:
                db_position.closed_at = datetime.utcnow()

            logger.info(
                "Position closed",
                position_id=position.id,
                close_qty=close_qty,
                realized_pnl=realized_pnl,
                remaining_qty=db_position.quantity
            )

    async def get_total_pnl(self) -> Dict[str, float]:
        """
        Calculate total PnL across all positions.

        Returns:
            Dictionary with realized, unrealized, and total PnL
        """
        try:
            positions = await self.get_positions(active_only=False)

            total_realized = sum(p.realized_pnl for p in positions)
            total_unrealized = sum(p.unrealized_pnl for p in positions)

            return {
                'realized_pnl': total_realized,
                'unrealized_pnl': total_unrealized,
                'total_pnl': total_realized + total_unrealized
            }

        except Exception as e:
            logger.error("Error calculating total PnL", error=str(e))
            return {
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'total_pnl': 0.0
            }

    async def get_exposure_by_market(self, event_id: int) -> Dict[str, float]:
        """
        Calculate total exposure for a specific market.

        Args:
            event_id: Event ID

        Returns:
            Dictionary with exposure by exchange
        """
        try:
            async with db_manager.session() as session:
                stmt = select(Position).where(
                    Position.event_id == event_id,
                    Position.quantity > 0
                )
                result = await session.execute(stmt)
                positions = result.scalars().all()

                exposure = {
                    'kalshi': 0.0,
                    'polymarket': 0.0,
                    'total': 0.0
                }

                for position in positions:
                    position_value = position.quantity * position.avg_price
                    if position.exchange == Exchange.KALSHI:
                        exposure['kalshi'] += position_value
                    elif position.exchange == Exchange.POLYMARKET:
                        exposure['polymarket'] += position_value

                    exposure['total'] += position_value

                return exposure

        except Exception as e:
            logger.error(
                "Error calculating market exposure",
                event_id=event_id,
                error=str(e)
            )
            return {'kalshi': 0.0, 'polymarket': 0.0, 'total': 0.0}
