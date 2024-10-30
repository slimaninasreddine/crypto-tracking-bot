import time
import requests
import telebot
import numpy as np
from datetime import datetime, timedelta
from collections import deque
import json
import os
import threading
import configparser  # Import configparser to read the .conf file


# Load configuration
config = configparser.ConfigParser()
config.read('config.conf')

# API and Bot Configuration
API_KEY = config['API']['API_KEY']
BASE_URL = config['API']['BASE_URL']
HEADERS = {'X-CMC_PRO_API_KEY': API_KEY}
BOT_TOKEN = config['BOT']['BOT_TOKEN']

bot = telebot.TeleBot(BOT_TOKEN)

# Opportunity History Manager
class OpportunityManager:
    def __init__(self, max_opportunities=10):
        self.max_opportunities = max_opportunities
        self.opportunities = deque(maxlen=max_opportunities)
        self.last_alert_time = datetime.now()
        self.opportunity_file = 'opportunity_history.json'
        self.load_opportunities()

    def load_opportunities(self):
        """Load previous opportunities from file"""
        try:
            if os.path.exists(self.opportunity_file):
                with open(self.opportunity_file, 'r') as f:
                    data = json.load(f)
                    self.opportunities = deque(data['opportunities'], maxlen=self.max_opportunities)
                    self.last_alert_time = datetime.fromtimestamp(data['last_alert_time'])
        except Exception as e:
            print(f"Error loading opportunities: {e}")
            self.opportunities = deque(maxlen=self.max_opportunities)
            self.last_alert_time = datetime.now()

    def save_opportunities(self):
        """Save opportunities to file"""
        try:
            data = {
                'opportunities': list(self.opportunities),
                'last_alert_time': self.last_alert_time.timestamp()
            }
            with open(self.opportunity_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving opportunities: {e}")

    def add_opportunity(self, opportunity):
        """Add new opportunity with timestamp"""
        opportunity['timestamp'] = datetime.now().timestamp()
        self.opportunities.append(opportunity)
        self.save_opportunities()

    def get_recent_opportunities(self):
        """Get last 10 opportunities"""
        return list(self.opportunities)

    def should_send_alert(self):
        """Check if 60 minutes have passed since last alert"""
        now = datetime.now()
        if (now - self.last_alert_time).total_seconds() >= 3600:  # 60 minutes
            self.last_alert_time = now
            self.save_opportunities()
            return True
        return False
class PriceHistoryManager:
    def __init__(self, max_history_size=288):  # 24 hours of 5-minute intervals
        self.max_history_size = max_history_size
        self.price_history = {}  # Dictionary to store price history for each symbol
        self.volume_history = {}  # Dictionary to store volume history for each symbol

    def add_data_point(self, symbol, price, volume):
        """Add new price and volume data point for a symbol"""
        # Initialize lists if symbol not present
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.volume_history[symbol] = []
        
        # Add new data points
        self.price_history[symbol].append(price)
        self.volume_history[symbol].append(volume)
        
        # Maintain maximum size
        if len(self.price_history[symbol]) > self.max_history_size:
            self.price_history[symbol].pop(0)
        if len(self.volume_history[symbol]) > self.max_history_size:
            self.volume_history[symbol].pop(0)

    def get_price_history(self, symbol):
        """Get price history for a symbol"""
        return self.price_history.get(symbol, [])

    def get_volume_history(self, symbol):
        """Get volume history for a symbol"""
        return self.volume_history.get(symbol, [])

    def get_history_length(self, symbol):
        """Get the number of data points available for a symbol"""
        return len(self.price_history.get(symbol, []))

    def clear_history(self, symbol=None):
        """Clear history for a specific symbol or all symbols"""
        if symbol:
            self.price_history.pop(symbol, None)
            self.volume_history.pop(symbol, None)
        else:
            self.price_history.clear()
            self.volume_history.clear()

# Initialize managers
history_manager = PriceHistoryManager(max_history_size=288)  # 24 hours of 5-minute intervals
opportunity_manager = OpportunityManager(max_opportunities=10)

class CryptoAnalyzer:
    @staticmethod
    def calculate_confidence_score(current_price, volume_24h, price_history, volume_history):
        """Calculate confidence score based on available data"""
        if not price_history or len(price_history) < 2:
            return 50.0  # Default score for insufficient data

        # Price stability (using available history)
        price_changes = np.diff(price_history) / price_history[:-1] * 100
        price_volatility = np.std(price_changes) if len(price_changes) > 0 else 0
        stability_score = max(0, min(100 - price_volatility, 100)) * 0.3

        # Volume consistency
        volume_consistency = np.std(volume_history) / np.mean(volume_history) if volume_history else 1
        volume_score = max(0, min(100 - volume_consistency * 100, 100)) * 0.3

        # Trend strength
        if len(price_history) >= 12:  # At least 1 hour of data (5-minute intervals)
            recent_trend = (current_price - price_history[-12]) / price_history[-12] * 100
            trend_score = min(abs(recent_trend), 100) * 0.4
        else:
            trend_score = 50 * 0.4

        total_score = stability_score + volume_score + trend_score
        return round(total_score, 2)

    @staticmethod
    def calculate_simple_moving_average(data, period):
        """Calculate Simple Moving Average"""
        if len(data) < period:
            return None
        return np.mean(data[-period:])

    @staticmethod
    def calculate_rsi(prices, periods=14):
        """Calculate Relative Strength Index"""
        if len(prices) < periods + 1:
            return None
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-periods:])
        avg_loss = np.mean(losses[-periods:])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)

def get_top_coins():
    """Fetch coins with free tier API"""
    try:
        params = {
            'sort': 'volume_24h',
            'limit': 200,  # Reduced limit for free tier
            'convert': 'USD'
        }
        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()['data']
    except Exception as e:
        print(f"Error fetching coin data: {e}")
        return []

def track_price_changes(threshold=1):
    """Track price changes and store significant opportunities"""
    significant_changes = []
    
    coins = get_top_coins()
    current_time = datetime.now()
    
    for coin in coins:
        symbol = coin['symbol']
        current_price = coin['quote']['USD']['price']
        current_volume = coin['quote']['USD']['volume_24h']
        
        history_manager.add_data_point(symbol, current_price, current_volume)
        price_history = history_manager.get_price_history(symbol)
        volume_history = history_manager.get_volume_history(symbol)
        
        if len(price_history) >= 2:
            price_change = ((current_price - price_history[-2]) / price_history[-2]) * 100
            
            if price_change >= threshold:
                confidence = CryptoAnalyzer.calculate_confidence_score(
                    current_price, current_volume, price_history, volume_history
                )
                
                opportunity = {
                    'symbol': symbol,
                    'price_change': price_change,
                    'current_price': current_price,
                    'volume_24h': current_volume,
                    'confidence_score': confidence,
                    'time': current_time.strftime('%Y-%m-%d %H:%M:%S')
                }
                
                significant_changes.append(opportunity)
                opportunity_manager.add_opportunity(opportunity)
    
    return significant_changes



def format_alert_message(opportunities):
    """Format opportunities for alert message"""
    message = "⏰ Hourly Crypto Alert - Top Opportunities:\n\n"
    
    for idx, opp in enumerate(opportunities, 1):
        time_str = datetime.fromtimestamp(opp['timestamp']).strftime('%H:%M:%S')
        message += (
            f"{idx}. {opp['symbol']} ({time_str})\n"
            f"📈 {opp['price_change']:.2f}% | "
            f"💰 ${opp['current_price']:.4f} | "
            f"🎯 {opp['confidence_score']}%\n\n"
        )
    
    return message

class ChatManager:
    def __init__(self):
        self.subscribed_chats = set()
        self.chats_file = 'subscribed_chats.json'
        self.load_chats()
    
    def load_chats(self):
        """Load subscribed chats from file"""
        try:
            if os.path.exists(self.chats_file):
                with open(self.chats_file, 'r') as f:
                    self.subscribed_chats = set(json.load(f))
        except Exception as e:
            print(f"Error loading chats: {e}")
            self.subscribed_chats = set()
    
    def save_chats(self):
        """Save subscribed chats to file"""
        try:
            with open(self.chats_file, 'w') as f:
                json.dump(list(self.subscribed_chats), f)
        except Exception as e:
            print(f"Error saving chats: {e}")
    
    def add_chat(self, chat_id):
        """Add a new chat subscription"""
        self.subscribed_chats.add(chat_id)
        self.save_chats()
    
    def remove_chat(self, chat_id):
        """Remove a chat subscription"""
        self.subscribed_chats.discard(chat_id)
        self.save_chats()
# Initialize chat manager
chat_manager = ChatManager()

def send_periodic_alert():
    """Send alerts every 60 minutes with recent opportunities"""
    while True:
        try:
            if opportunity_manager.should_send_alert():
                recent_opps = opportunity_manager.get_recent_opportunities()
                
                if recent_opps:
                    message = format_alert_message(recent_opps)
                    chat_id = "NoahSwitch_Bot"
                    bot.send_message(chat_id, message)
            
            time.sleep(300)  # Check every 5 minutes
        except Exception as e:
            print(f"Error in periodic alert: {e}")
            time.sleep(60)
def monitor_price_changes():
    """Continuously monitor price changes"""
    while True:
        try:
            # Track significant price changes
            significant_changes = track_price_changes(threshold=1)
            
            # If there are significant changes, log them
            if significant_changes:
                print(f"Found {len(significant_changes)} significant changes")
                for change in significant_changes:
                    print(f"{change['symbol']}: {change['price_change']:.2f}% change, "
                          f"Confidence: {change['confidence_score']}%")
            
            # Sleep for 50 minutes before next check
            time.sleep(300)  # 5 minutes
            
        except Exception as e:
            print(f"Error in price monitoring: {e}")
            time.sleep(60)  # Wait 1 minute before retrying if there's an error

def run_bot():
    """Run the Telegram bot"""
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(10)



@bot.message_handler(commands=['subscribe'])
def subscribe(message):
    """Subscribe to alerts"""
    chat_manager.add_chat(message.chat.id)
    bot.reply_to(message, "✅ You've been subscribed to crypto alerts!")

@bot.message_handler(commands=['unsubscribe'])
def unsubscribe(message):
    """Unsubscribe from alerts"""
    chat_manager.remove_chat(message.chat.id)
    bot.reply_to(message, "❌ You've been unsubscribed from crypto alerts.")

def send_periodic_alert():
    """Send alerts every 60 minutes with recent opportunities"""
    while True:
        try:
            if opportunity_manager.should_send_alert():
                recent_opps = opportunity_manager.get_recent_opportunities()
                
                if recent_opps:
                    message = format_alert_message(recent_opps)
                    
                    # Send to all subscribed chats
                    for chat_id in chat_manager.subscribed_chats:
                        try:
                            bot.send_message(chat_id, message)
                        except Exception as e:
                            print(f"Error sending alert to {chat_id}: {e}")
            
            time.sleep(300)  # Check every 5 minutes
        except Exception as e:
            print(f"Error in periodic alert: {e}")
            time.sleep(60)

# Update start command to include subscription information
@bot.message_handler(commands=['start'])
def start(message):
    welcome_message = (
        "🤖 Welcome to the Crypto Tracking Bot!\n\n"
        "Commands:\n"
        "/subscribe - Subscribe to hourly alerts\n"
        "/unsubscribe - Unsubscribe from alerts\n"
        "/opportunities - View last 10 crypto opportunities\n\n"
        "Features:\n"
        "• Tracks last 10 significant opportunities\n"
        "• 60-minute alert interval\n"
        "• Real-time price tracking\n"
        "• Volume analysis\n"
        "• Confidence scoring\n"
    )
    bot.send_message(message.chat.id, welcome_message)
    
@bot.message_handler(commands=['opportunities'])
def show_opportunities(message):
    """Show the last 10 crypto opportunities"""
    recent_opps = opportunity_manager.get_recent_opportunities()
    
    if recent_opps:
        message_text = format_alert_message(recent_opps)
    else:
        message_text = "❌ No recent opportunities to display."
    
    bot.send_message(message.chat.id, message_text)

if __name__ == '__main__':
    try:
        # Create and start price monitoring thread
        price_monitor_thread = threading.Thread(target=monitor_price_changes)
        price_monitor_thread.daemon = True
        price_monitor_thread.start()
        
        # Create and start alert thread
        alert_thread = threading.Thread(target=send_periodic_alert)
        alert_thread.daemon = True
        alert_thread.start()
        
        # Run the bot in the main thread
        run_bot()
        
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"Critical error: {e}")