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

ALTER TABLE kama_readings 
ADD COLUMN box_status VARCHAR(10);

ALTER TABLE kama_readings 
ADD COLUMN expired_in_days INTEGER;

-- Table to store generated dummy data (for simulation)
CREATE TABLE IF NOT EXISTS generate_data (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    ph_level REAL,
    status VARCHAR(20),
    box_status VARCHAR(10),
    expired_in_days INTEGER
);

-- Optional: simple index for queries by recorded_at
CREATE INDEX IF NOT EXISTS idx_generate_data_recorded_at 
    ON generate_data(recorded_at);


