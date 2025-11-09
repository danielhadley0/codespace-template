# 🎮 Super Simple Setup Guide

Welcome! This guide will help you set up your arbitrage bot, step by step. Don't worry - I'll explain everything like you're 5 years old! 🚀

## 📚 Table of Contents

1. [What Does This Bot Do?](#what-does-this-bot-do)
2. [What You Need Before Starting](#what-you-need-before-starting)
3. [Step-by-Step Setup](#step-by-step-setup)
4. [Running Your Bot](#running-your-bot)
5. [Using Discord Commands](#using-discord-commands)
6. [Understanding Paper Trading](#understanding-paper-trading)
7. [Troubleshooting](#troubleshooting)

---

## 🤔 What Does This Bot Do?

Imagine you have two lemonade stands:
- **Stand A** sells lemonade for 60 cents
- **Stand B** will buy your lemonade for 50 cents

If you could guarantee that one of them will pay you $1 tomorrow, you could:
1. Buy from Stand B for 50 cents
2. Buy from Stand A for 60 cents
3. Tomorrow, one pays you $1!
4. You made: $1 - $0.50 - $0.60 = -$0.10... wait, that's a loss!

But if the prices were different:
- Stand A sells for 40 cents
- Stand B sells for 50 cents
- Total cost: 90 cents
- You get back: $1
- **Profit: 10 cents!** 🎉

This bot does exactly that, but with prediction markets (Kalshi and Polymarket) instead of lemonade stands!

---

## 📋 What You Need Before Starting

Think of these like ingredients for baking cookies:

### Required (You MUST have these):

1. **A Computer** 💻
   - Mac, Windows, or Linux - any will work!

2. **Discord Account** 💬
   - This is like your walkie-talkie to talk to the bot
   - Free to make at [discord.com](https://discord.com)

3. **Kalshi Account** 🎯
   - Sign up at [kalshi.com](https://kalshi.com)
   - You'll need to get API keys (like special passwords for the bot)

4. **Polymarket Account** 🎲
   - Sign up at [polymarket.com](https://polymarket.com)
   - You'll also need API keys here

5. **Basic Computer Skills** 🖱️
   - Can you copy and paste? Great! You're ready!

### Optional (Nice to have):

- **Docker** 🐳 - Makes running the bot super easy (we'll show you how to install it)

---

## 🎯 Step-by-Step Setup

### Step 1: Get the Code

**What are we doing?** Getting the bot's code onto your computer (like downloading a game).

**How to do it:**

1. Open your terminal (it's like a text-based way to talk to your computer):
   - **Mac**: Press `Cmd + Space`, type "Terminal", press Enter
   - **Windows**: Press `Windows + R`, type "cmd", press Enter
   - **Linux**: Press `Ctrl + Alt + T`

2. Copy and paste this command:
   ```bash
   git clone https://github.com/danielhadley0/codespace-template.git
   cd codespace-template
   ```

3. Press Enter!

**What just happened?** You copied all the bot's code to your computer and went into its folder!

---

### Step 2: Create Your Discord Bot

**What are we doing?** Making a robot friend that lives in Discord and talks to you!

**How to do it:**

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click the big blue "New Application" button
3. Give it a fun name like "Arbitrage Bot" 🤖
4. Click "Create"!

5. On the left side, click "Bot"
6. Click "Add Bot" → "Yes, do it!"
7. Under "Privileged Gateway Intents", turn ON:
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT

8. Click "Reset Token" → Copy the token (it's like a super secret password!)
   - **IMPORTANT**: Save this somewhere safe! You'll need it soon!

9. On the left, click "OAuth2" → "URL Generator"
10. Check these boxes:
    - ✅ bot
    - ✅ applications.commands
11. Under "Bot Permissions", check:
    - ✅ Send Messages
    - ✅ Read Messages/View Channels
    - ✅ Add Reactions
12. Copy the URL at the bottom
13. Paste it in your browser and add the bot to your Discord server!

**What just happened?** You created a bot account and invited it to your Discord server!

---

### Step 3: Get API Keys from Kalshi

**What are we doing?** Getting special passwords so the bot can check prices on Kalshi.

**How to do it:**

1. Log in to [kalshi.com](https://kalshi.com)
2. Click your profile picture → "API Keys"
3. Click "Generate New API Key"
4. Copy both:
   - API Key (like a username)
   - API Secret (like a password)
5. Save them somewhere safe!

**What just happened?** You got the keys to let the bot see Kalshi prices!

---

### Step 4: Get API Keys from Polymarket

**What are we doing?** Same thing, but for Polymarket!

**How to do it:**

1. Log in to [polymarket.com](https://polymarket.com)
2. Go to Settings → API
3. Generate new API credentials
4. Copy your:
   - API Key
   - Private Key
5. Save them!

**What just happened?** Now the bot can see Polymarket prices too!

---

### Step 5: Set Up Your Configuration File

**What are we doing?** Filling in a form that tells the bot all your secret codes.

**How to do it:**

1. In the `codespace-template` folder, find the file called `.env.example`
2. Make a copy and rename it to `.env` (just remove the `.example` part)
3. Open `.env` with a text editor (Notepad on Windows, TextEdit on Mac)
4. Fill in the blanks:

```bash
# Discord Bot (from Step 2)
DISCORD_BOT_TOKEN=paste_your_discord_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here

# Kalshi (from Step 3)
KALSHI_API_KEY=paste_your_kalshi_api_key_here
KALSHI_API_SECRET=paste_your_kalshi_secret_here

# Polymarket (from Step 4)
POLYMARKET_API_KEY=paste_your_polymarket_key_here
POLYMARKET_PRIVATE_KEY=paste_your_polymarket_private_key_here

# Paper Trading - KEEP THIS AS true FOR NOW!
PAPER_TRADING_MODE=true
```

5. Save the file!

**Where do I find my Discord Channel ID?**
1. In Discord, right-click on the channel where you want bot messages
2. Click "Copy ID" (you might need to enable Developer Mode in Settings first)

**What just happened?** You gave the bot all the information it needs to work!

---

### Step 6: Install Docker (The Easy Way)

**What are we doing?** Installing a helper program that makes running the bot super easy!

**How to do it:**

1. Go to [https://www.docker.com/get-started](https://www.docker.com/get-started)
2. Download Docker Desktop for your computer
3. Install it (just like installing any app)
4. Open Docker Desktop - you'll see a whale icon 🐳

**What just happened?** You installed a program that packages everything the bot needs!

---

### Step 7: Start Your Database

**What are we doing?** Creating a memory bank where the bot stores information.

**How to do it:**

1. In your terminal (still in the `codespace-template` folder), type:
   ```bash
   docker-compose up -d postgres
   ```

2. Wait a few seconds for it to start!

**What just happened?** You created a database (like a super organized filing cabinet) for the bot!

---

## 🚀 Running Your Bot

**What are we doing?** Actually starting the bot!

### The Easy Way (With Docker):

```bash
docker-compose up -d
```

That's it! The bot is now running! 🎉

**To see if it's working:**
```bash
docker-compose logs -f arbitrage_app
```

You should see logs scrolling by!

### The Manual Way (Without Docker):

If you don't want to use Docker:

1. Install Python 3.11 from [python.org](https://python.org)
2. In terminal:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m src.main
   ```

---

## 💬 Using Discord Commands

**What are we doing?** Talking to your bot!

Go to the Discord channel where you added the bot and type:

### Basic Commands:

```
/help
```
Shows all available commands (like a menu at a restaurant)

```
/trading_mode
```
Checks if you're in paper mode (fake money) or live mode (real money)
**You should see "PAPER TRADING" - this is safe!** 🧪

```
/find_matches
```
Asks the bot to look for matching events on Kalshi and Polymarket

```
/paper_stats
```
Shows how well your fake trading is doing! Like checking your score in a video game 🎮

---

## 🧪 Understanding Paper Trading

**What is paper trading?**

Imagine playing a video game with fake money before playing with real money. That's paper trading!

- ✅ **Safe**: No real money at risk
- ✅ **Learning**: See how the bot works
- ✅ **Testing**: Make sure everything works right
- ✅ **Practice**: Learn the commands

**Your paper trading stats might look like this:**

```
📊 Paper Trading Statistics

💰 Balance
Starting: $10,000.00
Current: $10,234.50
Change: $234.50 (+2.35%)

📈 Trading Performance
Total Trades: 12
Successful: 11
Failed: 1
Win Rate: 91.7%
```

**What do these numbers mean?**
- **Starting Balance**: How much fake money you started with
- **Current Balance**: How much fake money you have now
- **Change**: Did you make or lose fake money?
- **Total Trades**: How many times the bot tried to make money
- **Win Rate**: What percentage of trades made money

**When should I switch to real money?**

❌ **NOT YET!** Stay in paper mode until:
- You've run it for at least a week
- You understand all the commands
- Your win rate is good (over 80%)
- You're comfortable with how it works

---

## 🎮 Your First Day With The Bot

**Here's what to do on Day 1:**

1. **Start the bot** (see "Running Your Bot" above)

2. **Check it's in paper mode:**
   ```
   /trading_mode
   ```
   You should see: "📄 PAPER TRADING"

3. **Look for matching events:**
   ```
   /find_matches
   ```

4. **When the bot suggests a match:**
   - Read both events carefully
   - Are they asking the same question?
   - Do they end at the same time?
   - If yes, click ✅
   - If no, click ❌

5. **Wait and watch!**
   - The bot will now monitor that pair
   - When it finds a good opportunity, it'll tell you!
   - It will make fake trades automatically

6. **Check your stats:**
   ```
   /paper_stats
   ```

7. **Let it run for a few days!**

---

## 🔧 Troubleshooting

### Problem: "Bot is not responding in Discord"

**What to check:**
1. Is the bot showing as "Online" in Discord? (It should have a green dot)
2. Did you copy the Discord token correctly in `.env`?
3. Try restarting:
   ```bash
   docker-compose restart
   ```

---

### Problem: "Can't find .env file"

**How to fix:**
1. You need to rename `.env.example` to `.env`
2. On Mac/Linux:
   ```bash
   cp .env.example .env
   ```
3. On Windows: Right-click `.env.example` → Rename → Remove `.example`

---

### Problem: "Database connection failed"

**How to fix:**
1. Make sure Docker is running (see the whale icon 🐳)
2. Restart the database:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

### Problem: "I see errors about API keys"

**How to fix:**
1. Open your `.env` file
2. Make sure there are NO spaces around the `=` sign
3. Make sure you didn't include any extra quotes
4. Should look like:
   ```
   KALSHI_API_KEY=abc123xyz
   ```
   NOT like:
   ```
   KALSHI_API_KEY = "abc123xyz"
   ```

---

### Problem: "The bot is making real trades!"

**STOP IMMEDIATELY:**
1. Open `.env`
2. Find this line:
   ```
   PAPER_TRADING_MODE=true
   ```
3. Make sure it says `true` NOT `false`
4. Restart the bot
5. Type `/trading_mode` to verify

---

## 🎓 Advanced Tips (For Later)

Once you're comfortable, you can:

### Adjust Settings:

In your `.env` file, you can change:

```bash
# How much profit you need to make a trade (1% = 0.01)
MIN_ARBITRAGE_THRESHOLD=0.01

# How much money to use per trade
MAX_TRADE_SIZE=1000

# How fast to check prices (in seconds)
PRICE_FETCH_INTERVAL=5
```

**What do these mean?**
- **MIN_ARBITRAGE_THRESHOLD**: Only trade if we can make at least this much profit (1% = make $1 for every $100)
- **MAX_TRADE_SIZE**: The most money to use in one trade
- **PRICE_FETCH_INTERVAL**: How many seconds to wait between checking prices

---

## 📞 Need More Help?

**Things to try:**
1. Check the main `README.md` for more details
2. Look at the logs: `docker-compose logs -f arbitrage_app`
3. Ask in the Discord where you found this project
4. Open an issue on GitHub

---

## 🎉 Congratulations!

You've set up your arbitrage bot! Here's what happens next:

1. **Week 1-2**: Let it run in paper mode. Watch and learn.
2. **Week 3-4**: Check your paper stats. Are you making fake profit?
3. **After testing**: If everything looks good and you understand it fully, THEN consider real trading.

Remember: **There's no rush!** Paper trading is completely free and safe. Take your time! 🌟

---

## 🔒 Safety Reminders

- ✅ Always start in paper mode
- ✅ Never share your API keys with anyone
- ✅ Keep your `.env` file private
- ✅ Test everything with fake money first
- ✅ Start with small amounts when you go live
- ⚠️ Only invest money you can afford to lose
- ⚠️ This is not financial advice - do your own research!

---

**Happy Trading! 🚀**

Remember: The best traders are patient and careful. Take your time, learn the system, and don't rush! You've got this! 💪
