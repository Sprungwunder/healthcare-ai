"""Unit tests for medical measurement validation and normalization."""

from dataclasses import FrozenInstanceError

import pytest

import healthcare_ai
from healthcare_ai.measurements import (
    ABSOLUTE_ZERO_CELSIUS,
    DEFAULT_BODY_TEMP_MAX_CELSIUS,
    DEFAULT_BODY_TEMP_MIN_CELSIUS,
    DEFAULT_GLUCOSE_MAX_MMOL_PER_L,
    DEFAULT_GLUCOSE_MIN_MMOL_PER_L,
    GLUCOSE_MG_PER_DL_PER_MMOL_PER_L,
    GlucoseUnit,
    InvalidValueError,
    Measurement,
    MeasurementValidationError,
    PhysiologicalRangeError,
    TemperatureUnit,
    UnknownUnitError,
    create_glucose_measurement,
    create_temperature_measurement,
    normalize_glucose,
    normalize_temperature,
    validate_glucose,
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


class TestGlucoseUnitParsing:
    """Tests for glucose unit parsing."""

    @pytest.mark.parametrize(
        "unit_input,expected",
        [
            ("mmol/L", GlucoseUnit.MMOL_PER_L),
            ("mmol/l", GlucoseUnit.MMOL_PER_L),
            ("MMOL/L", GlucoseUnit.MMOL_PER_L),
            ("mmol/liter", GlucoseUnit.MMOL_PER_L),
            ("mmol/litre", GlucoseUnit.MMOL_PER_L),
            ("  mmol/L  ", GlucoseUnit.MMOL_PER_L),
            ("mg/dL", GlucoseUnit.MG_PER_DL),
            ("mg/dl", GlucoseUnit.MG_PER_DL),
            ("MG/DL", GlucoseUnit.MG_PER_DL),
            ("mg%", GlucoseUnit.MG_PER_DL),
            ("mg/100ml", GlucoseUnit.MG_PER_DL),
            ("mg/100 mL", GlucoseUnit.MG_PER_DL),
            ("  mg/dL  ", GlucoseUnit.MG_PER_DL),
        ],
    )
    def test_valid_unit_parsing(self, unit_input: str, expected: GlucoseUnit) -> None:
        assert GlucoseUnit.from_str(unit_input) == expected

    @pytest.mark.parametrize(
        "invalid_unit",
        ["°C", "g/L", "mmol", "mg", "unknown", " ", ""],
    )
    def test_unknown_unit_raises_error(self, invalid_unit: str) -> None:
        with pytest.raises(UnknownUnitError) as exc_info:
            GlucoseUnit.from_str(invalid_unit)
        assert invalid_unit.strip() in str(exc_info.value) or "empty" in str(
            exc_info.value
        )

    def test_non_string_unit_parsing_raises_error(self) -> None:
        with pytest.raises(InvalidValueError):
            GlucoseUnit.from_str(5.5)  # type: ignore[arg-type]


class TestGlucoseNormalization:
    """Tests for normalizing glucose values to mmol/L."""

    def test_conversion_factor_matches_glucose_molar_mass(self) -> None:
        # 180.16 g/mol -> 1 mmol/L == 18.016 mg/dL
        assert GLUCOSE_MG_PER_DL_PER_MMOL_PER_L == pytest.approx(18.016)

    @pytest.mark.parametrize(
        "val,unit,expected_mmol",
        [
            (0.0, GlucoseUnit.MMOL_PER_L, 0.0),
            (5.5, GlucoseUnit.MMOL_PER_L, 5.5),
            (7, "mmol/L", 7.0),
            (18.016, GlucoseUnit.MG_PER_DL, 1.0),
            (90.08, "mg/dL", 5.0),
            (100, "mg/dl", 5.5506),
            (126.0, "mg%", 6.9938),
        ],
    )
    def test_normalize_valid_glucose(
        self, val: float | int, unit: GlucoseUnit | str, expected_mmol: float
    ) -> None:
        assert normalize_glucose(val, unit) == pytest.approx(expected_mmol, abs=1e-4)

    @pytest.mark.parametrize("unit", [GlucoseUnit.MMOL_PER_L, GlucoseUnit.MG_PER_DL])
    def test_negative_concentration_raises_error(self, unit: GlucoseUnit) -> None:
        with pytest.raises(InvalidValueError, match="cannot be negative"):
            normalize_glucose(-0.1, unit)

    @pytest.mark.parametrize("invalid_val", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_values_raise_error(self, invalid_val: float) -> None:
        with pytest.raises(InvalidValueError, match="must be finite"):
            normalize_glucose(invalid_val, GlucoseUnit.MMOL_PER_L)

    @pytest.mark.parametrize(
        "invalid_type_val",
        ["5.5", None, True, False, [5.5], {"val": 5.5}],
    )
    def test_invalid_types_raise_type_error(self, invalid_type_val: object) -> None:
        with pytest.raises(TypeError, match="must be numeric"):
            normalize_glucose(
                invalid_type_val,  # type: ignore[arg-type]
                GlucoseUnit.MMOL_PER_L,
            )

    def test_unknown_unit_raises_error(self) -> None:
        with pytest.raises(UnknownUnitError):
            normalize_glucose(5.5, "g/L")


class TestGlucoseValidation:
    """Tests for physiological glucose validation."""

    @pytest.mark.parametrize(
        "val,unit,expected_mmol",
        [
            (5.5, GlucoseUnit.MMOL_PER_L, 5.5),
            (2.8, "mmol/L", 2.8),  # hypoglycemia
            (40.0, "mmol/l", 40.0),  # hyperosmolar crisis
            (0.5, GlucoseUnit.MMOL_PER_L, DEFAULT_GLUCOSE_MIN_MMOL_PER_L),
            (55.0, GlucoseUnit.MMOL_PER_L, DEFAULT_GLUCOSE_MAX_MMOL_PER_L),
            (90.08, "mg/dL", 5.0),
            (990.0, "mg/dL", 54.9512),
        ],
    )
    def test_valid_physiological_glucose(
        self, val: float | int, unit: GlucoseUnit | str, expected_mmol: float
    ) -> None:
        assert validate_glucose(val, unit) == pytest.approx(expected_mmol, abs=1e-4)

    @pytest.mark.parametrize(
        "val,unit",
        [
            (0.0, GlucoseUnit.MMOL_PER_L),
            (0.49, GlucoseUnit.MMOL_PER_L),
            (55.1, "mmol/L"),
            (9.0, "mg/dL"),  # ~0.4996 mmol/L
            (1000.0, "mg/dL"),  # ~55.51 mmol/L
        ],
    )
    def test_out_of_bounds_glucose_raises_range_error(
        self, val: float, unit: GlucoseUnit | str
    ) -> None:
        with pytest.raises(
            PhysiologicalRangeError, match="outside plausible physiological bounds"
        ):
            validate_glucose(val, unit)

    @pytest.mark.parametrize(
        "val,declared_unit",
        [
            (100.0, "mmol/L"),  # really 100 mg/dL
            (5.5, "mg/dL"),  # really 5.5 mmol/L
        ],
    )
    def test_swapped_units_are_caught(self, val: float, declared_unit: str) -> None:
        with pytest.raises(PhysiologicalRangeError):
            validate_glucose(val, declared_unit)

    def test_default_unit_is_mmol_per_l(self) -> None:
        assert validate_glucose(5.5) == 5.5

    def test_custom_physiological_bounds(self) -> None:
        assert validate_glucose(3.5, "mmol/L", min_mmol=3.0, max_mmol=10.0) == 3.5

        with pytest.raises(PhysiologicalRangeError):
            validate_glucose(3.5, "mmol/L", min_mmol=3.9, max_mmol=10.0)

    def test_invalid_bound_configuration_raises_error(self) -> None:
        with pytest.raises(ValueError, match="cannot be greater than max_mmol"):
            validate_glucose(5.5, "mmol/L", min_mmol=10.0, max_mmol=3.0)


class TestGlucoseMeasurementCreation:
    """Tests for packaging glucose readings into Measurement objects."""

    def test_create_measurement_mmol_per_l(self) -> None:
        measurement = create_glucose_measurement(5.5, "mmol/L")
        assert isinstance(measurement, Measurement)
        assert measurement.value == 5.5
        assert measurement.unit == "mmol/L"
        assert measurement.measurement_type == "glucose"
        assert measurement.raw_value == 5.5
        assert measurement.raw_unit == "mmol/L"

    def test_create_measurement_mg_per_dl(self) -> None:
        measurement = create_glucose_measurement(90.08, GlucoseUnit.MG_PER_DL)
        assert measurement.value == pytest.approx(5.0, abs=1e-4)
        assert measurement.unit == "mmol/L"
        assert measurement.measurement_type == "glucose"
        assert measurement.raw_value == 90.08
        assert measurement.raw_unit == "mg/dL"

    def test_create_measurement_fail_fast_on_invalid_input(self) -> None:
        with pytest.raises(PhysiologicalRangeError):
            create_glucose_measurement(100.0, "mmol/L")

        with pytest.raises(UnknownUnitError):
            create_glucose_measurement(5.5, "°C")


@pytest.mark.parametrize(
    "name",
    [
        "DEFAULT_GLUCOSE_MAX_MMOL_PER_L",
        "DEFAULT_GLUCOSE_MIN_MMOL_PER_L",
        "GLUCOSE_MG_PER_DL_PER_MMOL_PER_L",
        "GlucoseUnit",
        "create_glucose_measurement",
        "normalize_glucose",
        "validate_glucose",
    ],
)
def test_glucose_api_is_exported_from_package(name: str) -> None:
    assert name in healthcare_ai.__all__
    assert hasattr(healthcare_ai, name)
