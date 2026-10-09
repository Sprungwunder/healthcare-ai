"""Unit tests for MeasurementValidator and temperature validation."""

import math

import pytest

from healthcare_ai.validation import (
    ABSOLUTE_ZERO_CELSIUS,
    ABSOLUTE_ZERO_FAHRENHEIT,
    InvalidMeasurementValueError,
    MeasurementOutOfRangeError,
    MeasurementValidationError,
    MeasurementValidator,
    TemperatureMeasurement,
    TemperatureUnit,
    UnknownUnitError,
    celsius_to_fahrenheit,
    convert_temperature,
    fahrenheit_to_celsius,
)


class TestTemperatureConversions:
    """Tests for unit conversion utilities."""

    @pytest.mark.parametrize(
        ("celsius", "expected_fahrenheit"),
        [
            (0.0, 32.0),
            (100.0, 212.0),
            (37.0, 98.6),
            (-40.0, -40.0),
            (25.0, 77.0),
            (45.0, 113.0),
        ],
    )
    def test_celsius_to_fahrenheit(
        self, celsius: float, expected_fahrenheit: float
    ) -> None:
        assert math.isclose(
            celsius_to_fahrenheit(celsius), expected_fahrenheit, rel_tol=1e-5
        )

    @pytest.mark.parametrize(
        ("fahrenheit", "expected_celsius"),
        [
            (32.0, 0.0),
            (212.0, 100.0),
            (98.6, 37.0),
            (-40.0, -40.0),
            (77.0, 25.0),
            (113.0, 45.0),
        ],
    )
    def test_fahrenheit_to_celsius(
        self, fahrenheit: float, expected_celsius: float
    ) -> None:
        assert math.isclose(
            fahrenheit_to_celsius(fahrenheit), expected_celsius, rel_tol=1e-5
        )

    def test_convert_temperature_same_unit(self) -> None:
        assert convert_temperature(37.0, "C", "celsius") == 37.0
        assert convert_temperature(98.6, "F", "fahrenheit") == 98.6

    def test_convert_temperature_cross_unit(self) -> None:
        assert math.isclose(convert_temperature(37.0, "°C", "°F"), 98.6, rel_tol=1e-5)
        assert math.isclose(convert_temperature(98.6, "°F", "°C"), 37.0, rel_tol=1e-5)

    def test_convert_temperature_invalid_value(self) -> None:
        with pytest.raises(InvalidMeasurementValueError):
            convert_temperature(float("nan"), "C", "F")


class TestTemperatureUnitParsing:
    """Tests for parsing and normalizing unit strings."""

    @pytest.mark.parametrize(
        "unit_input",
        [
            "c",
            "C",
            "°C",
            "degC",
            "celsius",
            "CELSIUS",
            "degree Celsius",
            TemperatureUnit.CELSIUS,
        ],
    )
    def test_parse_celsius_variants(self, unit_input: str | TemperatureUnit) -> None:
        assert TemperatureUnit.from_string(unit_input) == TemperatureUnit.CELSIUS

    @pytest.mark.parametrize(
        "unit_input",
        [
            "f",
            "F",
            "°F",
            "degF",
            "fahrenheit",
            "FAHRENHEIT",
            "degree Fahrenheit",
            TemperatureUnit.FAHRENHEIT,
        ],
    )
    def test_parse_fahrenheit_variants(self, unit_input: str | TemperatureUnit) -> None:
        assert TemperatureUnit.from_string(unit_input) == TemperatureUnit.FAHRENHEIT

    @pytest.mark.parametrize(
        "invalid_unit", ["kelvin", "K", "meter", "kg", "", " ", None, 123]
    )
    def test_parse_unknown_units(self, invalid_unit: object) -> None:
        with pytest.raises(UnknownUnitError) as exc_info:
            TemperatureUnit.from_string(invalid_unit)  # type: ignore[arg-type]
        assert exc_info.value.unit == invalid_unit
        assert isinstance(exc_info.value, MeasurementValidationError)


class TestTemperatureMeasurementModel:
    """Tests for the TemperatureMeasurement dataclass."""

    def test_measurement_properties_and_string_representation(self) -> None:
        m_c = TemperatureMeasurement(36.6, TemperatureUnit.CELSIUS)
        assert m_c.value == 36.6
        assert m_c.unit == TemperatureUnit.CELSIUS
        assert str(m_c) == "36.60 °C"

        m_f = TemperatureMeasurement(98.6, TemperatureUnit.FAHRENHEIT)
        assert str(m_f) == "98.60 °F"

    def test_measurement_conversions(self) -> None:
        m_c = TemperatureMeasurement(37.0, TemperatureUnit.CELSIUS)
        m_f = m_c.to_fahrenheit()
        assert m_f.unit == TemperatureUnit.FAHRENHEIT
        assert math.isclose(m_f.value, 98.6, rel_tol=1e-5)

        # Converting back to Celsius
        m_c_back = m_f.to_celsius()
        assert m_c_back.unit == TemperatureUnit.CELSIUS
        assert math.isclose(m_c_back.value, 37.0, rel_tol=1e-5)

        # Converting to same unit returns self
        assert m_c.to_celsius() is m_c
        assert m_f.to_fahrenheit() is m_f

        # to_unit helper
        m_converted = m_c.to_unit("fahrenheit")
        assert math.isclose(m_converted.value, 98.6, rel_tol=1e-5)


class TestMeasurementValidator:
    """Tests for MeasurementValidator class."""

    def setup_method(self) -> None:
        self.validator = MeasurementValidator()

    @pytest.mark.parametrize(
        ("value", "unit", "expected_val", "expected_unit"),
        [
            (36.5, "°C", 36.5, TemperatureUnit.CELSIUS),
            (37, "C", 37.0, TemperatureUnit.CELSIUS),
            (25.0, "celsius", 25.0, TemperatureUnit.CELSIUS),  # lower bound
            (45.0, "celsius", 45.0, TemperatureUnit.CELSIUS),  # upper bound
            (98.6, "°F", 98.6, TemperatureUnit.FAHRENHEIT),
            (77.0, "F", 77.0, TemperatureUnit.FAHRENHEIT),  # lower bound in F
            (
                113.0,
                "fahrenheit",
                113.0,
                TemperatureUnit.FAHRENHEIT,
            ),  # upper bound in F
        ],
    )
    def test_valid_temperatures(
        self,
        value: float | int,
        unit: str,
        expected_val: float,
        expected_unit: TemperatureUnit,
    ) -> None:
        result = self.validator.validate(value, unit)
        assert isinstance(result, TemperatureMeasurement)
        assert result.value == expected_val
        assert result.unit == expected_unit
        assert self.validator.is_valid(value, unit) is True

    @pytest.mark.parametrize(
        "invalid_value",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            "37.0",
            None,
            True,
            False,
            [37.0],
            {"temp": 37.0},
        ],
    )
    def test_invalid_value_types_and_non_finite_numbers(
        self, invalid_value: object
    ) -> None:
        with pytest.raises(InvalidMeasurementValueError) as exc_info:
            self.validator.validate(invalid_value, "°C")
        if isinstance(invalid_value, float) and math.isnan(invalid_value):
            assert math.isnan(exc_info.value.value)
        else:
            assert exc_info.value.value == invalid_value
        assert self.validator.is_valid(invalid_value, "°C") is False

    @pytest.mark.parametrize(
        "invalid_unit", ["kelvin", "K", "mmHg", "percent", "", "deg", None, 10]
    )
    def test_unknown_units_handling(self, invalid_unit: object) -> None:
        with pytest.raises(UnknownUnitError) as exc_info:
            self.validator.validate(37.0, invalid_unit)
        assert exc_info.value.unit == invalid_unit
        assert self.validator.is_valid(37.0, invalid_unit) is False

    @pytest.mark.parametrize(
        ("out_of_range_val", "unit"),
        [
            (24.9, "°C"),  # below default clinical min (25°C)
            (45.1, "°C"),  # above default clinical max (45°C)
            (76.9, "°F"),  # below default clinical min (77°F)
            (113.1, "°F"),  # above default clinical max (113°F)
            (-50.0, "°C"),
            (-300.0, "°C"),  # below absolute zero
            (-500.0, "°F"),  # below absolute zero
        ],
    )
    def test_out_of_range_temperatures(
        self, out_of_range_val: float, unit: str
    ) -> None:
        with pytest.raises(MeasurementOutOfRangeError) as exc_info:
            self.validator.validate(out_of_range_val, unit)
        assert exc_info.value.value == out_of_range_val
        assert self.validator.is_valid(out_of_range_val, unit) is False

    def test_absolute_zero_violation(self) -> None:
        with pytest.raises(MeasurementOutOfRangeError) as exc_c:
            self.validator.validate(ABSOLUTE_ZERO_CELSIUS - 1.0, "°C")
        assert "below absolute zero" in str(exc_c.value)

        with pytest.raises(MeasurementOutOfRangeError) as exc_f:
            self.validator.validate(ABSOLUTE_ZERO_FAHRENHEIT - 1.0, "°F")
        assert "below absolute zero" in str(exc_f.value)

    def test_custom_range_configuration(self) -> None:
        custom_validator = MeasurementValidator(min_celsius=35.0, max_celsius=42.0)
        assert custom_validator.is_valid(36.0, "°C") is True
        assert custom_validator.is_valid(34.9, "°C") is False
        assert custom_validator.is_valid(42.1, "°C") is False

    def test_non_strict_clinical_range(self) -> None:
        relaxed_validator = MeasurementValidator(strict_clinical_range=False)
        # Allows wide physical temperatures as long as above absolute zero
        assert relaxed_validator.is_valid(10.0, "°C") is True
        assert relaxed_validator.is_valid(80.0, "°C") is True
        assert relaxed_validator.is_valid(-100.0, "°C") is True
        # Still rejects below absolute zero
        assert relaxed_validator.is_valid(-280.0, "°C") is False

    def test_validate_and_convert(self) -> None:
        result_c = self.validator.validate_and_convert(98.6, "°F", target_unit="°C")
        assert result_c.unit == TemperatureUnit.CELSIUS
        assert math.isclose(result_c.value, 37.0, rel_tol=1e-5)

        result_f = self.validator.validate_and_convert(37.0, "°C", target_unit="°F")
        assert result_f.unit == TemperatureUnit.FAHRENHEIT
        assert math.isclose(result_f.value, 98.6, rel_tol=1e-5)


class TestValidationExceptions:
    """Tests for custom exception formatting and attributes."""

    def test_base_measurement_validation_error(self) -> None:
        err = MeasurementValidationError("Base validation failed")
        assert err.message == "Base validation failed"
        assert str(err) == "Base validation failed"

    def test_invalid_measurement_value_error_custom_message(self) -> None:
        err = InvalidMeasurementValueError("bad_val", message="Custom error")
        assert err.value == "bad_val"
        assert str(err) == "Custom error"

    def test_unknown_unit_error_custom_message_and_defaults(self) -> None:
        err_default = UnknownUnitError("unknown_unit")
        assert "unknown_unit" in str(err_default)
        assert err_default.supported_units == []

        err_custom = UnknownUnitError("kelvin", message="Custom unit message")
        assert str(err_custom) == "Custom unit message"
        assert err_custom.unit == "kelvin"

    def test_measurement_out_of_range_error_formatting(self) -> None:
        err_no_bounds = MeasurementOutOfRangeError(value=50.0, unit="°C")
        assert "Measurement value 50.0 °C is out of acceptable range." in str(
            err_no_bounds
        )

        err_custom = MeasurementOutOfRangeError(
            value=50.0, unit="°C", message="Out of bounds custom"
        )
        assert str(err_custom) == "Out of bounds custom"
