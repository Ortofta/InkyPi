"""
Unit tests for ENTSO-E API client.

These tests verify the ENTSO-E client functionality including:
- XML parsing
- Data normalization
- Error handling
- Country code validation
"""

import os
import sys
from datetime import datetime, date
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import requests

from plugins.electricity_price.entsoe_client import (
    ENTSOEEClient,
    ENTSOEEClientError,
    ENTSOEPriceEntry
)
from plugins.electricity_price.country_codes import (
    get_eic_code,
    get_all_country_codes,
    is_swedish_zone
)


class TestCountryCodes(TestCase):
    """Test country code mappings."""
    
    def test_swedish_zones(self):
        """Test Swedish zone codes."""
        self.assertTrue(is_swedish_zone("SE1"))
        self.assertTrue(is_swedish_zone("SE2"))
        self.assertTrue(is_swedish_zone("SE3"))
        self.assertTrue(is_swedish_zone("SE4"))
        self.assertFalse(is_swedish_zone("NO1"))
        self.assertFalse(is_swedish_zone("DE"))
    
    def test_eic_codes_exist(self):
        """Test that EIC codes exist for known countries."""
        self.assertEqual(get_eic_code("SE4"), "10YSE-4--------2")
        self.assertEqual(get_eic_code("NO1"), "10YNO-1--------2")
        self.assertEqual(get_eic_code("DK1"), "10YDK-1--------W")
        self.assertEqual(get_eic_code("FI"), "10YFI-1--------U")
        self.assertEqual(get_eic_code("DE"), "10YDE-RW-------I")
        self.assertEqual(get_eic_code("FR"), "10YFR-RTE------C")
    
    def test_all_country_codes(self):
        """Test that we have a reasonable number of country codes."""
        codes = get_all_country_codes()
        self.assertIsInstance(codes, list)
        self.assertGreater(len(codes), 20)  # Should have at least 20+ countries
        self.assertIn("SE4", codes)
        self.assertIn("NO1", codes)
        self.assertIn("FI", codes)


class TestENTSOEPriceEntry(TestCase):
    """Test ENTSO-E price entry dataclass."""
    
    def test_create_entry(self):
        """Test creating a price entry."""
        entry = ENTSOEPriceEntry(
            price_eur_per_mwh=42.50,
            start=datetime(2026, 10, 19, 0, 0, 0),
            end=datetime(2026, 10, 19, 1, 0, 0),
            currency="EUR",
            unit="MWH"
        )
        self.assertEqual(entry.price_eur_per_mwh, 42.50)
        self.assertEqual(entry.currency, "EUR")
        self.assertEqual(entry.unit, "MWH")


class TestENTSOEEClientInit(TestCase):
    """Test ENTSO-E client initialization."""
    
    @patch.dict(os.environ, {"ENTSOE_API_KEY": "test-api-key"})
    def test_init_with_env_var(self):
        """Test initialization with API key from environment."""
        client = ENTSOEEClient()
        self.assertEqual(client.api_key, "test-api-key")
        self.assertIsNotNone(client.session)
        client.close()
    
    def test_init_with_param(self):
        """Test initialization with API key parameter."""
        client = ENTSOEEClient(api_key="param-api-key")
        self.assertEqual(client.api_key, "param-api-key")
        client.close()
    
    def test_init_without_key(self):
        """Test that initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ENTSOEEClientError) as context:
                ENTSOEEClient()
            self.assertIn("API key is required", str(context.exception))
    
    def test_init_with_empty_key(self):
        """Test that initialization fails with empty API key."""
        with patch.dict(os.environ, {"ENTSOE_API_KEY": ""}):
            with self.assertRaises(ENTSOEEClientError):
                ENTSOEEClient(api_key="")


class TestENTSOEEClientValidation(TestCase):
    """Test ENTSO-E client validation."""
    
    def setUp(self):
        """Set up test client."""
        self.client = ENTSOEEClient(api_key="test-key")
    
    def tearDown(self):
        """Clean up."""
        self.client.close()
    
    def test_get_available_countries(self):
        """Test getting available countries."""
        countries = self.client.get_available_countries()
        self.assertIsInstance(countries, list)
        self.assertGreater(len(countries), 0)
        self.assertIn("SE4", countries)
        self.assertIn("NO1", countries)
    
    def test_invalid_country_code(self):
        """Test error with invalid country code."""
        with self.assertRaises(ENTSOEEClientError) as context:
            self.client.get_day_ahead_prices("INVALID", date(2026, 10, 19))
        self.assertIn("Invalid country/zone code", str(context.exception))


class TestENTSOEEClientXMLParsing(TestCase):
    """Test ENTSO-E client XML parsing."""
    
    def setUp(self):
        """Set up test client."""
        self.client = ENTSOEEClient(api_key="test-key")
    
    def tearDown(self):
        """Clean up."""
        self.client.close()
    
    def test_parse_simple_response(self):
        """Test parsing a simple XML response."""
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <glMarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0">
            <TimeSeries>
                <mRID codingScheme="A01">1</mRID>
                <businessType>A01</businessType>
                <inDomain.mRID codingScheme="A01">10YSE-4--------2</inDomain.mRID>
                <outDomain.mRID codingScheme="A01">10YSE-4--------2</outDomain.mRID>
                <currency_Unit.name>EUR</currency_Unit.name>
                <price_Amount unit="MWH">42.50</price_Amount>
                <Periode>
                    <timeInterval>
                        <start>2026-10-19T00:00:00Z</start>
                        <end>2026-10-19T01:00:00Z</end>
                    </timeInterval>
                    <Point>
                        <position>1</position>
                        <price.amount>42.50</price.amount>
                    </Point>
                </Periode>
            </TimeSeries>
        </glMarketDocument>"""
        
        prices = self.client._parse_day_ahead_response(xml_data)
        
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].price_eur_per_mwh, 42.50)
        self.assertEqual(prices[0].currency, "EUR")
        self.assertEqual(prices[0].unit, "MWH")
    
    def test_parse_multiple_prices(self):
        """Test parsing XML with multiple price points."""
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <glMarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0">
            <TimeSeries>
                <currency_Unit.name>EUR</currency_Unit.name>
                <price_Amount unit="MWH">42.50</price_Amount>
                <Periode>
                    <timeInterval>
                        <start>2026-10-19T00:00:00Z</start>
                        <end>2026-10-19T01:00:00Z</end>
                    </timeInterval>
                    <Point>
                        <price.amount>42.50</price.amount>
                    </Point>
                    <Point>
                        <price.amount>43.00</price.amount>
                    </Point>
                </Periode>
            </TimeSeries>
        </glMarketDocument>"""
        
        prices = self.client._parse_day_ahead_response(xml_data)
        
        self.assertEqual(len(prices), 2)
        # Check that both prices are present (order may vary due to parsing)
        price_values = {p.price_eur_per_mwh for p in prices}
        self.assertIn(42.50, price_values)
        self.assertIn(43.00, price_values)
    
    def test_parse_with_namespace(self):
        """Test parsing XML with explicit namespace."""
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <glMarketDocument xmlns:gl="urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0">
            <gl:TimeSeries>
                <gl:currency_Unit.name>EUR</gl:currency_Unit.name>
                <gl:price_Amount unit="MWH">42.50</gl:price_Amount>
                <gl:Periode>
                    <gl:timeInterval>
                        <gl:start>2026-10-19T00:00:00Z</gl:start>
                        <gl:end>2026-10-19T01:00:00Z</gl:end>
                    </gl:timeInterval>
                    <gl:Point>
                        <gl:price.amount>42.50</gl:price.amount>
                    </gl:Point>
                </gl:Periode>
            </gl:TimeSeries>
        </glMarketDocument>"""
        
        prices = self.client._parse_day_ahead_response(xml_data)
        
        # Should handle namespaced XML
        self.assertGreater(len(prices), 0)
    
    def test_parse_empty_response(self):
        """Test parsing empty XML response."""
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
        <glMarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0">
            <TimeSeries></TimeSeries>
        </glMarketDocument>"""
        
        prices = self.client._parse_day_ahead_response(xml_data)
        self.assertEqual(len(prices), 0)
    
    def test_parse_invalid_xml(self):
        """Test parsing invalid XML."""
        with self.assertRaises(ENTSOEEClientError) as context:
            self.client._parse_day_ahead_response("not valid xml")
        self.assertIn("Failed to parse XML", str(context.exception))


class TestENTSOEEClientNormalization(TestCase):
    """Test ENTSO-E client data normalization."""
    
    def setUp(self):
        """Set up test client."""
        self.client = ENTSOEEClient(api_key="test-key")
    
    def tearDown(self):
        """Clean up."""
        self.client.close()
    
    def test_to_plugin_format_basic(self):
        """Test conversion to plugin format with exchange rate."""
        entries = [
            ENTSOEPriceEntry(
                price_eur_per_mwh=42.50,
                start=datetime(2026, 10, 19, 0, 0, 0),
                end=datetime(2026, 10, 19, 1, 0, 0),
                currency="EUR",
                unit="MWH"
            )
        ]
        
        result = self.client.to_plugin_format(
            entries,
            target_currency="EUR",
            exchange_rate_sek=11.0
        )
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["EUR_per_kWh"], 0.0425)  # 42.50 / 1000
        self.assertEqual(result[0]["SEK_per_kWh"], 0.4675)  # 0.0425 * 11.0
        self.assertEqual(result[0]["EXR"], 11.0)
        self.assertEqual(result[0]["time_start"], "2026-10-19 00:00:00")
    
    def test_to_plugin_format_no_exchange_rate(self):
        """Test conversion without exchange rate."""
        entries = [
            ENTSOEPriceEntry(
                price_eur_per_mwh=42.50,
                start=datetime(2026, 10, 19, 0, 0, 0),
                end=datetime(2026, 10, 19, 1, 0, 0),
                currency="EUR",
                unit="MWH"
            )
        ]
        
        result = self.client.to_plugin_format(
            entries,
            target_currency="EUR",
            exchange_rate_sek=None
        )
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["EUR_per_kWh"], 0.0425)
        self.assertIsNone(result[0]["SEK_per_kWh"])
        self.assertIsNone(result[0]["EXR"])


class TestENTSOEEClientContextManager(TestCase):
    """Test ENTSO-E client context manager."""
    
    def test_context_manager(self):
        """Test using client as context manager."""
        with ENTSOEEClient(api_key="test-key") as client:
            self.assertIsNotNone(client)
            self.assertIsNotNone(client.session)
        
        # Session should be closed after context
        self.assertIsNone(client.session)


class TestENTSOEEClientMockAPI(TestCase):
    """Test ENTSO-E client with mocked API responses."""
    
    @patch('requests.Session.get')
    def test_fetch_with_mock(self, mock_get):
        """Test fetching data with mocked response."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """<?xml version="1.0" encoding="UTF-8"?>
        <glMarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:glmarketdocument:1:0">
            <TimeSeries>
                <currency_Unit.name>EUR</currency_Unit.name>
                <price_Amount unit="MWH">42.50</price_Amount>
                <Periode>
                    <timeInterval>
                        <start>2026-10-19T00:00:00Z</start>
                        <end>2026-10-19T01:00:00Z</end>
                    </timeInterval>
                    <Point>
                        <price.amount>42.50</price.amount>
                    </Point>
                </Periode>
            </TimeSeries>
        </glMarketDocument>"""
        mock_get.return_value = mock_response
        
        client = ENTSOEEClient(api_key="test-key")
        prices = client.get_day_ahead_prices("SE4", date(2026, 10, 19))
        
        self.assertEqual(len(prices), 1)
        self.assertEqual(prices[0].price_eur_per_mwh, 42.50)
        
        client.close()
    
    @patch('requests.Session.get')
    def test_fetch_http_error(self, mock_get):
        """Test error handling for HTTP errors."""
        # Create a mock HTTPError with response attribute
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        # Create the HTTPError with the response
        error = requests.exceptions.HTTPError("Unauthorized")
        error.response = mock_response
        
        mock_response.raise_for_status.side_effect = error
        mock_get.return_value = mock_response
        
        client = ENTSOEEClient(api_key="test-key")
        
        with self.assertRaises(ENTSOEEClientError) as context:
            client.get_day_ahead_prices("SE4", date(2026, 10, 19))
        
        self.assertIn("HTTP error 401", str(context.exception))
        
        client.close()
    
    @patch('requests.Session.get')
    def test_fetch_connection_error(self, mock_get):
        """Test error handling for connection errors."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Failed to connect")
        
        client = ENTSOEEClient(api_key="test-key")
        
        with self.assertRaises(ENTSOEEClientError) as context:
            client.get_day_ahead_prices("SE4", date(2026, 10, 19))
        
        self.assertIn("Connection error", str(context.exception))
        
        client.close()
    
    @patch('requests.Session.get')
    def test_fetch_timeout(self, mock_get):
        """Test error handling for timeout."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        client = ENTSOEEClient(api_key="test-key")
        
        with self.assertRaises(ENTSOEEClientError) as context:
            client.get_day_ahead_prices("SE4", date(2026, 10, 19))
        
        self.assertIn("Request timed out", str(context.exception))
        
        client.close()


if __name__ == '__main__':
    import unittest
    unittest.main()
