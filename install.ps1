# -*- coding: utf-8 -*-
# wxsummary Windows 一键安装脚本（PowerShell 入口）
# 负责预检环境，然后调用 setup.py 完成后续安装流程。

$ErrorActionPreference = "Stop"

# 1. 固定 UTF-8 输出，避免中文乱码
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

Write-Host "========================================================"
Write-Host "  wxsummary · 微信群聊日报一键安装 (Windows)"
Write-Host "========================================================"
Write-Host ""

# 2. 检查 PowerShell 版本（chatlog-keeper 的 Windows 提取依赖 >= 5.1）
if ($PSVersionTable.PSVersion.Major -lt 5) {
    Write-Host "❌ PowerShell 版本过低，需要 >= 5.1（Windows 10/11 自带即可满足）。" -ForegroundColor Red
    exit 1
}

# 3. 检测 Python：优先 python，其次 py -3
function Get-PythonCommand {
    $cmd = $null
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            $v = (& python --version 2>&1)
            if ($LASTEXITCODE -eq 0) { return @("python", $v.ToString()) }
        } catch {}
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $v = (& py -3 --version 2>&1)
            if ($LASTEXITCODE -eq 0) { return @("py", "-3", $v.ToString()) }
        } catch {}
    }
    return $null
}

$py = Get-PythonCommand
if ($null -eq $py) {
    Write-Host "❌ 未检测到 Python。请先安装 Python 3.9+：" -ForegroundColor Red
    Write-Host "   1. 到 https://www.python.org/downloads/ 下载并安装（勾选 Add python.exe to PATH）"
    Write-Host "   2. 或执行：winget install Python.Python.3.11"
    exit 1
}

$pyExe = $py[0]
$pyArgs = @()
if ($py[0] -eq "py") { $pyArgs += "-3" }
Write-Host "✅ 检测到 Python：$($py[-1])"

# 4. 检查 git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 未检测到 git。请先安装：" -ForegroundColor Red
    Write-Host "   1. 到 https://git-scm.com/download/win 下载安装"
    Write-Host "   2. 或执行：winget install Git.Git"
    exit 1
}
Write-Host "✅ 检测到 git"

Write-Host ""
Write-Host "Windows 使用说明：" -ForegroundColor Yellow
Write-Host "  · 本脚本面向 PC 版微信 Weixin 4.x（Weixin.exe / Weixin.dll）。"
Write-Host "  · 请以「普通用户」身份运行，不要使用「以管理员身份运行」。"
Write-Host "  · 后续提示「退出微信」时：在任务栏右下角托盘图标上右键 →「退出微信」。"
Write-Host "  · 密钥提取时会启动隔离的官方客户端，若弹出登录窗口请用手机扫码。"
Write-Host ""

# 5. 调用 setup.py（后续 probe → 提密钥 → 首次导出 → API Key → 生成 .env 均复用）
$setupPy = Join-Path $PSScriptRoot "setup.py"
Write-Host "启动安装流程..." -ForegroundColor Yellow
Write-Host ""

& $pyExe @pyArgs $setupPy
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-Host ""
    Write-Host "✅ 安装完成。" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "❌ 安装未完成（退出码 $code），请根据上方提示处理。" -ForegroundColor Red
}
exit $code