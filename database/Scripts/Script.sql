(-- Table to store KAMA IoT readings
CREATE TABLE IF NOT EXISTS kama_readings (
	id SERIAL PRIMARY KEY,
	recorded_at TIMESTAMPTZ DEFAULT now(),
	battery INTEGER,
	temperature REAL,
	humidity REAL,
	gas_level REAL,
	ph_level REAL,
	status VARCHAR(20)
);

-- Optional: simple index for queries by recorded_at
CREATE INDEX IF NOT EXISTS idx_kama_readings_recorded_at ON kama_readings(recorded_at);
)
