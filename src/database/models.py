"""
Database models for the arbitrage system.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    ForeignKey, Text, Enum as SQLEnum, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class OrderStatus(enum.Enum):
    """Order status enumeration."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderSide(enum.Enum):
    """Order side enumeration."""
    YES = "yes"
    NO = "no"


class Exchange(enum.Enum):
    """Exchange enumeration."""
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"


class Event(Base):
    """Events table - stores market events from both platforms."""
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(SQLEnum(Exchange), nullable=False)
    event_id = Column(String(255), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    url = Column(Text)
    close_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationship
    verified_pairs_kalshi = relationship(
        "VerifiedPair",
        foreign_keys="VerifiedPair.kalshi_event_id",
        back_populates="kalshi_event"
    )
    verified_pairs_polymarket = relationship(
        "VerifiedPair",
        foreign_keys="VerifiedPair.polymarket_event_id",
        back_populates="polymarket_event"
    )

    __table_args__ = (
        Index('idx_source_event_id', 'source', 'event_id'),
        Index('idx_close_time', 'close_time'),
    )


class VerifiedPair(Base):
    """Verified pairs table - stores manually approved event pairs."""
    __tablename__ = 'verified_pairs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    kalshi_event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    polymarket_event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    approved_by = Column(String(255))  # Discord user ID
    approved_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    notes = Column(Text)

    # Relationships
    kalshi_event = relationship(
        "Event",
        foreign_keys=[kalshi_event_id],
        back_populates="verified_pairs_kalshi"
    )
    polymarket_event = relationship(
        "Event",
        foreign_keys=[polymarket_event_id],
        back_populates="verified_pairs_polymarket"
    )
    arbitrage_opportunities = relationship("ArbitrageOpportunity", back_populates="pair")
    orders = relationship("Order", back_populates="pair")

    __table_args__ = (
        Index('idx_active_pairs', 'is_active'),
    )


class ArbitrageOpportunity(Base):
    """Arbitrage opportunities table - tracks detected arbitrage chances."""
    __tablename__ = 'arbitrage_opportunities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_id = Column(Integer, ForeignKey('verified_pairs.id'), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Prices at time of detection
    kalshi_yes_price = Column(Float, nullable=False)
    kalshi_no_price = Column(Float, nullable=False)
    polymarket_yes_price = Column(Float, nullable=False)
    polymarket_no_price = Column(Float, nullable=False)

    # Arbitrage details
    spread = Column(Float, nullable=False)  # Net profit percentage
    strategy = Column(String(50))  # e.g., "kalshi_yes_polymarket_no"
    expected_profit = Column(Float)

    # Execution status
    executed = Column(Boolean, default=False)
    execution_started_at = Column(DateTime)
    execution_completed_at = Column(DateTime)

    # PnL
    realized_pnl = Column(Float)
    notes = Column(Text)

    # Relationship
    pair = relationship("VerifiedPair", back_populates="arbitrage_opportunities")

    __table_args__ = (
        Index('idx_pair_timestamp', 'pair_id', 'timestamp'),
        Index('idx_executed', 'executed'),
    )


class Order(Base):
    """Orders table - tracks all orders placed on both exchanges."""
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair_id = Column(Integer, ForeignKey('verified_pairs.id'), nullable=False)
    opportunity_id = Column(Integer, ForeignKey('arbitrage_opportunities.id'))

    # Order details
    exchange = Column(SQLEnum(Exchange), nullable=False)
    order_id = Column(String(255))  # Exchange's order ID
    side = Column(SQLEnum(OrderSide), nullable=False)

    # Size and pricing
    size = Column(Float, nullable=False)  # Requested size
    filled_size = Column(Float, default=0.0)  # Actually filled size
    price = Column(Float, nullable=False)  # Limit price
    avg_fill_price = Column(Float)  # Average fill price

    # Status and timing
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    submitted_at = Column(DateTime)
    filled_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    # Metadata
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Relationships
    pair = relationship("VerifiedPair", back_populates="orders")

    __table_args__ = (
        Index('idx_exchange_order_id', 'exchange', 'order_id'),
        Index('idx_status', 'status'),
        Index('idx_pair_created', 'pair_id', 'created_at'),
    )


class Position(Base):
    """Positions table - tracks current positions on each exchange."""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(SQLEnum(Exchange), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    side = Column(SQLEnum(OrderSide), nullable=False)

    # Position details
    quantity = Column(Float, default=0.0)
    avg_price = Column(Float, default=0.0)

    # PnL tracking
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)

    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_exchange_event', 'exchange', 'event_id'),
    )


class PriceCache(Base):
    """Price cache table - stores recent price data for fast lookups."""
    __tablename__ = 'price_cache'

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    yes_price = Column(Float, nullable=False)
    no_price = Column(Float, nullable=False)
    liquidity = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_event_timestamp', 'event_id', 'timestamp'),
    )
