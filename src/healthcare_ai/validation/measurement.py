"""Measurement and temperature validation logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from healthcare_ai.validation.exceptions import (
    InvalidMeasurementValueError,
    MeasurementOutOfRangeError,
    MeasurementValidationError,
    UnknownUnitError,
)

# Physical absolute zero constants
ABSOLUTE_ZERO_CELSIUS: float = -273.15
ABSOLUTE_ZERO_FAHRENHEIT: float = -459.67

# Default clinical / physiological plausible limits for human body temperature
DEFAULT_MIN_BODY_TEMP_CELSIUS: float = 25.0
DEFAULT_MAX_BODY_TEMP_CELSIUS: float = 45.0


class TemperatureUnit(str, Enum):
    """Supported temperature units."""

    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"

    @property
    def symbol(self) -> str:
        """Return the standard symbol for the unit."""
        if self == TemperatureUnit.CELSIUS:
            return "°C"
        return "°F"

    @classmethod
    def from_string(cls, unit: str | TemperatureUnit) -> TemperatureUnit:
        """Parse and normalize a unit string into a TemperatureUnit enum.

        Raises:
            UnknownUnitError: If the unit is not recognized or unsupported.
        """
        if isinstance(unit, TemperatureUnit):
            return unit

        if not isinstance(unit, str):
            msg = (
                "Unit must be a string or TemperatureUnit, "
                f"got {type(unit).__name__}: {unit!r}"
            )
            raise UnknownUnitError(
                unit=unit,
                supported_units=[u.value for u in cls],
                message=msg,
            )

        cleaned = unit.strip().lower()
        # Remove degrees symbol variations if present (longest match first)
        for prefix in ("degrees", "degree", "deg", "°"):
            cleaned = cleaned.replace(prefix, "")
        cleaned = cleaned.strip()

        if cleaned in {"c", "celsius"}:
            return cls.CELSIUS
        if cleaned in {"f", "fahrenheit"}:
            return cls.FAHRENHEIT

        raise UnknownUnitError(
            unit=unit,
            supported_units=["celsius (C, °C)", "fahrenheit (F, °F)"],
        )


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (celsius * 9.0 / 5.0) + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32.0) * 5.0 / 9.0


def convert_temperature(
    value: float,
    from_unit: str | TemperatureUnit,
    to_unit: str | TemperatureUnit,
) -> float:
    """Convert a temperature value from one unit to another.

    Raises:
        InvalidMeasurementValueError: If value is not a finite number.
        UnknownUnitError: If either unit is unsupported.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise InvalidMeasurementValueError(value)

    source_unit = TemperatureUnit.from_string(from_unit)
    target_unit = TemperatureUnit.from_string(to_unit)

    if source_unit == target_unit:
        return float(value)

    if (
        source_unit == TemperatureUnit.CELSIUS
        and target_unit == TemperatureUnit.FAHRENHEIT
    ):
        return celsius_to_fahrenheit(float(value))

    return fahrenheit_to_celsius(float(value))


@dataclass(frozen=True)
class TemperatureMeasurement:
    """Represents a validated temperature measurement."""

    value: float
    unit: TemperatureUnit

    def to_celsius(self) -> TemperatureMeasurement:
        """Convert this measurement to Celsius."""
        if self.unit == TemperatureUnit.CELSIUS:
            return self
        converted_val = fahrenheit_to_celsius(self.value)
        return TemperatureMeasurement(value=converted_val, unit=TemperatureUnit.CELSIUS)

    def to_fahrenheit(self) -> TemperatureMeasurement:
        """Convert this measurement to Fahrenheit."""
        if self.unit == TemperatureUnit.FAHRENHEIT:
            return self
        converted_val = celsius_to_fahrenheit(self.value)
        return TemperatureMeasurement(
            value=converted_val, unit=TemperatureUnit.FAHRENHEIT
        )

    def to_unit(self, target_unit: str | TemperatureUnit) -> TemperatureMeasurement:
        """Convert this measurement to the specified target unit."""
        unit_enum = TemperatureUnit.from_string(target_unit)
        if unit_enum == TemperatureUnit.CELSIUS:
            return self.to_celsius()
        return self.to_fahrenheit()

    def __str__(self) -> str:
        return f"{self.value:.2f} {self.unit.symbol}"


class MeasurementValidator:
    """Validator for medical temperature measurements.

    Ensures that values are numeric, finite, non-null, within valid physical
    and physiological bounds, and with recognized units.
    """

    def __init__(
        self,
        min_celsius: Optional[float] = DEFAULT_MIN_BODY_TEMP_CELSIUS,
        max_celsius: Optional[float] = DEFAULT_MAX_BODY_TEMP_CELSIUS,
        strict_clinical_range: bool = True,
    ) -> None:
        """Initialize validator with optional range restrictions.

        Args:
            min_celsius: Minimum valid temperature in Celsius (None to disable
                lower physiological bound).
            max_celsius: Maximum valid temperature in Celsius (None to disable
                upper physiological bound).
            strict_clinical_range: If True, enforce min_celsius and max_celsius
                boundaries. If False, only enforce physical limits (absolute zero).
        """
        self.min_celsius = min_celsius
        self.max_celsius = max_celsius
        self.strict_clinical_range = strict_clinical_range

    def validate(self, value: Any, unit: Any) -> TemperatureMeasurement:
        """Validate a temperature measurement value and unit.

        Args:
            value: The measurement value (must be int or float).
            unit: The unit (str or TemperatureUnit).

        Returns:
            TemperatureMeasurement: Validated measurement object.

        Raises:
            InvalidMeasurementValueError: If value is not a finite number.
            UnknownUnitError: If unit is unknown or unsupported.
            MeasurementOutOfRangeError: If value is outside physical or clinical limits.
        """
        # 1. Validate value type and finiteness
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            msg = (
                "Invalid measurement value type: expected finite int or float, "
                f"got {type(value).__name__} ({value!r})"
            )
            raise InvalidMeasurementValueError(value, message=msg)

        float_val = float(value)
        if not math.isfinite(float_val):
            raise InvalidMeasurementValueError(
                value,
                message=f"Measurement value must be finite, got: {value}",
            )

        # 2. Validate and parse unit
        unit_enum = TemperatureUnit.from_string(unit)

        # 3. Convert to Celsius for range evaluation
        celsius_val = (
            float_val
            if unit_enum == TemperatureUnit.CELSIUS
            else fahrenheit_to_celsius(float_val)
        )

        # 4. Check absolute physical zero
        if celsius_val < ABSOLUTE_ZERO_CELSIUS:
            min_limit = (
                ABSOLUTE_ZERO_CELSIUS
                if unit_enum == TemperatureUnit.CELSIUS
                else ABSOLUTE_ZERO_FAHRENHEIT
            )
            msg = (
                f"Temperature {float_val} {unit_enum.symbol} is below absolute zero "
                f"({min_limit} {unit_enum.symbol})."
            )
            raise MeasurementOutOfRangeError(
                value=float_val,
                unit=unit_enum.symbol,
                min_value=min_limit,
                message=msg,
            )

        # 5. Check clinical / configured range if strict
        if self.strict_clinical_range:
            min_c = self.min_celsius
            max_c = self.max_celsius

            if min_c is not None and celsius_val < min_c:
                min_bound: float = (
                    min_c
                    if unit_enum == TemperatureUnit.CELSIUS
                    else celsius_to_fahrenheit(min_c)
                )
                max_bound: Optional[float] = (
                    max_c
                    if unit_enum == TemperatureUnit.CELSIUS
                    else (celsius_to_fahrenheit(max_c) if max_c is not None else None)
                )
                msg = (
                    f"Temperature {float_val} {unit_enum.symbol} is below minimum "
                    f"allowed bound ({round(min_bound, 2)} {unit_enum.symbol})."
                )
                raise MeasurementOutOfRangeError(
                    value=float_val,
                    unit=unit_enum.symbol,
                    min_value=round(min_bound, 2),
                    max_value=round(max_bound, 2) if max_bound is not None else None,
                    message=msg,
                )

            if max_c is not None and celsius_val > max_c:
                min_bound_opt: Optional[float] = (
                    min_c
                    if unit_enum == TemperatureUnit.CELSIUS
                    else (celsius_to_fahrenheit(min_c) if min_c is not None else None)
                )
                max_bound_val: float = (
                    max_c
                    if unit_enum == TemperatureUnit.CELSIUS
                    else celsius_to_fahrenheit(max_c)
                )
                msg = (
                    f"Temperature {float_val} {unit_enum.symbol} exceeds maximum "
                    f"allowed bound ({round(max_bound_val, 2)} {unit_enum.symbol})."
                )
                raise MeasurementOutOfRangeError(
                    value=float_val,
                    unit=unit_enum.symbol,
                    min_value=round(min_bound_opt, 2)
                    if min_bound_opt is not None
                    else None,
                    max_value=round(max_bound_val, 2),
                    message=msg,
                )

        return TemperatureMeasurement(value=float_val, unit=unit_enum)

    def is_valid(self, value: Any, unit: Any) -> bool:
        """Check if a measurement is valid without raising exceptions.

        Returns:
            bool: True if measurement passes validation, False otherwise.
        """
        try:
            self.validate(value, unit)
            return True
        except MeasurementValidationError:
            return False

    def validate_and_convert(
        self,
        value: Any,
        unit: Any,
        target_unit: str | TemperatureUnit = TemperatureUnit.CELSIUS,
    ) -> TemperatureMeasurement:
        """Validate a temperature measurement and convert it to the target unit."""
        measurement = self.validate(value, unit)
        return measurement.to_unit(target_unit)
