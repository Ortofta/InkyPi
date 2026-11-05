# Additional Test Suggestions for Electricity Price Plugin

## Current Test Coverage
The comprehensive test suite covers:
- ✅ URL generation for different zones
- ✅ Data model validation (ElectricityPriceEntry)
- ✅ Successful JSON fetching
- ✅ Error handling in JSON fetching
- ✅ Image generation with various configurations
- ✅ Max label toggle functionality
- ✅ Different Swedish price zones (SE1-SE4)
- ✅ Orientation handling (horizontal/vertical)
- ✅ Empty and invalid data scenarios
- ✅ Settings template generation
- ✅ Different time formats (12h/24h)

## Suggested Additional Tests

### 1. API Response Validation Tests
```python
@patch('plugins.electricity_price.electricity_price.requests.get')
def test_api_response_validation(self, mock_get):
    """Test that the plugin validates API responses properly"""
    # Test with missing required fields
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "EUR_per_kWh": 0.11,  # Missing SEK_per_kWh
            "EXR": 11.2,
            "time_start": "2023-01-01 00:00:00",
            "time_end": "2023-01-01 01:00:00"
        }
    ]
    mock_get.return_value = mock_response
    
    with self.assertRaises(Exception):
        self.plugin.fetch_json("SE4")
```

### 2. Timezone Handling Tests
```python
@patch('plugins.electricity_price.electricity_price.requests.get')
def test_different_timezones(self, mock_get):
    """Test image generation with different timezones"""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "SEK_per_kWh": 1.23 + i * 0.1,
            "EUR_per_kWh": 0.11 + i * 0.01,
            "EXR": 11.2,
            "time_start": f"2023-01-01 {i:02d}:00:00",
            "time_end": f"2023-01-01 {i+1:02d}:00:00"
        } for i in range(24)
    ]
    mock_get.return_value = mock_response
    
    # Test with different timezones
    for timezone in ["America/New_York", "Europe/London", "Asia/Tokyo"]:
        mock_config = MagicMock()
        mock_config.get_resolution.return_value = [800, 480]
        mock_config.get_config.side_effect = lambda key, default=None: {
            'orientation': 'horizontal',
            'timezone': timezone,
            'time_format': '24h'
        }.get(key, default)
        
        image = self.plugin.generate_image(self.base_settings, mock_config)
        self.assertIsNotNone(image)
```

### 3. Edge Case Data Tests
```python
@patch('plugins.electricity_price.electricity_price.requests.get')
def test_extreme_price_values(self, mock_get):
    """Test with extreme price values"""
    # Test with very high prices
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "SEK_per_kWh": 10.0 + i,  # Very high prices
            "EUR_per_kWh": 1.0 + i * 0.1,
            "EXR": 11.2,
            "time_start": f"2023-01-01 {i:02d}:00:00",
            "time_end": f"2023-01-01 {i+1:02d}:00:00"
        } for i in range(24)
    ]
    mock_get.return_value = mock_response
    
    image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
    self.assertIsNotNone(image)
    
    # Test with negative prices (if possible in the market)
    mock_response.json.return_value = [
        {
            "SEK_per_kWh": -0.5 + i * 0.1,  # Negative prices
            "EUR_per_kWh": -0.05 + i * 0.01,
            "EXR": 11.2,
            "time_start": f"2023-01-01 {i:02d}:00:00",
            "time_end": f"2023-01-01 {i+1:02d}:00:00"
        } for i in range(24)
    ]
    
    image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
    self.assertIsNotNone(image)
```

### 4. Network Error Tests
```python
@patch('plugins.electricity_price.electricity_price.requests.get')
def test_network_errors(self, mock_get):
    """Test various network error scenarios"""
    # Test timeout
    mock_get.side_effect = requests.Timeout("Connection timed out")
    with self.assertRaises(requests.Timeout):
        self.plugin.fetch_json("SE4")
    
    # Test connection error
    mock_get.side_effect = requests.ConnectionError("Failed to connect")
    with self.assertRaises(requests.ConnectionError):
        self.plugin.fetch_json("SE4")
    
    # Test HTTP errors
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
    mock_get.return_value = mock_response
    with self.assertRaises(requests.HTTPError):
        self.plugin.fetch_json("SE4")
```

### 5. Performance Tests
```python
def test_performance_with_large_dataset(self):
    """Test performance with large datasets"""
    import time
    
    # Create a large dataset (e.g., multiple days)
    large_data = []
    for day in range(7):  # 7 days
        for hour in range(24):
            large_data.append({
                "SEK_per_kWh": 1.0 + hour * 0.05 + day * 0.1,
                "EUR_per_kWh": 0.1 + hour * 0.005 + day * 0.01,
                "EXR": 11.2,
                "time_start": f"2023-01-{day+1:02d} {hour:02d}:00:00",
                "time_end": f"2023-01-{day+1:02d} {hour+1:02d}:00:00"
            })
    
    with patch('plugins.electricity_price.electricity_price.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = large_data
        mock_get.return_value = mock_response
        
        start_time = time.time()
        image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
        end_time = time.time()
        
        self.assertIsNotNone(image)
        self.assertLess(end_time - start_time, 5.0)  # Should complete in under 5 seconds
```

### 6. Integration Tests
```python
def test_integration_with_real_api(self):
    """Integration test with real API (can be skipped in CI)"""
    # Only run if environment variable is set
    if not os.environ.get('RUN_INTEGRATION_TESTS'):
        self.skipTest("Integration tests skipped")
    
    # Test with real API
    try:
        data = self.plugin.fetch_json("SE4")
        self.assertGreater(len(data), 0)
        
        # Test image generation with real data
        image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
        self.assertIsNotNone(image)
        
    except Exception as e:
        self.fail(f"Integration test failed: {e}")
```

## Test Improvements Recommendations

### 1. Add Property-Based Testing
Consider using Hypothesis for property-based testing to generate random test data:
```python
from hypothesis import given, strategies as st

@given(
    zone=st.sampled_from(["SE1", "SE2", "SE3", "SE4"]),
    show_max_label=st.booleans(),
    orientation=st.sampled_from(["horizontal", "vertical"])
)
@patch('plugins.electricity_price.electricity_price.requests.get')
def test_property_based_configurations(self, mock_get, zone, show_max_label, orientation):
    """Test various configuration combinations"""
    mock_response = MagicMock()
    mock_response.json.return_value = self._generate_mock_data()
    mock_get.return_value = mock_response
    
    settings = {
        "zone": zone,
        "show_max_label": show_max_label
    }
    
    mock_config = MagicMock()
    mock_config.get_resolution.return_value = [800, 480]
    mock_config.get_config.side_effect = lambda key, default=None: {
        'orientation': orientation,
        'timezone': 'Europe/Stockholm',
        'time_format': '24h'
    }.get(key, default)
    
    image = self.plugin.generate_image(settings, mock_config)
    self.assertIsNotNone(image)
```

### 2. Add Visual Regression Testing
Consider adding visual regression tests to ensure the chart appearance remains consistent:
```python
def test_visual_regression(self):
    """Test that generated images match expected visual output"""
    with patch('plugins.electricity_price.electricity_price.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = self._generate_mock_data()
        mock_get.return_value = mock_response
        
        image = self.plugin.generate_image(self.base_settings, self.mock_device_config)
        
        # Save reference image if it doesn't exist
        ref_path = "tests/reference_images/electricity_price_reference.png"
        if not os.path.exists(ref_path):
            image.save(ref_path)
            self.skipTest("Reference image created, skipping visual comparison")
        
        # Compare with reference image
        ref_image = Image.open(ref_path)
        
        # Simple pixel comparison (could use more sophisticated image comparison)
        self.assertEqual(image.size, ref_image.size)
        self.assertEqual(image.mode, ref_image.mode)
        
        # For more advanced comparison, consider using libraries like:
        # - PIL's ImageChops.difference()
        # - OpenCV's image comparison
        # - perceptualdiff
```

### 3. Add Mock Data Generation Helper
```python
def _generate_mock_data(self, hours=24, base_price=1.0, variation=0.5):
    """Helper method to generate mock price data"""
    return [
        {
            "SEK_per_kWh": base_price + i * variation / hours,
            "EUR_per_kWh": (base_price + i * variation / hours) / 10,
            "EXR": 11.2,
            "time_start": f"2023-01-01 {i:02d}:00:00",
            "time_end": f"2023-01-01 {i+1:02d}:00:00"
        } for i in range(hours)
    ]
```

## Test Infrastructure Improvements

1. **Add test fixtures** for common test data and configurations
2. **Add test markers** to categorize tests (unit, integration, slow, etc.)
3. **Add test coverage measurement** to ensure all code paths are tested
4. **Add CI/CD integration** to run tests automatically on pushes
5. **Add test data management** for reference images and expected outputs

## Current Test Gaps Identified

1. **No tests for the HTML template rendering** - The chart generation relies heavily on JavaScript
2. **No tests for CSS styling** - Visual appearance isn't validated
3. **Limited error handling tests** - More network and data validation scenarios needed
4. **No performance tests** - Large datasets aren't tested
5. **No integration tests** - Real API calls aren't tested (though this is understandable)

The current test suite provides good basic coverage but could be enhanced with more comprehensive testing of edge cases, performance, and visual output.