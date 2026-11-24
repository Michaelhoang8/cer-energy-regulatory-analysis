PRAGMA foreign_keys=ON;
CREATE TABLE flow_raw (
  SourceFile TEXT NOT NULL,SourceRow INTEGER NOT NULL,RowHash TEXT NOT NULL,
  PointId TEXT NOT NULL,Date TEXT NOT NULL,Month TEXT NOT NULL,
  Capacity REAL,Throughput REAL,EnergyThroughputGJ REAL,
  PRIMARY KEY(SourceFile,SourceRow)
);
CREATE TABLE incident_audit (
  IncidentId TEXT PRIMARY KEY,SourceRow INTEGER NOT NULL,Year INTEGER NOT NULL,
  Province TEXT NOT NULL,SpatialStatus TEXT NOT NULL,NormalizedRecord TEXT NOT NULL
);
