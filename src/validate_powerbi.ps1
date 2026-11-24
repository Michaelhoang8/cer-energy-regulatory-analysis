#requires -Version 7.0
param([Parameter(Mandatory=$true)][int]$Port)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$biProcess = Get-Process PBIDesktop | Select-Object -First 1
if (-not $biProcess) { throw 'Open CER_Energy_Analysis in Power BI Desktop and refresh first.' }
$biBin = Split-Path $biProcess.Path
$clientDir = Join-Path $env:TEMP 'cer-energy-powerbi-client'
New-Item -ItemType Directory -Path $clientDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $biBin 'Microsoft.PowerBI.AdomdClient.dll') -Destination $clientDir -Force
Add-Type -Path (Join-Path $clientDir 'Microsoft.PowerBI.AdomdClient.dll')
$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$connection.Open()

function Read-Dax([string]$Query) {
    $command = $connection.CreateCommand()
    $command.CommandText = $Query
    $command.CommandTimeout = 180
    $reader = $command.ExecuteReader()
    $rows = [System.Collections.Generic.List[object]]::new()
    try {
        while ($reader.Read()) {
            $row = [ordered]@{}
            for ($i=0; $i -lt $reader.FieldCount; $i++) {
                $value = $reader.GetValue($i)
                $row[$reader.GetName($i).Trim('[',']')] = $(if ($value -is [DBNull]) { $null } else { $value })
            }
            $rows.Add([pscustomobject]$row)
        }
    } finally { $reader.Close(); $command.Dispose() }
    return $rows.ToArray()
}

try {
    $flow = @(Read-Dax @'
EVALUATE
SELECTCOLUMNS(
 SUMMARIZECOLUMNS(DimMonth[Year], DimPoint[PointId],
  "ObservedDays", SUM(FactFlow[ObservedDays]), "ExpectedDays", SUM(FactFlow[ExpectedDays]),
  "PairedDays", SUM(FactFlow[PairedDays]), "ThroughputSum", SUM(FactFlow[ThroughputSum]),
  "CapacitySum", SUM(FactFlow[CapacitySum]), "ThroughputDays", SUM(FactFlow[ThroughputDays]),
  "CapacityDays", SUM(FactFlow[CapacityDays]), "ThroughputAllSum", SUM(FactFlow[ThroughputAllSum]),
  "CapacityAllSum", SUM(FactFlow[CapacityAllSum]), "MissingCapacityDays", SUM(FactFlow[MissingCapacityDays]),
  "MissingThroughputDays", SUM(FactFlow[MissingThroughputDays]), "OverCapacityDays", SUM(FactFlow[OverCapacityDays]),
  "NegativeThroughputDays", SUM(FactFlow[NegativeThroughputDays]),
  "MeanThroughput", [Mean throughput], "MeanCapacity", [Mean capacity],
  "Utilization", [Utilization], "Coverage", [Reporting coverage]
 ),
 "Year", DimMonth[Year], "PointId", DimPoint[PointId],
 "ObservedDays", [ObservedDays], "ExpectedDays", [ExpectedDays], "PairedDays", [PairedDays],
 "ThroughputSum", [ThroughputSum], "CapacitySum", [CapacitySum], "ThroughputDays", [ThroughputDays],
 "CapacityDays", [CapacityDays], "ThroughputAllSum", [ThroughputAllSum], "CapacityAllSum", [CapacityAllSum],
 "MissingCapacityDays", [MissingCapacityDays], "MissingThroughputDays", [MissingThroughputDays],
 "OverCapacityDays", [OverCapacityDays], "NegativeThroughputDays", [NegativeThroughputDays],
 "MeanThroughput", [MeanThroughput], "MeanCapacity", [MeanCapacity], "Utilization", [Utilization], "Coverage", [Coverage]
)
ORDER BY [Year], [PointId]
'@)
    $incidents = @(Read-Dax @'
EVALUATE
SELECTCOLUMNS(
 FILTER(SUMMARIZECOLUMNS(DimMonth[Year], DimProvince[Province],
  "Records", [Incidents], "Open", [Open incidents], "Significant", [Significant incidents], "Located", [Located incidents]
 ), NOT(ISBLANK([Records]))),
 "Year", DimMonth[Year], "Province", DimProvince[Province],
 "Records", [Records], "Open", [Open], "Significant", [Significant], "Located", [Located]
)
ORDER BY [Year], [Province]
'@)
    $modelPath = Join-Path $ProjectRoot 'powerbi/native/CER_Energy_Analysis.SemanticModel/model.bim'
    $model = Get-Content -LiteralPath $modelPath -Raw -Encoding utf8 | ConvertFrom-Json
    $names = @($model.model.tables | ForEach-Object { $_.measures } | Where-Object { $_ } | ForEach-Object { $_.name })
    $pairs = @($names | ForEach-Object { '"'+$_.Replace('"','""')+'", ['+$_.Replace(']',']]')+']' })
    $all = @(Read-Dax ('EVALUATE ROW('+($pairs -join ',')+')'))
    $payload = [ordered]@{
        generated_at_utc = [DateTime]::UtcNow.ToString('o')
        model = 'CER_Energy_Analysis'
        flow = $flow
        incidents = $incidents
        allMeasures = $all
        measureCount = $names.Count
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $ProjectRoot 'reports/powerbi_native_results.json') -Encoding utf8
    Write-Output "Executed native DAX for $($flow.Count) point/year groups, $($incidents.Count) province/year groups and $($names.Count) measures."
} finally { $connection.Close(); $connection.Dispose() }
