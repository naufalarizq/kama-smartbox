TRUNCATE TABLE kama_readings;
TRUNCATE TABLE generate_data;
DROP TABLE IF EXISTS kama_readings;
DROP TABLE IF EXISTS generate_data;

CREATE TABLE IF NOT EXISTS kama_readings (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    jenis_makanan VARCHAR(50) DEFAULT 'fruits',
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    ph_level REAL,
    nh3_level REAL,
    c6h6_level REAL,
    status VARCHAR(20),
    expired_days INTEGER,
    lid_status VARCHAR(10) CHECK (lid_status IN ('OPEN', 'CLOSED'))
);

CREATE INDEX IF NOT EXISTS idx_kama_readings_recorded_at 
ON kama_readings(recorded_at);

ALTER TABLE kama_readings
DROP COLUMN ph_level,
DROP COLUMN nh3_level,
DROP COLUMN c6h6_level;
