CREATE TABLE IF NOT EXISTS kama_realtime (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    status VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS idx_kama_realtime_recorded_at 
ON kama_realtime(recorded_at);

DROP TABLE IF EXISTS kama_server;


CREATE TABLE IF NOT EXISTS kama_server (
    id SERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ DEFAULT now(),
    jenis_makanan VARCHAR(50) DEFAULT 'fruits',
    battery INTEGER,
    temperature REAL,
    humidity REAL,
    gas_level REAL,
    status VARCHAR(20),
    predicted_spoil REAL
);

CREATE INDEX IF NOT EXISTS idx_kama_server_recorded_at 
ON kama_server(recorded_at);

ALTER TABLE kama_server
ADD recommendation_text VARCHAR(255);

ALTER TABLE kama_server
ALTER COLUMN recommendation_text TYPE TEXT;

ALTER TABLE kama_realtime ADD COLUMN device_id VARCHAR(64);
ALTER TABLE kama_server   ADD COLUMN device_id VARCHAR(64);



