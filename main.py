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
        "message": "Multi-Currency Binance Bot is alive!",
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

class MultiCurrencyTelegramBot:
    def __init__(self):
        # Environment variables
        self.telegram_token = os.getenv('TELEGRAM_TOKEN_75')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Supported cryptocurrencies with their API mappings
        self.currencies = {
            'BTC': {
                'name': 'Bitcoin',
                'symbol': 'BTC',
                'coingecko_id': 'bitcoin',
                'binance_symbol': 'BTCUSDT',
                'emoji': '🟠',
                'threshold': 1.0  # 1% change threshold
            },
            'TRB': {
                'name': 'Tellor',
                'symbol': 'TRB',
                'coingecko_id': 'tellor',
                'binance_symbol': 'TRBUSDT',
                'emoji': '🔷',
                'threshold': 2.0  # 2% change threshold for smaller coins
            },
            'ARB': {
                'name': 'Arbitrum',
                'symbol': 'ARB',
                'coingecko_id': 'arbitrum',
                'binance_symbol': 'ARBUSDT',
                'emoji': '🔵',
                'threshold': 2.0
            },
            'ENA': {
                'name': 'Ethena',
                'symbol': 'ENA',
                'coingecko_id': 'ethena',
                'binance_symbol': 'ENAUSDT',
                'emoji': '🟢',
                'threshold': 3.0  # Higher threshold for newer/volatile coins
            },
            'ETH': {
                'name': 'Ethereum',
                'symbol': 'ETH',
                'coingecko_id': 'ethereum',
                'binance_symbol': 'ETHUSDT',
                'emoji': '🔹',
                'threshold': 1.5
            }
        }
        
        # Bot state - track each currency separately
        self.last_prices = {}
        self.start_time = datetime.now()
        self.message_count = 0
        self.price_alerts_sent = {symbol: 0 for symbol in self.currencies.keys()}
        
        # Initialize last prices
        for symbol in self.currencies.keys():
            self.last_prices[symbol] = None
        
        logger.info(f"Multi-currency bot initialized for: {', '.join(self.currencies.keys())}")
        
    def get_crypto_prices_bulk(self):
        """Get prices for all cryptocurrencies in bulk"""
        # Try multiple data sources for bulk price fetching
        sources = [
            {
                'name': 'CoinGecko Bulk',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {
                    'ids': ','.join([self.currencies[symbol]['coingecko_id'] for symbol in self.currencies.keys()]),
                    'vs_currencies': 'usd'
                },
                'parse': self._parse_coingecko_bulk
            },
            {
                'name': 'CryptoCompare Bulk',
                'url': 'https://min-api.cryptocompare.com/data/pricemulti',
                'params': {
                    'fsyms': ','.join(self.currencies.keys()),
                    'tsyms': 'USD'
                },
                'parse': self._parse_cryptocompare_bulk
            }
        ]
        
        for source in sources:
            try:
                logger.info(f"Trying {source['name']} API...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                }
                
                response = requests.get(
                    source['url'], 
                    params=source['params'],
                    headers=headers,
                    timeout=15
                )
                response.raise_for_status()
                
                data = response.json()
                prices = source['parse'](data)
                
                if prices:
                    logger.info(f"✓ Bulk prices fetched from {source['name']}")
                    for symbol, price in prices.items():
                        if price:
                            logger.info(f"  {symbol}: ${price:,.4f}")
                    return prices
                
            except Exception as e:
                logger.warning(f"✗ {source['name']} failed: {e}")
                continue
        
        # Fallback to individual API calls
        logger.info("Falling back to individual API calls...")
        return asyncio.run(self._get_individual_prices())
    
    def _parse_coingecko_bulk(self, data):
        """Parse CoinGecko bulk price response"""
        prices = {}
        try:
            for symbol, config in self.currencies.items():
                coingecko_id = config['coingecko_id']
                if coingecko_id in data and 'usd' in data[coingecko_id]:
                    prices[symbol] = float(data[coingecko_id]['usd'])
        except Exception as e:
            logger.error(f"Error parsing CoinGecko bulk data: {e}")
        return prices
    
    def _parse_cryptocompare_bulk(self, data):
        """Parse CryptoCompare bulk price response"""
        prices = {}
        try:
            for symbol in self.currencies.keys():
                if symbol in data and 'USD' in data[symbol]:
                    prices[symbol] = float(data[symbol]['USD'])
        except Exception as e:
            logger.error(f"Error parsing CryptoCompare bulk data: {e}")
        return prices
    
    async def _get_individual_prices(self):
        """Fallback method to get prices individually"""
        prices = {}
        
        for symbol, config in self.currencies.items():
            try:
                # Try CoinGecko individual API
                url = 'https://api.coingecko.com/api/v3/simple/price'
                params = {'ids': config['coingecko_id'], 'vs_currencies': 'usd'}
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                }
                
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                if config['coingecko_id'] in data and 'usd' in data[config['coingecko_id']]:
                    prices[symbol] = float(data[config['coingecko_id']]['usd'])
                    logger.info(f"✓ Individual price for {symbol}: ${prices[symbol]:,.4f}")
                
                # Small delay between requests to avoid rate limiting
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.warning(f"✗ Individual price fetch failed for {symbol}: {e}")
                prices[symbol] = None
        
        return prices
    
    def get_24h_stats_bulk(self):
        """Get 24h statistics for all currencies"""
        sources = [
            {
                'name': 'CoinGecko Bulk Stats',
                'url': 'https://api.coingecko.com/api/v3/simple/price',
                'params': {
                    'ids': ','.join([self.currencies[symbol]['coingecko_id'] for symbol in self.currencies.keys()]),
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true',
                    'include_24hr_vol': 'true'
                },
                'parse': self._parse_coingecko_stats_bulk
            },
            {
                'name': 'CryptoCompare Full Stats',
                'url': 'https://min-api.cryptocompare.com/data/pricemultifull',
                'params': {
                    'fsyms': ','.join(self.currencies.keys()),
                    'tsyms': 'USD'
                },
                'parse': self._parse_cryptocompare_stats_bulk
            }
        ]
        
        for source in sources:
            try:
                logger.info(f"Trying {source['name']} for bulk 24h stats...")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json',
                }
                
                response = requests.get(
                    source['url'], 
                    params=source['params'],
                    headers=headers,
                    timeout=15
                )
                response.raise_for_status()
                
                data = response.json()
                stats = source['parse'](data)
                
                if stats:
                    logger.info(f"✓ Bulk 24h stats fetched from {source['name']}")
                    return stats
                
            except Exception as e:
                logger.warning(f"✗ {source['name']} bulk stats failed: {e}")
                continue
        
        # Return fallback stats
        logger.error("All bulk stats sources failed!")
        return {symbol: self._get_fallback_stats() for symbol in self.currencies.keys()}
    
    def _parse_coingecko_stats_bulk(self, data):
        """Parse CoinGecko bulk stats response"""
        stats = {}
        try:
            for symbol, config in self.currencies.items():
                coingecko_id = config['coingecko_id']
                if coingecko_id in data:
                    coin_data = data[coingecko_id]
                    current_price = float(coin_data.get('usd', 0))
                    change_24h = float(coin_data.get('usd_24h_change', 0))
                    volume_24h = float(coin_data.get('usd_24h_vol', 0))
                    
                    stats[symbol] = {
                        'price_change': change_24h * current_price / 100 if change_24h != 0 else 0,
                        'price_change_percent': change_24h,
                        'high': current_price * 1.02,  # Approximation
                        'low': current_price * 0.98,   # Approximation
                        'volume': volume_24h
                    }
        except Exception as e:
            logger.error(f"Error parsing CoinGecko bulk stats: {e}")
        return stats
    
    def _parse_cryptocompare_stats_bulk(self, data):
        """Parse CryptoCompare bulk stats response"""
        stats = {}
        try:
            if 'RAW' in data:
                for symbol in self.currencies.keys():
                    if symbol in data['RAW'] and 'USD' in data['RAW'][symbol]:
                        coin_data = data['RAW'][symbol]['USD']
                        stats[symbol] = {
                            'price_change': float(coin_data.get('CHANGE24HOUR', 0)),
                            'price_change_percent': float(coin_data.get('CHANGEPCT24HOUR', 0)),
                            'high': float(coin_data.get('HIGH24HOUR', 0)),
                            'low': float(coin_data.get('LOW24HOUR', 0)),
                            'volume': float(coin_data.get('VOLUME24HOUR', 0))
                        }
        except Exception as e:
            logger.error(f"Error parsing CryptoCompare bulk stats: {e}")
        return stats
    
    def _get_fallback_stats(self):
        """Get fallback stats when all sources fail"""
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
    
    def format_single_currency_message(self, symbol, price, stats):
        """Format single currency alert message"""
        config = self.currencies[symbol]
        change_emoji = "📈" if stats['price_change'] > 0 else "📉" if stats['price_change'] < 0 else "➖"
        
        # Handle cases where stats might be 0 or None
        price_change = stats.get('price_change', 0)
        price_change_percent = stats.get('price_change_percent', 0)
        high_price = stats.get('high', price)
        low_price = stats.get('low', price)
        volume = stats.get('volume', 0)
        
        message = f"""
🚨 <b>{config['emoji']} {config['name']} ({symbol}) Alert</b>

💰 <b>Current Price:</b> ${price:,.4f}
{change_emoji} <b>24h Change:</b> {price_change_percent:.2f}% (${price_change:+,.4f})

📊 <b>24h Stats:</b>
• <b>High:</b> ${high_price:,.4f}
• <b>Low:</b> ${low_price:,.4f}
• <b>Volume:</b> ${volume:,.0f}

⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
        """.strip()
        
        return message
    
    def format_multi_currency_summary(self, prices, stats):
        """Format multi-currency summary message"""
        message = f"""
📊 <b>Multi-Currency Price Summary</b>

"""
        
        for symbol, price in prices.items():
            if price is None:
                continue
                
            config = self.currencies[symbol]
            symbol_stats = stats.get(symbol, self._get_fallback_stats())
            change_emoji = "📈" if symbol_stats['price_change'] > 0 else "📉" if symbol_stats['price_change'] < 0 else "➖"
            
            price_change_percent = symbol_stats.get('price_change_percent', 0)
            
            message += f"""
{config['emoji']} <b>{symbol}</b>: ${price:,.4f} {change_emoji} {price_change_percent:+.2f}%"""
        
        message += f"""


⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
🤖 <b>Bot uptime:</b> {datetime.now() - self.start_time}
        """
        
        return message.strip()
    
    def should_send_individual_alert(self, symbol, current_price):
        """Determine if an individual currency alert should be sent"""
        config = self.currencies[symbol]
        threshold = config['threshold']
        
        # Send alert if:
        # 1. First time running
        # 2. Price changed by more than threshold%
        
        if self.last_prices[symbol] is None:
            return True, f"Initial price check for {symbol}"
        
        price_change_percent = abs((current_price - self.last_prices[symbol]) / self.last_prices[symbol] * 100)
        
        if price_change_percent >= threshold:
            return True, f"{symbol} price changed by {price_change_percent:.2f}%"
        
        return False, f"No significant change for {symbol}"
    
    def should_send_summary_alert(self):
        """Determine if a summary alert should be sent"""
        # Send summary every 30 minutes
        if self.message_count % 6 == 0:  # 6 * 5min = 30min
            return True, "Periodic summary update"
        
        return False, "No summary needed"
    
    async def monitor_prices(self):
        """Main monitoring loop"""
        try:
            # Get current prices for all currencies
            current_prices = self.get_crypto_prices_bulk()
            if not current_prices:
                logger.warning("Failed to fetch any prices, skipping this cycle")
                return
            
            # Get 24h statistics for all currencies
            stats = self.get_24h_stats_bulk()
            
            # Check for individual currency alerts
            individual_alerts = []
            for symbol, price in current_prices.items():
                if price is None:
                    continue
                
                should_alert, reason = self.should_send_individual_alert(symbol, price)
                if should_alert:
                    individual_alerts.append((symbol, price, reason))
            
            # Send individual alerts
            for symbol, price, reason in individual_alerts:
                logger.info(f"Sending individual alert for {symbol}: {reason}")
                symbol_stats = stats.get(symbol, self._get_fallback_stats())
                message = self.format_single_currency_message(symbol, price, symbol_stats)
                await self.send_telegram_message(message)
                self.price_alerts_sent[symbol] += 1
                
                # Small delay between messages
                await asyncio.sleep(1)
            
            # Check for summary alert
            should_summary, summary_reason = self.should_send_summary_alert()
            if should_summary and not individual_alerts:  # Only send summary if no individual alerts
                logger.info(f"Sending summary alert: {summary_reason}")
                message = self.format_multi_currency_summary(current_prices, stats)
                await self.send_telegram_message(message)
            
            # Update last prices
            for symbol, price in current_prices.items():
                if price is not None:
                    self.last_prices[symbol] = price
            
        except Exception as e:
            logger.error(f"Error in monitor_prices: {e}")
            # Send error notification
            error_message = f"⚠️ <b>Multi-Currency Bot Error</b>\n\n{str(e)}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            await self.send_telegram_message(error_message)
    
    async def run_bot(self):
        """Main bot loop"""
        logger.info("Starting Multi-Currency Telegram Bot...")
        
        # Send startup message
        currency_list = '\n'.join([f"{config['emoji']} {config['name']} ({symbol})" for symbol, config in self.currencies.items()])
        
        startup_message = f"""
🚀 <b>Multi-Currency Bot Started!</b>

📊 <b>Monitoring Cryptocurrencies:</b>
{currency_list}

⏰ <b>Check interval:</b> 5 minutes
🎯 <b>Alert thresholds:</b>
• BTC, ETH: 1-1.5% change
• ARB, TRB: 2% change  
• ENA: 3% change
📱 <b>Summary updates:</b> Every 30 minutes

🕒 <b>Started at:</b> {self.start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC
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
    bot = MultiCurrencyTelegramBot()
    asyncio.run(bot.run_bot())

if __name__ == "__main__":
    logger.info("="*50)
    logger.info("MULTI-CURRENCY TELEGRAM BOT STARTING")
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
