"""
Main orchestrator for the arbitrage system.
"""
import asyncio
import signal
import sys
from typing import Optional
from datetime import datetime
import structlog

from config.settings import settings
from src.utils.logger import setup_logging
from src.database import db_manager
from src.api import KalshiClient, PolymarketClient
from src.arbitrage import EventMatcher, ArbitrageDetector
from src.execution import TradeExecutor, PositionManager, PaperTradingExecutor
from src.discord_bot import ArbitrageBot

logger = structlog.get_logger()


class ArbitrageOrchestrator:
    """
    Main orchestrator that coordinates all components of the arbitrage system.
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.kalshi_client: Optional[KalshiClient] = None
        self.polymarket_client: Optional[PolymarketClient] = None
        self.event_matcher: Optional[EventMatcher] = None
        self.arbitrage_detector: Optional[ArbitrageDetector] = None
        self.trade_executor: Optional[TradeExecutor] = None
        self.position_manager: Optional[PositionManager] = None
        self.discord_bot: Optional[ArbitrageBot] = None

        self.running = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.discord_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing arbitrage orchestrator")

        try:
            # Initialize database
            await db_manager.initialize()

            # Initialize API clients
            self.kalshi_client = KalshiClient()
            await self.kalshi_client.initialize()

            self.polymarket_client = PolymarketClient()
            await self.polymarket_client.initialize()

            # Initialize components
            self.event_matcher = EventMatcher(
                kalshi_client=self.kalshi_client,
                polymarket_client=self.polymarket_client
            )

            self.arbitrage_detector = ArbitrageDetector(
                kalshi_client=self.kalshi_client,
                polymarket_client=self.polymarket_client
            )

            # Initialize trade executor based on mode
            if settings.paper_trading_mode:
                logger.warning(
                    "🧪 PAPER TRADING MODE ENABLED - No real money at risk",
                    starting_balance=settings.paper_starting_balance
                )
                self.trade_executor = PaperTradingExecutor()
            else:
                logger.warning(
                    "⚠️  LIVE TRADING MODE ENABLED - Real money at risk!",
                    mode="LIVE"
                )
                self.trade_executor = TradeExecutor(
                    kalshi_client=self.kalshi_client,
                    polymarket_client=self.polymarket_client
                )

            self.position_manager = PositionManager()

            # Initialize Discord bot with paper executor if in paper mode
            self.discord_bot = ArbitrageBot(
                event_matcher=self.event_matcher,
                position_manager=self.position_manager,
                paper_executor=self.trade_executor if settings.paper_trading_mode else None
            )

            logger.info(
                "Arbitrage orchestrator initialized successfully",
                mode="PAPER" if settings.paper_trading_mode else "LIVE"
            )

        except Exception as e:
            logger.error("Failed to initialize orchestrator", error=str(e))
            raise

    async def start(self):
        """Start the arbitrage system."""
        logger.info("Starting arbitrage system")

        self.running = True

        # Start Discord bot in background
        self.discord_task = asyncio.create_task(
            self.discord_bot.start(settings.discord_bot_token)
        )

        # Start monitoring loop
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())

        logger.info("Arbitrage system started")

        # Wait for tasks
        try:
            await asyncio.gather(
                self.monitoring_task,
                self.discord_task,
                return_exceptions=True
            )
        except Exception as e:
            logger.error("Error in main tasks", error=str(e))
            await self.stop()

    async def stop(self):
        """Stop the arbitrage system."""
        logger.info("Stopping arbitrage system")

        self.running = False

        # Cancel tasks
        if self.monitoring_task:
            self.monitoring_task.cancel()

        if self.discord_task:
            self.discord_task.cancel()

        # Close connections
        if self.kalshi_client:
            await self.kalshi_client.close()

        if self.polymarket_client:
            await self.polymarket_client.close()

        if self.discord_bot:
            await self.discord_bot.close()

        # Close database
        await db_manager.close()

        logger.info("Arbitrage system stopped")

    async def monitoring_loop(self):
        """Main monitoring loop for detecting and executing arbitrage."""
        logger.info("Starting monitoring loop")

        # Initial data fetch
        await self.fetch_events()

        while self.running:
            try:
                # Get all verified pairs
                pairs = await self.event_matcher.get_verified_pairs(active_only=True)

                if not pairs:
                    logger.debug("No verified pairs to monitor")
                    await asyncio.sleep(settings.price_fetch_interval)
                    continue

                logger.info(f"Monitoring {len(pairs)} verified pairs")

                # Check for arbitrage opportunities
                opportunities = await self.arbitrage_detector.monitor_pairs(pairs)

                # Process each opportunity
                for pair, strategy in opportunities:
                    await self.process_arbitrage_opportunity(pair, strategy)

                # Refresh event data periodically (every 5 minutes)
                current_time = datetime.utcnow()
                if not hasattr(self, '_last_fetch') or \
                   (current_time - self._last_fetch).total_seconds() > 300:
                    await self.fetch_events()
                    self._last_fetch = current_time

                # Sleep before next iteration
                await asyncio.sleep(settings.price_fetch_interval)

            except Exception as e:
                logger.error("Error in monitoring loop", error=str(e))
                await asyncio.sleep(settings.price_fetch_interval)

    async def fetch_events(self):
        """Fetch and store events from both platforms."""
        try:
            logger.info("Fetching events from both platforms")
            await self.event_matcher.fetch_and_store_events()
            logger.info("Events fetched successfully")
        except Exception as e:
            logger.error("Error fetching events", error=str(e))

    async def process_arbitrage_opportunity(self, pair, strategy):
        """
        Process a detected arbitrage opportunity.

        Args:
            pair: VerifiedPair object
            strategy: ArbitrageStrategy object
        """
        try:
            # Log the opportunity
            opportunity = await self.arbitrage_detector.log_opportunity(
                pair=pair,
                strategy=strategy,
                executed=False
            )

            # Send Discord alert
            if self.discord_bot:
                await self.discord_bot.send_arbitrage_alert(
                    pair_id=pair.id,
                    strategy=strategy.strategy_type,
                    spread=strategy.spread,
                    expected_profit=strategy.expected_profit
                )

            # Check if we should execute (can add more conditions here)
            if strategy.spread >= settings.min_arbitrage_threshold:
                # Execute the trade
                success, message = await self.trade_executor.execute_arbitrage(
                    pair=pair,
                    strategy=strategy,
                    opportunity=opportunity
                )

                # Send execution update
                if self.discord_bot:
                    status = 'success' if success else 'failed'
                    await self.discord_bot.send_execution_update(
                        pair_id=pair.id,
                        status=status,
                        message=message
                    )

                if success:
                    logger.info(
                        "Arbitrage executed successfully",
                        pair_id=pair.id,
                        opportunity_id=opportunity.id
                    )
                else:
                    logger.warning(
                        "Arbitrage execution failed",
                        pair_id=pair.id,
                        message=message
                    )

                # Cooldown between trades
                await asyncio.sleep(settings.cooldown_between_trades)

        except Exception as e:
            logger.error(
                "Error processing arbitrage opportunity",
                pair_id=pair.id,
                error=str(e)
            )


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging()

    logger.info("Starting Kalshi-Polymarket Arbitrage System")

    # Create orchestrator
    orchestrator = ArbitrageOrchestrator()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(orchestrator.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize and start
        await orchestrator.initialize()
        await orchestrator.start()

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await orchestrator.stop()

    except Exception as e:
        logger.error("Fatal error", error=str(e))
        await orchestrator.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
