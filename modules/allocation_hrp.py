import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
from typing import List, Dict, Any

class HRPAllocator:
    """
    Implements Hierarchical Risk Parity (HRP) for portfolio allocation.
    HRP addresses the instability of traditional Mean-Variance Optimization 
    by leveraging the hierarchical structure of asset correlations.
    """
    
    def __init__(self, max_single_weight=0.15, min_single_weight=0.01):
        self.max_single_weight = max_single_weight
        self.min_single_weight = min_single_weight

    def allocate(self, returns_df: pd.DataFrame) -> pd.Series:
        """
        Main HRP allocation logic.
        Args:
            returns_df: DataFrame of historical returns (daily).
        Returns:
            pd.Series: Optimal weights indexed by asset symbol.
        """
        if returns_df.empty:
            return pd.Series()

        if len(returns_df.columns) == 1:
            return pd.Series([1.0], index=returns_df.columns)

        # 1. Compute Correlation and Distance Matrix
        corr = returns_df.corr().fillna(0)
        dist = np.sqrt(0.5 * (1 - corr))
        
        # 2. Hierarchical Clustering (Single Linkage)
        link = sch.linkage(sch.distance.pdist(dist), method='single')
        
        # 3. Quasi-Diagonalization (Sort indices by cluster)
        sort_ix = sch.leaves_list(link)
        sorted_symbols = returns_df.columns[sort_ix].tolist()
        
        # 4. Recursive Bisection
        weights = pd.Series(1.0, index=sorted_symbols)
        self._recursive_bisection(weights, sorted_symbols, returns_df.cov())
        
        # 5. Apply Constraints & Re-normalize Iteratively
        for _ in range(20):
            weights = weights.clip(lower=self.min_single_weight, upper=self.max_single_weight)
            weights = weights / weights.sum()
            # If all constraints are satisfied within a small tolerance, we can stop
            if (weights.max() <= self.max_single_weight + 1e-7 and 
                weights.min() >= self.min_single_weight - 1e-7):
                break
        
        return weights

    def _recursive_bisection(self, weights, sorted_symbols, cov):
        """
        Recursively bisects the sorted symbols and allocates weights based on variance.
        """
        if len(sorted_symbols) <= 1:
            return

        # Divide into two clusters
        mid = len(sorted_symbols) // 2
        cluster_left = sorted_symbols[:mid]
        cluster_right = sorted_symbols[mid:]
        
        # Calculate cluster variance
        v_left = self._get_cluster_var(cluster_left, cov)
        v_right = self._get_cluster_var(cluster_right, cov)
        
        # Calculate allocation factor (alpha)
        alpha = 1 - v_left / (v_left + v_right)
        
        # Update weights
        weights[cluster_left] *= alpha
        weights[cluster_right] *= (1 - alpha)
        
        # Recurse
        self._recursive_bisection(weights, cluster_left, cov)
        self._recursive_bisection(weights, cluster_right, cov)

    def _get_cluster_var(self, symbols, cov):
        """
        Calculates the variance of a cluster using inverse-variance weights.
        """
        sub_cov = cov.loc[symbols, symbols]
        inv_diag = 1 / np.diag(sub_cov)
        ivw = inv_diag / np.sum(inv_diag)
        cluster_var = np.dot(ivw, np.dot(sub_cov, ivw))
        return cluster_var

    def calculate_hrp_weights(self, stocks_list: List[Dict[str, Any]], history_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Helper to integrate HRP into the existing stocks list format.
        """
        if history_df.empty:
            return stocks_list
            
        # Ensure only common symbols are used
        common_symbols = [s for s in history_df.columns if s in [stock['Symbol'] for stock in stocks_list]]
        if not common_symbols:
            return stocks_list
            
        returns = history_df[common_symbols].pct_change().dropna()
        if returns.empty:
            return stocks_list
            
        hrp_weights = self.allocate(returns)
        
        # Map weights back to stocks list
        for stock in stocks_list:
            sym = stock['Symbol']
            stock['hrp_weight'] = float(hrp_weights.get(sym, 0.0))
            
        return stocks_list

if __name__ == "__main__":
    # Test stub
    print("HRP Allocator module ready.")
