"""Unit tests for the simulated sensor model and message builder (no broker needed)."""
from app.simulator.device import build_message
from app.simulator.sensor_models import AgriSensorModel


def _series(seed, device="dev-001", n=50):
    model = AgriSensorModel(device, seed=seed)
    return [model.read(1_700_000_000 + i) for i in range(n)]


def test_same_seed_is_deterministic():
    assert _series(42) == _series(42)


def test_different_devices_differ():
    assert _series(42, "dev-001") != _series(42, "dev-002")


def test_readings_stay_in_physical_ranges():
    model = AgriSensorModel("dev-003", seed=7)
    for i in range(5000):  # ~1.4 simulated months at time_scale=720
        r = model.read(1_700_000_000 + i * 10)
        assert -40 <= r["temperature_c"] <= 85
        assert 0 <= r["humidity_pct"] <= 100
        assert 0 <= r["soil_moisture_pct"] <= 100


def test_soil_moisture_dries_then_gets_irrigated():
    model = AgriSensorModel("dev-004", seed=1)
    values = [model.read(1_700_000_000 + i * 10)["soil_moisture_pct"] for i in range(5000)]
    jumps = [b - a for a, b in zip(values, values[1:])]
    assert min(jumps) < 0, "soil should dry out"
    assert max(jumps) > 15, "an irrigation event should occur"


def test_message_has_required_fields():
    msg = build_message("dev-001", 5, {"temperature_c": 25.0, "humidity_pct": 60.0, "soil_moisture_pct": 40.0})
    assert set(msg) == {"schema_version", "device_id", "seq", "ts_sent", "ts_mono_ns", "simulated", "readings"}
    assert msg["simulated"] is True and msg["seq"] == 5
