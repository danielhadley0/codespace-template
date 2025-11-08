# Kalshi–Polymarket Arbitrage Monitor & Executor

A fully automated system that continuously monitors Kalshi and Polymarket for arbitrage opportunities between equivalent prediction markets. Once a pair of events is manually confirmed by the user as identical, the system automatically executes orders to exploit arbitrage spreads while managing partial fills, position limits, and execution slippage.

## Features

- **Real-time Market Monitoring**: Continuously fetches market data from both Kalshi and Polymarket APIs
- **Intelligent Event Matching**: Uses fuzzy string matching to identify equivalent markets across platforms
- **Manual Approval Workflow**: Discord bot integration for reviewing and approving event pairs
- **Automated Arbitrage Detection**: Calculates profitable opportunities with fee and slippage considerations
- **Smart Trade Execution**: Two-phase order placement with partial fill management
- **Position & PnL Tracking**: Real-time tracking of positions and profit/loss across both exchanges
- **Discord Notifications**: Alerts for arbitrage opportunities, execution updates, and position summaries

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Discord Bot Interface                      │
│        (Manual Approval, Monitoring, Commands)               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  Main Orchestrator                           │
│         (Coordinates all components)                         │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│Event Matcher │    │  Arbitrage   │    │    Trade     │
│              │───▶│  Detector    │───▶│  Executor    │
└──────────────┘    └──────────────┘    └──────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────┐
│              PostgreSQL Database                      │
│  (Events, Pairs, Opportunities, Orders, Positions)   │
└──────────────────────────────────────────────────────┘
         │                                        │
         ▼                                        ▼
┌──────────────┐                        ┌──────────────┐
│  Kalshi API  │                        │Polymarket API│
└──────────────┘                        └──────────────┘
```

## Project Structure

```
.
├── config/
│   └── settings.py              # Configuration management
├── src/
│   ├── api/
│   │   ├── kalshi_client.py     # Kalshi API client
│   │   └── polymarket_client.py # Polymarket API client
│   ├── arbitrage/
│   │   ├── event_matcher.py     # Event matching engine
│   │   └── detector.py          # Arbitrage detection logic
│   ├── database/
│   │   ├── models.py            # SQLAlchemy models
│   │   └── connection.py        # Database connection manager
│   ├── execution/
│   │   ├── executor.py          # Trade execution engine
│   │   └── position_manager.py  # Position and PnL tracking
│   ├── discord_bot/
│   │   └── bot.py               # Discord bot with commands
│   ├── utils/
│   │   ├── logger.py            # Logging configuration
│   │   └── retry.py             # Retry logic utilities
│   └── main.py                  # Main orchestrator
├── .env.example                 # Environment variables template
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker container configuration
├── docker-compose.yml           # Docker Compose setup
└── README.md                    # This file
```

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis (optional, for future enhancements)
- Docker & Docker Compose (for containerized deployment)
- Discord Bot Token
- Kalshi API credentials
- Polymarket API credentials

## Installation

### Option 1: Docker (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd codespace-template
```

2. Copy environment template:
```bash
cp .env.example .env
```

3. Edit `.env` with your credentials:
```bash
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
KALSHI_API_KEY=your_kalshi_api_key
KALSHI_API_SECRET=your_kalshi_api_secret
POLYMARKET_API_KEY=your_polymarket_api_key
POLYMARKET_PRIVATE_KEY=your_polymarket_private_key

# Optional (defaults provided)
MIN_ARBITRAGE_THRESHOLD=0.01
MAX_TRADE_SIZE=1000
MAX_POSITION_PER_MARKET=5000
```

4. Start the system:
```bash
docker-compose up -d
```

5. View logs:
```bash
docker-compose logs -f arbitrage_app
```

### Option 2: Local Development

1. Clone and navigate to the repository:
```bash
git clone <repository-url>
cd codespace-template
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up PostgreSQL database:
```bash
createdb arbitrage_db
```

5. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

6. Run the application:
```bash
python -m src.main
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:password@localhost:5432/arbitrage_db` |
| `DISCORD_BOT_TOKEN` | Discord bot authentication token | Required |
| `DISCORD_CHANNEL_ID` | Discord channel ID for notifications | Required |
| `KALSHI_API_KEY` | Kalshi API key | Required |
| `KALSHI_API_SECRET` | Kalshi API secret | Required |
| `POLYMARKET_API_KEY` | Polymarket API key (wallet address) | Required |
| `POLYMARKET_PRIVATE_KEY` | Polymarket private key for signing | Required |
| `MIN_ARBITRAGE_THRESHOLD` | Minimum profit threshold (%) | `0.01` (1%) |
| `MAX_TRADE_SIZE` | Maximum trade size per opportunity ($) | `1000` |
| `MAX_POSITION_PER_MARKET` | Maximum open exposure per market ($) | `5000` |
| `SLIPPAGE_TOLERANCE` | Maximum acceptable slippage (%) | `0.02` (2%) |
| `ORDER_TIMEOUT_SECONDS` | Order fill timeout | `30` |
| `PRICE_FETCH_INTERVAL` | Market data refresh interval (seconds) | `5` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Usage

### Discord Bot Commands

The Discord bot provides several commands for interacting with the system:

- **`/find_matches [similarity]`** - Find potential matching events between platforms
  ```
  /find_matches 80
  ```

- **`/approve_pair <kalshi_id> <poly_id>`** - Manually approve an event pair
  ```
  /approve_pair 123 456
  ```

- **`/list_pairs`** - List all active verified pairs
  ```
  /list_pairs
  ```

- **`/positions`** - Show current positions and PnL summary
  ```
  /positions
  ```

- **`/pause_pair <pair_id>`** - Pause trading for a specific pair
  ```
  /pause_pair 42
  ```

- **`/help`** - Show available commands
  ```
  /help
  ```

### Workflow

1. **System starts and fetches markets** from both Kalshi and Polymarket

2. **Find potential matches** using `/find_matches` command in Discord

3. **Review suggestions** - The bot will post potential matches with similarity scores

4. **Approve pairs** by reacting with ✅ or using `/approve_pair` command

5. **Automated monitoring begins** - System continuously monitors approved pairs

6. **Arbitrage detection** - When spread exceeds threshold, Discord alert is sent

7. **Automatic execution** - System places orders on both platforms simultaneously

8. **Partial fill management** - Monitors fills and attempts to balance positions

9. **PnL tracking** - Updates positions and profit/loss in real-time

10. **Discord notifications** - Receive updates on execution status and results

## Database Schema

### Tables

- **`events`** - Market events from both platforms
- **`verified_pairs`** - Manually approved event pairs
- **`arbitrage_opportunities`** - Detected arbitrage chances
- **`orders`** - All placed orders with fill status
- **`positions`** - Current positions across exchanges
- **`price_cache`** - Recent price data for fast lookups

## Safety Features

- **Two-phase execution** - Places orders sequentially to minimize unhedged exposure
- **Partial fill management** - Monitors and balances fills across both sides
- **Position limits** - Enforces maximum exposure per market
- **Slippage protection** - Cancels orders if execution price deviates too much
- **Cooldown periods** - Prevents rapid-fire trades on the same pair
- **Manual approval** - Requires user confirmation before pairing markets
- **Comprehensive logging** - All trades logged with timestamps and IDs

## Monitoring & Logging

Logs are written to both console and file (`logs/arbitrage.log`):

```bash
# View live logs (Docker)
docker-compose logs -f arbitrage_app

# View logs (local)
tail -f logs/arbitrage.log
```

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# View database logs
docker-compose logs postgres

# Connect to database
docker-compose exec postgres psql -U arbitrage_user -d arbitrage_db
```

### Discord Bot Not Responding
```bash
# Verify bot token in .env
# Check bot has proper permissions in Discord server
# View bot logs
docker-compose logs arbitrage_app | grep discord
```

### API Authentication Errors
```bash
# Verify API credentials in .env
# Check API key permissions on exchange platforms
# View API logs
docker-compose logs arbitrage_app | grep "api"
```

### No Arbitrage Opportunities Found
- Markets may be efficiently priced
- Adjust `MIN_ARBITRAGE_THRESHOLD` to lower value
- Verify verified pairs exist: `/list_pairs`
- Check if markets are still open

## Development

### Running Tests
```bash
pytest tests/ -v
```

### Code Structure Guidelines
- Async/await for all I/O operations
- Structured logging with context
- Retry logic for API calls
- Type hints for better code clarity

### Adding New Features
1. Create feature branch
2. Implement changes with tests
3. Update documentation
4. Submit pull request

## Performance Metrics

Target performance (from PRD):
- ≥ 95% of detected arbitrage trades executed within slippage limits
- ≤ 5% of total trades result in unhedged partial positions
- Average trade execution time < 1 second
- Daily PnL logged with accurate reconciliation

## Security Considerations

- **API Keys**: Store securely in `.env`, never commit to git
- **Private Keys**: Encrypted storage recommended for production
- **Database**: Use strong passwords, enable SSL connections
- **Discord Bot**: Restrict command usage to authorized users only
- **Network**: Use HTTPS for all API communications

## Future Enhancements

- [ ] Automatic calibration of execution size based on liquidity
- [ ] Historical backtesting for arbitrage frequency and PnL
- [ ] Multi-platform expansion (PredictIt, Zeitgeist)
- [ ] Web dashboard for analytics and controls
- [ ] Machine learning for better event matching
- [ ] Advanced hedging strategies for partial fills

## License

[Your License Here]

## Contributing

Contributions are welcome! Please read our contributing guidelines first.

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

## Disclaimer

This software is for educational purposes only. Trading prediction markets involves financial risk. The authors are not responsible for any financial losses incurred through use of this software. Always comply with applicable laws and exchange terms of service.

---

**Author**: Daniel
**Date**: November 2025
**Version**: 1.0.0
