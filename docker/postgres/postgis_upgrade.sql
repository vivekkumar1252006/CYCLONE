-- OPTIONAL PostGIS upgrade (run after the backend has created its tables):
--   docker compose exec db psql -U cycloneguard -d cycloneguard -f /opt/postgis_upgrade.sql
--
-- Adds generated geometry columns + spatial indexes on top of the portable lat/lon schema,
-- enabling spatial SQL (e.g. ST_DWithin buffers around the track) without changing the app.

ALTER TABLE infrastructure
  ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED;
CREATE INDEX IF NOT EXISTS ix_infrastructure_geom ON infrastructure USING GIST (geom);

ALTER TABLE cyclone_tracks
  ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED;
CREATE INDEX IF NOT EXISTS ix_cyclone_tracks_geom ON cyclone_tracks USING GIST (geom);

ALTER TABLE weather_observations
  ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)) STORED;
CREATE INDEX IF NOT EXISTS ix_weather_geom ON weather_observations USING GIST (geom);

-- Example: assets within 50 km of a cyclone's forecast track
-- SELECT i.name FROM infrastructure i
-- WHERE ST_DWithin(i.geom::geography,
--   (SELECT ST_MakeLine(geom ORDER BY timestamp) FROM cyclone_tracks WHERE cyclone_id = 1)::geography, 50000);
