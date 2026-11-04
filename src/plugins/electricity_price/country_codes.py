"""
Country/Zone to ENTSO-E EIC Code Mappings

This module provides mappings between user-friendly country/zone codes
and the official ENTSO-E EIC (Energy Identification Code) domain codes.

Reference: https://www.entsoe.eu/data-portal/energy-identification-codes-eic
"""

from typing import Dict, Optional

# Mapping of country/zone codes to ENTSO-E EIC domain codes
# Format: {country_zone: eic_code}
# Country codes follow ISO 3166-1 alpha-2 where applicable

ENTSOE_COUNTRY_CODES: Dict[str, str] = {
    # Sweden - 4 bidding zones
    "SE1": "10YSE-1--------2",  # Northern Sweden (Luleå)
    "SE2": "10YSE-2--------2",  # Central Sweden (Sundsvall)
    "SE3": "10YSE-3--------2",  # Southern Sweden (Malmö)
    "SE4": "10YSE-4--------2",  # Stockholm/Malmö area
    
    # Norway - 5 bidding zones
    "NO1": "10YNO-1--------2",  # Oslo area
    "NO2": "10YNO-2--------2",  # Kristiansand
    "NO3": "10YNO-3--------2",  # Trondheim
    "NO4": "10YNO-4--------2",  # Tromsø
    "NO5": "10YNO-5--------2",  # Bergen
    
    # Denmark - 2 bidding zones
    "DK1": "10YDK-1--------W",  # Western Denmark (Jutland/Funen)
    "DK2": "10YDK-2--------M",  # Eastern Denmark (Zealand)
    
    # Finland - 1 bidding zone
    "FI": "10YFI-1--------U",
    
    # Germany - 1 bidding zone (for day-ahead market)
    "DE": "10YDE-RW-------I",
    
    # Netherlands - 1 bidding zone
    "NL": "10YNL----------L",
    
    # Belgium - 1 bidding zone
    "BE": "10YBE----------2",
    
    # France - 1 bidding zone
    "FR": "10YFR-RTE------C",
    
    # Austria - 1 bidding zone
    "AT": "10YAT-APG------W",
    
    # Switzerland - 1 bidding zone
    "CH": "10YCH-SWISSGRIDZ",
    
    # Poland - 1 bidding zone
    "PL": "10YPL-AREA-----S",
    
    # Spain - 1 bidding zone
    "ES": "10YES-REE------0",
    
    # Portugal - 1 bidding zone
    "PT": "10YPT-REN------W",
    
    # Italy - Multiple zones (using North as default)
    "IT": "10YIT-GRTN-----B",
    "IT-NORD": "10YIT-GRTN-----B",
    "IT-CNOR": "10Y1001A1001A699",
    "IT-CSUD": "10Y1001A1001A700",
    "IT-SUD": "10Y1001A1001A719",
    "IT-CALA": "10Y1001A1001A720",
    "IT-SICI": "10Y1001A1001A721",
    "IT-SARD": "10Y1001A1001A722",
    
    # United Kingdom - Multiple zones
    "GB": "10YGB----------A",
    "GB-NGA": "10Y1001A1001A929",
    
    # Ireland
    "IE": "10YIE-1001A08H--U",
    
    # Baltic States
    "EE": "10Y1001A1001A48S",  # Estonia
    "LV": "10YLV-1001A00074J",  # Latvia
    "LT": "10YLT-1001A0008QT",  # Lithuania
    
    # Eastern Europe
    "CZ": "10YCZ-CEPS-----N",  # Czech Republic
    "SK": "10YSK-SEPS-----K",  # Slovakia
    "HU": "10YHU-MAVIR----N",  # Hungary
    "RO": "10YRO-TEL------P",  # Romania
    "BG": "10YCA-TSO-------W",  # Bulgaria
    "GR": "10YGR-HTSO------Y",  # Greece
    "HR": "10YHR-HEP------M",  # Croatia
    "SI": "10YSI-ELES-----O",  # Slovenia
}

# Reverse mapping: EIC code to country/zone code
EIC_TO_COUNTRY: Dict[str, str] = {v: k for k, v in ENTSOE_COUNTRY_CODES.items()}

# Group countries by region for UI organization
COUNTRY_GROUPS: Dict[str, list] = {
    "Sweden": ["SE1", "SE2", "SE3", "SE4"],
    "Norway": ["NO1", "NO2", "NO3", "NO4", "NO5"],
    "Denmark": ["DK1", "DK2"],
    "Finland": ["FI"],
    "Germany": ["DE"],
    "Netherlands": ["NL"],
    "Belgium": ["BE"],
    "France": ["FR"],
    "Austria": ["AT"],
    "Switzerland": ["CH"],
    "Poland": ["PL"],
    "Spain": ["ES", "PT"],  # Spain and Portugal often grouped
    "Italy": ["IT", "IT-NORD", "IT-CNOR", "IT-CSUD", "IT-SUD", "IT-CALA", "IT-SICI", "IT-SARD"],
    "UK & Ireland": ["GB", "IE"],
    "Baltic States": ["EE", "LV", "LT"],
    "Eastern Europe": ["CZ", "SK", "HU", "RO", "BG", "GR", "HR", "SI"],
}


def get_eic_code(country_zone: str) -> Optional[str]:
    """
    Get ENTSO-E EIC code for a given country/zone code.
    
    Args:
        country_zone: Country/zone code (e.g., "SE4", "NO1", "DE")
        
    Returns:
        EIC code as string, or None if not found
    """
    return ENTSOE_COUNTRY_CODES.get(country_zone.upper())


def get_country_from_eic(eic_code: str) -> Optional[str]:
    """
    Get country/zone code from an ENTSO-E EIC code.
    
    Args:
        eic_code: EIC code (e.g., "10YSE-4--------2")
        
    Returns:
        Country/zone code as string, or None if not found
    """
    return EIC_TO_COUNTRY.get(eic_code.upper())


def get_all_country_codes() -> list:
    """
    Get list of all supported country/zone codes.
    
    Returns:
        List of all country/zone codes
    """
    return list(ENTSOE_COUNTRY_CODES.keys())


def get_country_group(country_zone: str) -> Optional[str]:
    """
    Get the region group for a country/zone code.
    
    Args:
        country_zone: Country/zone code
        
    Returns:
        Region group name, or None if not found
    """
    for group_name, codes in COUNTRY_GROUPS.items():
        if country_zone.upper() in [c.upper() for c in codes]:
            return group_name
    return None


def get_countries_by_group(group_name: str) -> list:
    """
    Get all country/zone codes for a region group.
    
    Args:
        group_name: Region group name (e.g., "Sweden", "Norway")
        
    Returns:
        List of country/zone codes in the group
    """
    return COUNTRY_GROUPS.get(group_name, [])


def is_swedish_zone(country_zone: str) -> bool:
    """
    Check if a country/zone code is a Swedish zone.
    
    Args:
        country_zone: Country/zone code
        
    Returns:
        True if the code is a Swedish zone (SE1-SE4)
    """
    return country_zone.upper().startswith("SE") and country_zone.upper() in ENTSOE_COUNTRY_CODES
