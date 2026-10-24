"""
ENTSO-E Transparency Platform API Client

This module provides a client for fetching electricity price data from the
ENTSO-E (European Network of Transmission System Operators for Electricity)
Transparency Platform API.

API Documentation: https://transparency.entsoe.eu/transparency-platform/access-to-data/api-urls-and-guidelines
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

import requests
import xml.etree.ElementTree as ET

from .country_codes import get_eic_code, get_all_country_codes

logger = logging.getLogger(__name__)


@dataclass
class ENTSOEPriceEntry:
    """Raw price data from ENTSO-E API before normalization."""
    price_eur_per_mwh: float
    start: datetime
    end: datetime
    currency: str
    unit: str


class ENTSOEEClientError(Exception):
    """Custom exception for ENTSO-E API errors."""
    pass


class Cache:
    """
    Simple cache with TTL support for ENTSO-E API responses.
    
    Supports both in-memory and file-based caching.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None, default_ttl: int = 3600):
        """
        Initialize cache.
        
        Args:
            cache_dir: Directory for file-based cache (None = memory only)
            default_ttl: Default time-to-live in seconds (1 hour default)
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        
        if self.cache_dir and not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _make_key(self, country_zone: str, date: datetime.date) -> str:
        """Generate a cache key for the given country/zone and date."""
        return f"{country_zone}_{date.isoformat()}"
    
    def _get_cache_path(self, key: str) -> Path:
        """Get file path for a cache key."""
        if self.cache_dir:
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            return self.cache_dir / f"entsoe_{key_hash}.json"
        return None
    
    def get(self, country_zone: str, date: datetime.date) -> Optional[List[ENTSOEPriceEntry]]:
        """
        Get cached data if it exists and hasn't expired.
        
        Args:
            country_zone: Country/zone code
            date: Date of the data
            
        Returns:
            Cached price entries or None if not found/expired
        """
        key = self._make_key(country_zone, date)
        
        # Try memory cache first
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            expires_at = entry["expires_at"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if datetime.now() < expires_at:
                return [ENTSOEPriceEntry(**data) for data in entry["data"]]
            else:
                # Expired, remove from memory
                del self._memory_cache[key]
        
        # Try file cache
        cache_path = self._get_cache_path(key)
        if cache_path and cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    entry = json.load(f)
                
                if datetime.fromisoformat(entry["expires_at"]) > datetime.now():
                    # Valid, load into memory cache
                    self._memory_cache[key] = entry
                    return [ENTSOEPriceEntry(**data) for data in entry["data"]]
                else:
                    # Expired, remove file
                    cache_path.unlink()
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to read cache file {cache_path}: {e}")
        
        return None
    
    def set(
        self,
        country_zone: str,
        date: datetime.date,
        data: List[ENTSOEPriceEntry],
        ttl: Optional[int] = None
    ) -> None:
        """
        Store data in cache.
        
        Args:
            country_zone: Country/zone code
            date: Date of the data
            data: Price entries to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        key = self._make_key(country_zone, date)
        ttl = ttl or self.default_ttl
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        entry = {
            "data": [asdict(d) for d in data],
            "expires_at": expires_at.isoformat(),
            "country_zone": country_zone,
            "date": date.isoformat()
        }
        
        # Store in memory
        self._memory_cache[key] = entry
        
        # Store in file if cache_dir is set
        cache_path = self._get_cache_path(key)
        if cache_path:
            try:
                with open(cache_path, 'w') as f:
                    json.dump(entry, f, indent=2)
                logger.debug(f"Cached data for {country_zone} on {date} to {cache_path}")
            except OSError as e:
                logger.warning(f"Failed to write cache file {cache_path}: {e}")
    
    def clear(self) -> None:
        """Clear all cached data."""
        self._memory_cache.clear()
        
        if self.cache_dir and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("entsoe_*.json"):
                try:
                    cache_file.unlink()
                except OSError as e:
                    logger.warning(f"Failed to remove cache file {cache_file}: {e}")
    
    def cleanup_expired(self) -> None:
        """Remove expired cache entries from memory and disk."""
        now = datetime.now()
        
        # Clean memory cache
        expired_keys = [
            key for key, entry in self._memory_cache.items()
            if datetime.fromisoformat(entry["expires_at"]) < now
        ]
        for key in expired_keys:
            del self._memory_cache[key]
        
        # Clean file cache
        if self.cache_dir and self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("entsoe_*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        entry = json.load(f)
                    if datetime.fromisoformat(entry["expires_at"]) < now:
                        cache_file.unlink()
                except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
                    logger.debug(f"Failed to check/remove expired cache {cache_file}: {e}")


def asdict(obj):
    """Convert dataclass instance to dict."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: asdict(v) if hasattr(v, '__dataclass_fields__') else v 
                for k, v in obj.__dict__.items()}
    elif isinstance(obj, (list, tuple)):
        return [asdict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: asdict(v) for k, v in obj.items()}
    else:
        return obj


class ENTSOEEClient:
    """
    Client for the ENTSO-E Transparency Platform API.
    
    This client fetches day-ahead electricity prices for various European countries.
    Requires an API key from https://transparency.entsoe.eu/
    
    Features:
    - Dual caching (in-memory and file-based)
    - Automatic retry with exponential backoff
    - Data normalization to plugin format
    
    Example:
        client = ENTSOEEClient(api_key="your-api-key")
        prices = client.get_day_ahead_prices("SE4", datetime.date(2026, 10, 19))
        
        # With caching
        client = ENTSOEEClient(api_key="your-api-key", cache_dir=Path(".cache"))
        
        # With retry
        client = ENTSOEEClient(api_key="your-api-key", max_retries=3)
    """
    
    BASE_URL = "https://web-api.tp.entsoe.eu/api"
    
    # Default settings
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_BACKOFF = 1.0  # Exponential backoff multiplier
    DEFAULT_CACHE_TTL = 3600  # 1 hour in seconds
    
    # User agent for API requests
    USER_AGENT = "InkyPi-ElectricityPricePlugin/1.0"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF
    ):
        """
        Initialize the ENTSO-E client.
        
        Args:
            api_key: ENTSO-E API key. If not provided, will attempt to read
                    from ENTSOE_API_KEY environment variable.
            cache_dir: Directory for file-based cache (None = memory only)
            cache_ttl: Cache time-to-live in seconds
            max_retries: Maximum number of retry attempts
            retry_backoff: Exponential backoff multiplier
        """
        # Try to get API key from parameter, then environment, then fail
        self.api_key = api_key or os.getenv('ENTSOE_API_KEY')
        
        if not self.api_key:
            raise ENTSOEEClientError(
                "ENTSO-E API key is required. "
                "Get a free API key from https://transparency.entsoe.eu/ "
                "and provide it via parameter or ENTSOE_API_KEY environment variable."
            )
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
        })
        
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.cache_ttl = cache_ttl
        
        # Initialize cache
        self.cache = Cache(cache_dir=cache_dir, default_ttl=cache_ttl)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests including API key."""
        return {
            "Accept": "application/xml",
            "X-Request-ID": self.api_key,
        }
    
    def _retry_request(
        self,
        func: Callable[[], requests.Response],
        max_retries: int,
        backoff: float
    ) -> requests.Response:
        """
        Execute a request with retry logic and exponential backoff.
        
        Args:
            func: Function that returns a requests.Response
            max_retries: Maximum number of retry attempts
            backoff: Exponential backoff multiplier
            
        Returns:
            requests.Response object
            
        Raises:
            ENTSOEEClientError: If all retries fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                response = func()
                
                # Check for rate limiting (HTTP 429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    if attempt < max_retries:
                        logger.warning(
                            f"Rate limited. Retrying after {retry_after} seconds (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(retry_after)
                        continue
                
                # Check for other retryable errors (5xx)
                if response.status_code >= 500 and attempt < max_retries:
                    delay = backoff * (2 ** attempt)
                    logger.warning(
                        f"Server error {response.status_code}. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < max_retries:
                    delay = backoff * (2 ** attempt)
                    logger.warning(
                        f"Timeout. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise ENTSOEEClientError(f"Request timed out after {max_retries + 1} attempts: {e}")
                    
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < max_retries:
                    delay = backoff * (2 ** attempt)
                    logger.warning(
                        f"Connection error. Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise ENTSOEEClientError(f"Connection error after {max_retries + 1} attempts: {e}")
        
        # This should not be reached, but just in case
        raise ENTSOEEClientError(f"Request failed after {max_retries + 1} attempts: {last_exception}")
    
    def _fetch_prices_for_date(
        self,
        country_zone: str,
        date: datetime.date,
        process_type: str,
        currency: str = "EUR",
        use_cache: bool = True
    ) -> List[ENTSOEPriceEntry]:
        """
        Internal method to fetch prices for a specific date and process type.
        
        Args:
            country_zone: Country/zone code
            date: Date for which to fetch prices
            process_type: ENTSO-E process type (e.g., A01 for day-ahead, A03 for intraday)
            currency: Currency for prices
            use_cache: Whether to use cached data
            
        Returns:
            List of ENTSOEPriceEntry objects
        """
        eic_code = get_eic_code(country_zone)
        if not eic_code:
            raise ENTSOEEClientError(f"No EIC code found for: {country_zone}")
        
        # Build API parameters
        params = {
            "documentType": "A44",  # Aggregated data
            "processType": process_type,
            "in_Domain": eic_code,
            "out_Domain": eic_code,
            "periodStart": date.strftime("%Y%m%d0000"),
            "periodEnd": date.strftime("%Y%m%d2359"),
            "securityToken": self.api_key,
        }
        
        logger.info(f"Fetching {process_type} prices for {country_zone} on {date}")
        
        try:
            response = self._retry_request(
                func=lambda: self.session.get(
                    self.BASE_URL,
                    params=params,
                    headers=self._get_headers(),
                    timeout=self.DEFAULT_TIMEOUT
                ),
                max_retries=self.max_retries,
                backoff=self.retry_backoff
            )
            
            prices = self._parse_day_ahead_response(response.text, currency)
            
            # Cache the result only if we got data
            if use_cache and prices:
                self.cache.set(country_zone, date, prices, self.cache_ttl)
            
            return prices
            
        except requests.exceptions.Timeout:
            raise ENTSOEEClientError(
                f"Request timed out for {country_zone} on {date}"
            )
        except requests.exceptions.ConnectionError as e:
            raise ENTSOEEClientError(
                f"Connection error fetching data for {country_zone} on {date}: {e}"
            )
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', 'unknown')
            raise ENTSOEEClientError(
                f"HTTP error {status_code} for {country_zone} on {date}: {e}"
            )
        except Exception as e:
            raise ENTSOEEClientError(
                f"Unexpected error fetching data for {country_zone} on {date}: {e}"
            )
    
    def get_day_ahead_prices(
        self,
        country_zone: str,
        date: datetime.date,
        currency: str = "EUR",
        use_cache: bool = True,
        max_retry_days: int = 7
    ) -> List[ENTSOEPriceEntry]:
        """
        Fetch day-ahead electricity prices for a specific country/zone.
        
        This method tries multiple strategies to get prices:
        1. Day-ahead prices for the requested date
        2. Intraday prices for the requested date (same-day)
        3. Day-ahead prices for tomorrow (published today)
        4. If still no data, tries previous days up to max_retry_days
        
        Args:
            country_zone: Country/zone code (e.g., "SE4", "NO1", "DE")
            date: Date for which to fetch prices
            currency: Currency for prices (default: "EUR")
            use_cache: Whether to use cached data if available (default: True)
            max_retry_days: Maximum number of previous days to try (default: 7)
            
        Returns:
            List of ENTSOEPriceEntry objects with raw price data
            
        Raises:
            ENTSOEEClientError: If API request fails or data cannot be parsed
        """
        # Validate country code
        country_zone = country_zone.upper()
        if country_zone not in get_all_country_codes():
            valid_countries = ", ".join(sorted(get_all_country_codes()))
            raise ENTSOEEClientError(
                f"Invalid country/zone code: {country_zone}. "
                f"Valid codes: {valid_countries}"
            )
        
        # Check cache first
        if use_cache:
            cached_data = self.cache.get(country_zone, date)
            if cached_data is not None:
                logger.info(f"Using cached data for {country_zone} on {date}")
                return cached_data
        
        # Strategy 1: Try day-ahead prices for the requested date
        logger.info(f"Strategy 1: Trying day-ahead (A01) for {country_zone} on {date}")
        try:
            prices = self._fetch_prices_for_date(country_zone, date, "A01", currency, use_cache)
            if prices:
                logger.info(f"Found {len(prices)} day-ahead prices for {date}")
                return prices
            else:
                logger.info(f"No day-ahead prices found for {date}, trying other strategies")
        except ENTSOEEClientError as e:
            logger.warning(f"Day-ahead (A01) failed for {date}: {e}")
        
        # Strategy 2: Try intraday prices for the requested date
        logger.info(f"Strategy 2: Trying intraday (A03) for {country_zone} on {date}")
        try:
            prices = self._fetch_prices_for_date(country_zone, date, "A03", currency, use_cache)
            if prices:
                logger.info(f"Found {len(prices)} intraday prices for {date}")
                return prices
            else:
                logger.info(f"No intraday prices found for {date}, trying other strategies")
        except ENTSOEEClientError as e:
            logger.warning(f"Intraday (A03) failed for {date}: {e}")
        
        # Strategy 3: Try day-ahead prices for tomorrow (published today)
        tomorrow = date + timedelta(days=1)
        logger.info(f"Strategy 3: Trying day-ahead (A01) for {country_zone} on {tomorrow}")
        try:
            prices = self._fetch_prices_for_date(country_zone, tomorrow, "A01", currency, use_cache)
            if prices:
                logger.info(f"Found {len(prices)} day-ahead prices for {tomorrow} (published today)")
                # Cache with tomorrow's date
                if use_cache:
                    self.cache.set(country_zone, tomorrow, prices, self.cache_ttl)
                return prices
        except ENTSOEEClientError as e:
            logger.warning(f"Day-ahead (A01) for tomorrow failed: {e}")
        
        # Strategy 4: Try previous days (day-ahead prices)
        for days_back in range(1, max_retry_days + 1):
            prev_date = date - timedelta(days=days_back)
            logger.info(f"Strategy 4: Trying day-ahead (A01) for {country_zone} on {prev_date} ({days_back} days back)")
            try:
                prices = self._fetch_prices_for_date(country_zone, prev_date, "A01", currency, use_cache)
                if prices:
                    logger.info(f"Found {len(prices)} day-ahead prices for {prev_date}")
                    return prices
            except ENTSOEEClientError as e:
                logger.warning(f"Day-ahead (A01) for {prev_date} failed: {e}")
            
            # Also try intraday for previous days
            try:
                prices = self._fetch_prices_for_date(country_zone, prev_date, "A03", currency, use_cache)
                if prices:
                    logger.info(f"Found {len(prices)} intraday prices for {prev_date}")
                    return prices
            except ENTSOEEClientError as e:
                pass  # Already logged above
        
        # If all strategies failed, return empty list (no error, just no data)
        logger.warning(f"No price data found for {country_zone} on {date} (tried all strategies)")
        return []
    
    def _parse_day_ahead_response(
        self,
        xml_string: str,
        currency: str = "EUR"
    ) -> List[ENTSOEPriceEntry]:
        """
        Parse ENTSO-E XML response for day-ahead prices.
        
        Args:
            xml_string: Raw XML response from API
            currency: Target currency (currently only EUR is supported by most endpoints)
            
        Returns:
            List of ENTSOEPriceEntry objects
        """
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as e:
            raise ENTSOEEClientError(f"Failed to parse XML response: {e}")
        
        prices = []
        
        # Helper function to find elements with or without namespace
        def find_element(parent, tag_name):
            """Find element by tag name, trying both with and without namespace."""
            # Try without namespace first
            elem = parent.find(tag_name)
            if elem is not None:
                return elem
            
            # Try with known namespace
            ns = 'urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0'
            elem = parent.find(f'{{{ns}}}{tag_name}')
            if elem is not None:
                return elem
            
            # Try any namespace
            for child in parent:
                if child.tag.endswith(tag_name):
                    return child
            
            return None
        
        def find_all_elements(parent, tag_name):
            """Find all elements by tag name, trying both with and without namespace."""
            results = []
            
            # Try without namespace
            results.extend(parent.findall(tag_name))
            
            # Try with known namespace
            ns = 'urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0'
            results.extend(parent.findall(f'{{{ns}}}{tag_name}'))
            
            # Try any namespace recursively
            for child in parent:
                if child.tag.endswith(tag_name):
                    results.append(child)
                results.extend(find_all_elements(child, tag_name))
            
            # Deduplicate
            return list({id(e): e for e in results}.values())
        
        # Find all TimeSeries elements
        time_series_list = find_all_elements(root, 'TimeSeries')
        
        if not time_series_list:
            logger.warning("No TimeSeries elements found in ENTSO-E response")
            logger.debug(f"Response XML: {xml_string[:1000]}")
            return prices
        
        for time_series in time_series_list:
            # Extract currency
            currency_elem = find_element(time_series, 'currency_Unit.name')
            response_currency = currency_elem.text if currency_elem is not None else "EUR"
            
            # Extract price unit from price_Amount element
            price_amount_elem = find_element(time_series, 'price_Amount')
            price_unit = price_amount_elem.get('unit', 'MWH') if price_amount_elem is not None else 'MWH'
            
            # Find all Period/Periode elements
            period_list = find_all_elements(time_series, 'Periode')
            if not period_list:
                period_list = find_all_elements(time_series, 'Period')
            
            for period in period_list:
                # Get time interval
                time_interval = find_element(period, 'timeInterval')
                
                if time_interval is None:
                    continue
                
                start_elem = find_element(time_interval, 'start')
                end_elem = find_element(time_interval, 'end')
                
                if start_elem is None or end_elem is None:
                    continue
                
                try:
                    start_text = start_elem.text
                    end_text = end_elem.text
                    
                    # Handle various datetime formats
                    if start_text and start_text.endswith('Z'):
                        start_text = start_text[:-1] + '+00:00'
                    if end_text and end_text.endswith('Z'):
                        end_text = end_text[:-1] + '+00:00'
                    
                    start = datetime.fromisoformat(start_text)
                    end = datetime.fromisoformat(end_text)
                except (ValueError, AttributeError, TypeError) as e:
                    logger.warning(f"Failed to parse datetime: {e}")
                    continue
                
                # Find all Point elements in this period
                point_list = find_all_elements(period, 'Point')
                
                for point in point_list:
                    price_elem = find_element(point, 'price.amount')
                    if price_elem is None:
                        # Try just amount
                        price_elem = find_element(point, 'amount')
                    
                    if price_elem is None:
                        continue
                    
                    try:
                        price = float(price_elem.text)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Failed to parse price: {e}")
                        continue
                    
                    prices.append(ENTSOEPriceEntry(
                        price_eur_per_mwh=price,
                        start=start,
                        end=end,
                        currency=response_currency,
                        unit=price_unit
                    ))
        
        if not prices:
            logger.warning("No price data found in ENTSO-E response")
            logger.debug(f"Response XML: {xml_string[:2000]}")
        
        return prices
    
    def get_available_countries(self) -> List[str]:
        """
        Get list of all available country/zone codes.
        
        Returns:
            List of supported country/zone codes
        """
        return get_all_country_codes()
    
    def to_plugin_format(
        self,
        entsoe_prices: List[ENTSOEPriceEntry],
        target_currency: str = "EUR",
        exchange_rate_sek: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Convert ENTSO-E price entries to the plugin's expected format.
        
        The plugin expects entries with:
        - SEK_per_kWh
        - EUR_per_kWh
        - EXR (exchange rate)
        - time_start
        - time_end
        
        Args:
            entsoe_prices: List of ENTSOEPriceEntry objects
            target_currency: Target currency for display (default: EUR)
            exchange_rate_sek: SEK/EUR exchange rate (optional, for SEK conversion)
            
        Returns:
            List of dictionaries matching the plugin's expected format
        """
        result = []
        
        for entry in entsoe_prices:
            # Convert EUR/MWh to EUR/kWh (divide by 1000)
            price_eur_per_kwh = entry.price_eur_per_mwh / 1000.0
            
            # Build base result
            plugin_entry = {
                "EUR_per_kWh": price_eur_per_kwh,
                "time_start": entry.start.strftime("%Y-%m-%d %H:%M:%S"),
                "time_end": entry.end.strftime("%Y-%m-%d %H:%M:%S"),
            }
            
            # Add SEK conversion if exchange rate is provided
            if exchange_rate_sek is not None:
                plugin_entry["SEK_per_kWh"] = price_eur_per_kwh * exchange_rate_sek
                plugin_entry["EXR"] = exchange_rate_sek
            else:
                # If no exchange rate, we can't provide SEK price
                plugin_entry["SEK_per_kWh"] = None
                plugin_entry["EXR"] = None
            
            result.append(plugin_entry)
        
        return result
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()
    
    def cleanup_cache(self) -> None:
        """Remove expired cache entries."""
        self.cache.cleanup_expired()
    
    def close(self):
        """Close the client and clean up resources."""
        self.cleanup_cache()
        if self.session:
            self.session.close()
            self.session = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
