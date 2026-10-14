"""Healthcare AI package."""

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

__version__ = "0.1.0"

__all__ = [
    "ABSOLUTE_ZERO_CELSIUS",
    "DEFAULT_BODY_TEMP_MAX_CELSIUS",
    "DEFAULT_BODY_TEMP_MIN_CELSIUS",
    "DEFAULT_GLUCOSE_MAX_MMOL_PER_L",
    "DEFAULT_GLUCOSE_MIN_MMOL_PER_L",
    "GLUCOSE_MG_PER_DL_PER_MMOL_PER_L",
    "GlucoseUnit",
    "InvalidValueError",
    "Measurement",
    "MeasurementValidationError",
    "PhysiologicalRangeError",
    "TemperatureUnit",
    "UnknownUnitError",
    "create_glucose_measurement",
    "create_temperature_measurement",
    "normalize_glucose",
    "normalize_temperature",
    "validate_glucose",
    "validate_temperature",
    "__version__",
]
