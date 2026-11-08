import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

import pytz
import requests

from plugins.base_plugin.base_plugin import BasePlugin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import ENTSO-E client components
try:
    from .entsoe_client import ENTSOEEClient, ENTSOEEClientError
    from .country_codes import get_eic_code, is_swedish_zone, get_all_country_codes
    ENTSOE_AVAILABLE = True
except ImportError:
    ENTSOE_AVAILABLE = False
    logger.warning("ENTSO-E client not available, falling back to Swedish API only")

from .country_codes import get_zone_currency


def get_service_url(zone: str = "SE4", date: datetime.date = None) -> str:
    """
    Get URL for Swedish electricity price API (elprisetjustnu.se).
    
    Args:
        zone: Swedish zone code (SE1, SE2, SE3, SE4)
        date: Date for prices (defaults to today)
        
    Returns:
        API URL string
    """
    if date is None:
        date = datetime.now().date()
    year = date.year
    month = f"{date.month:02d}"
    day = f"{date.day:02d}"
    return f"https://www.elprisetjustnu.se/api/v1/prices/{year}/{month}-{day}_{zone}.json"


@dataclass
class ElectricityPriceEntry:
    """Data class for electricity price entries."""
    SEK_per_kWh: float
    EUR_per_kWh: float
    EXR: float
    time_start: str
    time_end: str


class ElectricityPrice(BasePlugin):
    """
    Electricity Price Plugin for InkyPi.
    
    Supports multiple data sources:
    - Swedish API (elprisetjustnu.se) - for SE1-SE4 zones, no API key required
    - ENTSO-E API (web-api.tp.entsoe.eu) - for 25+ European countries, API key required
    
    Data source selection:
    - auto: Uses Swedish API for SE zones, ENTSO-E for others
    - swedish: Always use Swedish API (SE zones only)
    - entsoe: Always use ENTSO-E API
    """
    
    data: List[ElectricityPriceEntry] = []
    _entsoe_client: Optional[ENTSOEEClient] = None
    _last_exchange_rate: Optional[float] = None
    
    # Default exchange rate for SEK/EUR (used when ENTSO-E data is converted)
    # This is a fallback value; can be overridden via settings
    DEFAULT_EXCHANGE_RATE_SEK = 11.0

    def __init__(self, config):
        super().__init__(config)
        self.data_source = None  # Will be set from settings in generate_image

    def generate_settings_template(self):
        """Generate default settings template."""
        template_params = super().generate_settings_template()
        
        # Set defaults, but preserve any existing settings from config
        defaults = {
            "zone": "SE4",
            "data_source": "auto",
            "show_max_label": True,
            "entsoe_api_key": "",
            "exchange_rate_source": "auto",
            "exchange_rate_sek": self.DEFAULT_EXCHANGE_RATE_SEK,
            "currency": "auto"
        }
        
        # If config has saved settings, use them; otherwise use defaults
        for key, default_value in defaults.items():
            template_params[key] = self.config.get(key, default_value)
        
        return template_params

    def _get_data_source(self, settings: Dict[str, Any]) -> str:
        """Get the configured data source from settings."""
        return settings.get("data_source", "auto")

    def _should_use_swedish_api(self, zone: str, data_source: str) -> bool:
        """
        Determine whether to use the Swedish API for the given zone and data source.
        
        Args:
            zone: Country/zone code
            data_source: Data source setting ("auto", "swedish", "entsoe")
            
        Returns:
            True if Swedish API should be used
        """
        if data_source == "swedish":
            return True
        elif data_source == "entsoe":
            return False
        else:  # auto
            # Use Swedish API for Swedish zones, ENTSO-E for others
            return is_swedish_zone(zone)

    def _get_data_source_info(self, use_swedish: bool, data_source: str, 
                               fallback: bool, zone: str) -> Dict[str, Any]:
        """
        Generate data source information for user feedback.
        
        Args:
            use_swedish: Whether Swedish API was used
            data_source: Configured data source
            fallback: Whether we fell back from one API to another
            zone: Country/zone code
            
        Returns:
            Dictionary with data source info for template
        """
        from datetime import datetime
        
        # Determine source name and type
        if use_swedish:
            source_name = "Swedish API"
            source_type = "source-swedish"
        else:
            source_name = "ENTSO-E API"
            source_type = "source-entsoe"
        
        # Add fallback indicator if we switched
        if fallback:
            source_name = f"{source_name} (Fallback)"
            source_type = "source-fallback"
        
        return {
            "source_name": source_name,
            "source_type": source_type,
            "last_updated": datetime.now().strftime("%H:%M:%S"),
            "entry_count": len(self.data),
            "exchange_rate": getattr(self, "_last_exchange_rate", None),
        }

    def _get_entsoe_client(self, settings: Dict[str, Any]) -> Optional[ENTSOEEClient]:
        """
        Get or create ENTSO-E client instance.
        
        Args:
            settings: Plugin settings
            
        Returns:
            ENTSOEEClient instance or None if not available
        """
        if not ENTSOE_AVAILABLE:
            return None
        
        # Get API key from settings or environment
        api_key = settings.get("entsoe_api_key") or os.getenv("ENTSOE_API_KEY")
        
        if not api_key:
            logger.warning("ENTSO-E API key not configured")
            return None
        
        # Create client if not exists or if API key changed
        if self._entsoe_client is None:
            try:
                self._entsoe_client = ENTSOEEClient(api_key=api_key)
            except ENTSOEEClientError as e:
                logger.error(f"Failed to initialize ENTSO-E client: {e}")
                self._entsoe_client = None
        
        return self._entsoe_client

    def generate_image(self, settings, device_config):
        """
        Generate electricity price image.
        
        Args:
            settings: Plugin settings
            device_config: Device configuration
            
        Returns:
            PIL Image object
        """
        zone = settings.get("zone", "SE4")
        data_source = self._get_data_source(settings)
        
        # Determine which API to use
        use_swedish = self._should_use_swedish_api(zone, data_source)
        
        try:
            if use_swedish:
                logger.info(f"Using Swedish API for zone {zone}")
                self.data = self.fetch_swedish_json(zone)
            else:
                logger.info(f"Using ENTSO-E API for zone {zone}")
                self.data = self.fetch_entsoe_json(zone, settings)
        except Exception as e:
            logger.error(f"Failed to fetch price data: {e}")
            # Fallback: try the other source if one fails
            if use_swedish and ENTSOE_AVAILABLE:
                logger.info(f"Falling back to ENTSO-E API for zone {zone}")
                try:
                    self.data = self.fetch_entsoe_json(zone, settings)
                except Exception as e2:
                    logger.error(f"Both APIs failed: Swedish={e}, ENTSO-E={e2}")
                    raise RuntimeError(f"Failed to fetch price data: {e}")
            elif not use_swedish and is_swedish_zone(zone):
                logger.info(f"Falling back to Swedish API for zone {zone}")
                try:
                    self.data = self.fetch_swedish_json(zone)
                except Exception as e2:
                    logger.error(f"Both APIs failed: ENTSO-E={e}, Swedish={e2}")
                    raise RuntimeError(f"Failed to fetch price data: {e}")
            else:
                raise RuntimeError(f"Failed to fetch price data: {e}")
        
        # Additional fallback: if ENTSO-E returned empty data for a Swedish zone, try Swedish API
        if not self.data and not use_swedish and is_swedish_zone(zone):
            logger.info(f"ENTSO-E returned no data for Swedish zone {zone}, falling back to Swedish API")
            try:
                self.data = self.fetch_swedish_json(zone)
                # Update data source info since we fell back
                use_swedish = True
                data_source_fallback = True
            except Exception as e:
                logger.error(f"Both APIs returned no data: ENTSO-E (empty), Swedish={e}")
                data_source_fallback = False
        else:
            data_source_fallback = False
        
        # Resolve display currency ("auto" = the zone's native currency)
        currency = (settings.get("currency") or "auto").strip().upper()
        if currency == "AUTO":
            currency = get_zone_currency(zone)

        # Build the price series in the display currency
        if currency == "EUR":
            prices = [entry.EUR_per_kWh for entry in self.data]
            self._last_exchange_rate = None
        elif currency == "SEK":
            prices = [entry.SEK_per_kWh for entry in self.data]
        else:
            rate = self._get_exchange_rate(currency, settings)
            prices = [entry.EUR_per_kWh * rate for entry in self.data]

        # Track data source and timestamp for user feedback
        data_source_info = self._get_data_source_info(use_swedish, data_source, data_source_fallback, zone)

        # Check if we have data and add warning if not
        warning_message = None
        if not self.data:
            warning_message = "No price data available for selected zone and date"

        data_dicts = [asdict(entry) for entry in self.data]
        
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        template_params = {
            "data": data_dicts,
            "plugin_settings": settings,
            "title": "Electricity Prices - " + datetime.now(tz).strftime("%Y-%m-%d"),
            "current_date": datetime.now(tz).strftime("%Y-%m-%d"),
            "zone": zone,
            "currency": currency,
            "prices": prices,
            "data_source_info": data_source_info,
            "warning_message": warning_message,
        }

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        # "Now" marker label for the current 15-minute interval, computed in the
        # data's own timezone (device tz may differ; ENTSO-E times are UTC)
        now_label = None
        try:
            data_tz = datetime.fromisoformat(data_dicts[0]["time_start"]).tzinfo or pytz.UTC
        except (IndexError, KeyError, ValueError):
            data_tz = tz
        now_data = datetime.now(data_tz)
        today_str = now_data.strftime("%Y-%m-%d")
        if any(entry.get("time_start", "").startswith(today_str) for entry in data_dicts):
            now_floored = now_data.replace(minute=(now_data.minute // 15) * 15, second=0, microsecond=0)
            now_label = now_floored.strftime("%H:%M")
        template_params["now_label"] = now_label

        image = self.render_image(
            dimensions,
            "electricity_price.html",
            "electricity_price.css",
            template_params,
        )

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")

        return image

    def fetch_swedish_json(self, zone: str = "SE4") -> List[ElectricityPriceEntry]:
        """
        Fetch price data from Swedish API (elprisetjustnu.se).
        
        Args:
            zone: Swedish zone code (SE1, SE2, SE3, SE4)
            
        Returns:
            List of ElectricityPriceEntry objects
        """
        url = get_service_url(zone)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        return [ElectricityPriceEntry(**entry) for entry in data]

    def fetch_entsoe_json(self, zone: str, settings: Dict[str, Any]) -> List[ElectricityPriceEntry]:
        """
        Fetch price data from ENTSO-E API.
        
        Args:
            zone: Country/zone code
            settings: Plugin settings
            
        Returns:
            List of ElectricityPriceEntry objects
        """
        if not ENTSOE_AVAILABLE:
            raise RuntimeError("ENTSO-E client not available")
        
        client = self._get_entsoe_client(settings)
        if client is None:
            raise RuntimeError(
                "ENTSO-E API key is required. "
                "Get a free key from https://transparency.entsoe.eu/ "
                "and configure it in plugin settings or ENTSOE_API_KEY environment variable."
            )
        
        # Get exchange rate
        exchange_rate = self._get_exchange_rate("SEK", settings)
        
        # Fetch raw prices from ENTSO-E
        # For Swedish zones, use fewer retry days to fail faster and fallback to Swedish API
        import datetime as dt
        today = dt.datetime.now().date()
        max_retry_days = 2 if is_swedish_zone(zone) else 7
        entsoe_prices = client.get_day_ahead_prices(zone, today, max_retry_days=max_retry_days)
        
        # Convert to plugin format
        plugin_data = client.to_plugin_format(
            entsoe_prices,
            target_currency="EUR",
            exchange_rate_sek=exchange_rate
        )
        
        # Convert to ElectricityPriceEntry objects
        result = []
        for entry in plugin_data:
            result.append(ElectricityPriceEntry(
                SEK_per_kWh=entry.get("SEK_per_kWh", 0.0),
                EUR_per_kWh=entry.get("EUR_per_kWh", 0.0),
                EXR=entry.get("EXR", exchange_rate),
                time_start=entry.get("time_start", ""),
                time_end=entry.get("time_end", "")
            ))
        
        return result
    
    def _get_exchange_rate(self, currency: str, settings: Dict[str, Any]) -> float:
        """
        Get exchange rate for converting EUR prices to the display currency.

        With exchange_rate_source "auto" (default) the live rate is fetched from a
        free API (cached 24h); with "manual" no network call is made and the
        configured exchange_rate_sek is used for SEK (built-in approximate rates
        for other currencies). Fallback order after the primary source: manual
        value, EXCHANGE_RATE_SEK env var (SEK only), then built-in defaults.

        Args:
            currency: Target ISO 4217 currency code (e.g., "SEK", "DKK")
            settings: Plugin settings

        Returns:
            Exchange rate (units of currency per 1 EUR)
        """
        currency = currency.upper()
        source = settings.get("exchange_rate_source", "auto")

        # The manual override value is defined as SEK per EUR
        manual_rate = None
        if currency == "SEK":
            raw = settings.get("exchange_rate_sek")
            if raw not in (None, "", "auto"):
                try:
                    manual_rate = float(raw)
                except (TypeError, ValueError):
                    manual_rate = None

        # Live lookup first unless the user chose manual
        if source != "manual":
            try:
                from .exchange_rate import get_rate
                rate = get_rate("EUR", currency)
                self._last_exchange_rate = rate
                return rate
            except Exception as e:
                logger.warning(f"Failed to fetch live exchange rate EUR->{currency}: {e}")

        # Manual value (SEK only)
        if manual_rate is not None:
            self._last_exchange_rate = manual_rate
            return manual_rate

        # Environment variable (SEK only)
        if currency == "SEK":
            env_rate = os.getenv("EXCHANGE_RATE_SEK")
            if env_rate:
                try:
                    rate = float(env_rate)
                    self._last_exchange_rate = rate
                    return rate
                except ValueError:
                    pass
            self._last_exchange_rate = self.DEFAULT_EXCHANGE_RATE_SEK
            return self.DEFAULT_EXCHANGE_RATE_SEK

        # Non-SEK currency without live access: built-in approximate rate
        from .exchange_rate import get_fallback_rate
        rate = get_fallback_rate("EUR", currency)
        self._last_exchange_rate = rate
        return rate

    def fetch_json(self, zone: str = "SE4") -> List[ElectricityPriceEntry]:
        """
        Fetch price data (backward compatible method).
        
        This method maintains backward compatibility with the original API.
        For new code, prefer using fetch_swedish_json() or fetch_entsoe_json() directly.
        
        Args:
            zone: Zone code (default: SE4)
            
        Returns:
            List of ElectricityPriceEntry objects
        """
        # For backward compatibility, use Swedish API for SE zones
        if is_swedish_zone(zone):
            return self.fetch_swedish_json(zone)
        else:
            # For non-Swedish zones, we need settings
            # Use default settings with auto data source
            settings = {"data_source": "auto", "zone": zone}
            return self.fetch_entsoe_json(zone, settings)

    def close(self):
        """Clean up resources."""
        if self._entsoe_client is not None:
            self._entsoe_client.close()
            self._entsoe_client = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
