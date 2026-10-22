"""
Unit tests for Exchange Rate Service.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from plugins.electricity_price.exchange_rate import (
    ExchangeRateFetcher,
    ExchangeRateError,
    get_rate,
    get_exchange_rate_fetcher,
)
import requests


class TestExchangeRateFetcherInit(TestCase):
    """Test ExchangeRateFetcher initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        fetcher = ExchangeRateFetcher()
        self.assertIsNotNone(fetcher)
        self.assertEqual(fetcher.cache_ttl, 86400)
        self.assertIsNone(fetcher.api_key)
        self.assertIsNone(fetcher.cache_dir)
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        fetcher = ExchangeRateFetcher(api_key="test-key")
        self.assertEqual(fetcher.api_key, "test-key")
    
    def test_init_with_cache_dir(self):
        """Test initialization with cache directory."""
        with mock.patch('pathlib.Path') as mock_path:
            mock_dir = MagicMock()
            mock_dir.exists.return_value = True
            mock_path.return_value = mock_dir
            
            fetcher = ExchangeRateFetcher(cache_dir=Path("/tmp/cache"))
            self.assertEqual(fetcher.cache_dir, Path("/tmp/cache"))


class TestExchangeRateFetcherFallback(TestCase):
    """Test fallback exchange rates."""
    
    def setUp(self):
        """Set up test fetcher."""
        self.fetcher = ExchangeRateFetcher()
    
    def test_fallback_rate_sek(self):
        """Test fallback rate for SEK."""
        rate = self.fetcher._get_fallback_rate("EUR", "SEK")
        self.assertEqual(rate, 11.0)
    
    def test_fallback_rate_nok(self):
        """Test fallback rate for NOK."""
        rate = self.fetcher._get_fallback_rate("EUR", "NOK")
        self.assertEqual(rate, 11.0)
    
    def test_fallback_rate_unknown(self):
        """Test fallback rate for unknown currency."""
        rate = self.fetcher._get_fallback_rate("EUR", "XYZ")
        self.assertEqual(rate, 1.0)


class TestExchangeRateFetcherCache(TestCase):
    """Test exchange rate caching."""
    
    def setUp(self):
        """Set up test fetcher."""
        self.fetcher = ExchangeRateFetcher(cache_ttl=3600)
    
    @patch('requests.get')
    def test_cache_rate(self, mock_get):
        """Test caching a rate."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-10-20",
            "rates": {"SEK": 11.23}
        }
        mock_get.return_value = mock_response
        
        # First call should hit API
        rate1 = self.fetcher.get_rate("EUR", "SEK")
        self.assertEqual(rate1, 11.23)
        self.assertEqual(mock_get.call_count, 1)
        
        # Second call should use cache
        rate2 = self.fetcher.get_rate("EUR", "SEK")
        self.assertEqual(rate2, 11.23)
        self.assertEqual(mock_get.call_count, 1)  # Still 1, not 2
    
    def test_clear_cache(self):
        """Test cache clearing."""
        # Manually add to cache
        self.fetcher._rate_cache["EUR_SEK"] = {
            "rate": 11.23,
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
            "fetched_at": datetime.now().isoformat()
        }
        
        # Verify it's there
        cached = self.fetcher._get_cached_rate("EUR_SEK")
        self.assertEqual(cached, 11.23)
        
        # Clear cache
        self.fetcher.clear_cache()
        
        # Verify it's gone
        cached = self.fetcher._get_cached_rate("EUR_SEK")
        self.assertIsNone(cached)


class TestExchangeRateFetcherAPI(TestCase):
    """Test exchange rate API fetching."""
    
    @patch('requests.get')
    def test_frankfurter_success(self, mock_get):
        """Test successful fetch from Frankfurter API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-10-20",
            "rates": {"SEK": 11.23, "NOK": 11.50}
        }
        mock_get.return_value = mock_response
        
        fetcher = ExchangeRateFetcher()
        rate = fetcher.get_rate("EUR", "SEK")
        
        self.assertEqual(rate, 11.23)
    
    @patch('requests.get')
    def test_frankfurter_failure_fallback(self, mock_get):
        """Test fallback when Frankfurter API fails."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed")
        
        fetcher = ExchangeRateFetcher()
        rate = fetcher.get_rate("EUR", "SEK")
        
        # Should use fallback
        self.assertEqual(rate, 11.0)
    
    @patch('requests.get')
    def test_get_rates(self, mock_get):
        """Test fetching all rates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-10-20",
            "rates": {"SEK": 11.23, "NOK": 11.50, "DKK": 7.45}
        }
        mock_get.return_value = mock_response
        
        fetcher = ExchangeRateFetcher()
        rates = fetcher.get_rates("EUR")
        
        self.assertIn("SEK", rates)
        self.assertEqual(rates["SEK"], 11.23)


class TestExchangeRateConvenienceFunctions(TestCase):
    """Test convenience functions."""
    
    @patch('requests.get')
    def test_get_rate_function(self, mock_get):
        """Test get_rate convenience function."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "amount": 1.0,
            "base": "EUR",
            "date": "2026-10-20",
            "rates": {"SEK": 11.23}
        }
        mock_get.return_value = mock_response
        
        rate = get_rate("EUR", "SEK")
        self.assertEqual(rate, 11.23)
    
    def test_get_exchange_rate_fetcher_singleton(self):
        """Test that get_exchange_rate_fetcher returns a singleton."""
        fetcher1 = get_exchange_rate_fetcher()
        fetcher2 = get_exchange_rate_fetcher()
        
        # Should be the same instance
        self.assertIs(fetcher1, fetcher2)


if __name__ == '__main__':
    import unittest
    unittest.main()
