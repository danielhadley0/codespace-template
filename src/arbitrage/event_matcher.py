"""
Event matching engine for finding equivalent markets across platforms.
"""
import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from fuzzywuzzy import fuzz
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import db_manager, Event, VerifiedPair, Exchange
from src.api import KalshiClient, PolymarketClient

logger = structlog.get_logger()


class EventMatcher:
    """
    Matches events between Kalshi and Polymarket using string similarity
    and temporal proximity.
    """

    def __init__(
        self,
        kalshi_client: KalshiClient,
        polymarket_client: PolymarketClient,
        similarity_threshold: int = 75,
        time_window_hours: int = 24
    ):
        """
        Initialize event matcher.

        Args:
            kalshi_client: Kalshi API client
            polymarket_client: Polymarket API client
            similarity_threshold: Minimum similarity score (0-100) for matching
            time_window_hours: Maximum time difference for close times (hours)
        """
        self.kalshi_client = kalshi_client
        self.polymarket_client = polymarket_client
        self.similarity_threshold = similarity_threshold
        self.time_window = timedelta(hours=time_window_hours)

    async def fetch_and_store_events(self):
        """Fetch events from both platforms and store in database."""
        logger.info("Fetching events from both platforms")

        # Fetch markets from both platforms
        kalshi_markets, polymarket_markets = await asyncio.gather(
            self.kalshi_client.get_markets(),
            self.polymarket_client.get_markets()
        )

        # Validate responses
        if not isinstance(kalshi_markets, list):
            logger.error("Kalshi API returned unexpected type",
                        type=type(kalshi_markets).__name__,
                        response=str(kalshi_markets)[:200])
            kalshi_markets = []

        if not isinstance(polymarket_markets, list):
            logger.error("Polymarket API returned unexpected type",
                        type=type(polymarket_markets).__name__,
                        response=str(polymarket_markets)[:200])
            polymarket_markets = []

        async with db_manager.session() as session:
            # Store Kalshi events
            for market in kalshi_markets:
                if not isinstance(market, dict):
                    logger.warning("Skipping invalid Kalshi market - not a dict",
                                  type=type(market).__name__,
                                  data=str(market)[:100])
                    continue
                try:
                    parsed = self.kalshi_client.parse_market_to_event(market)
                    await self._store_event(session, Exchange.KALSHI, parsed)
                except Exception as e:
                    logger.error("Error parsing/storing Kalshi market",
                               error=str(e),
                               market_data=str(market)[:200])

            # Store Polymarket events
            for market in polymarket_markets:
                if not isinstance(market, dict):
                    logger.warning("Skipping invalid Polymarket market - not a dict",
                                  type=type(market).__name__,
                                  data=str(market)[:100])
                    continue
                try:
                    parsed = self.polymarket_client.parse_market_to_event(market)
                    await self._store_event(session, Exchange.POLYMARKET, parsed)
                except Exception as e:
                    logger.error("Error parsing/storing Polymarket market",
                               error=str(e),
                               market_data=str(market)[:200])

        logger.info(
            "Events fetched and stored",
            kalshi_count=len(kalshi_markets),
            polymarket_count=len(polymarket_markets)
        )

    async def _store_event(
        self,
        session,
        source: Exchange,
        event_data: Dict
    ):
        """Store or update an event in the database."""
        # Check if event already exists
        stmt = select(Event).where(
            Event.source == source,
            Event.event_id == event_data['event_id']
        )
        result = await session.execute(stmt)
        existing_event = result.scalar_one_or_none()

        if existing_event:
            # Update existing event
            existing_event.title = event_data['title']
            existing_event.url = event_data.get('url')
            existing_event.close_time = event_data.get('close_time')
            existing_event.updated_at = datetime.utcnow()
        else:
            # Create new event
            new_event = Event(
                source=source,
                event_id=event_data['event_id'],
                title=event_data['title'],
                url=event_data.get('url'),
                close_time=event_data.get('close_time'),
                is_active=True
            )
            session.add(new_event)

    async def find_potential_matches(
        self,
        min_similarity: Optional[int] = None
    ) -> List[Dict]:
        """
        Find potential matching event pairs using string similarity.
        Excludes events that are already part of verified pairs.

        Args:
            min_similarity: Override default similarity threshold

        Returns:
            List of potential match dictionaries with similarity scores
        """
        threshold = min_similarity or self.similarity_threshold
        matches = []

        async with db_manager.session() as session:
            # Get all verified pairs to exclude already-matched events
            verified_stmt = select(VerifiedPair).where(
                VerifiedPair.is_active == True
            )
            verified_result = await session.execute(verified_stmt)
            verified_pairs = verified_result.scalars().all()

            # Build sets of event IDs that are already matched
            matched_kalshi_ids = {pair.kalshi_event_id for pair in verified_pairs}
            matched_polymarket_ids = {pair.polymarket_event_id for pair in verified_pairs}

            logger.debug(
                "Excluding already-matched events",
                matched_kalshi=len(matched_kalshi_ids),
                matched_polymarket=len(matched_polymarket_ids)
            )

            # Get all active Kalshi events that aren't already matched
            kalshi_stmt = select(Event).where(
                Event.source == Exchange.KALSHI,
                Event.is_active == True,
                Event.id.not_in(matched_kalshi_ids) if matched_kalshi_ids else True
            )
            kalshi_result = await session.execute(kalshi_stmt)
            kalshi_events = kalshi_result.scalars().all()

            # Get all active Polymarket events that aren't already matched
            polymarket_stmt = select(Event).where(
                Event.source == Exchange.POLYMARKET,
                Event.is_active == True,
                Event.id.not_in(matched_polymarket_ids) if matched_polymarket_ids else True
            )
            polymarket_result = await session.execute(polymarket_stmt)
            polymarket_events = polymarket_result.scalars().all()

            logger.debug(
                "Unmatched events available",
                kalshi=len(kalshi_events),
                polymarket=len(polymarket_events)
            )

            # Compare each pair
            for k_event in kalshi_events:
                for p_event in polymarket_events:
                    similarity = self._calculate_similarity(
                        k_event.title,
                        p_event.title
                    )

                    # Check time proximity if both have close times
                    time_match = True
                    if k_event.close_time and p_event.close_time:
                        time_diff = abs(k_event.close_time - p_event.close_time)
                        time_match = time_diff <= self.time_window

                    if similarity >= threshold and time_match:
                        matches.append({
                            'kalshi_event': k_event,
                            'polymarket_event': p_event,
                            'similarity': similarity,
                            'time_diff': time_diff if k_event.close_time and p_event.close_time else None
                        })

        # Sort by similarity score (descending)
        matches.sort(key=lambda x: x['similarity'], reverse=True)

        logger.info(
            "Potential matches found",
            count=len(matches),
            threshold=threshold
        )

        return matches

    def _calculate_similarity(self, text1: str, text2: str) -> int:
        """
        Calculate similarity between two text strings.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-100)
        """
        # Use token sort ratio for better matching of reordered words
        return fuzz.token_sort_ratio(text1.lower(), text2.lower())

    async def verify_pair(
        self,
        kalshi_event_id: int,
        polymarket_event_id: int,
        approved_by: str,
        notes: Optional[str] = None
    ) -> VerifiedPair:
        """
        Create a verified event pair after manual approval.

        Args:
            kalshi_event_id: Kalshi event database ID
            polymarket_event_id: Polymarket event database ID
            approved_by: User ID who approved the pair
            notes: Optional notes about the pairing

        Returns:
            Created VerifiedPair object
        """
        async with db_manager.session() as session:
            # Check if pair already exists
            stmt = select(VerifiedPair).where(
                VerifiedPair.kalshi_event_id == kalshi_event_id,
                VerifiedPair.polymarket_event_id == polymarket_event_id
            )
            result = await session.execute(stmt)
            existing_pair = result.scalar_one_or_none()

            if existing_pair:
                logger.info(
                    "Pair already verified",
                    pair_id=existing_pair.id,
                    kalshi_event_id=kalshi_event_id,
                    polymarket_event_id=polymarket_event_id
                )
                return existing_pair

            # Create new verified pair
            verified_pair = VerifiedPair(
                kalshi_event_id=kalshi_event_id,
                polymarket_event_id=polymarket_event_id,
                approved_by=approved_by,
                approved_at=datetime.utcnow(),
                is_active=True,
                notes=notes
            )
            session.add(verified_pair)
            await session.flush()
            await session.refresh(verified_pair)

            logger.info(
                "Pair verified",
                pair_id=verified_pair.id,
                kalshi_event_id=kalshi_event_id,
                polymarket_event_id=polymarket_event_id,
                approved_by=approved_by
            )

            return verified_pair

    async def get_verified_pairs(self, active_only: bool = True) -> List[VerifiedPair]:
        """
        Get all verified event pairs.

        Args:
            active_only: Only return active pairs

        Returns:
            List of VerifiedPair objects
        """
        async with db_manager.session() as session:
            stmt = select(VerifiedPair).options(
                selectinload(VerifiedPair.kalshi_event),
                selectinload(VerifiedPair.polymarket_event)
            )
            if active_only:
                stmt = stmt.where(VerifiedPair.is_active == True)

            result = await session.execute(stmt)
            pairs = result.scalars().all()

            logger.debug("Retrieved verified pairs", count=len(pairs))
            return list(pairs)

    async def deactivate_pair(self, pair_id: int):
        """
        Deactivate a verified pair.

        Args:
            pair_id: Verified pair ID
        """
        async with db_manager.session() as session:
            stmt = select(VerifiedPair).where(VerifiedPair.id == pair_id)
            result = await session.execute(stmt)
            pair = result.scalar_one_or_none()

            if pair:
                pair.is_active = False
                logger.info("Pair deactivated", pair_id=pair_id)
            else:
                logger.warning("Pair not found", pair_id=pair_id)
