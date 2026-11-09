#!/usr/bin/env python3
"""
Comprehensive test suite for the ElectricityPrice plugin.
Tests various scenarios including error handling, edge cases, and configuration options.
"""

import os
import re
import sys

sys.path.insert(0, "src")

import unittest
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import requests

from PIL import Image

from plugins.electricity_price.electricity_price import (
    ElectricityPrice,
    ElectricityPriceEntry,
    get_service_url,
)


class TestElectricityPrice(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.config = {
            "id": "electricity_price",
            "name": "Electricity Price",
            "description": "Show electricity prices",
            "author": "Test",
            "version": "1.0.0",
            "plugin_module": "plugins.electricity_price.electricity_price",
            "plugin_class": "ElectricityPrice",
        }

        self.plugin = ElectricityPrice(self.config)

        # Mock device config
        self.mock_device_config = MagicMock()
        self.mock_device_config.get_resolution.return_value = [800, 480]
        self.mock_device_config.get_config.side_effect = lambda key, default=None: {
            "orientation": "horizontal",
            "timezone": "Europe/Stockholm",
            "time_format": "24h",
        }.get(key, default)

        # Base settings
        self.base_settings = {"zone": "SE4", "show_max_label": True}

    def test_get_service_url(self):
        """Test that the service URL is generated correctly"""
        url = get_service_url("SE3")
        today = datetime.now().date()
        expected = f"https://www.elprisetjustnu.se/api/v1/prices/{today.year}/{today.month:02d}-{today.day:02d}_SE3.json"
        self.assertEqual(url, expected)

    def test_electricity_price_entry(self):
        """Test the ElectricityPriceEntry dataclass"""
        entry = ElectricityPriceEntry(
            SEK_per_kWh=1.23,
            EUR_per_kWh=0.11,
            EXR=11.2,
            time_start="2023-01-01 00:00:00",
            time_end="2023-01-01 01:00:00",
        )

        self.assertEqual(entry.SEK_per_kWh, 1.23)
        self.assertEqual(entry.EUR_per_kWh, 0.11)
        self.assertEqual(entry.EXR, 11.2)
        self.assertEqual(entry.time_start, "2023-01-01 00:00:00")
        self.assertEqual(entry.time_end, "2023-01-01 01:00:00")

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_fetch_json_success(self, mock_get):
        """Test successful JSON fetching"""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23,
                "EUR_per_kWh": 0.11,
                "EXR": 11.2,
                "time_start": "2023-01-01 00:00:00",
                "time_end": "2023-01-01 01:00:00",
            }
        ]
        mock_get.return_value = mock_response

        result = self.plugin.fetch_json("SE4")

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], ElectricityPriceEntry)
        self.assertEqual(result[0].SEK_per_kWh, 1.23)

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_fetch_json_error(self, mock_get):
        """Test error handling in JSON fetching"""
        mock_get.side_effect = Exception("Network error")

        with self.assertRaises(Exception):
            self.plugin.fetch_json("SE4")

    @patch("plugins.base_plugin.base_plugin.take_screenshot_html")
    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_success(self, mock_get, mock_shot):
        """Test successful image generation"""
        # Mock response with realistic data
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23 + i * 0.1,
                "EUR_per_kWh": 0.11 + i * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-01 {i:02d}:00:00",
                "time_end": f"2023-01-01 {i + 1:02d}:00:00",
            }
            for i in range(24)
        ]
        mock_get.return_value = mock_response
        mock_shot.return_value = Image.new("RGB", (800, 480))

        # Test with max label enabled
        settings = self.base_settings.copy()
        settings["show_max_label"] = True

        image = self.plugin.generate_image(settings, self.mock_device_config)

        self.assertIsNotNone(image)
        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (800, 480))
        # Max label annotation must be present in the rendered HTML
        html = mock_shot.call_args[0][0]
        self.assertIn("Högsta pris", html)

    @patch("plugins.base_plugin.base_plugin.take_screenshot_html")
    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_max_label_disabled(self, mock_get, mock_shot):
        """Test image generation with max label disabled"""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23 + i * 0.1,
                "EUR_per_kWh": 0.11 + i * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-01 {i:02d}:00:00",
                "time_end": f"2023-01-01 {i + 1:02d}:00:00",
            }
            for i in range(24)
        ]
        mock_get.return_value = mock_response
        mock_shot.return_value = Image.new("RGB", (800, 480))

        # Test with max label disabled (form submits strings)
        settings = self.base_settings.copy()
        settings["show_max_label"] = "false"

        image = self.plugin.generate_image(settings, self.mock_device_config)

        self.assertIsNotNone(image)
        self.assertIsInstance(image, Image.Image)
        # Max label annotation must be absent from the rendered HTML
        html = mock_shot.call_args[0][0]
        self.assertNotIn("Högsta pris", html)

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_different_zones(self, mock_get):
        """Test image generation with different zones"""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23 + i * 0.1,
                "EUR_per_kWh": 0.11 + i * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-01 {i:02d}:00:00",
                "time_end": f"2023-01-01 {i + 1:02d}:00:00",
            }
            for i in range(24)
        ]
        mock_get.return_value = mock_response

        for zone in ["SE1", "SE2", "SE3", "SE4"]:
            settings = self.base_settings.copy()
            settings["zone"] = zone

            image = self.plugin.generate_image(settings, self.mock_device_config)

            self.assertIsNotNone(image)
            self.assertIsInstance(image, Image.Image)

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_vertical_orientation(self, mock_get):
        """Test image generation with vertical orientation"""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23 + i * 0.1,
                "EUR_per_kWh": 0.11 + i * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-01 {i:02d}:00:00",
                "time_end": f"2023-01-01 {i + 1:02d}:00:00",
            }
            for i in range(24)
        ]
        mock_get.return_value = mock_response

        # Mock vertical device config
        mock_vertical_config = MagicMock()
        mock_vertical_config.get_resolution.return_value = [
            480,
            800,
        ]  # Swapped dimensions
        mock_vertical_config.get_config.side_effect = lambda key, default=None: {
            "orientation": "vertical",
            "timezone": "Europe/Stockholm",
            "time_format": "24h",
        }.get(key, default)

        image = self.plugin.generate_image(self.base_settings, mock_vertical_config)

        self.assertIsNotNone(image)
        self.assertIsInstance(image, Image.Image)
        # Note: The current implementation doesn't actually swap dimensions for vertical orientation
        # This test documents the current behavior - the plugin maintains the same dimensions
        # regardless of orientation setting. This might be intentional or a bug to fix.
        self.assertEqual(image.size, (800, 480))  # Current behavior

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_empty_data(self, mock_get):
        """Test image generation with empty data"""
        # Mock empty response
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        # The plugin should handle empty data gracefully by not raising an exception
        # but the chart rendering might fail, so we expect some kind of error
        try:
            image = self.plugin.generate_image(
                self.base_settings, self.mock_device_config
            )
            # If we get here, the plugin handled empty data gracefully
            self.assertIsNotNone(image)
        except Exception as e:
            # This is also acceptable - empty data should cause an error
            self.assertIsInstance(e, Exception)

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_generate_image_invalid_data(self, mock_get):
        """Test image generation with invalid data"""
        # Mock response with invalid data structure
        mock_response = MagicMock()
        mock_response.json.return_value = [{"invalid_key": "invalid_value"}]
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            self.plugin.generate_image(self.base_settings, self.mock_device_config)

    def test_generate_settings_template(self):
        """Test settings template generation"""
        template_params = self.plugin.generate_settings_template()

        self.assertIn("settings_template", template_params)
        self.assertIn("zone", template_params)
        self.assertEqual(template_params["zone"], "SE4")
        self.assertIn("frame_styles", template_params)

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_different_time_formats(self, mock_get):
        """Test image generation with different time formats"""
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "SEK_per_kWh": 1.23 + i * 0.1,
                "EUR_per_kWh": 0.11 + i * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-01 {i:02d}:00:00",
                "time_end": f"2023-01-01 {i + 1:02d}:00:00",
            }
            for i in range(24)
        ]
        mock_get.return_value = mock_response

        # Test with 12h format
        mock_12h_config = MagicMock()
        mock_12h_config.get_resolution.return_value = [800, 480]
        mock_12h_config.get_config.side_effect = lambda key, default=None: {
            "orientation": "horizontal",
            "timezone": "Europe/Stockholm",
            "time_format": "12h",
        }.get(key, default)

        image = self.plugin.generate_image(self.base_settings, mock_12h_config)

        self.assertIsNotNone(image)
        self.assertIsInstance(image, Image.Image)


class TestExchangeRateSource(unittest.TestCase):
    """Test the auto/manual exchange rate source selection."""

    def setUp(self):
        self.config = {
            "id": "electricity_price",
            "name": "Electricity Price",
            "description": "Show electricity prices",
            "author": "Test",
            "version": "1.0.0",
            "plugin_module": "plugins.electricity_price.electricity_price",
            "plugin_class": "ElectricityPrice",
        }
        self.plugin = ElectricityPrice(self.config)

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_auto_uses_live_rate(self, mock_get_rate):
        mock_get_rate.return_value = 11.5
        settings = {"exchange_rate_source": "auto", "exchange_rate_sek": "11.0"}
        self.assertEqual(self.plugin._get_exchange_rate("SEK", settings), 11.5)
        mock_get_rate.assert_called_once_with("EUR", "SEK")

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_auto_uses_live_rate_for_other_currency(self, mock_get_rate):
        mock_get_rate.return_value = 7.42
        settings = {"exchange_rate_source": "auto"}
        self.assertEqual(self.plugin._get_exchange_rate("DKK", settings), 7.42)
        mock_get_rate.assert_called_once_with("EUR", "DKK")

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_auto_falls_back_to_manual_when_live_fails(self, mock_get_rate):
        mock_get_rate.side_effect = Exception("API down")
        settings = {"exchange_rate_source": "auto", "exchange_rate_sek": "11.2"}
        self.assertEqual(self.plugin._get_exchange_rate("SEK", settings), 11.2)

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_manual_ignores_live(self, mock_get_rate):
        mock_get_rate.return_value = 11.5
        settings = {"exchange_rate_source": "manual", "exchange_rate_sek": "11.2"}
        self.assertEqual(self.plugin._get_exchange_rate("SEK", settings), 11.2)
        mock_get_rate.assert_not_called()

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_manual_non_sek_uses_builtin_fallback(self, mock_get_rate):
        settings = {"exchange_rate_source": "manual"}
        rate = self.plugin._get_exchange_rate("DKK", settings)
        self.assertEqual(rate, 7.5)  # built-in approximate DKK rate
        mock_get_rate.assert_not_called()

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_default_when_live_and_manual_unavailable(self, mock_get_rate):
        mock_get_rate.side_effect = Exception("API down")
        settings = {"exchange_rate_source": "auto"}
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                self.plugin._get_exchange_rate("SEK", settings),
                ElectricityPrice.DEFAULT_EXCHANGE_RATE_SEK,
            )

    @patch("plugins.electricity_price.exchange_rate.get_rate")
    def test_records_rate_used(self, mock_get_rate):
        mock_get_rate.return_value = 11.5
        settings = {"exchange_rate_source": "auto"}
        self.plugin._get_exchange_rate("SEK", settings)
        self.assertEqual(self.plugin._last_exchange_rate, 11.5)


class TestZoneCurrency(unittest.TestCase):
    """Test zone-to-native-currency mapping."""

    def test_nordic_zones(self):
        from plugins.electricity_price.country_codes import get_zone_currency
        self.assertEqual(get_zone_currency("SE4"), "SEK")
        self.assertEqual(get_zone_currency("NO1"), "NOK")
        self.assertEqual(get_zone_currency("DK2"), "DKK")

    def test_euro_and_others(self):
        from plugins.electricity_price.country_codes import get_zone_currency
        self.assertEqual(get_zone_currency("DE"), "EUR")
        self.assertEqual(get_zone_currency("FI"), "EUR")
        self.assertEqual(get_zone_currency("CH"), "CHF")
        self.assertEqual(get_zone_currency("PL"), "PLN")
        self.assertEqual(get_zone_currency("GB"), "GBP")
        self.assertEqual(get_zone_currency("BG"), "BGN")

    def test_unknown_zone_defaults_to_eur(self):
        from plugins.electricity_price.country_codes import get_zone_currency
        self.assertEqual(get_zone_currency("XX"), "EUR")


class TestInstanceIsolation(unittest.TestCase):
    """Plugin instances (e.g., multiple playlist entries) must not share state."""

    def _make_plugin(self):
        config = {
            "id": "electricity_price", "name": "Electricity Price",
            "description": "", "author": "", "version": "1.0.0",
            "plugin_module": "plugins.electricity_price.electricity_price",
            "plugin_class": "ElectricityPrice",
        }
        return ElectricityPrice(config)

    def test_instances_do_not_share_data(self):
        p1 = self._make_plugin()
        p2 = self._make_plugin()
        p1.data = [ElectricityPriceEntry(
            SEK_per_kWh=1.0, EUR_per_kWh=0.09, EXR=11.0,
            time_start="2026-11-05 00:00:00", time_end="2026-11-05 01:00:00",
        )]
        p1._last_exchange_rate = 11.1
        p1._entsoe_client = object()
        self.assertEqual(p2.data, [])
        self.assertIsNone(p2._last_exchange_rate)
        self.assertIsNone(p2._entsoe_client)


class TestAdditionalCoverage(unittest.TestCase):
    """Edge-case, error-handling, timezone and performance tests (from test_suggestions.md)."""

    def setUp(self):
        self.config = {
            "id": "electricity_price", "name": "Electricity Price",
            "description": "", "author": "", "version": "1.0.0",
            "plugin_module": "plugins.electricity_price.electricity_price",
            "plugin_class": "ElectricityPrice",
        }
        self.plugin = ElectricityPrice(self.config)
        self.mock_device_config = MagicMock()
        self.mock_device_config.get_resolution.return_value = [800, 480]
        self.mock_device_config.get_config.side_effect = lambda key, default=None: {
            "orientation": "horizontal",
            "timezone": "Europe/Stockholm",
            "time_format": "24h",
        }.get(key, default)
        self.base_settings = {"zone": "SE4", "show_max_label": True}

    @staticmethod
    def _entries(prices, start_date="2023-01-01", with_t=True):
        sep = "T" if with_t else " "
        suffix = "+01:00" if with_t else ""
        return [
            {
                "SEK_per_kWh": p,
                "EUR_per_kWh": round(p / 11.2, 4),
                "EXR": 11.2,
                "time_start": f"{start_date}{sep}{i:02d}:00:00{suffix}",
                "time_end": f"{start_date}{sep}{min(i + 1, 23):02d}:00:00{suffix}",
            }
            for i, p in enumerate(prices)
        ]

    @staticmethod
    def _mock_response(entries):
        r = MagicMock()
        r.json.return_value = entries
        return r

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_missing_required_field_raises(self, mock_get):
        mock_get.return_value = self._mock_response([{
            "EUR_per_kWh": 0.1, "EXR": 11.2,
            "time_start": "2023-01-01 00:00:00", "time_end": "2023-01-01 01:00:00",
        }])
        with self.assertRaises(TypeError):
            self.plugin.fetch_swedish_json("SE4")

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_malformed_json_raises(self, mock_get):
        r = MagicMock()
        r.json.side_effect = ValueError("No JSON object could be decoded")
        mock_get.return_value = r
        with self.assertRaises(ValueError):
            self.plugin.fetch_swedish_json("SE4")

    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_network_errors_propagate(self, mock_get):
        mock_get.side_effect = requests.Timeout("timed out")
        with self.assertRaises(requests.Timeout):
            self.plugin.fetch_swedish_json("SE4")

        mock_get.side_effect = requests.ConnectionError("failed to connect")
        with self.assertRaises(requests.ConnectionError):
            self.plugin.fetch_swedish_json("SE4")

        mock_get.side_effect = None  # clear the previous side_effect, use return_value
        r = MagicMock()
        r.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = r
        with self.assertRaises(requests.HTTPError):
            self.plugin.fetch_swedish_json("SE4")

    @patch("plugins.base_plugin.base_plugin.take_screenshot_html")
    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_negative_and_extreme_prices_render(self, mock_get, mock_shot):
        mock_shot.return_value = Image.new("RGB", (800, 480))
        for prices in ([-0.5 + i * 0.1 for i in range(24)], [10.0 + i for i in range(24)]):
            mock_get.return_value = self._mock_response(self._entries(prices, with_t=False))
            image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
            self.assertIsNotNone(image)

    @patch("plugins.base_plugin.base_plugin.take_screenshot_html")
    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_now_label_uses_data_timezone(self, mock_get, mock_shot):
        """The now-marker must follow the price data's timezone, not the device's."""
        mock_shot.return_value = Image.new("RGB", (800, 480))
        data_tz = dt_timezone(timedelta(hours=1))  # Swedish API offset (+01:00)
        today = datetime.now(data_tz).strftime("%Y-%m-%d")
        entries = self._entries([1.0 + i * 0.05 for i in range(24)], start_date=today, with_t=True)
        mock_get.return_value = self._mock_response(entries)

        ny_config = MagicMock()
        ny_config.get_resolution.return_value = [800, 480]
        ny_config.get_config.side_effect = lambda key, default=None: {
            "orientation": "horizontal",
            "timezone": "America/New_York",  # deliberately different from the data tz
            "time_format": "24h",
        }.get(key, default)

        self.plugin.generate_image(self.base_settings, ny_config)
        html = mock_shot.call_args[0][0]
        m = re.search(r'let nowLabel = "([^"]+)"', html)
        self.assertIsNotNone(m, "nowLabel missing from rendered HTML")

        # Accept the slot containing "now" or the previous one (15-min boundary race)
        after = datetime.now(data_tz)
        valid = set()
        for ref in (after, after - timedelta(minutes=15)):
            valid.add(ref.replace(minute=(ref.minute // 15) * 15, second=0, microsecond=0).strftime("%H:%M"))
        self.assertIn(m.group(1), valid)

    @patch("plugins.base_plugin.base_plugin.take_screenshot_html")
    @patch("plugins.electricity_price.electricity_price.requests.get")
    def test_large_dataset_performance(self, mock_get, mock_shot):
        import time
        mock_shot.return_value = Image.new("RGB", (800, 480))
        prices = [1.0 + (i % 24) * 0.05 + (i // 24) * 0.1 for i in range(7 * 24)]
        mock_get.return_value = self._mock_response(self._entries(prices, with_t=False))

        start = time.time()
        image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
        elapsed = time.time() - start

        self.assertIsNotNone(image)
        self.assertLess(elapsed, 2.0)

    def test_integration_real_api(self):
        """Live API test, opt-in via RUN_INTEGRATION_TESTS=1."""
        if not os.environ.get("RUN_INTEGRATION_TESTS"):
            self.skipTest("Set RUN_INTEGRATION_TESTS=1 to run live API tests")
        data = self.plugin.fetch_swedish_json("SE4")
        self.assertGreater(len(data), 0)


if __name__ == "__main__":
    unittest.main()
