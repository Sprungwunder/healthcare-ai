"""Exceptions for measurement validation."""

from typing import Any, Optional


class MeasurementValidationError(ValueError):
    """Base exception for all measurement validation errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidMeasurementValueError(MeasurementValidationError):
    """Raised when a measurement value is not a valid number (e.g., NaN, Inf)."""

    def __init__(self, value: Any, message: Optional[str] = None) -> None:
        if message is not None:
            detail = message
        else:
            detail = (
                f"Invalid measurement value: {value!r}. "
                "Value must be a finite real number."
            )
        super().__init__(detail)
        self.value = value


class UnknownUnitError(MeasurementValidationError):
    """Raised when an unknown or unsupported measurement unit is provided."""

    def __init__(
        self,
        unit: Any,
        supported_units: Optional[list[str]] = None,
        message: Optional[str] = None,
    ) -> None:
        if message is None:
            supported_str = (
                f" Supported units: {', '.join(supported_units)}."
                if supported_units
                else ""
            )
            detail = (
                f"Unknown or unsupported measurement unit: {unit!r}.{supported_str}"
            )
        else:
            detail = message
        super().__init__(detail)
        self.unit = unit
        self.supported_units = supported_units or []


class MeasurementOutOfRangeError(MeasurementValidationError):
    """Raised when a value is outside the allowed or plausible range."""

    def __init__(
        self,
        value: float,
        unit: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        if message is None:
            bounds = []
            if min_value is not None:
                bounds.append(f"min: {min_value}")
            if max_value is not None:
                bounds.append(f"max: {max_value}")
            bounds_str = f" (allowed range: {', '.join(bounds)})" if bounds else ""
            detail = (
                f"Measurement value {value} {unit} is out of acceptable "
                f"range{bounds_str}."
            )
        else:
            detail = message
        super().__init__(detail)
        self.value = value
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value
