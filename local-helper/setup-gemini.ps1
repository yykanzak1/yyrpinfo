$ErrorActionPreference = 'Stop'

function Convert-SecureStringToPlainText {
    param([System.Security.SecureString]$Value)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) {
    throw 'OpenCodeが見つかりません。OpenCodeをインストールし、opencodeコマンドが使える状態にしてから再実行してください。'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Pythonが見つかりません。Pythonをインストールし、pythonコマンドが使える状態にしてから再実行してください。'
}

$helperPort = 8765
if ($env:HELPER_PORT) { $helperPort = [int]$env:HELPER_PORT }
$listener = Get-NetTCPConnection -LocalPort $helperPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "ポート $helperPort を既存のヘルパーが使用中です。既存のヘルパーを起動したPowerShellウィンドウで Ctrl+C を押して停止し、このスクリプトを再実行してください。"
}

$configDir = Join-Path $env:USERPROFILE '.config\opencode'
$configPath = Join-Path $configDir 'opencode.json'
New-Item -ItemType Directory -Path $configDir -Force | Out-Null

if (Test-Path $configPath) {
    try {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "既存のOpenCode設定を通常のJSONとして読み込めませんでした。ファイルは変更していません。手動設定について local-helper/RUN_GUIDE_ja.md を確認してください。設定ファイル: $configPath"
    }
    $backupPath = "$configPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item -LiteralPath $configPath -Destination $backupPath
    Write-Host "既存設定のバックアップ: $backupPath"
}
else {
    $config = [pscustomobject]@{}
}

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
$config | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $configPath -Encoding UTF8

$env:DASSAI_FREE_MODELS = 'google-gemini/gemini-3.8-flash'
if (-not $env:DASSAI_LOGIN_ID) {
    $loginId = Read-Host '獺祭AIのログインID（空欄ならdassai）'
    if ([string]::IsNullOrWhiteSpace($loginId)) { $loginId = 'dassai' }
    $env:DASSAI_LOGIN_ID = $loginId
}
if (-not $env:DASSAI_LOGIN_PASSWORD) {
    Write-Host '獺祭AI画面にログインするための任意のパスワードを入力してください。入力内容は保存されません。'
    $securePassword = Read-Host '獺祭AI login password' -AsSecureString
    $env:DASSAI_LOGIN_PASSWORD = Convert-SecureStringToPlainText $securePassword
    if ([string]::IsNullOrWhiteSpace($env:DASSAI_LOGIN_PASSWORD)) { throw 'ログインパスワードが空です。処理を中止しました。' }
}

Write-Host 'Google AI Studioで作成したGemini APIキーを入力してください。入力内容は画面に表示されず、このPowerShellの実行中だけ使用します。'
$secureKey = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = Convert-SecureStringToPlainText $secureKey
if ([string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)) { throw 'APIキーが空です。処理を中止しました。' }

Write-Host ''
Write-Host 'Gemini設定を保存しました。APIキーは設定ファイルに保存していません。'
Write-Host "無料枠の自動切替対象: $env:DASSAI_FREE_MODELS"
Write-Host 'ローカルヘルパーを起動します。このウィンドウは開いたままにしてください。'
Push-Location $PSScriptRoot
try {
    & python (Join-Path $PSScriptRoot 'server.py')
}
finally {
    Pop-Location
    Remove-Item Env:\GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_FREE_MODELS -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_LOGIN_PASSWORD -ErrorAction SilentlyContinue
}
