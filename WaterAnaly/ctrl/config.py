"""Project-wide configuration for the ctrl implementation."""

# Direction
DIR_FORWARD = "FORWARD"  # suction
DIR_REVERSE = "REVERSE"  # dispense / blow

# Sampling and debounce
SAMPLE_PERIOD_MS = 20
STABLE_COUNT = 10
VALVE_SWITCH_STABLE_MS = 50

# Timeouts
TIMEOUT_TAKE_LARGE_MS = 15000
TIMEOUT_TAKE_SMALL_MS = 15000
TIMEOUT_DISPENSE_MS = 10000
TIMEOUT_PULL_DIGESTOR_MS = 12000
HEAT_UP_TIMEOUT_MS = 180000

# Blow compensation
SUPPLEMENT_BLOW_MS = 500

# Process settings
DIGEST_TEMP_C = 50.0
HEAT_HOLD_MS = 300000
DIGEST_SETTLE_TOTAL_MS = 900000
STIR_DURATION_MS = 15000
OPTICS_PREHEAT_MS = 2000

# Thresholds (tune by calibration file later)
UPPER_FULL_THRESHOLD_MV = 1200.0
LOWER_FULL_THRESHOLD_MV = 1200.0
EMPTY_THRESHOLD_MV = 2200.0

# I2C addresses
ADS1115_I2C_ADDR = 0x48
TCA9555_I2C_ADDR = 0x20

# Valve mapping
# Mappings aligned with cp_test where available; extra names are placeholders.
VALVE_PIN_MAP = {
    "计量单元入口": 0,
    "消解器上阀": 1,
    "消解器下阀": 2,
    "消解器阀": 3,
    "标一": 4,
    "标二": 5,
    "废液1": 6,
    "待测溶液": 7,
    "试剂A": 8,
    "试剂B": 9,
    "试剂C": 13,
}

# Pump pins (same as cp_test)
PUMP_PUL_PIN = 10
PUMP_DIR_PIN = 11
PUMP_ENA_PIN = 12
PUMP_SUBDIVISION = 800
PUMP_TARGET_RPM = 300

# ADS channels
METER_UPPER_CHANNEL = 0  # P0
METER_LOWER_CHANNEL = 1  # P1
DIGEST_OPTICS_CHANNEL = 2  # P2

# MAX31865 settings
MAX31865_CS_PIN = "D5"

