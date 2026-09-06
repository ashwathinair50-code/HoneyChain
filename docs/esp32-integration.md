# Future ESP32 integration
Load cell → HX711 → ESP32. DHT22 → ESP32. ESP32 → HTTPS POST /api/telemetry.
Use board-specific pin assignments and safe electrical levels from the chosen
components' documentation; calibrate the load-cell tare and scale before deployment.

Provision one device credential and register PHYSICAL_DEVICE against its one hive.
Store device credentials in protected device configuration, never frontend code.
Canonical payload:
```json
{"device_id":"DEV-MH-88492-01","hive_id":"HIVE-MH-88492-01","beekeeper_id":"NHM-MH-88492","timestamp":"2026-09-05T14:10:00+05:30","weight_kg":38.2,"temperature_c":35.1,"humidity_percent":58.2}
```
Send X-Device-Key over TLS. Synchronize a real-time clock; retain explicit timezone.
Persist measurements locally during outages and submit chronologically on reconnect.
Delete each local measurement only after acknowledgement. Retry the identical
device/timestamp/value tuple; changed values at the same timestamp return conflict.
The backend records measurement and receipt times separately. Configure buffer
retention consistently with the API's default 30-day accepted history.
No frontend changes are required. Python replay verifies API integration, not
physical calibration, biological validity, sensor durability or rural connectivity.
