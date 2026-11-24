-- Ratios pair rates from the SAME date and measurement point. No energy conversion.
CREATE VIEW flow_monthly AS
SELECT Month,PointId,COUNT(*) AS ObservedDays,
       SUM(CASE WHEN Capacity>0 AND Throughput IS NOT NULL THEN 1 ELSE 0 END) AS PairedDays,
       SUM(CASE WHEN Capacity>0 AND Throughput IS NOT NULL THEN Throughput ELSE 0 END) AS ThroughputSum,
       SUM(CASE WHEN Capacity>0 AND Throughput IS NOT NULL THEN Capacity ELSE 0 END) AS CapacitySum,
       SUM(CASE WHEN Throughput IS NOT NULL THEN 1 ELSE 0 END) AS ThroughputDays,
       SUM(CASE WHEN Capacity IS NOT NULL THEN 1 ELSE 0 END) AS CapacityDays,
       COALESCE(SUM(Throughput),0) AS ThroughputAllSum,
       COALESCE(SUM(Capacity),0) AS CapacityAllSum,
       SUM(CASE WHEN Capacity IS NULL THEN 1 ELSE 0 END) AS MissingCapacityDays,
       SUM(CASE WHEN Throughput IS NULL THEN 1 ELSE 0 END) AS MissingThroughputDays,
       SUM(CASE WHEN Capacity>0 AND Throughput>Capacity THEN 1 ELSE 0 END) AS OverCapacityDays,
       SUM(CASE WHEN Throughput<0 THEN 1 ELSE 0 END) AS NegativeThroughputDays
FROM flow_daily GROUP BY Month,PointId;
