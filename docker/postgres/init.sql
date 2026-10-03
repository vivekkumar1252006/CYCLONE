-- Runs once when the PostGIS container initialises its data directory.
-- Tables themselves are created by the backend (SQLAlchemy) on startup.
CREATE EXTENSION IF NOT EXISTS postgis;
