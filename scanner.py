import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
from telegram import Bot

logger = logging.getLogger(__name__)

class ArbitrageScanner:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.scanned_tokens = set()
        self.found_opportunities = set()
    
    async def get_top_tokens(self) -> List[dict]:
        """Автоматично отримує топ токенів з DexScreener"""
        tokens = []
        networks = ["ethereum", "bsc", "polygon", "arbitrum", "optimism"]
        
        async with aiohttp.ClientSession() as session:
            for network in networks:
                try:
                    url = f"https://api.dexscreener.com/latest/dex/search?q={network}"
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            pairs = data.get('pairs', [])[:30]
                            
                            for pair in pairs:
                                try:
                                    if not pair.get('baseToken') or not pair.get('priceUsd'):
                                        continue
                                    
                                    liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                                    if liquidity < 10000:  # Мінімум $10K ліквідності
                                        continue
                                    
                                    symbol = pair['baseToken']['symbol']
                                    if symbol in ['USDT', 'USDC', 'DAI', 'BUSD']:
                                        continue
                                    
                                    if symbol not in self.scanned_tokens:
                                        token = {
                                            'symbol': symbol,
                                            'address': pair['baseToken']['address'],
                                            'network': pair['chainId'],
                                            'dex_price': float(pair['priceUsd']),
                                            'liquidity': liquidity,
                                            'dex_url': f"https://dexscreener.com/{pair['chainId']}/{pair['pairAddress']}"
                                        }
                                        tokens.append(token)
                                        self.scanned_tokens.add(symbol)
                                        
                                except Exception as e:
                                    continue
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Помилка: {e}")
        
        logger.info(f"✅ Знайдено {len(tokens)} токенів")
        return tokens
    
    async def check_cex_prices(self, symbol: str) -> Dict[str, float]:
        """Перевіряє ціни на CEX біржах"""
        prices = {}
        
        async with aiohttp.ClientSession() as session:
            # Перевіряємо Binance
            try:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        prices['binance'] = float(data['price'])
            except:
                pass
            
            # Перевіряємо MEXC
            try:
                url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}USDT"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        prices['mexc'] = float(data['price'])
            except:
                pass
            
            # Перевіряємо Gate.io
            try:
                url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={symbol}_USDT"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and len(data) > 0:
                            prices['gateio'] = float(data[0]['last'])
            except:
                pass
            
            # Перевіряємо Bitget
            try:
                url = f"https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}USDT"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('data') and len(data['data']) > 0:
                            prices['bitget'] = float(data['data'][0]['lastPr'])
            except:
                pass
        
        return prices
    
    async def analyze_token(self, token: dict) -> Optional[dict]:
        """Аналізує токен на арбітраж"""
        try:
            symbol = token['symbol']
            
            # Отримуємо CEX ціни
            cex_prices = await self.check_cex_prices(symbol)
            
            # Потрібно мінімум 2 біржі
            if len(cex_prices) < 2:
                return None
            
            # Найкраща CEX ціна (найнижча)
            best_cex = min(cex_prices.items(), key=lambda x: x[1])
            best_cex_price = best_cex[1]
            best_cex_name = best_cex[0]
            
            # Розраховуємо спред
            spread = ((token['dex_price'] - best_cex_price) / best_cex_price) * 100
            
            # Якщо спред > 10%
            if spread >= 10:
                opportunity = {
                    'symbol': symbol,
                    'spread': spread,
                    'dex_price': token['dex_price'],
                    'cex_price': best_cex_price,
                    'best_cex': best_cex_name,
                    'cex_prices': cex_prices,
                    'liquidity': token['liquidity'],
                    'network': token['network'],
                    'contract': token['address'],
                    'dex_url': token['dex_url']
                }
                
                opp_key = f"{symbol}_{spread:.2f}"
                if opp_key not in self.found_opportunities:
                    self.found_opportunities.add(opp_key)
                    return opportunity
            
            return None
            
        except Exception as e:
            logger.error(f"Помилка аналізу {token.get('symbol')}: {e}")
            return None
    
    def format_message(self, opp: dict) -> str:
        """Форматує повідомлення"""
        symbol = opp['symbol']
        spread = opp['spread']
        
        cex_list = ""
        for exchange, price in opp['cex_prices'].items():
            emoji = "🟢" if exchange == opp['best_cex'] else "⚪"
            cex_list += f"{emoji} {exchange}: {price:.6f}\n"
        
        message = f"""
🔥 <b>АРБІТРАЖ ЗНАЙДЕНО! СПРЕД > 10%</b> 🔥

<b>{symbol}</b>

📊 <b>Спред: +{spread:.2f}%</b>

💎 <b>DEX ({opp['network']}):</b>
💰 Ціна: ${opp['dex_price']:.6f}
💧 Ліквідність: ${opp['liquidity']:,.0f}
🔗 {opp['dex_url']}

🏦 <b>CEX ціни:</b>
{cex_list}

✅ Найкраща CEX: <b>{opp['best_cex']}</b> (${opp['cex_price']:.6f})

📝 <b>Контракт:</b>
<code>{opp['contract']}</code>

#ARBITRAGE #{symbol}
        """
        return message
    
    async def scan_all(self):
        """Сканує всі токени"""
        logger.info("=" * 50)
        logger.info("🔍 ПОЧАТОК АВТОМАТИЧНОГО СКАНУВАННЯ")
        
        tokens = await self.get_top_tokens()
        
        if not tokens:
            logger.warning("❌ Не знайдено токенів")
            return
        
        found = 0
        for i, token in enumerate(tokens, 1):
            logger.info(f"📊 [{i}/{len(tokens)}] Перевіряю {token['symbol']}...")
            
            opportunity = await self.analyze_token(token)
            
            if opportunity:
                message = self.format_message(opportunity)
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='HTML'
                )
                found += 1
                await asyncio.sleep(2)
            
            await asyncio.sleep(1)
        
        logger.info(f"✅ Сканування завершено. Знайдено {found} можливостей")
        logger.info("=" * 50)