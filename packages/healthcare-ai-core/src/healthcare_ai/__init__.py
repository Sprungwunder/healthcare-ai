"""Healthcare AI package."""

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

__version__ = "0.1.0"

__all__ = [
    "ABSOLUTE_ZERO_CELSIUS",
    "DEFAULT_BODY_TEMP_MAX_CELSIUS",
    "DEFAULT_BODY_TEMP_MIN_CELSIUS",
    "InvalidValueError",
    "Measurement",
    "MeasurementValidationError",
    "PhysiologicalRangeError",
    "TemperatureUnit",
    "UnknownUnitError",
    "create_temperature_measurement",
    "normalize_temperature",
    "validate_temperature",
    "__version__",
]
