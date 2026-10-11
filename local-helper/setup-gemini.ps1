param(
    [switch]$ResetCredentials,
    [string]$WorkingDirectory
)
$ErrorActionPreference = 'Stop'

function Convert-SecureStringToPlainText {
    param([System.Security.SecureString]$Value)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
function Write-JsonNoBom {
    param([Parameter(Mandatory = $true)][object]$Value, [Parameter(Mandatory = $true)][string]$Path)
    $json = $Value | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
    throw 'OpenCodeが見つかりません。OpenCodeをインストールし、opencodeコマンドが使える状態にしてから実行してください。'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Pythonが見つかりません。Pythonをインストールし、pythonコマンドが使える状態にしてから実行してください。'
}
if (-not (Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue)) {
    throw 'Windowsタスクスケジューラを利用できません。Windows PowerShellから実行してください。'
}

$helperPort = 8765
if ($env:HELPER_PORT) { $helperPort = [int]$env:HELPER_PORT }
$helperListener = Get-NetTCPConnection -LocalPort $helperPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($helperListener) {
    throw "Helperのポート $helperPort が使用中です。AI画面でサーバーを停止するか、稼働中Helperのウィンドウで Ctrl+C を押してから再実行してください。"
}
$opencodePort = 4096
if ($env:OPENCODE_API) {
    try { $apiUri = [Uri]$env:OPENCODE_API; if (-not $apiUri.IsDefaultPort) { $opencodePort = $apiUri.Port } }
    catch { throw 'OPENCODE_API のURLを解釈できません。値を確認してください。' }
}
$opencodeListener = Get-NetTCPConnection -LocalPort $opencodePort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($opencodeListener) {
    throw "OpenCodeのポート $opencodePort が使用中です。稼働中のOpenCodeサーバーをAI画面の［設定・サーバー］から停止し、既存のOpenCode TUIも終了してから再実行してください。作業中の変更を先に保存してください。"
}

$configDir = Join-Path $env:USERPROFILE '.config\opencode'
$configPath = Join-Path $configDir 'opencode.json'
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
if (Test-Path -LiteralPath $configPath) {
    try { $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw "既存のOpenCode設定をJSONとして読めませんでした。ファイルは変更していません: $configPath" }
    $backupPath = "$configPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item -LiteralPath $configPath -Destination $backupPath
    Write-Host "既存設定のバックアップ: $backupPath"
}
else { $config = [pscustomobject]@{} }
if (-not ($config.PSObject.Properties.Name -contains '$schema')) {
    $config | Add-Member -NotePropertyName '$schema' -NotePropertyValue 'https://opencode.ai/config.json'
}
if (-not ($config.PSObject.Properties.Name -contains 'provider') -or $null -eq $config.provider) {
    $config | Add-Member -NotePropertyName 'provider' -NotePropertyValue ([pscustomobject]@{}) -Force
}
$geminiProvider = [pscustomobject]@{
    npm = '@ai-sdk/openai-compatible'
    name = 'Google Gemini API (free tier)'
    options = [pscustomobject]@{
        baseURL = 'https://generativelanguage.googleapis.com/v1beta/openai/'
        apiKey = '{env:GEMINI_API_KEY}'
    }
    models = [pscustomobject]@{
        'gemini-3.8-flash' = [pscustomobject]@{ name = 'Gemini 3.8 Flash' }
    }
}
$config.provider | Add-Member -NotePropertyName 'google-gemini' -NotePropertyValue $geminiProvider -Force
Write-JsonNoBom -Value $config -Path $configPath

$stateDir = Join-Path $env:APPDATA 'DASSAI-AI'
$statePath = Join-Path $stateDir 'helper-secrets.json'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$savedState = $null
$secureApiKey = $null
$securePassword = $null
$needNewCredentials = $ResetCredentials -or (-not (Test-Path -LiteralPath $statePath))

if (-not $needNewCredentials) {
    try {
        $savedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $secureApiKey = ConvertTo-SecureString -String ([string]$savedState.GeminiApiKey) -ErrorAction Stop
        $securePassword = ConvertTo-SecureString -String ([string]$savedState.LoginPassword) -ErrorAction Stop
        if (-not $savedState.LoginId) { throw 'ログインIDがありません。' }
        Write-Host '既存のDPAPI暗号化設定を再利用します。APIキーやパスワードの再入力は不要です。'
    }
    catch {
        throw '保存済み設定をこのWindowsユーザーで復号できません。設定を残したままです。必要なら -ResetCredentials を付けて再設定してください。'
    }
}
else {
    if (Test-Path -LiteralPath $statePath) {
        Copy-Item -LiteralPath $statePath -Destination ($statePath + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    $defaultLoginId = if ($env:DASSAI_LOGIN_ID) { $env:DASSAI_LOGIN_ID } else { 'dassai' }
    $loginId = Read-Host "獺祭AIのログインID [$defaultLoginId]（同じIDを使うなら空欄）"
    if ([string]::IsNullOrWhiteSpace($loginId)) { $loginId = $defaultLoginId }
    $securePassword = Read-Host '獺祭AIのログインパスワード（入力は表示されません）' -AsSecureString
    if ($securePassword.Length -eq 0) { throw 'ログインパスワードが空です。処理を中止しました。' }
    $secureApiKey = Read-Host 'Google AI StudioのAPIキー（入力は表示されません）' -AsSecureString
    if ($secureApiKey.Length -eq 0) { throw 'APIキーが空です。Google AI Studioのキーを入力してください。' }

    $defaultWorkDir = Join-Path $env:USERPROFILE 'yyrpinfo'
    if (-not (Test-Path -LiteralPath $defaultWorkDir)) { $defaultWorkDir = $env:USERPROFILE }
    if ($WorkingDirectory) { $workDir = $WorkingDirectory }
    else {
        $workDirInput = Read-Host "OpenCodeの既定作業フォルダー [$defaultWorkDir]"
        $workDir = if ([string]::IsNullOrWhiteSpace($workDirInput)) { $defaultWorkDir } else { $workDirInput }
    }
    if (-not (Test-Path -LiteralPath $workDir -PathType Container)) { throw "作業フォルダーが見つかりません: $workDir" }
    $workDir = (Resolve-Path -LiteralPath $workDir).Path

    Write-Host ''
    Write-Host 'OpenCode TUIでも無料枠自動切替を使う場合だけ、APIキーをWindowsユーザー環境変数に保存します。'
    $enableTui = (Read-Host 'OpenCode TUI用の追加設定も有効にしますか？ [y/N]') -match '^(y|yes)$'
    $encryptedApiKey = ConvertFrom-SecureString -SecureString $secureApiKey
    $encryptedPassword = ConvertFrom-SecureString -SecureString $securePassword
    $savedState = [pscustomobject]@{
        Version = 1
        LoginId = $loginId
        LoginPassword = $encryptedPassword
        GeminiApiKey = $encryptedApiKey
        WorkingDirectory = $workDir
        EnableTuiFallback = [bool]$enableTui
    }
    Write-JsonNoBom -Value $savedState -Path $statePath
    Write-Host 'キーとパスワードをWindowsユーザー専用のDPAPIで暗号化して保存しました。平文では保存していません。'
}

if ($WorkingDirectory) {
    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) { throw "作業フォルダーが見つかりません: $WorkingDirectory" }
    $savedState.WorkingDirectory = (Resolve-Path -LiteralPath $WorkingDirectory).Path
    Write-JsonNoBom -Value $savedState -Path $statePath
}
if (-not (Test-Path -LiteralPath ([string]$savedState.WorkingDirectory) -PathType Container)) {
    throw '保存済みの作業フォルダーがありません。-WorkingDirectory "C:\path\to\project" を指定してください。'
}

if ([bool]$savedState.EnableTuiFallback) {
    $plainApiKey = Convert-SecureStringToPlainText $secureApiKey
    [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', $plainApiKey, 'User')
    [Environment]::SetEnvironmentVariable('GOOGLE_GENERATIVE_AI_API_KEY', $plainApiKey, 'User')
    $pluginDir = Join-Path $configDir 'plugins'
    New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null
    $pluginSource = Join-Path $PSScriptRoot 'dassai-free-fallback.js'
    if (-not (Test-Path -LiteralPath $pluginSource)) { throw "自動切替プラグインが見つかりません: $pluginSource" }
    Copy-Item -LiteralPath $pluginSource -Destination (Join-Path $pluginDir 'dassai-free-fallback.js') -Force
}

$launcherPath = Join-Path $PSScriptRoot 'start-helper.ps1'
if (-not (Test-Path -LiteralPath $launcherPath)) { throw "自動起動スクリプトが見つかりません: $launcherPath" }
$taskName = 'DASSAI AI Helper'
$userIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$powerShellExe = Join-Path $PSHOME 'powershell.exe'
$arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $launcherPath + '"'
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userIdentity
$principal = New-ScheduledTaskPrincipal -UserId $userIdentity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Starts the local DASSAI AI helper and OpenCode after this Windows user signs in.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$helperPort/status" -TimeoutSec 2
        if ($status.helper) { $ready = $true; break }
    }
    catch { Start-Sleep -Seconds 1 }
}
if ($ready) {
    Write-Host '設定完了: Helperを起動し、Windowsサインイン時の自動起動タスクも登録しました。'
    Write-Host "既定の作業フォルダー: $($savedState.WorkingDirectory)"
    Write-Host 'OpenCodeもバックグラウンドで自動起動します。次回以降はPCにサインインするだけです。'
}
else {
    Write-Warning '自動起動タスクは登録しましたが、Helperの起動確認ができません。ログを確認してください。'
}
Write-Host "Helperログ: $(Join-Path $env:LOCALAPPDATA 'DASSAI-AI\helper.log')"
Write-Host "OpenCodeログ: $(Join-Path $PSScriptRoot 'opencode_serve.log')"
Write-Host 'AI画面のログインは引き続き必要です（セキュリティ保護のため）。'
