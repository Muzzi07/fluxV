import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


class PerformanceAnalyzer:
    """Analyze backtest performance"""
    
    def __init__(self, broker):
        self.broker = broker
    
    def analyze(self) -> Dict:
        """Analyze backtest results"""
        equity_curve = self.broker.get_equity_curve()
        trade_history = self.broker.get_trade_history()
        stats = self.broker.get_stats()
        
        # Additional metrics
        if len(equity_curve) > 0:
            sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
            sortino_ratio = self._calculate_sortino_ratio(equity_curve)
            calmar_ratio = self._calculate_calmar_ratio(equity_curve)
        else:
            sharpe_ratio = 0
            sortino_ratio = 0
            calmar_ratio = 0
        
        # Trade metrics
        if len(trade_history) > 0:
            avg_trade = trade_history['profit'].mean()
            avg_win = trade_history[trade_history['profit'] > 0]['profit'].mean() if len(trade_history[trade_history['profit'] > 0]) > 0 else 0
            avg_loss = trade_history[trade_history['profit'] < 0]['profit'].mean() if len(trade_history[trade_history['profit'] < 0]) > 0 else 0
            profit_factor = abs(trade_history[trade_history['profit'] > 0]['profit'].sum() / trade_history[trade_history['profit'] < 0]['profit'].sum()) if trade_history[trade_history['profit'] < 0]['profit'].sum() != 0 else 0
        else:
            avg_trade = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
        
        return {
            **stats,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'avg_trade': avg_trade,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_bars': len(equity_curve),
            'equity_curve': equity_curve,
            'trade_history': trade_history
        }
    
    def _calculate_sharpe_ratio(self, equity_curve: pd.DataFrame) -> float:
        """Calculate Sharpe ratio"""
        if len(equity_curve) < 2:
            return 0
        
        returns = equity_curve['equity'].pct_change().dropna()
        if len(returns) == 0 or returns.std() == 0:
            return 0
        
        return returns.mean() / returns.std() * np.sqrt(252)
    
    def _calculate_sortino_ratio(self, equity_curve: pd.DataFrame) -> float:
        """Calculate Sortino ratio"""
        if len(equity_curve) < 2:
            return 0
        
        returns = equity_curve['equity'].pct_change().dropna()
        negative_returns = returns[returns < 0]
        
        if len(negative_returns) == 0 or negative_returns.std() == 0:
            return 0
        
        return returns.mean() / negative_returns.std() * np.sqrt(252)
    
    def _calculate_calmar_ratio(self, equity_curve: pd.DataFrame) -> float:
        """Calculate Calmar ratio"""
        max_drawdown = self.broker._calculate_max_drawdown()
        if max_drawdown == 0:
            return 0
        
        total_return = (equity_curve['equity'].iloc[-1] - equity_curve['equity'].iloc[0]) / equity_curve['equity'].iloc[0]
        years = len(equity_curve) / 252  # Approximate trading days
        
        if years == 0:
            return 0
        
        annual_return = (1 + total_return) ** (1 / years) - 1
        return annual_return / (max_drawdown / 100)