"""
Exchange Rate Service for Currency Conversion

This module provides exchange rate fetching and caching for converting
EUR prices to local currencies (e.g., SEK, NOK, DKK).

Free APIs used:
- ExchangeRate-API (https://www.exchangerate-api.com/)
- Frankfurter (https://www.frankfurter.app/)
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class ExchangeRateError(Exception):
    """Custom exception for exchange rate errors."""
    pass


class ExchangeRateFetcher:
    """
    Fetcher for exchange rates with caching support.
    
    Supports multiple free exchange rate APIs with automatic fallback.
    
    Example:
        fetcher = ExchangeRateFetcher()
        rate = fetcher.get_rate("EUR", "SEK")
        print(f"1 EUR = {rate} SEK")
    """
    
    # Default cache TTL in seconds (24 hours)
    DEFAULT_CACHE_TTL = 86400
    
    # Supported APIs with their endpoints
    API_ENDPOINTS = {
        "frankfurter": {
            "url": "https://api.frankfurter.app/latest",
            "base_currency": "EUR",
            "requires_key": False,
        },
        "exchangerate-api": {
            "url": "https://v6.exchangerate-api.com/v6/{api_key}/latest/EUR",
            "base_currency": "EUR",
            "requires_key": True,
        },
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL
    ):
        """
        Initialize exchange rate fetcher.
        
        Args:
            api_key: API key for exchange rate API (optional)
            cache_dir: Directory for cache files (None = memory only)
            cache_ttl: Cache TTL in seconds
        """
        self.api_key = api_key or os.getenv("EXCHANGE_RATE_API_KEY")
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl
        
        # In-memory cache
        self._rate_cache: Dict[str, Dict[str, Any]] = {}
        
        # Ensure cache directory exists
        if self.cache_dir and not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Get exchange rate from one currency to another.
        
        Args:
            from_currency: Source currency code (e.g., "EUR")
            to_currency: Target currency code (e.g., "SEK")
            
        Returns:
            Exchange rate (amount of to_currency per 1 from_currency)
            
        Raises:
            ExchangeRateError: If rate cannot be fetched
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Normalize to EUR base if needed
        # For now, we assume EUR is the base currency from ENTSO-E
        if from_currency != "EUR":
            # We need to convert via EUR
            # rate = (1 / get_rate(from_currency, EUR)) * get_rate(EUR, to_currency)
            # For simplicity in Phase 2, we'll just use EUR as base
            logger.warning(f"Exchange rate from {from_currency} not yet supported, using EUR as base")
            from_currency = "EUR"
        
        # Generate cache key
        cache_key = f"{from_currency}_{to_currency}"
        
        # Try to get from cache
        cached_rate = self._get_cached_rate(cache_key)
        if cached_rate is not None:
            logger.debug(f"Using cached exchange rate {from_currency}->{to_currency}: {cached_rate}")
            return cached_rate
        
        # Fetch fresh rate
        try:
            rate = self._fetch_rate(from_currency, to_currency)
            
            # Cache it
            self._cache_rate(cache_key, rate)
            
            return rate
            
        except Exception as e:
            raise ExchangeRateError(f"Failed to fetch exchange rate {from_currency}->{to_currency}: {e}")
    
    def _get_cached_rate(self, cache_key: str) -> Optional[float]:
        """Get rate from cache if valid."""
        if cache_key in self._rate_cache:
            entry = self._rate_cache[cache_key]
            expires_at = entry["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if datetime.now() < expires_at:
                return entry["rate"]
            else:
                del self._rate_cache[cache_key]
        
        # Try file cache
        if self.cache_dir:
            cache_file = self.cache_dir / f"exchange_rate_{cache_key}.json"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r') as f:
                        entry = json.load(f)
                    expires_at = datetime.fromisoformat(entry["expires_at"])
                    if expires_at > datetime.now():
                        self._rate_cache[cache_key] = entry
                        return entry["rate"]
                    else:
                        cache_file.unlink()
                except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
                    logger.warning(f"Failed to read exchange rate cache {cache_file}: {e}")
        
        return None
    
    def _cache_rate(self, cache_key: str, rate: float) -> None:
        """Cache an exchange rate."""
        entry = {
            "rate": rate,
            "expires_at": (datetime.now() + timedelta(seconds=self.cache_ttl)).isoformat(),
            "fetched_at": datetime.now().isoformat()
        }
        
        # Store in memory
        self._rate_cache[cache_key] = entry
        
        # Store in file if cache_dir is set
        if self.cache_dir:
            cache_file = self.cache_dir / f"exchange_rate_{cache_key}.json"
            try:
                with open(cache_file, 'w') as f:
                    json.dump(entry, f, indent=2)
            except OSError as e:
                logger.warning(f"Failed to write exchange rate cache {cache_file}: {e}")
    
    def _fetch_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Fetch exchange rate from API.
        
        Args:
            from_currency: Source currency
            to_currency: Target currency
            
        Returns:
            Exchange rate
        """
        # Try each API in order until one works
        for api_name, api_config in self.API_ENDPOINTS.items():
            try:
                if api_config["requires_key"] and not self.api_key:
                    logger.debug(f"Skipping {api_name}, requires API key")
                    continue
                
                rate = self._fetch_from_api(api_name, api_config, from_currency, to_currency)
                if rate is not None:
                    logger.debug(f"Fetched rate from {api_name}: {from_currency}->{to_currency} = {rate}")
                    return rate
                    
            except Exception as e:
                logger.warning(f"Failed to fetch from {api_name}: {e}")
                continue
        
        # If all APIs failed, try fallback
        return self._get_fallback_rate(from_currency, to_currency)
    
    def _fetch_from_api(
        self,
        api_name: str,
        api_config: Dict[str, Any],
        from_currency: str,
        to_currency: str
    ) -> Optional[float]:
        """Fetch rate from a specific API."""
        if api_name == "frankfurter":
            return self._fetch_from_frankfurter(api_config, from_currency, to_currency)
        elif api_name == "exchangerate-api":
            return self._fetch_from_exchangerate_api(api_config, from_currency, to_currency)
        return None
    
    def _fetch_from_frankfurter(
        self,
        api_config: Dict[str, Any],
        from_currency: str,
        to_currency: str
    ) -> Optional[float]:
        """Fetch rate from Frankfurter API (free, no key required)."""
        url = api_config["url"]
        
        # Frankfurter uses EUR as base, returns all rates relative to EUR
        # So we need from_currency to be EUR, and to_currency is the target
        if from_currency != "EUR":
            logger.warning("Frankfurter API only supports EUR as base currency")
            return None
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Frankfurter returns {"amount": 1.0, "base": "EUR", "date": "...", "rates": {"SEK": 11.23, ...}}
            if "rates" in data and to_currency in data["rates"]:
                return float(data["rates"][to_currency])
            
            return None
            
        except Exception as e:
            logger.warning(f"Frankfurter API error: {e}")
            return None
    
    def _fetch_from_exchangerate_api(
        self,
        api_config: Dict[str, Any],
        from_currency: str,
        to_currency: str
    ) -> Optional[float]:
        """Fetch rate from ExchangeRate-API."""
        if not self.api_key:
            return None
        
        url = api_config["url"].format(api_key=self.api_key)
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # ExchangeRate-API returns {"base_code": "EUR", "conversion_rates": {"SEK": 11.23, ...}}
            if "conversion_rates" in data and to_currency in data["conversion_rates"]:
                return float(data["conversion_rates"][to_currency])
            
            return None
            
        except Exception as e:
            logger.warning(f"ExchangeRate-API error: {e}")
            return None
    
    def _get_fallback_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Get fallback exchange rate.
        
        Returns hardcoded rates for common currencies.
        """
        # Common EUR exchange rates (approximate, updated periodically)
        # These are fallback values when API is unavailable
        fallback_rates = {
            "SEK": 11.0,    # Swedish Krona
            "NOK": 11.0,    # Norwegian Krone
            "DKK": 7.5,     # Danish Krone
            "USD": 1.1,     # US Dollar
            "GBP": 0.85,    # British Pound
            "CHF": 1.0,     # Swiss Franc
            "PLN": 4.5,     # Polish Zloty
            "CZK": 24.5,    # Czech Koruna
            "HUF": 380.0,   # Hungarian Forint
            "RON": 4.9,     # Romanian Leu
        }
        
        if to_currency in fallback_rates:
            logger.warning(f"Using fallback exchange rate for {to_currency}: {fallback_rates[to_currency]}")
            return fallback_rates[to_currency]
        
        # Default to 1.0 if we don't have a fallback
        logger.warning(f"No exchange rate available for {from_currency}->{to_currency}, using 1.0")
        return 1.0
    
    def get_rates(self, from_currency: str) -> Dict[str, float]:
        """
        Get all available exchange rates from a source currency.
        
        Args:
            from_currency: Source currency code
            
        Returns:
            Dictionary of currency codes to exchange rates
        """
        # For now, just fetch from API
        # In future, could cache all rates at once
        try:
            url = self.API_ENDPOINTS["frankfurter"]["url"]
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if "rates" in data:
                return {k: float(v) for k, v in data["rates"].items()}
            
            return {}
        except Exception as e:
            logger.warning(f"Failed to fetch all rates: {e}")
            return {}
    
    def clear_cache(self) -> None:
        """Clear all cached exchange rates."""
        self._rate_cache.clear()
        
        if self.cache_dir and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("exchange_rate_*.json"):
                try:
                    cache_file.unlink()
                except OSError as e:
                    logger.warning(f"Failed to remove cache file {cache_file}: {e}")


# Global instance for convenience
_default_fetcher: Optional[ExchangeRateFetcher] = None


def get_exchange_rate_fetcher() -> ExchangeRateFetcher:
    """Get the default exchange rate fetcher instance."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = ExchangeRateFetcher()
    return _default_fetcher


def get_rate(from_currency: str, to_currency: str) -> float:
    """
    Convenience function to get exchange rate.
    
    Args:
        from_currency: Source currency code
        to_currency: Target currency code
        
    Returns:
        Exchange rate
    """
    return get_exchange_rate_fetcher().get_rate(from_currency, to_currency)
