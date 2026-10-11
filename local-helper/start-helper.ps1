$ErrorActionPreference = 'Stop'

function Convert-SecureStringToPlainText {
    param([System.Security.SecureString]$Value)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$statePath = Join-Path $env:APPDATA 'DASSAI-AI\helper-secrets.json'
$logDir = Join-Path $env:LOCALAPPDATA 'DASSAI-AI'
$logPath = Join-Path $logDir 'helper.log'
$errorLogPath = Join-Path $logDir 'helper-error.log'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

try {
    if (-not (Test-Path -LiteralPath $statePath)) {
        throw "暗号化設定が見つかりません: $statePath"
    }
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $secureApiKey = ConvertTo-SecureString -String ([string]$state.GeminiApiKey)
    $securePassword = ConvertTo-SecureString -String ([string]$state.LoginPassword)
    if (-not $state.LoginId -or -not $secureApiKey -or -not $securePassword) {
        throw '暗号化設定に必要な値がありません。setup-gemini.ps1 -ResetCredentials を実行してください。'
    }

    $env:DASSAI_LOGIN_ID = [string]$state.LoginId
    $env:DASSAI_LOGIN_PASSWORD = Convert-SecureStringToPlainText $securePassword
    $env:GEMINI_API_KEY = Convert-SecureStringToPlainText $secureApiKey
    $env:GOOGLE_GENERATIVE_AI_API_KEY = $env:GEMINI_API_KEY
    $env:DASSAI_FREE_MODELS = 'google-gemini/gemini-3.8-flash'
    $env:DASSAI_DISABLE_OPENCODE_FALLBACK = '1'
    $env:DASSAI_AUTO_START_OPENCODE = '1'
    if ($state.WorkingDirectory -and (Test-Path -LiteralPath ([string]$state.WorkingDirectory))) {
        $env:OPENCODE_CWD = [string]$state.WorkingDirectory
    }
    else {
        $env:OPENCODE_CWD = $env:USERPROFILE
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'Pythonが見つかりません。PythonをPATHに追加してください。' }
    $pythonPath = $python.Source
    if (-not $pythonPath) { $pythonPath = $python.Path }
    $serverPath = Join-Path $PSScriptRoot 'server.py'
    if (-not (Test-Path -LiteralPath $serverPath)) { throw "server.py が見つかりません: $serverPath" }

    if ((Test-Path -LiteralPath $logPath) -and (Get-Item -LiteralPath $logPath).Length -gt 5242880) {
        Move-Item -LiteralPath $logPath -Destination ($logPath + '.1') -Force
    }
    if ((Test-Path -LiteralPath $errorLogPath) -and (Get-Item -LiteralPath $errorLogPath).Length -gt 5242880) {
        Move-Item -LiteralPath $errorLogPath -Destination ($errorLogPath + '.1') -Force
    }
    Push-Location $PSScriptRoot
    try {
        $process = Start-Process -FilePath $pythonPath -ArgumentList ('"{0}"' -f $serverPath) -WorkingDirectory $PSScriptRoot -NoNewWindow -RedirectStandardOutput $logPath -RedirectStandardError $errorLogPath -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "server.py が終了コード $($process.ExitCode) で終了しました。ログ: $logPath" }
    }
    finally { Pop-Location }
}
catch {
    ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $_.Exception.Message) | Add-Content -LiteralPath $logPath -Encoding UTF8
    throw
}
finally {
    Remove-Item Env:\GEMINI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\GOOGLE_GENERATIVE_AI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_LOGIN_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_FREE_MODELS -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_DISABLE_OPENCODE_FALLBACK -ErrorAction SilentlyContinue
    Remove-Item Env:\DASSAI_AUTO_START_OPENCODE -ErrorAction SilentlyContinue
}
