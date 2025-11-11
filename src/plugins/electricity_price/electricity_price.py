from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from plugins.base_plugin.base_plugin import BasePlugin
import requests
import pytz
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_service_url():
    today = datetime.now().date()
    year = today.year
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"
    return f"https://www.elprisetjustnu.se/api/v1/prices/{year}/{month}-{day}_SE4.json"

@dataclass
class ElectricityPriceEntry:
    SEK_per_kWh: float
    EUR_per_kWh: float
    EXR: float
    time_start: str
    time_end: str

class ElectricityPrice(BasePlugin):
    data: list[ElectricityPriceEntry] = []

    def generate_image(self, settings, device_config):
        self.data = self.fetch_json()
        data_dicts = [asdict(entry) for entry in self.data]
        template_params = {"data": data_dicts}

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        template_params["plugin_settings"] = settings
        template_params["title"] = "Electricity Prices - " + datetime.now(tz).strftime("%Y-%m-%d")
        template_params["current_date"] = datetime.now(tz).strftime("%Y-%m-%d")

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        logger.info(f"Using template parameters: {template_params}")

        image = self.render_image(dimensions, "electricity_price.html", "electricity_price.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        
        return image
    
    def fetch_json(self):
        url = get_service_url()
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return [ElectricityPriceEntry(**entry) for entry in data]