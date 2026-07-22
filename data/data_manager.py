"""
Unified data management for multiple symbols
"""
import asyncio
import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any, Union
from datetime import datetime, timedelta
from pathlib import Path
import json
import logging

from fluxV.core.types import Timeframe
from fluxV.data.news import NewsManager

logger = logging.getLogger(__name__)


class DataManager:
    """
    Manage data for multiple symbols including price data, news, and fundamentals
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir) if data_dir else Path("./data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._news_manager = NewsManager()
        self._symbol_info: Dict[str, Dict] = {}
        
    async def get_rates(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data for a symbol
        
        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        cache_key = f"{symbol}_{timeframe.value}_{from_date.date()}_{to_date.date()}"
        
        if cache_key in self._price_cache:
            df = self._price_cache[cache_key]
            mask = (df['time'] >= from_date) & (df['time'] <= to_date)
            return df[mask].copy()
        
        # Try to load from local files first
        df = await self._load_from_local(symbol, timeframe, from_date, to_date)
        
        if df is None:
            # Generate synthetic data for demo
            df = await self._generate_synthetic_data(symbol, timeframe, from_date, to_date)
        
        if df is not None:
            self._price_cache[cache_key] = df
            return df
        
        return None
    
    async def _load_from_local(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> Optional[pd.DataFrame]:
        """Load data from local files"""
        # Check multiple possible file locations
        file_patterns = [
            f"{symbol}_{timeframe.name}.csv",
            f"{symbol}.csv",
            f"{symbol.lower()}_{timeframe.name}.csv"
        ]
        
        for pattern in file_patterns:
            file_path = self.data_dir / pattern
            if file_path.exists():
                try:
                    df = pd.read_csv(file_path, parse_dates=['time'])
                    mask = (df['time'] >= from_date) & (df['time'] <= to_date)
                    return df[mask].copy()
                except Exception as e:
                    logger.warning(f"Failed to load {file_path}: {e}")
        
        return None
    
    async def _generate_synthetic_data(
        self,
        symbol: str,
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing"""
        # Calculate number of bars
        seconds_per_bar = timeframe.value * 60
        total_seconds = (to_date - from_date).total_seconds()
        n_bars = int(total_seconds / seconds_per_bar)
        
        if n_bars < 1:
            n_bars = 100
        
        # Generate dates
        dates = pd.date_range(start=from_date, end=to_date, periods=n_bars)
        
        # Generate price series with different characteristics per symbol
        base_price = 1.2000
        trend = 0.0001
        volatility = 0.001
        
        # Adjust parameters based on symbol
        if "ZAR" in symbol or "RUB" in symbol:
            volatility = 0.005
            trend = 0.0005
        elif "JPY" in symbol:
            base_price = 150.0
            trend = 0.01
            volatility = 0.1
        elif "GBP" in symbol:
            base_price = 1.3000
        elif "CHF" in symbol:
            base_price = 0.9000
        
        np.random.seed(hash(symbol) % 2**32)
        
        # Generate price path
        n = len(dates)
        trend_line = np.linspace(0, trend * n, n)
        noise = np.random.normal(0, volatility, n)
        prices = base_price + trend_line + np.cumsum(noise)
        
        # Create OHLCV
        data = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.abs(np.random.normal(0, volatility/2, n)),
            'low': prices - np.abs(np.random.normal(0, volatility/2, n)),
            'close': prices + np.random.normal(0, volatility/3, n),
            'volume': np.random.randint(100, 1000, n)
        })
        
        # Ensure high is highest and low is lowest
        data['high'] = data[['open', 'high', 'close']].max(axis=1)
        data['low'] = data[['open', 'low', 'close']].min(axis=1)
        
        logger.info(f"Generated synthetic data for {symbol}: {len(data)} bars")
        return data
    
    async def get_rates_for_symbols(
        self,
        symbols: List[str],
        timeframe: Timeframe,
        from_date: datetime,
        to_date: datetime
    ) -> Dict[str, pd.DataFrame]:
        """Get rates for multiple symbols concurrently"""
        tasks = []
        for symbol in symbols:
            task = self.get_rates(symbol, timeframe, from_date, to_date)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        data = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get data for {symbol}: {result}")
                continue
            if result is not None and len(result) > 0:
                data[symbol] = result
        
        return data
    
    def save_data(self, symbol: str, df: pd.DataFrame, timeframe: Timeframe):
        """Save data to local file"""
        file_path = self.data_dir / f"{symbol}_{timeframe.name}.csv"
        df.to_csv(file_path, index=False)
        logger.info(f"Saved data for {symbol} to {file_path}")
    
    def load_symbol_info(self, symbol: str) -> Dict:
        """Load symbol information"""
        if symbol in self._symbol_info:
            return self._symbol_info[symbol]
        
        # Default info
        info = {
            'symbol': symbol,
            'digits': 5,
            'pip_size': 0.0001,
            'contract_size': 100000,
            'margin_required': 0.01
        }
        
        # Adjust for specific symbols
        if 'JPY' in symbol:
            info['digits'] = 3
            info['pip_size'] = 0.01
        elif 'ZAR' in symbol or 'RUB' in symbol:
            info['digits'] = 5
            info['pip_size'] = 0.0001
        
        self._symbol_info[symbol] = info
        return info