# ENTSO-E API Integration Specification
## Electricity Price Plugin Extension

**Author:** Markus Svensson  
**Date:** 2026-10-19  
**Version:** 0.1 (Draft)  
**Status:** Proposal  

---

## 1. Overview

### 1.1 Purpose
This document specifies the integration of the **ENTSO-E Transparency Platform API** into the existing InkyPi electricity price plugin, enabling support for electricity price data across 25+ European countries beyond the current Swedish-only (elprisetjustnu.se) implementation.

### 1.2 Background
The current electricity price plugin only supports Swedish zones (SE1-SE4) via the `elprisetjustnu.se` API. ENTSO-E provides official electricity market data for most European countries, making it the ideal source for international expansion.

### 1.3 Goals
- ✅ Support 25+ European countries
- ✅ Maintain backward compatibility with Swedish API
- ✅ Consistent data format for all sources
- ✅ User-selectable data source (Swedish API or ENTSO-E)
- ✅ Graceful error handling and fallbacks

---

## 2. Scope

### 2.1 In Scope
- ENTSO-E API client implementation
- Data source selection in plugin settings
- Country/zone configuration
- Data normalization (ENTSO-E → plugin format)
- Error handling and retry logic
- XML parsing (ENTSO-E uses XML format)
- API key management

### 2.2 Out of Scope
- Real-time data streaming
- Historical data beyond current day
- Intraday market data (initial phase)
- User authentication flow
- Rate limiting at the API level (handled by ENTSO-E)

---

## 3. Technical Requirements

### 3.1 Dependencies

**New dependencies:**
```
requests>=2.33.0  # Already in requirements.txt
lxml>=4.9.3       # For XML parsing (or use built-in xml.etree)
python-dotenv>=1.2.2  # Already in requirements.txt
```

**No new dependencies required** - can use built-in `xml.etree.ElementTree` for XML parsing.

### 3.2 API Key Management

**Options:**
1. **Environment variable:** `ENTSOE_API_KEY` (recommended for production)
2. **Plugin settings:** Store in device config (encrypted)
3. **Config file:** `src/config/entsoe_api_key.txt`

**Recommended approach:** Option 1 (environment variable) with fallback to plugin settings for development.

---

## 4. Architecture

### 4.1 Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                 ElectricityPrice Plugin                     │
├─────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐      ┌──────────────────┐        │
│  │   Data Source     │      │   Data Source     │        │
│  │   Selector        │─────▶│   elprisetjustnu  │        │
│  │                   │      │   (Sweden only)    │        │
│  └──────────────────┘      └──────────────────┘        │
│           │                                         │        │
│           ▼                                         │        │
│  ┌───────────────────────────────────────────────────┐  │
│  │              ENTSO-E Client                        │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  │  │
│  │  │ API Key Manager │  │ Request Builder  │  │  │
│  │  └─────────────────┘  └─────────────────┘  │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  │  │
│  │  │ XML Parser      │  │ Data Normalizer  │  │  │
│  │  └─────────────────┘  └─────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Data Cache                            │  │
│  │  (Prevents repeated API calls for same day)        │  │
│  └───────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Chart Generator                        │  │
│  │  (Existing - no changes needed)                    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Class Structure

```python
# New file: src/plugins/electricity_price/entsoe_client.py

class ENTSOEEClient:
    """Client for ENTSO-E Transparency Platform API"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('ENTSOE_API_KEY')
        self.base_url = "https://web-api.tp.entsoe.eu/api"
        self.cache = {}
        
    def get_day_ahead_prices(self, country_code: str, date: datetime.date) -> list[dict]:
        """Fetch day-ahead prices for a specific country/zone"""
        pass
        
    def get_available_countries(self) -> dict:
        """Return mapping of country codes to EIC domain codes"""
        pass

# Modified file: src/plugins/electricity_price/electricity_price.py

class ElectricityPrice(BasePlugin):
    def __init__(self, config):
        super().__init__(config)
        self.data_source = "auto"  # or "swedish" or "entsoe"
        self.entsoe_client = None
        
    def _get_client(self, settings: dict) -> BasePriceClient:
        """Factory method to get appropriate client based on settings"""
        data_source = settings.get('data_source', 'auto')
        country = settings.get('zone', 'SE4')
        
        if data_source == 'swedish' or (data_source == 'auto' and country.startswith('SE')):
            return SwedishPriceClient()
        else:
            api_key = settings.get('entsoe_api_key') or os.getenv('ENTSOE_API_KEY')
            if not api_key:
                raise ValueError("ENTSO-E API key required")
            return ENTSOEEClient(api_key)
        
    def fetch_json(self, zone: str, settings: dict = None):
        """Fetch prices using appropriate client"""
        client = self._get_client(settings or {})
        return client.get_prices(zone)
```

---

## 5. Data Source Configuration

### 5.1 Settings Schema

**New settings for the plugin:**

```json
{
  "data_source": "auto",           // "auto" | "swedish" | "entsoe"
  "zone": "SE4",                  // Country/zone code
  "show_max_label": true,          // Existing setting
  "entsoe_api_key": ""            // Optional: store API key in settings
}
```

### 5.2 Country/Zone Mapping

**Format:** Use ISO country codes with zone suffixes where applicable

| Country | Zone Code | ENTSO-E EIC Code | Notes |
|---------|-----------|------------------|-------|
| Sweden | SE1 | 10YSE-1--------2 | Northern Sweden |
| Sweden | SE2 | 10YSE-2--------2 | Central Sweden |
| Sweden | SE3 | 10YSE-3--------2 | Southern Sweden |
| Sweden | SE4 | 10YSE-4--------2 | Stockholm/Malmö |
| Norway | NO1 | 10YNO-1--------2 | Oslo area |
| Norway | NO2 | 10YNO-2--------2 | Kristiansand |
| Norway | NO3 | 10YNO-3--------2 | Trondheim |
| Norway | NO4 | 10YNO-4--------2 | Tromsø |
| Norway | NO5 | 10YNO-5--------2 | Bergen |
| Denmark | DK1 | 10YDK-1--------W | Western Denmark |
| Denmark | DK2 | 10YDK-2--------M | Eastern Denmark |
| Finland | FI | 10YFI-1--------U | All Finland |
| Germany | DE | 10YDE-RW-------I | Germany (one zone) |
| Netherlands | NL | 10YNL----------L | Netherlands |
| France | FR | 10YFR-RTE------C | France |
| Belgium | BE | 10YBE----------2 | Belgium |

**Special cases:**
- Some countries have multiple bidding zones (NO, DK, SE)
- Some countries have a single zone (FI, DE, NL)

---

## 6. ENTSO-E API Implementation Details

### 6.1 Endpoint Specification

**Day-Ahead Prices:**
```
GET https://web-api.tp.entsoe.eu/api?documentType=A44&processType=A16&in_Domain={in_domain}&out_Domain={out_domain}&periodStart={start}&periodEnd={end}
```

**Parameters:**
- `documentType=A44` - Aggregated data
- `processType=A16` - Day-ahead prices
- `in_Domain` - Origin domain (EIC code)
- `out_Domain` - Destination domain (EIC code, usually same as in_Domain)
- `periodStart` - Start timestamp (YYYYMMDD0000 format)
- `periodEnd` - End timestamp (YYYYMMDD2359 format)

### 6.2 Response Format (XML)

**Example response structure:**
```xml
<.glMarketDocument>
    <mRID codingScheme="A01">...</mRID>
    <revisionNumber>1</revisionNumber>
    <type>A44</type>
    <sender_MarketParticipant.mRID codingScheme="A01">...</sender_MarketParticipant.mRID>
    <receiver_MarketParticipant.mRID codingScheme="A01">...</receiver_MarketParticipant.mRID>
    <createdDateTime>2026-10-19T00:00:00Z</createdDateTime>
    <period.timeInterval>
        <start>2026-10-19T00:00:00Z</start>
        <end>2026-10-20T00:00:00Z</end>
    </period.timeInterval>
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
            <!-- More points... -->
        </Periode>
    </TimeSeries>
</glMarketDocument>
```

### 6.3 Data Normalization

**Convert ENTSO-E XML → Plugin format:**

```python
# Input (from ENTSO-E)
{
    "price_amount": 42.50,        # EUR/MWh
    "start": "2026-10-19T00:00:00Z",
    "end": "2026-10-19T01:00:00Z",
    "currency": "EUR",
    "unit": "MWh"
}

# Output (plugin format - ElectricityPriceEntry)
{
    "SEK_per_kWh": 0.425,        # Converted from EUR/MWh
    "EUR_per_kWh": 0.0425,       # EUR/MWh → EUR/kWh
    "EXR": 11.138733,           # Exchange rate (from separate call or cached)
    "time_start": "2026-10-19 00:00:00",
    "time_end": "2026-10-19 01:00:00"
}
```

**Note:** ENTSO-E returns prices in **EUR/MWh**, plugin expects **EUR/kWh** and **SEK/kWh**. Conversion:
- EUR/MWh → EUR/kWh: divide by 1000
- EUR/kWh → SEK/kWh: multiply by exchange rate (EXR)

### 6.4 Exchange Rate Handling

**Options:**
1. **Hardcode EXR** - Use a fixed average rate (e.g., 11.0 for SEK/EUR)
2. **Fetch from API** - Use a currency API (e.g., Open Exchange Rates, Fixer.io)
3. **User configuration** - Let user specify EXR in settings
4. **Omit SEK** - Only show EUR for non-Swedish countries

**Recommended:** Option 4 (simplest) + Option 1 for Sweden (maintain consistency)

---

## 7. Error Handling

### 7.1 Error Scenarios

| Scenario | Handling |
|----------|----------|
| Missing API key | Raise clear error with instructions |
| Invalid API key | Log error, show in UI |
| Network timeout | Retry 3 times with exponential backoff |
| Rate limited | Wait and retry, respect Retry-After header |
| Invalid country code | Return list of valid codes |
| No data for date | Return empty list, log warning |
| XML parsing error | Log full response, raise exception |

### 7.2 Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry_error_callback=lambda _: None
)
def _fetch_with_retry(self, url: str, params: dict) -> requests.Response:
    response = requests.get(url, params=params, headers=self._get_headers())
    response.raise_for_status()
    return response
```

---

## 8. Caching Strategy

### 8.1 Cache Layers

```
┌─────────────────────────────────────────────────┐
│                    Cache Layers                     │
├─────────────────────────────────────────────────┤
│  1. In-Memory Cache                                │
│     - Per-instance cache for current day          │
│     - TTL: 1 hour                                  │
│     - Cleared on plugin reload                    │
├─────────────────────────────────────────────────┤
│  2. File System Cache                             │
│     - Path: ~/.cache/inkypi/entsoe/{date}.json    │
│     - TTL: 24 hours                                │
│     - Persists between reloads                    │
├─────────────────────────────────────────────────┤
│  3. Display Cache                                 │
│     - Existing: Image caching in InkyPi            │
│     - No changes needed                           │
└─────────────────────────────────────────────────┘
```

### 8.2 Cache Key Structure

```python
cache_key = f"{country_code}_{date.isoformat()}_{process_type}"
# Example: "SE4_2026-10-19_A16"
```

---

## 9. UI/UX Changes

### 9.1 Settings Form (settings.html)

**Add new fields:**

```html
<!-- Data Source Selection -->
<div class="form-group">
  <label for="data_source" class="form-label">Data Source:</label>
  <select id="data_source" name="data_source" class="form-input">
    <option value="auto">Auto (Sweden: elprisetjustnu, Others: ENTSO-E)</option>
    <option value="swedish">Swedish API (elprisetjustnu.se)</option>
    <option value="entsoe">ENTSO-E API</option>
  </select>
  <small class="form-help">ENTSO-E requires an API key for most countries</small>
</div>

<!-- Country/Zone Selection -->
<div class="form-group">
  <label for="zone" class="form-label">Country/Zone:</label>
  <select id="zone" name="zone" class="form-input">
    <optgroup label="Sweden">
      <option value="SE1">SE1 - Northern Sweden</option>
      <option value="SE2">SE2 - Central Sweden</option>
      <option value="SE3">SE3 - Southern Sweden</option>
      <option value="SE4" selected>SE4 - Stockholm/Malmö</option>
    </optgroup>
    <optgroup label="Norway">
      <option value="NO1">NO1 - Oslo</option>
      <option value="NO2">NO2 - Kristiansand</option>
      <option value="NO3">NO3 - Trondheim</option>
      <option value="NO4">NO4 - Tromsø</option>
      <option value="NO5">NO5 - Bergen</option>
    </optgroup>
    <optgroup label="Denmark">
      <option value="DK1">DK1 - Western Denmark</option>
      <option value="DK2">DK2 - Eastern Denmark</option>
    </optgroup>
    <optgroup label="Other Europe">
      <option value="FI">Finland</option>
      <option value="DE">Germany</option>
      <option value="NL">Netherlands</option>
      <option value="FR">France</option>
      <option value="BE">Belgium</option>
    </optgroup>
  </select>
</div>

<!-- ENTSO-E API Key -->
<div class="form-group" id="api_key_group" style="display: none;">
  <label for="entsoe_api_key" class="form-label">ENTSO-E API Key:</label>
  <input type="password" id="entsoe_api_key" name="entsoe_api_key" 
         class="form-input" placeholder="Optional: Get from transparency.entsoe.eu">
  <small class="form-help">
    <a href="https://transparency.entsoe.eu/" target="_blank">Get API Key</a>
  </small>
</div>

<script>
document.addEventListener("DOMContentLoaded", () => {
  const dataSourceSelect = document.getElementById("data_source");
  const apiKeyGroup = document.getElementById("api_key_group");
  
  // Show/hide API key field based on data source
  dataSourceSelect.addEventListener("change", () => {
    const showApiKey = dataSourceSelect.value !== "swedish";
    apiKeyGroup.style.display = showApiKey ? "block" : "none";
  });
  
  // Initialize based on current value
  if (loadPluginSettings) {
    dataSourceSelect.value = pluginSettings.data_source || "auto";
    document.getElementById("zone").value = pluginSettings.zone || "SE4";
    document.getElementById("entsoe_api_key").value = pluginSettings.entsoe_api_key || "";
    dataSourceSelect.dispatchEvent(new Event("change"));
  }
});
</script>
```

### 9.2 Help Text

Add to plugin-info.json or documentation:

```json
{
  "description": "Display electricity prices for your region. Supports Sweden via elprisetjustnu.se (no API key) and 25+ European countries via ENTSO-E API (requires free API key).",
  "settings_help": {
    "data_source": "Choose which API to use. 'Auto' uses Swedish API for SE zones and ENTSO-E for others.",
    "zone": "Select your country/region. Swedish zones (SE1-SE4) use local API, others use ENTSO-E.",
    "entsoe_api_key": "Required for ENTSO-E API. Get your free key at https://transparency.entsoe.eu/"
  }
}
```

---

## 10. Testing Strategy

### 10.1 Test Coverage

| Test Case | Description | Priority |
|-----------|-------------|----------|
| Swedish zones with Swedish API | SE1-SE4 using elprisetjustnu.se | High |
| Swedish zones with ENTSO-E API | SE1-SE4 using ENTSO-E (fallback) | Medium |
| Norwegian zones | NO1-NO5 using ENTSO-E | High |
| Danish zones | DK1, DK2 using ENTSO-E | High |
| Finnish zone | FI using ENTSO-E | High |
| Other countries | DE, NL, FR, etc. | Medium |
| Invalid country code | Error handling | High |
| Missing API key | Error handling | High |
| Invalid API key | Error handling | Medium |
| Network errors | Retry logic | High |
| XML parsing | Various XML formats | Medium |
| Data normalization | EUR/MWh → EUR/kWh → SEK/kWh | High |
| Caching | Verify cache hits/misses | Medium |
| Date handling | Different date formats | Medium |

### 10.2 Test Data

**Mock responses:**
- Create fixture XML files for different countries
- Mock network failures
- Mock rate limiting responses

**Example test fixture:**
```xml
<!-- tests/fixtures/entsoe_se4_2026-10-19.xml -->
<glMarketDocument>
    <TimeSeries>
        <price_Amount unit="MWH">42.50</price_Amount>
        <currency_Unit.name>EUR</currency_Unit.name>
        <Periode>
            <timeInterval>
                <start>2026-10-19T00:00:00Z</start>
                <end>2026-10-19T01:00:00Z</end>
            </timeInterval>
            <!-- 24 points -->
        </Periode>
    </TimeSeries>
</glMarketDocument>
```

---

## 11. Implementation Phases

### Phase 1: Core ENTSO-E Integration (High Priority)
- [ ] Implement `ENTSOEEClient` class
- [ ] XML parsing and data normalization
- [ ] Basic error handling
- [ ] Unit tests with mock data
- [ ] Settings UI updates

**Estimated effort:** 4-6 hours

### Phase 2: Enhanced Features (Medium Priority)
- [ ] Caching implementation
- [ ] Retry logic with exponential backoff
- [ ] Exchange rate support (for SEK conversion)
- [ ] All 25+ countries support
- [ ] Integration tests

**Estimated effort:** 4-8 hours

### Phase 3: Polish & Documentation (Low Priority)
- [ ] Performance optimization
- [ ] Better error messages
- [ ] Documentation updates
- [ ] Example configurations

**Estimated effort:** 2-4 hours

---

## 12. File Changes Summary

### New Files:
```
src/plugins/electricity_price/entsoe_client.py     # ENTSO-E API client
src/plugins/electricity_price/country_codes.py    # Country/zone mappings
tests/test_entsoe_client.py                         # Unit tests
```

### Modified Files:
```
src/plugins/electricity_price/electricity_price.py  # Add client factory
src/plugins/electricity_price/settings.html         # Add new settings fields
src/plugins/electricity_price/plugin-info.json     # Update description
```

### Configuration:
```
src/config/device_dev.json                         # Optional: API key
.env                                             # Optional: ENTSOE_API_KEY
```

---

## 13. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| ENTSO-E API changes | Low | High | Use stable endpoints, monitor changelog |
| Rate limiting | Medium | Medium | Implement retry with backoff, caching |
| XML format changes | Low | Medium | Flexible parser, validate schema |
| API key exposure | Medium | High | Use environment variables, never commit keys |
| Performance issues | Medium | Low | Caching, async requests |
| Country code changes | Low | Medium | Maintain mapping table, validate on startup |

---

## 14. Open Questions

1. **Exchange Rate Source:** Should we hardcode rates, fetch from API, or omit SEK for non-Swedish countries?
2. **Caching Strategy:** In-memory only, or persist to disk?
3. **Fallback Behavior:** If ENTSO-E fails, should we try Swedish API as fallback for SE zones?
4. **Historical Data:** Should we support fetching prices for past dates?
5. **Time Zone Handling:** Should prices be displayed in local time or UTC?

---

## 15. Next Steps

1. **Review this spec** - Provide feedback on approach
2. **Prioritize features** - Which phase 2 items are critical?
3. **Resolve open questions** - Decide on the 5 questions above
4. **Implementation** - Start with Phase 1

---

## Appendix A: ENTSO-E EIC Codes Reference

| Country | Zone | EIC Code | Notes |
|---------|------|----------|-------|
| Austria | AT | 10YAT-APG------W | |
| Belgium | BE | 10YBE----------2 | |
| Bosnia | BA | 10YBA-JPCC------S | |
| Bulgaria | BG | 10YCA-TSO-------W | |
| Croatia | HR | 10YHR-HEP------M | |
| Cyprus | CY | 10YCY-TSO------M | |
| Czech | CZ | 10YCZ-CEPS-----N | |
| Denmark | DK1 | 10YDK-1--------W | Western |
| Denmark | DK2 | 10YDK-2--------M | Eastern |
| Estonia | EE | 10Y1001A1001A48S | |
| Finland | FI | 10YFI-1--------U | |
| France | FR | 10YFR-RTE------C | |
| Germany | DE | 10YDE-RW-------I | |
| Greece | GR | 10YGR-HTSO------Y | |
| Hungary | HU | 10YHU-MAVIR----N | |
| Ireland | IE | 10YIE-1001A08H--U | |
| Italy | IT | 10YIT-GRTN-----B | |
| Latvia | LV | 10YLV-1001A00074J | |
| Lithuania | LT | 10YLT-1001A0008QT | |
| Luxembourg | LU | 10YLU-CEGEDEL--Z | |
| Malta | MT | 10Y1001A1001A371 | |
| Moldova | MD | 10Y1001C--00003F | |
| Montenegro | ME | 10YCS-CG-TSO---S | |
| Netherlands | NL | 10YNL----------L | |
| North Macedonia | MK | 10YMK-MEPSO----8 | |
| Norway | NO1 | 10YNO-1--------2 | Oslo |
| Norway | NO2 | 10YNO-2--------2 | Kristiansand |
| Norway | NO3 | 10YNO-3--------2 | Trondheim |
| Norway | NO4 | 10YNO-4--------2 | Tromsø |
| Norway | NO5 | 10YNO-5--------2 | Bergen |
| Poland | PL | 10YPL-AREA-----S | |
| Portugal | PT | 10YPT-REN------W | |
| Romania | RO | 10YRO-TEL------P | |
| Serbia | RS | 10YCS-SERBIATSO-V | |
| Slovakia | SK | 10YSK-SEPS-----K | |
| Slovenia | SI | 10YSI-ELES-----O | |
| Spain | ES | 10YES-REE------0 | |
| Sweden | SE1 | 10YSE-1--------2 | Northern |
| Sweden | SE2 | 10YSE-2--------2 | Central |
| Sweden | SE3 | 10YSE-3--------2 | Southern |
| Sweden | SE4 | 10YSE-4--------2 | Stockholm |
| Switzerland | CH | 10YCH-SWISSGRIDZ | |
| Ukraine | UA | 10Y1001C--00000K | |

---

## Appendix B: Useful Links

- **ENTSO-E Transparency Platform:** https://transparency.entsoe.eu/
- **API Documentation:** https://transparency.entsoe.eu/transparency-platform/access-to-data/api-urls-and-guidelines
- **EIC Codes:** https://www.entsoe.eu/data-portal/energy-identification-codes-eic
- **Postman Collection:** https://documenter.getpostman.com/view/7009892/2s93JtP3F6
- **Python XML Parsing:** https://docs.python.org/3/library/xml.etree.elementtree.html
- **Requests Library:** https://docs.python-requests.org/
