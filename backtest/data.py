import pandas as pd
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from fluxV.core.types import Timeframe


class DataLoader:
    """Load and manage historical data for backtesting"""
    
    @staticmethod
    def load_csv(
        file_path: str,
        date_col: str = 'time',
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None
    ) -> pd.DataFrame:
        """
        Load data from CSV file
        
        Args:
            file_path: Path to CSV file
            date_col: Name of date column
            symbol: Symbol name (for filtering)
            timeframe: Timeframe (for validation)
        
        Returns:
            DataFrame with OHLCV data
        """
        df = pd.read_csv(file_path)
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.rename(columns={date_col: 'time'})
        
        # Validate columns
        required_cols = ['time', 'open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"CSV must have columns: {required_cols}")
        
        # Add volume if missing
        if 'volume' not in df.columns:
            df['volume'] = 0
        
        return df
    
    @staticmethod
    def generate_sample_data(
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: Timeframe,
        base_price: float = 1.2000,
        trend: float = 0.0001,
        volatility: float = 0.001
    ) -> pd.DataFrame:
        """
        Generate sample OHLCV data for testing
        
        Args:
            symbol: Symbol name
            start_date: Start date
            end_date: End date
            timeframe: Timeframe
            base_price: Starting price
            trend: Daily trend
            volatility: Price volatility
        
        Returns:
            DataFrame with OHLCV data
        """
        import numpy as np
        
        # Generate dates
        periods = int((end_date - start_date).total_seconds() / timeframe.value * 60)
        dates = pd.date_range(start=start_date, end=end_date, periods=periods)
        
        # Generate prices
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
        
        return data
    
    @staticmethod
    def save_data(df: pd.DataFrame, file_path: str):
        """Save data to CSV"""
        df.to_csv(file_path, index=False)