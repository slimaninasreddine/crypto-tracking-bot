# Crypto Tracking Bot

## Overview

The Crypto Tracking Bot is a Telegram bot that monitors cryptocurrency prices and alerts users about significant price changes and opportunities. It leverages the CoinMarketCap API to fetch real-time cryptocurrency data and provides alerts based on user-defined criteria.

## Features

- Real-time price tracking
- Confidence scoring based on price and volume history
- Subscription system for alerts
- Tracks last 10 significant opportunities
- Sends hourly alerts

## Installation

-  Clone the repository:
   ```bash
   git clone */crypto-tracking-bot.git
   cd crypto-tracking-bot
-  Create a configuration file named config.conf in the project directory and populate it with your API key and bot token as shown below:

[API]
API_KEY = your_api_key_here
 BASE_URL = https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest
[BOT]
 BOT_TOKEN = your_bot_token_here

-  Install the required libraries:
pip install requests telebot numpy

## Usage

- Start the bot by running:

python your_script.py

- Use the following commands in Telegram:
- /subscribe - Subscribe to hourly alerts
- /unsubscribe - Unsubscribe from alerts
- /opportunities - View the last 10 crypto opportunities

## Contributing
- If you want to contribute to this project, feel free to fork the repository and submit a pull request.
