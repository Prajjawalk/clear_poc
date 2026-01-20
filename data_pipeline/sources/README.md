# Data Pipeline Sources

This directory contains the implementation of data sources for the NRC Early Warning and Alert System (EWAS) data pipeline. Each data source is implemented as a Python class that inherits from the base `Source` class and provides methods for data retrieval and processing.

## Architecture Overview

### Base Source Class

All data sources inherit from `base_source.Source` which provides:

- **Logging**: Structured logging with source context
- **File Management**: Raw data file path management and storage
- **Location Matching**: Gazetteer-based location validation and matching
- **Abstract Methods**: `get()` and `process()` methods that must be implemented

### Data Flow

1. **Retrieval (`get` method)**: Fetch raw data from external API/source
2. **Storage**: Save raw data to `raw_data/{source_name}/` directory
3. **Processing (`process` method)**: Parse and standardize raw data
4. **Database Storage**: Create `VariableData` records in the database

## Available Data Sources

### IDMC (Internal Displacement Monitoring Centre)

**Location**: `data_pipeline/sources/idmc.py`
**API Documentation**: [IDMC External API](https://helix-tools-api.idmcdb.org/external-api/)
**Status**: ✅ Active

IDMC provides authoritative data on internal displacement worldwide. The implementation covers two key datasets:

#### GIDD (Global Internal Displacement Database)

**Endpoint**: `https://helix-tools-api.idmcdb.org/external-api/gidd/disaggregations/disaggregation-geojson/`
**Data Format**: GeoJSON FeatureCollection
**Update Frequency**: Quarterly
**Geographic Scope**: Sudan (SDN) and Abiey Area (AB9)

##### Parameters
```python
{
    "client_id": "API_KEY",
    "iso3__in": "SDN,AB9",
    "start_date": "YYYY-MM-DD",  # optional
    "end_date": "YYYY-MM-DD",    # optional
    "year": "YYYY"               # optional
}
```

##### Variables Extracted

| Variable Code | Description | Figure Cause Filter | Unit |
|---------------|-------------|-------------------|------|
| `idmc_gidd_conflict_displacement` | Conflict-induced displacement | "conflict" in Figure cause | People |
| `idmc_gidd_disaster_displacement` | Disaster-induced displacement | "disaster" in Figure cause | People |
| `idmc_gidd_total_displacement` | Total new displacement | All causes | People |

##### Data Processing Steps

1. **Date Extraction**
   ```python
   event_start_date = properties.get("Event start date")  # Format: YYYY-MM-DD
   event_end_date = properties.get("Event end date")      # Format: YYYY-MM-DD
   start_date = datetime.strptime(event_start_date[:10], "%Y-%m-%d").date()
   end_date = datetime.strptime(event_end_date[:10], "%Y-%m-%d").date() if event_end_date else start_date
   ```

2. **Location Matching**
   ```python
   locations_name_list = properties.get("Locations name", [])  # ["Al Jazirah, Sudan"]
   location_string = locations_name_list[0]
   location_parts = [part.strip() for part in location_string.split(',')]
   location_name = location_parts[0]  # Primary location name

   # Match against gazetteer with source "IDMC GIDD"
   location = self.validate_location_match(location_name, "IDMC GIDD")
   ```

3. **Value Filtering and Extraction**
   ```python
   figure_cause = properties.get("Figure cause")          # "Conflict" or "Disaster"
   total_figures = properties.get("Total figures")        # Numeric displacement count
   figure_category = properties.get("Figure category")    # "New displacement" or "IDPs"
   violence_type = properties.get("Violence type")        # e.g., "Non-International armed conflict"
   hazard_type = properties.get("Hazard Type")           # e.g., "Flood", "Drought"
   year = properties.get("Year")                          # Numeric year
   ```

4. **Variable-Specific Processing**
   - **Conflict Displacement**: Only processes records where `"conflict" in figure_cause.lower()`
   - **Disaster Displacement**: Only processes records where `"disaster" in figure_cause.lower()`
   - **Total Displacement**: Processes all records regardless of cause

5. **Period Assignment**
   ```python
   period = "year" if figure_category == "IDPs" else "event"
   ```

6. **Text Description Generation**
   ```python
   text = f"{figure_category} - {figure_cause} ({violence_type or hazard_type}) in {location_name} ({year})"
   # Example: "New displacement - Conflict (Non-International armed conflict) in Al Jazirah (2023)"
   ```

#### IDU (Internal Displacement Updates)

**Endpoint**: `https://helix-tools-api.idmcdb.org/external-api/idus/last-180-days/`
**Data Format**: JSON array (direct list response)
**Update Frequency**: Real-time (last 180 days)
**Geographic Scope**: Global (filtered for Sudan during processing)

##### Parameters
```python
{
    "client_id": "API_KEY"
    # Note: Country filtering does not work at API level
    # Sudan filtering is performed during processing
}
```

##### Variables Extracted

| Variable Code | Description | Displacement Type Filter | Unit |
|---------------|-------------|------------------------|------|
| `idmc_idu_new_displacements` | All new displacements | All types | People |
| `idmc_idu_conflict_displacements` | Conflict displacements | "Conflict" displacement_type | People |
| `idmc_idu_disaster_displacements` | Disaster displacements | "Disaster" displacement_type | People |

##### Data Processing Steps

1. **Sudan Filtering**
   ```python
   # Filter for Sudan records only (API doesn't support country filtering)
   if record.get("iso3") != "SDN":
       return False
   ```

2. **Date Range Processing**
   ```python
   displacement_date = record.get("displacement_date")
   displacement_start_date = record.get("displacement_start_date")
   displacement_end_date = record.get("displacement_end_date")

   # Handle multi-day vs single-day events
   if displacement_start_date and displacement_end_date:
       start_date = datetime.strptime(displacement_start_date[:10], "%Y-%m-%d").date()
       end_date = datetime.strptime(displacement_end_date[:10], "%Y-%m-%d").date()
       period = "period" if start_date != end_date else "event"
   else:
       # Fall back to displacement_date for single-day events
       date_obj = datetime.strptime(displacement_date[:10], "%Y-%m-%d").date()
       start_date = end_date = date_obj
       period = "event"
   ```

3. **Location Parsing from locations_name**
   ```python
   # Extract location from locations_name field
   # Format: "Al Fasher, North Darfur State, Sudan" or "Al Jazirah, Sudan"
   locations_name = record.get("locations_name", "")
   location_parts = [part.strip() for part in locations_name.split(',')]
   location_name = location_parts[0] if location_parts else locations_name

   # Match against gazetteer with source "IDMC IDU"
   location = self.validate_location_match(location_name, "IDMC IDU")
   ```

4. **Value and Type Processing**
   ```python
   figure = record.get("figure", 0)
   displacement_type = record.get("displacement_type", "")  # "Conflict" or "Disaster"
   event_name = record.get("event_name", "")  # Rich event description
   qualifier = record.get("qualifier", "")  # "approximately", "total", etc.
   ```

5. **Variable-Specific Processing**
   - **New Displacements**: Processes all Sudan records regardless of type
   - **Conflict Displacements**: Only processes records where `displacement_type == "Conflict"`
   - **Disaster Displacements**: Only processes records where `displacement_type == "Disaster"`

6. **Enhanced Text Description Generation**
   ```python
   # Use event_name if available for rich descriptions
   if event_name:
       text = f"{displacement_type} displacement: {event_name}"
       if qualifier:
           text += f" ({qualifier} {figure:,.0f} people displaced)"
   else:
       text = f"{displacement_type} displacement in {location_name} ({figure:,.0f} people)"

   # Examples:
   # "Conflict displacement: Sudan: Conflict - Al Jazirah - 10/12/2023 (approximately 25,000 people displaced)"
   # "Disaster displacement: Sudan: Flood - Central Darfur (total 500 people displaced)"
   ```

### Location Matching System

All IDMC variables use the gazetteer-based location matching system with source-specific entries:

#### Gazetteer Sources
- **IDMC GIDD**: Used by all GIDD variables
- **IDMC IDU**: Used by all IDU variables

#### Location Matching Process
1. **Exact Match**: Case-insensitive exact name matching
2. **Partial Match**: `icontains` fuzzy matching if exact fails
3. **Fallback Strategy**:
   - Try alternative location name parts (for comma-separated locations)
   - Fall back to "Sudan" country-level if all else fails

#### Sample Gazetteer Entries
```python
# IDMC GIDD gazetteer entries
{"name": "Al Jazirah", "source": "IDMC GIDD", "code": "Al_Jazirah", "location": SD_001}
{"name": "Gezira State", "source": "IDMC GIDD", "code": "Gezira", "location": SD_001}
{"name": "Central Darfur", "source": "IDMC GIDD", "code": "Central_Darfur", "location": SD_004}
{"name": "Sudan", "source": "IDMC GIDD", "code": "SDN", "location": SD}

# IDMC IDU gazetteer entries (duplicate set with different source)
{"name": "Al Jazirah", "source": "IDMC IDU", "code": "Al_Jazirah_idu", "location": SD_001}
{"name": "Sudan", "source": "IDMC IDU", "code": "SDN_idu", "location": SD}
```

## Configuration and Setup

### Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `IDMC_API_KEY` | IDMC API authentication key | Yes | `ABCDEF123456` |

### Raw Data Storage

All raw data is stored in timestamped files:
```
raw_data/
├── IDMC - Internal Displacement Monitoring Centre/
│   ├── IDMC - Internal Displacement Monitoring Centre_idmc_gidd_total_displacement_20250722_185732.json
│   ├── IDMC - Internal Displacement Monitoring Centre_idmc_gidd_conflict_displacement_20250722_190117.json
│   └── IDMC - Internal Displacement Monitoring Centre_idmc_idu_new_displacements_20250722_191203.json
```

### Gazetteer Setup

Run the management command to create necessary gazetteer entries:

```bash
# Setup IDMC gazetteer entries
export UV_ENV_FILE=.env
uv run manage.py setup_idmc_gazetteer

# Setup IDMC source and variables
uv run manage.py setup_idmc_source
```

## Data Pipeline Usage

### Manual Execution

```bash
# Retrieve data for all IDMC variables
export UV_ENV_FILE=.env
uv run manage.py run_pipeline --source "IDMC - Internal Displacement Monitoring Centre" --task-type retrieve

# Process retrieved data
uv run manage.py run_pipeline --source "IDMC - Internal Displacement Monitoring Centre" --task-type process

# Full pipeline (retrieve + process)
uv run manage.py run_pipeline --source "IDMC - Internal Displacement Monitoring Centre" --task-type full
```

### Variable-Specific Execution

```bash
# Process specific variable
uv run manage.py run_pipeline --source "IDMC - Internal Displacement Monitoring Centre" --variable idmc_gidd_total_displacement --task-type full
```

## Error Handling and Monitoring

### Common Error Scenarios

1. **API Key Issues**
   ```
   ERROR IDMC_API_KEY environment variable not set
   ```
   **Solution**: Set the `IDMC_API_KEY` environment variable

2. **Location Matching Failures**
   ```
   WARNING No location match found for: Unknown Location Name
   INFO Skipping GIDD record due to location mismatch
   ```
   **Solution**: Add gazetteer entries for new location names

3. **API Rate Limiting**
   ```
   ERROR Failed to retrieve IDMC data | Response status: 429
   ```
   **Solution**: Implement retry logic with exponential backoff

4. **Data Format Changes**
   ```
   ERROR Failed to process IDMC data | KeyError: 'Total figures'
   ```
   **Solution**: Update field mappings in processing methods

### Monitoring Metrics

The source generates structured logs for monitoring:

```python
# Retrieval metrics
self.log_info("Successfully retrieved IDMC GIDD data",
              variable=variable.code,
              records=record_count,
              file_path=raw_data_path)

# Processing metrics
self.log_info("Successfully processed IDMC data",
              variable=variable.code,
              total_records=len(records),
              processed_count=processed_count)
```

## Testing

Comprehensive tests are available in `data_pipeline/tests_sources_idmc.py`:

```bash
# Run all IDMC tests
export UV_ENV_FILE=.env
uv run manage.py test data_pipeline.tests_sources_idmc

# Run specific test categories
uv run manage.py test data_pipeline.tests_sources_idmc.IDMCDataRetrievalTest
uv run manage.py test data_pipeline.tests_sources_idmc.IDMCDataProcessingTest
uv run manage.py test data_pipeline.tests_sources_idmc.IDMCLocationMatchingTest

# Run IDU-specific tests
uv run manage.py test data_pipeline.tests_sources_idmc.IDMCIDUSpecificTest
uv run manage.py test data_pipeline.tests_sources_idmc.IDMCIDUGlobalDataTest
```

### Test Coverage

- ✅ **Data Retrieval**: API calls, authentication, error handling
- ✅ **Data Processing**: GIDD and IDU record processing, filtering
- ✅ **Location Matching**: Gazetteer lookups, fallback strategies
- ✅ **Variable Filtering**: Conflict vs. disaster type filtering
- ✅ **IDU Functionality**: Sudan filtering, date range processing, direct list API response handling
- ✅ **Error Scenarios**: Missing API keys, invalid data, location mismatches

## Development Guidelines

### Adding New Data Sources

1. **Create Source Class**
   ```python
   # data_pipeline/sources/new_source.py
   from ..base_source import Source

   class NewSource(Source):
       def get(self, variable: Variable, **kwargs) -> bool:
           # Implement data retrieval
           pass

       def process(self, variable: Variable, **kwargs) -> bool:
           # Implement data processing
           pass
   ```

2. **Create Management Commands**
   - `setup_newsource_source.py` - Create Source and Variable records
   - `setup_newsource_gazetteer.py` - Create gazetteer entries (if needed)

3. **Add Tests**
   ```python
   # data_pipeline/tests_sources_newsource.py
   class NewSourceTestCase(TestCase):
       # Implement comprehensive tests
       pass
   ```

4. **Update Documentation**
   - Add source details to this README
   - Document API endpoints, parameters, and processing logic
   - Include setup and configuration instructions

### Code Quality Standards

- **Type Hints**: Use type annotations for all methods
- **Error Handling**: Graceful error handling with structured logging
- **Documentation**: Comprehensive docstrings and inline comments
- **Testing**: >90% test coverage including edge cases
- **Validation**: Input validation and data quality checks

## Future Enhancements

### IDMC Roadmap

- **Additional Variables**: Population at risk, return movements
- **Enhanced Filtering**: Date range filtering, cause-specific queries
- **Real-time Updates**: Webhook integration for live data updates
- **Data Quality**: Automated validation and anomaly detection
- **Performance**: Caching and incremental updates

### General Improvements

- **Rate Limiting**: Intelligent request throttling
- **Retry Logic**: Exponential backoff for API failures
- **Monitoring**: Dashboard for data pipeline health
- **Alerting**: Automated alerts for data pipeline failures
- **Documentation**: Auto-generated API documentation

## Support and Troubleshooting

### Common Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| API Authentication | `401 Unauthorized` responses | Verify `IDMC_API_KEY` is correct |
| Location Mismatch | High skip rates in processing | Update gazetteer entries |
| Data Format Change | Processing errors | Update field mappings |
| Network Connectivity | `ConnectionError` or timeouts | Check network/firewall settings |

### Getting Help

1. **Logs**: Check `logs/django_app.log` for detailed error information
2. **Tests**: Run relevant test suite to identify specific issues
3. **Documentation**: Review API documentation for data source
4. **Contact**: Reach out to development team for support

---

*This documentation is maintained by the NRC EWAS development team. Last updated: January 2025*
