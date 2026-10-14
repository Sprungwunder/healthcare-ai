"""Medical measurement validation and normalization module.

This module provides scalar validation and normalization for medical measurements
with a fail-fast approach and standardized SI / clinical target units
(°C, L, kg, m, mol).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

# Absolute physical zero in Celsius
ABSOLUTE_ZERO_CELSIUS: Final[float] = -273.15

# Default physiological bounds for human body temperature in °C
DEFAULT_BODY_TEMP_MIN_CELSIUS: Final[float] = 25.0
DEFAULT_BODY_TEMP_MAX_CELSIUS: Final[float] = 45.0


class MeasurementValidationError(ValueError):
    """Base exception for all measurement validation and normalization errors."""


class UnknownUnitError(MeasurementValidationError):
    """Raised when an unrecognized or unsupported measurement unit is provided."""


class InvalidValueError(MeasurementValidationError):
    """Raised when a measurement value is non-numeric, non-finite, or impossible."""


class PhysiologicalRangeError(MeasurementValidationError):
    """Raised when a measurement falls outside plausible physiological bounds."""


class TemperatureUnit(str, Enum):
    """Supported temperature units."""

    CELSIUS = "°C"
    FAHRENHEIT = "°F"

    @classmethod
    def from_str(cls, unit_str: str) -> TemperatureUnit:
        """Parse a unit string into a standardized TemperatureUnit.

        Supports case-insensitive matching and common aliases/symbols.

        Args:
            unit_str: String representation of the unit
                (e.g. "C", "celsius", "°F", "fahrenheit").

        Returns:
            The corresponding TemperatureUnit enum member.

        Raises:
            UnknownUnitError: If unit_str cannot be mapped to a known unit.
            InvalidValueError: If unit_str is not a string.
        """
        if not isinstance(unit_str, str):
            raise InvalidValueError(
                f"Unit must be a string or TemperatureUnit, got "
                f"{type(unit_str).__name__}"
            )

        cleaned = unit_str.strip().lower()
        if not cleaned:
            raise UnknownUnitError("Unit string cannot be empty.")

        celsius_synonyms = {
            "c",
            "°c",
            "degc",
            "celsius",
            "degree celsius",
            "degrees celsius",
        }
        fahrenheit_synonyms = {
            "f",
            "°f",
            "degf",
            "fahrenheit",
            "degree fahrenheit",
            "degrees fahrenheit",
        }

        if cleaned in celsius_synonyms:
            return cls.CELSIUS
        if cleaned in fahrenheit_synonyms:
            return cls.FAHRENHEIT

        supported_list = ", ".join(sorted(celsius_synonyms | fahrenheit_synonyms))
        raise UnknownUnitError(
            f"Unknown or unsupported temperature unit: '{unit_str}'. "
            f"Supported units: {supported_list}"
        )


@dataclass(frozen=True)
class Measurement:
    """Represents a validated and normalized medical measurement.

    Attributes:
        value: The numerical value in standard SI / target clinical units.
        unit: Standardized unit string (e.g. '°C').
        measurement_type: Category of the measurement (e.g. 'temperature').
        raw_value: The original value before normalization.
        raw_unit: The original unit before normalization.
    """

    value: float
    unit: str
    measurement_type: str = "temperature"
    raw_value: float | None = None
    raw_unit: str | None = None


def normalize_temperature(
    value: float | int,
    unit: TemperatureUnit | str,
) -> float:
    """Convert a temperature value to standard Celsius (°C).

    Args:
        value: Numeric temperature value.
        unit: Unit of the temperature value (Celsius or Fahrenheit).

    Returns:
        Temperature in degrees Celsius as float.

    Raises:
        TypeError: If value is not a real number (int or float, not bool).
        InvalidValueError: If value is NaN, infinite, or below absolute zero.
        UnknownUnitError: If unit is unrecognized.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"Measurement value must be numeric (int or float), got "
            f"{type(value).__name__}: {value!r}"
        )

    val = float(value)
    if math.isnan(val) or math.isinf(val):
        raise InvalidValueError(f"Measurement value must be finite, got {val}")

    if isinstance(unit, TemperatureUnit):
        parsed_unit = unit
    else:
        parsed_unit = TemperatureUnit.from_str(unit)

    if parsed_unit == TemperatureUnit.CELSIUS:
        celsius_val = val
    elif parsed_unit == TemperatureUnit.FAHRENHEIT:
        celsius_val = (val - 32.0) * 5.0 / 9.0
    else:  # pragma: no cover
        raise UnknownUnitError(f"Unsupported unit: {parsed_unit}")

    if celsius_val < ABSOLUTE_ZERO_CELSIUS:
        raise InvalidValueError(
            f"Temperature {val} {parsed_unit.value} ({celsius_val:.2f} °C) "
            f"is below absolute zero (-273.15 °C)."
        )

    return celsius_val


def validate_temperature(
    value: float | int,
    unit: TemperatureUnit | str = TemperatureUnit.CELSIUS,
    *,
    min_celsius: float = DEFAULT_BODY_TEMP_MIN_CELSIUS,
    max_celsius: float = DEFAULT_BODY_TEMP_MAX_CELSIUS,
) -> float:
    """Validate that a temperature reading lies within plausible physiological bounds.

    Converts to Celsius first if necessary, then checks against bounds.

    Args:
        value: Numeric temperature reading.
        unit: Unit of the input temperature (defaults to Celsius).
        min_celsius: Lower plausible bound in °C (default: 25.0 °C).
        max_celsius: Upper plausible bound in °C (default: 45.0 °C).

    Returns:
        The validated temperature normalized to degrees Celsius (°C).

    Raises:
        TypeError: If value is non-numeric.
        InvalidValueError: If value is non-finite or below absolute zero.
        UnknownUnitError: If unit is not recognized.
        PhysiologicalRangeError: If normalized temperature is out of bounds.
    """
    if min_celsius > max_celsius:
        raise ValueError(
            f"min_celsius ({min_celsius}) cannot be greater than "
            f"max_celsius ({max_celsius})"
        )

    celsius_val = normalize_temperature(value, unit)

    if celsius_val < min_celsius or celsius_val > max_celsius:
        input_unit_str = unit.value if isinstance(unit, TemperatureUnit) else str(unit)
        raise PhysiologicalRangeError(
            f"Temperature {value} {input_unit_str} ({celsius_val:.2f} °C) is outside "
            f"plausible physiological bounds "
            f"[{min_celsius:.1f} °C, {max_celsius:.1f} °C]."
        )

    return celsius_val


def create_temperature_measurement(
    value: float | int,
    unit: TemperatureUnit | str,
    *,
    min_celsius: float = DEFAULT_BODY_TEMP_MIN_CELSIUS,
    max_celsius: float = DEFAULT_BODY_TEMP_MAX_CELSIUS,
) -> Measurement:
    """Validate and package a temperature reading into a standardized Measurement.

    Args:
        value: Raw temperature value.
        unit: Raw temperature unit.
        min_celsius: Lower plausible bound in °C.
        max_celsius: Upper plausible bound in °C.

    Returns:
        A validated Measurement instance normalized to °C.
    """
    validated_celsius = validate_temperature(
        value,
        unit,
        min_celsius=min_celsius,
        max_celsius=max_celsius,
    )
    raw_unit_str = unit.value if isinstance(unit, TemperatureUnit) else str(unit)
    is_valid_numeric = not isinstance(value, bool) and isinstance(value, (int, float))
    raw_num = float(value) if is_valid_numeric else None
    return Measurement(
        value=validated_celsius,
        unit=TemperatureUnit.CELSIUS.value,
        measurement_type="temperature",
        raw_value=raw_num,
        raw_unit=raw_unit_str,
    )
