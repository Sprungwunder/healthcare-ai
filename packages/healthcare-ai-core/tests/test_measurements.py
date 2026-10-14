"""Unit tests for medical measurement validation and normalization."""

from dataclasses import FrozenInstanceError

import pytest

from healthcare_ai.measurements import (
    ABSOLUTE_ZERO_CELSIUS,
    DEFAULT_BODY_TEMP_MAX_CELSIUS,
    DEFAULT_BODY_TEMP_MIN_CELSIUS,
    InvalidValueError,
    Measurement,
    MeasurementValidationError,
    PhysiologicalRangeError,
    TemperatureUnit,
    UnknownUnitError,
    create_temperature_measurement,
    normalize_temperature,
    validate_temperature,
)


class TestTemperatureUnitParsing:
    """Tests for unit parsing and normalization."""

    @pytest.mark.parametrize(
        "unit_input,expected",
        [
            ("C", TemperatureUnit.CELSIUS),
            ("c", TemperatureUnit.CELSIUS),
            ("°C", TemperatureUnit.CELSIUS),
            ("degC", TemperatureUnit.CELSIUS),
            ("celsius", TemperatureUnit.CELSIUS),
            ("degree celsius", TemperatureUnit.CELSIUS),
            ("degrees celsius", TemperatureUnit.CELSIUS),
            ("  °C  ", TemperatureUnit.CELSIUS),
            ("F", TemperatureUnit.FAHRENHEIT),
            ("f", TemperatureUnit.FAHRENHEIT),
            ("°F", TemperatureUnit.FAHRENHEIT),
            ("degF", TemperatureUnit.FAHRENHEIT),
            ("fahrenheit", TemperatureUnit.FAHRENHEIT),
            ("degree fahrenheit", TemperatureUnit.FAHRENHEIT),
            ("degrees fahrenheit", TemperatureUnit.FAHRENHEIT),
            ("  °F  ", TemperatureUnit.FAHRENHEIT),
        ],
    )
    def test_valid_unit_parsing(
        self, unit_input: str, expected: TemperatureUnit
    ) -> None:
        assert TemperatureUnit.from_str(unit_input) == expected

    @pytest.mark.parametrize(
        "invalid_unit",
        [
            "K",
            "kelvin",
            "mg/dL",
            "unknown",
            "123",
            " ",
            "",
        ],
    )
    def test_unknown_unit_raises_error(self, invalid_unit: str) -> None:
        with pytest.raises(UnknownUnitError) as exc_info:
            TemperatureUnit.from_str(invalid_unit)
        assert issubclass(UnknownUnitError, MeasurementValidationError)
        assert issubclass(UnknownUnitError, ValueError)
        assert str(invalid_unit).strip() in str(exc_info.value) or "empty" in str(
            exc_info.value
        )

    def test_non_string_unit_parsing_raises_error(self) -> None:
        with pytest.raises(InvalidValueError):
            TemperatureUnit.from_str(123)  # type: ignore[arg-type]


class TestTemperatureNormalization:
    """Tests for normalizing temperature values to Celsius."""

    @pytest.mark.parametrize(
        "val,unit,expected_celsius",
        [
            (0.0, TemperatureUnit.CELSIUS, 0.0),
            (37.0, TemperatureUnit.CELSIUS, 37.0),
            (37, "°C", 37.0),
            (-50.0, "celsius", -50.0),
            (32.0, TemperatureUnit.FAHRENHEIT, 0.0),
            (98.6, TemperatureUnit.FAHRENHEIT, 37.0),
            (212.0, "°F", 100.0),
            (-40.0, "fahrenheit", -40.0),  # -40°F == -40°C
        ],
    )
    def test_normalize_valid_temperatures(
        self, val: float | int, unit: TemperatureUnit | str, expected_celsius: float
    ) -> None:
        result = normalize_temperature(val, unit)
        assert result == pytest.approx(expected_celsius, abs=1e-4)

    def test_below_absolute_zero_raises_error(self) -> None:
        with pytest.raises(InvalidValueError, match="below absolute zero"):
            normalize_temperature(ABSOLUTE_ZERO_CELSIUS - 1.0, TemperatureUnit.CELSIUS)

        with pytest.raises(InvalidValueError, match="below absolute zero"):
            normalize_temperature(-500.0, TemperatureUnit.FAHRENHEIT)

    @pytest.mark.parametrize("invalid_val", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_values_raise_error(self, invalid_val: float) -> None:
        with pytest.raises(InvalidValueError, match="must be finite"):
            normalize_temperature(invalid_val, TemperatureUnit.CELSIUS)

    @pytest.mark.parametrize(
        "invalid_type_val",
        ["37.0", None, True, False, [37.0], {"val": 37.0}],
    )
    def test_invalid_types_raise_type_error(self, invalid_type_val: object) -> None:
        with pytest.raises(TypeError, match="must be numeric"):
            normalize_temperature(
                invalid_type_val,  # type: ignore[arg-type]
                TemperatureUnit.CELSIUS,
            )


class TestTemperatureValidation:
    """Tests for physiological validation and fail-fast behavior."""

    @pytest.mark.parametrize(
        "val,unit,expected_celsius",
        [
            (36.5, TemperatureUnit.CELSIUS, 36.5),
            (37, "°C", 37.0),
            (38.2, "celsius", 38.2),
            (25.0, TemperatureUnit.CELSIUS, DEFAULT_BODY_TEMP_MIN_CELSIUS),
            (45.0, TemperatureUnit.CELSIUS, DEFAULT_BODY_TEMP_MAX_CELSIUS),
            (98.6, TemperatureUnit.FAHRENHEIT, 37.0),
            (77.0, "°F", 25.0),  # 77°F == 25°C
            (113.0, "fahrenheit", 45.0),  # 113°F == 45°C
        ],
    )
    def test_valid_physiological_temperature(
        self, val: float | int, unit: TemperatureUnit | str, expected_celsius: float
    ) -> None:
        result = validate_temperature(val, unit)
        assert result == pytest.approx(expected_celsius, abs=1e-4)

    @pytest.mark.parametrize(
        "val,unit",
        [
            (24.9, TemperatureUnit.CELSIUS),
            (45.1, TemperatureUnit.CELSIUS),
            (10.0, "°C"),
            (50.0, "celsius"),
            (76.9, TemperatureUnit.FAHRENHEIT),  # ~24.94°C
            (113.1, TemperatureUnit.FAHRENHEIT),  # ~45.05°C
            (0.0, "°F"),
            (150.0, "fahrenheit"),
        ],
    )
    def test_out_of_bounds_temperature_raises_range_error(
        self, val: float, unit: TemperatureUnit | str
    ) -> None:
        with pytest.raises(
            PhysiologicalRangeError, match="outside plausible physiological bounds"
        ):
            validate_temperature(val, unit)

    def test_custom_physiological_bounds(self) -> None:
        # 34.0°C should pass custom bounds [30.0, 40.0]
        assert (
            validate_temperature(34.0, "°C", min_celsius=30.0, max_celsius=40.0) == 34.0
        )

        # 34.0°C should fail custom bounds [35.0, 40.0]
        with pytest.raises(PhysiologicalRangeError):
            validate_temperature(34.0, "°C", min_celsius=35.0, max_celsius=40.0)

    def test_invalid_bound_configuration_raises_error(self) -> None:
        with pytest.raises(ValueError, match="cannot be greater than max_celsius"):
            validate_temperature(37.0, "°C", min_celsius=40.0, max_celsius=35.0)


class TestMeasurementObjectCreation:
    """Tests for Measurement dataclass encapsulation."""

    def test_create_measurement_celsius(self) -> None:
        measurement = create_temperature_measurement(37.0, "°C")
        assert isinstance(measurement, Measurement)
        assert measurement.value == 37.0
        assert measurement.unit == "°C"
        assert measurement.measurement_type == "temperature"
        assert measurement.raw_value == 37.0
        assert measurement.raw_unit == "°C"

    def test_create_measurement_fahrenheit(self) -> None:
        measurement = create_temperature_measurement(98.6, "°F")
        assert isinstance(measurement, Measurement)
        assert measurement.value == pytest.approx(37.0, abs=1e-4)
        assert measurement.unit == "°C"
        assert measurement.measurement_type == "temperature"
        assert measurement.raw_value == 98.6
        assert measurement.raw_unit == "°F"

    def test_measurement_is_immutable(self) -> None:
        measurement = create_temperature_measurement(36.8, TemperatureUnit.CELSIUS)
        with pytest.raises(FrozenInstanceError):
            measurement.value = 38.0  # type: ignore[misc]

    def test_create_measurement_fail_fast_on_invalid_input(self) -> None:
        with pytest.raises(PhysiologicalRangeError):
            create_temperature_measurement(15.0, "°C")

        with pytest.raises(UnknownUnitError):
            create_temperature_measurement(37.0, "Kelvin")
