"""
Discord bot for manual approval and monitoring.
"""
import discord
from discord.ext import commands
from typing import Optional, Dict
import structlog
from datetime import datetime

from config.settings import settings
from src.arbitrage.event_matcher import EventMatcher
from src.execution.position_manager import PositionManager
from src.database import db_manager, VerifiedPair, Exchange
from sqlalchemy import select

logger = structlog.get_logger()


class ArbitrageBot(commands.Bot):
    """Discord bot for arbitrage system interaction."""

    def __init__(
        self,
        event_matcher: EventMatcher,
        position_manager: PositionManager,
        paper_executor=None,
        *args,
        **kwargs
    ):
        """
        Initialize Discord bot.

        Args:
            event_matcher: EventMatcher instance
            position_manager: PositionManager instance
            paper_executor: PaperTradingExecutor instance (if in paper mode)
        """
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix='/',
            intents=intents,
            *args,
            **kwargs
        )

        self.event_matcher = event_matcher
        self.position_manager = position_manager
        self.paper_executor = paper_executor
        self.notification_channel_id = settings.discord_channel_id
        self.pending_approvals: Dict[str, Dict] = {}  # message_id -> match data

    async def on_ready(self):
        """Called when bot is ready."""
        logger.info(
            "Discord bot connected",
            bot_name=self.user.name,
            bot_id=self.user.id
        )
        await self.setup_commands()

    async def setup_commands(self):
        """Set up bot commands."""

        @self.command(name='find_matches')
        async def find_matches(ctx, min_similarity: int = 75):
            """
            Find potential matching events between platforms.

            Usage: /find_matches [min_similarity]
            """
            await ctx.send("🔍 Searching for potential matches...")

            try:
                matches = await self.event_matcher.find_potential_matches(
                    min_similarity=min_similarity
                )

                if not matches:
                    await ctx.send("No potential matches found.")
                    return

                # Show top 10 matches
                for i, match in enumerate(matches[:10], 1):
                    await self.send_match_approval_request(
                        ctx.channel,
                        match
                    )

                await ctx.send(f"Found {len(matches)} potential matches. Showing top 10.")

            except Exception as e:
                logger.error("Error finding matches", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='approve_pair')
        async def approve_pair(ctx, kalshi_event_id: int, polymarket_event_id: int):
            """
            Manually approve an event pair.

            Usage: /approve_pair <kalshi_event_id> <polymarket_event_id>
            """
            try:
                verified_pair = await self.event_matcher.verify_pair(
                    kalshi_event_id=kalshi_event_id,
                    polymarket_event_id=polymarket_event_id,
                    approved_by=str(ctx.author.id),
                    notes=f"Manually approved via Discord by {ctx.author.name}"
                )

                embed = discord.Embed(
                    title="✅ Pair Approved",
                    description=f"Pair ID: {verified_pair.id}",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(
                    name="Kalshi Event",
                    value=f"ID: {kalshi_event_id}",
                    inline=True
                )
                embed.add_field(
                    name="Polymarket Event",
                    value=f"ID: {polymarket_event_id}",
                    inline=True
                )

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error("Error approving pair", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='list_pairs')
        async def list_pairs(ctx):
            """
            List all active verified pairs.

            Usage: /list_pairs
            """
            try:
                pairs = await self.event_matcher.get_verified_pairs(active_only=True)

                if not pairs:
                    await ctx.send("No active pairs found.")
                    return

                embed = discord.Embed(
                    title="📊 Active Verified Pairs",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )

                for pair in pairs[:25]:  # Limit to 25 for Discord field limit
                    kalshi_title = pair.kalshi_event.title[:100]
                    poly_title = pair.polymarket_event.title[:100]

                    embed.add_field(
                        name=f"Pair #{pair.id}",
                        value=(
                            f"**Kalshi:** {kalshi_title}\n"
                            f"**Polymarket:** {poly_title}\n"
                            f"Approved: {pair.approved_at.strftime('%Y-%m-%d')}"
                        ),
                        inline=False
                    )

                await ctx.send(embed=embed)

                if len(pairs) > 25:
                    await ctx.send(f"Showing 25 of {len(pairs)} pairs.")

            except Exception as e:
                logger.error("Error listing pairs", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='positions')
        async def positions(ctx):
            """
            Show current positions.

            Usage: /positions
            """
            try:
                positions = await self.position_manager.get_positions()
                pnl_summary = await self.position_manager.get_total_pnl()

                embed = discord.Embed(
                    title="💼 Current Positions",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow()
                )

                # PnL Summary
                embed.add_field(
                    name="PnL Summary",
                    value=(
                        f"**Realized:** ${pnl_summary['realized_pnl']:.2f}\n"
                        f"**Unrealized:** ${pnl_summary['unrealized_pnl']:.2f}\n"
                        f"**Total:** ${pnl_summary['total_pnl']:.2f}"
                    ),
                    inline=False
                )

                # Individual positions
                if positions:
                    for pos in positions[:10]:  # Limit to 10
                        embed.add_field(
                            name=f"{pos.exchange.value.upper()} - Event {pos.event_id}",
                            value=(
                                f"Side: {pos.side.value.upper()}\n"
                                f"Qty: {pos.quantity:.2f} @ ${pos.avg_price:.3f}\n"
                                f"Unrealized PnL: ${pos.unrealized_pnl:.2f}"
                            ),
                            inline=True
                        )
                else:
                    embed.add_field(
                        name="Positions",
                        value="No open positions",
                        inline=False
                    )

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error("Error getting positions", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='pause_pair')
        async def pause_pair(ctx, pair_id: int):
            """
            Pause trading for a specific pair.

            Usage: /pause_pair <pair_id>
            """
            try:
                await self.event_matcher.deactivate_pair(pair_id)
                await ctx.send(f"✅ Pair #{pair_id} has been paused.")

            except Exception as e:
                logger.error("Error pausing pair", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='paper_stats')
        async def paper_stats(ctx):
            """
            Show paper trading statistics.

            Usage: /paper_stats
            """
            if not self.paper_executor:
                await ctx.send("❌ Paper trading mode is not enabled.")
                return

            try:
                stats = self.paper_executor.get_stats()

                embed = discord.Embed(
                    title="📊 Paper Trading Statistics",
                    description="Simulated trading performance",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )

                # Balance info
                balance_change = stats['current_balance'] - stats['starting_balance']
                balance_pct = (balance_change / stats['starting_balance'] * 100) if stats['starting_balance'] > 0 else 0

                embed.add_field(
                    name="💰 Balance",
                    value=(
                        f"Starting: ${stats['starting_balance']:.2f}\n"
                        f"Current: ${stats['current_balance']:.2f}\n"
                        f"Change: ${balance_change:.2f} ({balance_pct:+.2f}%)"
                    ),
                    inline=False
                )

                # Trading stats
                embed.add_field(
                    name="📈 Trading Performance",
                    value=(
                        f"Total Trades: {stats['total_trades']}\n"
                        f"Successful: {stats['successful_trades']}\n"
                        f"Failed: {stats['failed_trades']}\n"
                        f"Win Rate: {stats['win_rate']:.1f}%"
                    ),
                    inline=True
                )

                # PnL stats
                embed.add_field(
                    name="💵 Profit & Loss",
                    value=(
                        f"Total PnL: ${stats['total_pnl']:.2f}\n"
                        f"Avg Profit: ${stats['avg_profit_per_trade']:.2f}\n"
                        f"Runtime: {stats['runtime_seconds']/60:.1f} min"
                    ),
                    inline=True
                )

                embed.set_footer(text=f"Paper trading mode • Session started: {stats['session_start'].strftime('%Y-%m-%d %H:%M')}")

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error("Error getting paper trading stats", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='reset_paper')
        async def reset_paper(ctx):
            """
            Reset paper trading statistics.

            Usage: /reset_paper
            """
            if not self.paper_executor:
                await ctx.send("❌ Paper trading mode is not enabled.")
                return

            try:
                old_stats = self.paper_executor.get_stats()
                self.paper_executor.reset_stats()

                embed = discord.Embed(
                    title="🔄 Paper Trading Stats Reset",
                    description="Statistics have been reset to starting values",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )

                embed.add_field(
                    name="Previous Session",
                    value=(
                        f"Total PnL: ${old_stats['total_pnl']:.2f}\n"
                        f"Total Trades: {old_stats['total_trades']}\n"
                        f"Win Rate: {old_stats['win_rate']:.1f}%"
                    ),
                    inline=False
                )

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error("Error resetting paper trading stats", error=str(e))
                await ctx.send(f"Error: {str(e)}")

        @self.command(name='trading_mode')
        async def trading_mode(ctx):
            """
            Show current trading mode (paper or live).

            Usage: /trading_mode
            """
            mode = "PAPER TRADING" if settings.paper_trading_mode else "LIVE TRADING"
            color = discord.Color.blue() if settings.paper_trading_mode else discord.Color.red()

            embed = discord.Embed(
                title=f"{'📄' if settings.paper_trading_mode else '💰'} Current Trading Mode",
                description=f"**{mode}**",
                color=color,
                timestamp=datetime.utcnow()
            )

            if settings.paper_trading_mode:
                embed.add_field(
                    name="Paper Trading Info",
                    value=(
                        "✅ Safe mode - no real money at risk\n"
                        "✅ Simulates fills with realistic slippage\n"
                        "✅ Tracks performance metrics\n"
                        f"Starting balance: ${settings.paper_starting_balance:.2f}"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="To switch to live trading",
                    value="Set `PAPER_TRADING_MODE=false` in .env and restart",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ LIVE TRADING WARNING",
                    value=(
                        "🔴 Real money is at risk\n"
                        "🔴 Actual orders will be placed\n"
                        "🔴 Ensure APIs are properly configured\n"
                        "🔴 Monitor positions carefully"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="To switch to paper trading",
                    value="Set `PAPER_TRADING_MODE=true` in .env and restart",
                    inline=False
                )

            await ctx.send(embed=embed)

        @self.command(name='commands')
        async def commands_list_command(ctx):
            """
            Show available commands.

            Usage: /commands
            """
            embed = discord.Embed(
                title="🤖 Arbitrage Bot Commands",
                description="Available commands for managing the arbitrage system",
                color=discord.Color.purple()
            )

            cmd_list = [
                ("/find_matches [similarity]", "Find potential matching events"),
                ("/approve_pair <kalshi_id> <poly_id>", "Approve an event pair"),
                ("/list_pairs", "List all active verified pairs"),
                ("/positions", "Show current positions and PnL"),
                ("/pause_pair <pair_id>", "Pause trading for a pair"),
                ("/trading_mode", "Show current trading mode (paper/live)"),
                ("/paper_stats", "Show paper trading statistics"),
                ("/reset_paper", "Reset paper trading stats"),
                ("/commands", "Show this command list"),
            ]

            for cmd, desc in cmd_list:
                embed.add_field(name=cmd, value=desc, inline=False)

            await ctx.send(embed=embed)

    async def send_match_approval_request(self, channel, match: Dict):
        """
        Send a match approval request to Discord with reactions.

        Args:
            channel: Discord channel to send to
            match: Match data dictionary
        """
        kalshi_event = match['kalshi_event']
        polymarket_event = match['polymarket_event']
        similarity = match['similarity']

        embed = discord.Embed(
            title="🔄 Potential Match Found",
            description=f"Similarity: {similarity}%",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(
            name="Kalshi",
            value=(
                f"**Title:** {kalshi_event.title}\n"
                f"**ID:** {kalshi_event.id}\n"
                f"**Close:** {kalshi_event.close_time.strftime('%Y-%m-%d %H:%M') if kalshi_event.close_time else 'N/A'}\n"
                f"**URL:** {kalshi_event.url}"
            ),
            inline=False
        )

        embed.add_field(
            name="Polymarket",
            value=(
                f"**Title:** {polymarket_event.title}\n"
                f"**ID:** {polymarket_event.id}\n"
                f"**Close:** {polymarket_event.close_time.strftime('%Y-%m-%d %H:%M') if polymarket_event.close_time else 'N/A'}\n"
                f"**URL:** {polymarket_event.url}"
            ),
            inline=False
        )

        embed.set_footer(text="React with ✅ to approve or ❌ to reject")

        message = await channel.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        # Store pending approval
        self.pending_approvals[str(message.id)] = match

    async def on_reaction_add(self, reaction, user):
        """Handle reaction-based approvals."""
        if user.bot:
            return

        message_id = str(reaction.message.id)
        if message_id not in self.pending_approvals:
            return

        match = self.pending_approvals[message_id]

        if str(reaction.emoji) == "✅":
            # Approve the pair
            try:
                verified_pair = await self.event_matcher.verify_pair(
                    kalshi_event_id=match['kalshi_event'].id,
                    polymarket_event_id=match['polymarket_event'].id,
                    approved_by=str(user.id),
                    notes=f"Approved via reaction by {user.name}"
                )

                await reaction.message.channel.send(
                    f"✅ Pair #{verified_pair.id} approved by {user.mention}"
                )

                # Remove from pending
                del self.pending_approvals[message_id]

            except Exception as e:
                logger.error("Error approving pair via reaction", error=str(e))
                await reaction.message.channel.send(f"Error approving pair: {str(e)}")

        elif str(reaction.emoji) == "❌":
            # Reject the pair
            await reaction.message.channel.send(
                f"❌ Match rejected by {user.mention}"
            )
            del self.pending_approvals[message_id]

    async def send_arbitrage_alert(
        self,
        pair_id: int,
        strategy: str,
        spread: float,
        expected_profit: float
    ):
        """
        Send arbitrage opportunity alert to Discord.

        Args:
            pair_id: Pair ID
            strategy: Strategy type
            spread: Arbitrage spread percentage
            expected_profit: Expected profit in USD
        """
        try:
            channel = self.get_channel(self.notification_channel_id)
            if not channel:
                logger.error("Notification channel not found")
                return

            embed = discord.Embed(
                title="🚨 Arbitrage Opportunity Detected",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="Pair ID", value=str(pair_id), inline=True)
            embed.add_field(name="Strategy", value=strategy, inline=True)
            embed.add_field(name="Spread", value=f"{spread*100:.2f}%", inline=True)
            embed.add_field(
                name="Expected Profit",
                value=f"${expected_profit:.2f}",
                inline=True
            )

            await channel.send(embed=embed)

        except Exception as e:
            logger.error("Error sending arbitrage alert", error=str(e))

    async def send_execution_update(
        self,
        pair_id: int,
        status: str,
        message: str
    ):
        """
        Send execution status update to Discord.

        Args:
            pair_id: Pair ID
            status: Status (success, failed, partial)
            message: Status message
        """
        try:
            channel = self.get_channel(self.notification_channel_id)
            if not channel:
                return

            color_map = {
                'success': discord.Color.green(),
                'failed': discord.Color.red(),
                'partial': discord.Color.orange()
            }

            embed = discord.Embed(
                title=f"📈 Execution Update - Pair #{pair_id}",
                description=message,
                color=color_map.get(status, discord.Color.blue()),
                timestamp=datetime.utcnow()
            )

            await channel.send(embed=embed)

        except Exception as e:
            logger.error("Error sending execution update", error=str(e))


async def run_discord_bot(
    event_matcher: EventMatcher,
    position_manager: PositionManager,
    paper_executor=None
):
    """
    Run the Discord bot.

    Args:
        event_matcher: EventMatcher instance
        position_manager: PositionManager instance
        paper_executor: PaperTradingExecutor instance (optional)
    """
    bot = ArbitrageBot(
        event_matcher=event_matcher,
        position_manager=position_manager,
        paper_executor=paper_executor
    )

    try:
        await bot.start(settings.discord_bot_token)
    except Exception as e:
        logger.error("Discord bot error", error=str(e))
        raise
