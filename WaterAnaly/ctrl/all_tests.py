"""Single entry file for independent hardware/module tests."""

from hardware import create_hardware_context
from recipe import run_nh3n_recipe
from primitives import sleep_ms
from operations import heat_and_hold, read_digest_value
from config import DIGEST_TEMP_C

# No CLI args by design. Change this in code directly.
# options: "valves", "pump", "meter", "temp", "digest", "full"
RUN_TARGET = "full"


def test_valves():
    ctx = create_hardware_context()
    print("=== test_valves ===")
    ctx.valve.close_all()
    for name in ctx.valve.valve_pin_map:
        print(f"Open valve: {name}")
        ctx.valve.close_all()
        ctx.valve.open(name)
        sleep_ms(1000)
    ctx.valve.close_all()
    ctx.shutdown()


def test_pump():
    ctx = create_hardware_context()
    print("=== test_pump ===")
    print("Forward 3s")
    ctx.pump.set_direction("FORWARD")
    ctx.pump.enable()
    ctx.pump.run_for(3000)
    ctx.pump.disable()
    sleep_ms(1000)
    print("Reverse 3s")
    ctx.pump.set_direction("REVERSE")
    ctx.pump.enable()
    ctx.pump.run_for(3000)
    ctx.pump.disable()
    ctx.shutdown()


def test_meter_optics():
    ctx = create_hardware_context()
    print("=== test_meter_optics ===")
    for _ in range(10):
        upper = ctx.meter_optics.read_upper_transmittance()
        lower = ctx.meter_optics.read_lower_transmittance()
        print(f"upper={upper:.2f}mV, lower={lower:.2f}mV")
        sleep_ms(500)
    ctx.shutdown()


def test_temp_control():
    ctx = create_hardware_context()
    print("=== test_temp_control ===")
    for _ in range(5):
        t = ctx.temp_ctrl.read_temperature()
        print(f"temperature={t:.2f}C")
        sleep_ms(1000)
    print("heat_and_hold demo: 5s")
    heat_and_hold(ctx.temp_ctrl, DIGEST_TEMP_C, 5000)
    ctx.shutdown()


def test_digest_optics():
    ctx = create_hardware_context()
    print("=== test_digest_optics ===")
    value = read_digest_value(ctx.digest_optics, 1000)
    print(f"digest_value={value:.2f}mV")
    ctx.shutdown()


def test_full_recipe():
    print("=== test_full_recipe ===")
    result = run_nh3n_recipe(std2_concentration=1.0)
    print(result)


if __name__ == "__main__":
    if RUN_TARGET == "valves":
        test_valves()
    elif RUN_TARGET == "pump":
        test_pump()
    elif RUN_TARGET == "meter":
        test_meter_optics()
    elif RUN_TARGET == "temp":
        test_temp_control()
    elif RUN_TARGET == "digest":
        test_digest_optics()
    else:
        test_full_recipe()

