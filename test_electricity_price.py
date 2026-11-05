#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, 'src')

from unittest.mock import MagicMock
from plugins.electricity_price.electricity_price import ElectricityPrice
from PIL import Image

def test_electricity_price():
    # Create a minimal config for the plugin
    config = {
        "id": "electricity_price",
        "name": "Electricity Price",
        "description": "Show electricity prices",
        "author": "Test",
        "version": "1.0.0",
        "plugin_module": "plugins.electricity_price.electricity_price",
        "plugin_class": "ElectricityPrice"
    }
    
    plugin = ElectricityPrice(config)
    
    # Mock device config
    mock_device_config = MagicMock()
    mock_device_config.get_resolution.return_value = [800, 480]
    mock_device_config.get_config.side_effect = lambda key, default=None: {
        'orientation': 'horizontal',
        'timezone': 'Europe/Stockholm',
        'time_format': '24h'
    }.get(key, default)
    
    # Plugin settings - test with label disabled
    settings = {
        "zone": "SE4",
        "show_max_label": False
    }
    
    try:
        # Generate image
        image = plugin.generate_image(settings, mock_device_config)
        
        # Save the image
        output_path = "src/static/images/test_electricity_price.png"
        image.save(output_path)
        print(f"Image generated successfully: {output_path}")
        
        # Show image info
        print(f"Image size: {image.size}")
        print(f"Image mode: {image.mode}")
        
    except Exception as e:
        print(f"Error generating image: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_electricity_price()
