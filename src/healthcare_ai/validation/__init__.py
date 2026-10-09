"""Measurement validation package."""

from healthcare_ai.validation.exceptions import (
    InvalidMeasurementValueError,
    MeasurementOutOfRangeError,
    MeasurementValidationError,
    UnknownUnitError,
)
from healthcare_ai.validation.measurement import (
    ABSOLUTE_ZERO_CELSIUS,
    ABSOLUTE_ZERO_FAHRENHEIT,
    DEFAULT_MAX_BODY_TEMP_CELSIUS,
    DEFAULT_MIN_BODY_TEMP_CELSIUS,
    MeasurementValidator,
    TemperatureMeasurement,
    TemperatureUnit,
    celsius_to_fahrenheit,
    convert_temperature,
    fahrenheit_to_celsius,
)

__all__ = [
    "MeasurementValidationError",
    "InvalidMeasurementValueError",
    "UnknownUnitError",
    "MeasurementOutOfRangeError",
    "TemperatureUnit",
    "TemperatureMeasurement",
    "MeasurementValidator",
    "celsius_to_fahrenheit",
    "fahrenheit_to_celsius",
    "convert_temperature",
    "ABSOLUTE_ZERO_CELSIUS",
    "ABSOLUTE_ZERO_FAHRENHEIT",
    "DEFAULT_MIN_BODY_TEMP_CELSIUS",
    "DEFAULT_MAX_BODY_TEMP_CELSIUS",
]
