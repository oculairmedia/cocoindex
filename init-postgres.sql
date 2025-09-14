-- Initialize PostgreSQL database for CocoIndex
-- This script runs automatically when the container starts

-- Create the main database (already created by POSTGRES_DB env var)
-- CREATE DATABASE cocoindex;

-- Create user (already created by POSTGRES_USER env var)
-- CREATE USER cocoindex WITH PASSWORD 'cocoindex';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE cocoindex TO cocoindex;

-- Connect to the cocoindex database
\c cocoindex;

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO cocoindex;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cocoindex;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cocoindex;

-- Enable vector extension if available (for future use)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Create a simple test table to verify connection
CREATE TABLE IF NOT EXISTS cocoindex_test (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO cocoindex_test (name) VALUES ('CocoIndex PostgreSQL Ready');

-- Display success message
SELECT 'CocoIndex PostgreSQL database initialized successfully!' as status;
