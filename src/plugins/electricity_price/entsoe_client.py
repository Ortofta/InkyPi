"""
ENTSO-E Transparency Platform API Client

This module provides a client for fetching electricity price data from the
ENTSO-E (European Network of Transmission System Operators for Electricity)
Transparency Platform API.

API Documentation: https://transparency.entsoe.eu/transparency-platform/access-to-data/api-urls-and-guidelines
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
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


class ENTSOEEClient:
    """
    Client for the ENTSO-E Transparency Platform API.
    
    This client fetches day-ahead electricity prices for various European countries.
    Requires an API key from https://transparency.entsoe.eu/
    
    Example:
        client = ENTSOEEClient(api_key="your-api-key")
        prices = client.get_day_ahead_prices("SE4", datetime.date(2026, 10, 19))
    """
    
    BASE_URL = "https://web-api.tp.entsoe.eu/api"
    
    # Default timeout in seconds
    DEFAULT_TIMEOUT = 30
    
    # User agent for API requests
    USER_AGENT = "InkyPi-ElectricityPricePlugin/1.0"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the ENTSO-E client.
        
        Args:
            api_key: ENTSO-E API key. If not provided, will attempt to read
                    from ENTSOE_API_KEY environment variable.
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
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests including API key."""
        return {
            "Accept": "application/xml",
            "X-Request-ID": self.api_key,
        }
    
    def get_day_ahead_prices(
        self,
        country_zone: str,
        date: datetime.date,
        currency: str = "EUR"
    ) -> List[ENTSOEPriceEntry]:
        """
        Fetch day-ahead electricity prices for a specific country/zone.
        
        Args:
            country_zone: Country/zone code (e.g., "SE4", "NO1", "DE")
            date: Date for which to fetch prices
            currency: Currency for prices (default: "EUR")
            
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
        
        # Get EIC code for the country/zone
        eic_code = get_eic_code(country_zone)
        if not eic_code:
            raise ENTSOEEClientError(f"No EIC code found for: {country_zone}")
        
        # Build API parameters
        params = {
            "documentType": "A44",  # Aggregated data
            "processType": "A16",   # Day-ahead prices
            "in_Domain": eic_code,
            "out_Domain": eic_code,
            "periodStart": date.strftime("%Y%m%d0000"),
            "periodEnd": date.strftime("%Y%m%d2359"),
        }
        
        # Add currency if not EUR (default)
        # Note: Currency parameter support varies by endpoint
        
        logger.info(f"Fetching day-ahead prices for {country_zone} on {date}")
        
        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                headers=self._get_headers(),
                timeout=self.DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            
            # Parse XML response
            return self._parse_day_ahead_response(response.text, currency)
            
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
            # Try without namespace first (works if no namespace or if we stripped it)
            elem = parent.find(tag_name)
            if elem is not None:
                return elem
            
            # Try with namespace
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
            
            # Try with namespace
            ns = 'urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0'
            results.extend(parent.findall(f'{{{ns}}}{tag_name}'))
            
            # Try any namespace
            for child in parent:
                if child.tag.endswith(tag_name):
                    results.append(child)
                results.extend(find_all_elements(child, tag_name))
            
            # Deduplicate
            return list(set(results))
        
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
                        # Try price.amount with different case
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
            # Note: ENTSO-E returns prices in EUR/MWh
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
                # But we should still provide EUR price
                plugin_entry["SEK_per_kWh"] = None
                plugin_entry["EXR"] = None
            
            result.append(plugin_entry)
        
        return result
    
    def close(self):
        """Close the client and clean up resources."""
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
