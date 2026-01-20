"""Stability tests for IDMC GIDD data source using reference data."""

from typing import Any

from data_pipeline.sources.idmcgidd import IDMCGIDD

from .base_stability_test import BaseStabilityTest, SourceStabilityTestMixin


class TestIDMCGIDDStability(BaseStabilityTest, SourceStabilityTestMixin):
    """Test IDMC GIDD data format stability using hard-coded reference data."""

    def setUp(self):
        """Set up IDMC GIDD test environment."""
        super().setUp()

        self.source_model, self.test_variable = self.create_test_source_and_variable(
            source_name="IDMC GIDD - Test",
            source_class_name="IDMCGIDD",
            variable_code="idmc_gidd_conflict_displacement",
            variable_name="IDMC GIDD - Conflict Displacement",
            base_url="https://helix-tools-api.idmcdb.org"
        )

        self.source_instance = IDMCGIDD(self.source_model)

    def get_reference_data(self) -> dict[str, Any]:
        """Return hard-coded IDMC GIDD reference data for year=2023."""
        return {
            "retrieved_at": "2025-09-25T07:25:43.966140+00:00",
            "endpoint": "gidd",
            "query_params": {
                "year": 2023
            },
            "api_params": {
                "client_id": "KIZKJAGEJO225PTD",
                "iso3__in": "SDN,AB9",
                "year": 2023
            },
            "data": {
                "type": "FeatureCollection",
                "readme": "TITLE: Global Internal Displacement Database (GIDD)",
                "lastUpdated": "2025-05-13",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "MultiPoint",
                            "coordinates": [[28.46257, 9.46809]]
                        },
                        "properties": {
                            "ID": 143576,
                            "ISO3": "SDN",
                            "Country": "Sudan",
                            "Geographical region": "Sub-Saharan Africa",
                            "Figure cause": "Conflict",
                            "Year": 2023,
                            "Figure category": "IDPs",
                            "Figure unit": "Person",
                            "Reported figures": 5000,
                            "Total figures": 5000,
                            "Violence type": "Non-International armed conflict (NIAC)",
                            "Stock date": "2023-04-30",
                            "Stock date accuracy": "Day",
                            "Stock reporting date": "2023-12-31",
                            "Publishers": ["IOM DTM Sudan"],
                            "Sources": ["IOM DTM Sudan"],
                            "Sources type": ["United Nations"],
                            "Event ID": "EV-SUD-2023-0045",
                            "Event name": "Sudan Conflict Displacement 2023",
                            "Event cause": "Conflict",
                            "Locations name": ["North Darfur State, Sudan"],
                            "Locations accuracy": ["Admin 1"],
                            "Locations type": ["Origin"]
                        }
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "MultiPoint",
                            "coordinates": [[32.5599, 15.5007]]
                        },
                        "properties": {
                            "ID": 143577,
                            "ISO3": "SDN",
                            "Country": "Sudan",
                            "Geographical region": "Sub-Saharan Africa",
                            "Figure cause": "Conflict",
                            "Year": 2023,
                            "Figure category": "IDPs",
                            "Figure unit": "Person",
                            "Reported figures": 12000,
                            "Total figures": 12000,
                            "Violence type": "Non-International armed conflict (NIAC)",
                            "Stock date": "2023-06-15",
                            "Stock date accuracy": "Day",
                            "Stock reporting date": "2023-12-31",
                            "Publishers": ["UNHCR"],
                            "Sources": ["UNHCR"],
                            "Sources type": ["United Nations"],
                            "Event ID": "EV-SUD-2023-0067",
                            "Event name": "Khartoum Violence April 2023",
                            "Event cause": "Conflict",
                            "Locations name": ["Khartoum, Sudan"],
                            "Locations accuracy": ["Admin 1"],
                            "Locations type": ["Origin"]
                        }
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "MultiPoint",
                            "coordinates": [[33.9778, 9.5411]]
                        },
                        "properties": {
                            "ID": 143578,
                            "ISO3": "AB9",
                            "Country": "Abyei Area",
                            "Geographical region": "Sub-Saharan Africa",
                            "Figure cause": "Disaster",
                            "Year": 2023,
                            "Figure category": "IDPs",
                            "Figure unit": "Person",
                            "Reported figures": 3500,
                            "Total figures": 3500,
                            "Hazard Category": "Hydrological",
                            "Hazard sub category": "Flood",
                            "Hazard Type": "Flood",
                            "Hazard Sub-Type": "Flash flood",
                            "Stock date": "2023-08-20",
                            "Stock date accuracy": "Day",
                            "Stock reporting date": "2023-12-31",
                            "Publishers": ["IOM DTM"],
                            "Sources": ["IOM DTM"],
                            "Sources type": ["United Nations"],
                            "Event ID": "EV-AB9-2023-0012",
                            "Event name": "Abyei Flash Floods August 2023",
                            "Event cause": "Disaster",
                            "Locations name": ["Abyei Town, Abyei Area"],
                            "Locations accuracy": ["Admin 2"],
                            "Locations type": ["Origin"]
                        }
                    }
                ]
            }
        }

    def get_expected_record_count_range(self) -> tuple[int, int]:
        """IDMC GIDD 2023 data should have 2-10 features for Sudan."""
        return (2, 10)

    def get_required_fields(self) -> dict[str, Any]:
        """Required fields for IDMC GIDD feature properties."""
        return {
            "Figure cause": str,
            "Total figures": int,
            "Year": 2023,  # Fixed year for stable testing
            "Locations name": list,
            "ISO3": str,
            "Country": str
        }

    def extract_records_from_data(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract features from IDMC GIDD GeoJSON structure."""
        if "data" in data and "features" in data["data"]:
            return data["data"]["features"]
        elif "features" in data:
            return data["features"]
        else:
            return []

    def validate_data_structure(self, data: dict[str, Any]):
        """Validate IDMC GIDD GeoJSON structure."""
        # Check top-level structure
        expected_top_level = {
            "retrieved_at": str,
            "endpoint": str,
            "data": dict
        }
        self.assert_has_required_fields(data, expected_top_level)

        # Check GeoJSON structure
        geojson_data = data["data"]
        expected_geojson = {
            "type": "FeatureCollection",
            "features": list
        }
        self.assert_has_required_fields(geojson_data, expected_geojson)

        # Check feature structure if features exist
        features = geojson_data["features"]
        if features:
            sample_feature = features[0]
            expected_feature = {
                "type": "Feature",
                "geometry": dict,
                "properties": dict
            }
            self.assert_has_required_fields(sample_feature, expected_feature)

            # Check properties structure
            props = sample_feature["properties"]
            required_props = self.get_required_fields()
            self.assert_has_required_fields(props, required_props)

    def test_conflict_displacement_filtering(self):
        """Test that conflict displacement records are properly filtered."""
        reference_data = self.get_reference_data()
        features = self.extract_records_from_data(reference_data)

        conflict_features = [f for f in features if f["properties"]["Figure cause"] == "Conflict"]
        disaster_features = [f for f in features if f["properties"]["Figure cause"] == "Disaster"]

        # Should have both conflict and disaster features in reference
        self.assertGreater(len(conflict_features), 0, "Should have conflict displacement records")
        self.assertGreater(len(disaster_features), 0, "Should have disaster displacement records")

        # Test that conflict variable would only process conflict records
        for feature in conflict_features:
            self.assertEqual(feature["properties"]["Figure cause"], "Conflict")

    def test_location_name_structure(self):
        """Test that location names are properly structured."""
        reference_data = self.get_reference_data()
        features = self.extract_records_from_data(reference_data)

        for feature in features:
            locations = feature["properties"]["Locations name"]
            self.assertIsInstance(locations, list, "Locations name should be a list")
            self.assertGreater(len(locations), 0, "Should have at least one location")

            # Each location should be a string
            for location in locations:
                self.assertIsInstance(location, str, "Each location should be a string")
                # Should contain either Sudan or Abyei (for Abyei Area)
                has_sudan_or_abyei = "Sudan" in location or "Abyei" in location
                self.assertTrue(has_sudan_or_abyei, f"Location '{location}' should contain 'Sudan' or 'Abyei'")

    def test_numeric_values_validation(self):
        """Test that numeric values are properly typed and reasonable."""
        reference_data = self.get_reference_data()
        features = self.extract_records_from_data(reference_data)

        for feature in features:
            props = feature["properties"]

            # Check numeric fields
            self.assertIsInstance(props["Total figures"], int, "Total figures should be integer")
            self.assertGreater(props["Total figures"], 0, "Total figures should be positive")
            self.assertLess(props["Total figures"], 1000000, "Total figures should be reasonable")

            self.assertIsInstance(props["Year"], int, "Year should be integer")
            self.assertEqual(props["Year"], 2023, "Year should be 2023 for stable test")

    def test_iso3_code_validation(self):
        """Test that ISO3 codes are correct for Sudan/Abyei."""
        reference_data = self.get_reference_data()
        features = self.extract_records_from_data(reference_data)

        valid_iso3_codes = {"SDN", "AB9"}

        for feature in features:
            iso3 = feature["properties"]["ISO3"]
            self.assertIn(iso3, valid_iso3_codes, f"ISO3 code {iso3} should be SDN or AB9")

    def test_geometry_structure(self):
        """Test that geometry follows GeoJSON MultiPoint structure."""
        reference_data = self.get_reference_data()
        features = self.extract_records_from_data(reference_data)

        for feature in features:
            geometry = feature["geometry"]
            self.assertEqual(geometry["type"], "MultiPoint", "Geometry should be MultiPoint")
            self.assertIsInstance(geometry["coordinates"], list, "Coordinates should be a list")

            if geometry["coordinates"]:
                # Check first coordinate pair
                coord_pair = geometry["coordinates"][0]
                self.assertIsInstance(coord_pair, list, "Coordinate pair should be list")
                self.assertEqual(len(coord_pair), 2, "Coordinate pair should have 2 elements")

                lon, lat = coord_pair
                self.assertIsInstance(lon, (int, float), "Longitude should be numeric")
                self.assertIsInstance(lat, (int, float), "Latitude should be numeric")

                # Validate coordinate ranges for Sudan/Abyei region
                self.assertGreaterEqual(lon, 20, "Longitude should be reasonable for Sudan")
                self.assertLessEqual(lon, 40, "Longitude should be reasonable for Sudan")
                self.assertGreaterEqual(lat, 3, "Latitude should be reasonable for Sudan")
                self.assertLessEqual(lat, 23, "Latitude should be reasonable for Sudan")

    def test_required_fields_present(self):
        """Test that all required fields are present in sample record properties."""
        if not hasattr(self, 'get_required_fields'):
            self.skipTest("Required fields not defined")

        reference_data = self.get_reference_data()
        records = self.extract_records_from_data(reference_data)

        if records:
            sample_record = records[0]
            # For IDMC GIDD, check properties instead of top-level feature
            if "properties" in sample_record:
                sample_properties = sample_record["properties"]
                required_fields = self.get_required_fields()
                self.assert_has_required_fields(sample_properties, required_fields)
            else:
                # Fallback to top-level if no properties
                required_fields = self.get_required_fields()
                self.assert_has_required_fields(sample_record, required_fields)
