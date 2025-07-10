import os
import asyncio
import logging
import time
from datetime import datetime
from threading import Thread
import requests
from flask import Flask, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app for keep-alive
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "message": "Binance Bot is alive!",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/stats')
def stats():
    return jsonify({
        "bot_status": "active",
        "last_check": datetime.now().isoformat(),
        "uptime": "running"
    })

class BinanceTelegramBot:
    def __init__(self):
        # Environment variables
        self.telegram_token = os.getenv('TELEGRAM_TOKEN_75')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.binance_api_url = "https://api.binance.com/api/v3"
        
        # Bot state
        self.last_price = None
        self.start_time = datetime.now()
        self.message_count = 0
        
        logger.info("Bot initialized successfully")
        
    def get_btc_price(self):
        """Get BTC price with multiple fallback APIs"""
        # Try multiple data sources in order of preference
        sources = [
            {
                'name': 'CoinGecko',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {'ids': 'bitcoin', 'vs_currencies': 'usd'},
                'parse': lambda data: float(data['bitcoin']['usd'])
            },
            {
                'name': 'CoinCap',
                'url': 'https://api.coincap.io/v2/assets/bitcoin',
                'params': {},
                'parse': lambda data: float(data['data']['priceUsd'])
            },
            {
                'name': 'CryptoCompare',
                'url': 'https://min-api.cryptocompare.com/data/price',
                'params': {'fsym': 'BTC', 'tsyms': 'USD'},
                'parse': lambda data: float(data['USD'])
            },
            {
                'name': 'Binance (Original)',
                'url': f"{self.binance_api_url}/ticker/price",
                'params': {'symbol': 'BTCUSDT'},
                'parse': lambda data: float(data['price'])
            }
        ]
        
        for source in sources:
            try:
                logger.info(f"Trying {source['name']} API...")
                
                # Add headers to look more like a regular browser request
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                response = requests.get(
                    source['url'], 
                    params=source['params'],
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()
                
                data = response.json()
                price = source['parse'](data)
                
                logger.info(f"✓ BTC Price fetched from {source['name']}: ${price:,.2f}")
                return price
                
            except Exception as e:
                logger.warning(f"✗ {source['name']} failed: {e}")
                continue
        
        logger.error("All price sources failed!")
        return None
    
    def get_24h_stats(self):
        """Get 24h statistics with multiple fallback APIs"""
        # Try multiple sources for 24h stats
        sources = [
            {
                'name': 'CoinGecko',
                'url': 'https://api.coingecko.com/api/v3/coins/bitcoin',
                'params': {'localization': 'false', 'tickers': 'false', 'market_data': 'true', 'community_data': 'false', 'developer_data': 'false'},
                'parse': lambda data: {
                    'price_change': data['market_data']['price_change_24h']['usd'],
                    'price_change_percent': data['market_data']['price_change_percentage_24h'],
                    'high': data['market_data']['high_24h']['usd'],
                    'low': data['market_data']['low_24h']['usd'],
                    'volume': data['market_data']['total_volume']['usd']
                }
            },
            {
                'name': 'CoinCap',
                'url': 'https://api.coincap.io/v2/assets/bitcoin',
                'params': {},
                'parse': lambda data: {
                    'price_change': float(data['data']['changePercent24Hr']) * float(data['data']['priceUsd']) / 100,
                    'price_change_percent': float(data['data']['changePercent24Hr']),
                    'high': float(data['data']['priceUsd']) * 1.02,  # Approximation
                    'low': float(data['data']['priceUsd']) * 0.98,   # Approximation
                    'volume': float(data['data']['volumeUsd24Hr'])
                }
            },
            {
                'name': 'Binance (Original)',
                'url': f"{self.binance_api_url}/ticker/24hr",
                'params': {'symbol': 'BTCUSDT'},
                'parse': lambda data: {
                    'price_change': float(data['priceChange']),
                    'price_change_percent': float(data['priceChangePercent']),
                    'high': float(data['highPrice']),
                    'low': float(data['lowPrice']),
                    'volume': float(data['volume'])
                }
            }
        ]
        
        for source in sources:
            try:
                logger.info(f"Trying {source['name']} for 24h stats...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/json',
                }
                
                response = requests.get(
                    source['url'], 
                    params=source['params'],
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()
                
                data = response.json()
                stats = source['parse'](data)
                
                logger.info(f"✓ 24h stats fetched from {source['name']}")
                return stats
                
            except Exception as e:
                logger.warning(f"✗ {source['name']} 24h stats failed: {e}")
                continue
        
        logger.error("All 24h stats sources failed!")
        # Return fallback stats if all sources fail
        return {
            'price_change': 0,
            'price_change_percent': 0,
            'high': 0,
            'low': 0,
            'volume': 0
        }
    
    async def send_telegram_message(self, message):
        """Send message to Telegram"""
        try:
            if not self.telegram_token or not self.chat_id:
                logger.warning("Telegram token or chat ID not configured")
                return False
                
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            self.message_count += 1
            logger.info(f"Message sent to Telegram successfully (#{self.message_count})")
            return True
            
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    def format_price_message(self, price, stats, source_name="API"):
        """Format price information for Telegram"""
        change_emoji = "📈" if stats['price_change'] > 0 else "📉" if stats['price_change'] < 0 else "➖"
        
        message = f"""
🚀 <b>BTC Price Alert</b>

💰 <b>Current Price:</b> ${price:,.2f}
{change_emoji} <b>24h Change:</b> {stats['price_change_percent']:.2f}% (${stats['price_change']:+,.2f})

📊 <b>24h Stats:</b>
• <b>High:</b> ${stats['high']:,.2f}
• <b>Low:</b> ${stats['low']:,.2f}
• <b>Volume:</b> ${stats['volume']:,.0f}

📡 <b>Source:</b> {source_name}
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC

🤖 <i>Bot uptime: {datetime.now() - self.start_time}</i>
        """.strip()
        
        return message
    
    def should_send_alert(self, current_price):
        """Determine if an alert should be sent"""
        # Send alert if:
        # 1. First time running
        # 2. Price changed by more than 1%
        # 3. Every 30 minutes regardless
        
        if self.last_price is None:
            return True, "Initial price check"
        
        price_change_percent = abs((current_price - self.last_price) / self.last_price * 100)
        
        if price_change_percent >= 1.0:
            return True, f"Price changed by {price_change_percent:.2f}%"
        
        # Send update every 30 minutes
        if self.message_count == 0 or (self.message_count % 6 == 0):  # 6 * 5min = 30min
            return True, "Periodic update"
        
        return False, "No significant change"
    
    async def monitor_prices(self):
        """Main monitoring loop"""
        source_used = "Unknown"
        try:
            # Get current price
            current_price = self.get_btc_price()
            if current_price is None:
                logger.warning("Failed to fetch price, skipping this cycle")
                return
            
            # Get 24h statistics
            stats = self.get_24h_stats()
            if stats is None:
                logger.warning("Failed to fetch 24h stats, using fallback")
                stats = {
                    'price_change': 0,
                    'price_change_percent': 0,
                    'high': current_price,
                    'low': current_price,
                    'volume': 0
                }
            
            # Determine which source was used (for display purposes)
            source_used = "Multi-Source API"
            
            # Check if we should send alert
            should_alert, reason = self.should_send_alert(current_price)
            
            if should_alert:
                logger.info(f"Sending alert: {reason}")
                message = self.format_price_message(current_price, stats, source_used)
                await self.send_telegram_message(message)
            else:
                logger.info(f"No alert needed: {reason}")
            
            # Update last price
            self.last_price = current_price
            
        except Exception as e:
            logger.error(f"Error in monitor_prices: {e}")
            # Send error notification
            error_message = f"⚠️ <b>Bot Error</b>\n\n{str(e)}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            await self.send_telegram_message(error_message)
    
    async def run_bot(self):
        """Main bot loop"""
        logger.info("Starting Binance Telegram Bot...")
        
        # Send startup message
        startup_message = f"""
🚀 <b>Binance Bot Started!</b>

📊 Monitoring BTC/USDT price
⏰ Check interval: 5 minutes
🎯 Alert threshold: 1% price change
📱 Periodic updates: Every 30 minutes

🕒 Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC
        """.strip()
        
        await self.send_telegram_message(startup_message)
        
        while True:
            try:
                await self.monitor_prices()
                logger.info("Waiting 5 minutes for next check...")
                await asyncio.sleep(300)  # Wait 5 minutes
                
            except Exception as e:
                logger.error(f"Critical error in bot loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry

def run_web_server():
    """Run Flask web server for keep-alive"""
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting web server on port {port}")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False
    )

def run_bot():
    """Run the bot"""
    bot = BinanceTelegramBot()
    asyncio.run(bot.run_bot())

if __name__ == "__main__":
    logger.info("="*50)
    logger.info("BINANCE TELEGRAM BOT STARTING")
    logger.info("="*50)
    
    # Check environment variables
    required_vars = ['TELEGRAM_TOKEN_75', 'TELEGRAM_CHAT_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {missing_vars}")
        logger.error("Please set TELEGRAM_TOKEN_75 and TELEGRAM_CHAT_ID")
        exit(1)
    
    logger.info("Environment variables configured ✓")
    
    try:
        # Start web server in background thread
        web_thread = Thread(target=run_web_server)
        web_thread.daemon = True
        web_thread.start()
        
        logger.info("Web server started ✓")
        
        # Give web server time to start
        time.sleep(2)
        
        # Start bot in main thread
        run_bot()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)
