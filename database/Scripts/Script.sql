CREATE TABLE IF NOT EXISTS kama_realtime (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    lid_status VARCHAR(10) CHECK (lid_status IN ('OPEN', 'CLOSED'))
);

CREATE INDEX IF NOT EXISTS idx_kama_realtime_recorded_at 
ON kama_realtime(recorded_at);

DROP TABLE IF EXISTS kama_realtime;

CREATE TABLE IF NOT EXISTS kama_server (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    jenis_makanan VARCHAR(50) DEFAULT 'fruits',
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    status VARCHAR(20),
    expired_days INTEGER,
    lid_status VARCHAR(10) CHECK (lid_status IN ('OPEN', 'CLOSED'))
);

CREATE INDEX IF NOT EXISTS idx_kama_server_recorded_at 
ON kama_server(recorded_at);


