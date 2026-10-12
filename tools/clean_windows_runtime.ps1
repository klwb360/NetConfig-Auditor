param(
    [Parameter(Mandatory=$true)][string]$PackageDirectory,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = 'Stop'
# This operation is restricted to the disposable hosted Windows CI runner.
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
    throw 'Clean runtime acceptance is permitted only on a disposable GitHub-hosted runner.'
}
$runtimeTemp = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\','/')
$packageRoot = [IO.Path]::GetFullPath($PackageDirectory)
$reportFile = [IO.Path]::GetFullPath($ReportPath)
foreach ($target in @($packageRoot,$reportFile)) {
    if (-not $target.StartsWith($runtimeTemp + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Acceptance inputs and outputs must stay below RUNNER_TEMP.'
    }
}
$record = [ordered]@{
    platform=[Environment]::OSVersion.VersionString
    source_commit=$env:GITHUB_SHA
    runner_cpython_removed=$false
    external_python_commands_absent=$false
    checks=@()
    passed=$false
    limitations='Hosted Windows Server runner; Explorer double-click, Windows 10/11 desktop and ordinary-user acceptance remain separate checks.'
}

function Invoke-FrozenCommand([string]$Executable,[string[]]$Arguments) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$Executable
    $info.UseShellExecute=$false
    $info.CreateNoWindow=$true
    $info.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
    $info.RedirectStandardOutput=$true
    $info.RedirectStandardError=$true
    foreach($argument in $Arguments){[void]$info.ArgumentList.Add($argument)}
    $info.Environment['PATH']="$env:SystemRoot\System32;$env:SystemRoot"
    foreach($key in @('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV')){[void]$info.Environment.Remove($key)}
    $process=[Diagnostics.Process]::new()
    $process.StartInfo=$info
    if(-not $process.Start()){throw 'Frozen command did not start.'}
    $stdout=$process.StandardOutput.ReadToEndAsync()
    $stderr=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(60000)){$process.Kill($true);throw 'Frozen command timed out.'}
    $output=$stdout.GetAwaiter().GetResult()
    $errorText=$stderr.GetAwaiter().GetResult()
    $exitCode=$process.ExitCode
    $process.Dispose()
    if($exitCode -ne 0){throw "Frozen command failed with exit code $exitCode`: $errorText"}
    return $output
}

try {
    $extractRoot=Join-Path $runtimeTemp 'netaudit-clean-runtime'
    New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null
    $executables=@()
    foreach($mode in @('portable','onefile')){
        $archives=@(Get-ChildItem -LiteralPath $packageRoot -Filter "*-$mode.zip")
        if($archives.Count -ne 1){throw "Expected exactly one $mode package."}
        $destination=Join-Path $extractRoot $mode
        Expand-Archive -LiteralPath $archives[0].FullName -DestinationPath $destination
        $found=@(Get-ChildItem -LiteralPath $destination -Recurse -Filter 'NetAudit.exe')
        if($found.Count -ne 1){throw "Expected exactly one executable in $mode package."}
        $executables+=@{mode=$mode;path=$found[0].FullName}
    }
    # Remove only the known CPython installation cache on this disposable image.
    $toolRoot=[IO.Path]::GetFullPath($env:RUNNER_TOOL_CACHE).TrimEnd('\','/')
    if(-not $toolRoot.Equals('C:\hostedtoolcache\windows',[StringComparison]::OrdinalIgnoreCase)){
        throw 'Unexpected hosted tool-cache root; refusing any removal.'
    }
    $pythonRoot=[IO.Path]::GetFullPath((Join-Path $toolRoot 'Python'))
    if(-not $pythonRoot.Equals($toolRoot+'\Python',[StringComparison]::OrdinalIgnoreCase)){
        throw 'Python cache target escaped the explicit installation directory.'
    }
    if(Test-Path -LiteralPath $pythonRoot){
        $item=Get-Item -LiteralPath $pythonRoot
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Python cache is a reparse point.'}
        $ownedInterpreters=@(Get-ChildItem -LiteralPath $pythonRoot -Recurse -Filter 'python.exe')
        if($ownedInterpreters.Count -eq 0){throw 'Python cache has no CPython ownership evidence.'}
        Remove-Item -LiteralPath $pythonRoot -Recurse -Force
        if(Test-Path -LiteralPath $pythonRoot){throw 'External CPython cache still exists.'}
        $record.runner_cpython_removed=$true
    }
    $env:PATH="$env:SystemRoot\System32;$env:SystemRoot"
    if(Get-Command python,python3,py -ErrorAction SilentlyContinue){throw 'External Python remains on the restricted runtime PATH.'}
    $record.external_python_commands_absent=$true
    $inputDirectory=Join-Path $extractRoot '合成配置'
    New-Item -ItemType Directory -Path $inputDirectory | Out-Null
    for($number=1;$number -le 50;$number++){
        [IO.File]::WriteAllText((Join-Path $inputDirectory "$number.cfg"),"hostname Clean$number`nip http server`n",[Text.UTF8Encoding]::new($false))
    }
    $utf16=[Text.UnicodeEncoding]::new($false,$true,$true)
    [IO.File]::WriteAllBytes((Join-Path $inputDirectory '49.cfg'),($utf16.GetPreamble()+$utf16.GetBytes("hostname Clean49`nip http server`n")))
    $gbText=[Text.Encoding]::ASCII.GetBytes("hostname Clean50`n! ")+[byte[]](0xD6,0xD0,0xCE,0xC4)+[Text.Encoding]::ASCII.GetBytes("`nip http server`n")
    [IO.File]::WriteAllBytes((Join-Path $inputDirectory '50.cfg'),$gbText)
    foreach($executable in $executables){
        $version=Invoke-FrozenCommand $executable.path @('--version')
        if($version.Trim() -ne 'NetAudit 1.1.0'){throw 'Unexpected frozen version.'}
        $record.checks+=@{mode=$executable.mode;check='version_without_external_python';status='passed'}
        $reportsDirectory=Join-Path $extractRoot ($executable.mode+'-reports')
        $null=Invoke-FrozenCommand $executable.path @('audit-batch',$inputDirectory,'--vendor','cisco','--out-dir',$reportsDirectory)
        $batch=Get-Content -LiteralPath (Join-Path $reportsDirectory 'batch.json') -Raw | ConvertFrom-Json
        if($batch.summary.total -ne 50 -or $batch.summary.succeeded -ne 50 -or $batch.exit_code -ne 0){throw 'Frozen 50-file batch failed.'}
        if(-not (Test-Path -LiteralPath (Join-Path $reportsDirectory 'batch.html'))){throw 'Frozen HTML summary is absent.'}
        foreach($device in $batch.devices){
            if($device.source.path -notmatch '^\d+\.cfg$' -or $device.source.sha256 -notmatch '^[a-f0-9]{64}$'){throw 'Frozen batch source trace is incomplete.'}
        }
        if(($batch.devices | Where-Object {$_.source.path -eq '49.cfg'}).source.encoding -ne 'utf-16-le'){
            throw 'Frozen UTF-16 BOM decoding failed.'
        }
        if(($batch.devices | Where-Object {$_.source.path -eq '50.cfg'}).source.encoding -ne 'gb18030'){
            throw 'Frozen GB18030 codec decoding failed.'
        }
        $record.checks+=@{mode=$executable.mode;check='50_file_batch_json_html_and_source_trace';status='passed'}
        $record.checks+=@{mode=$executable.mode;check='utf16_bom_and_gb18030_without_external_python';status='passed'}
    }
    $record.passed=$true
} catch {
    $record['error']=$_.Exception.Message
    throw
} finally {
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding utf8
}
