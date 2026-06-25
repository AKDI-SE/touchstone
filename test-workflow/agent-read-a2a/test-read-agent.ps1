# agent-read-a2a 端到端冒烟测试脚本（PowerShell）
# 用法：
#   1. 先打包：  ./mvnw -f examples/travel/pom.xml -pl agent-read-a2a package -DskipTests -q
#   2. 运行：    pwsh examples/travel/agent-read-a2a/test-read-agent.ps1
#
# 脚本会：
#   - 以 stub profile 后台启动 agent-read-a2a（端口 13005，不发真 HTTP，不调真 LLM 之外的网络）
#     注：stub 模式下 read_url 的 HTTP 抓取走 fixture，但 ReAct 推理仍需要一个 LLM。
#         若没有真 LLM，可只跑下面的 /a2a 健康检查 + AgentCard 校验（不依赖 LLM）。
#   - 拉 /.well-known/agent-card.json 校验 AgentCard
#   - 发 3 条 SendMessage：pricing / spa_blocked / cloudflare_403
#   - 打印每条响应，校验关键字段（doc_type）
#   - 最后关闭服务

param(
    [string]$BaseUrl = "http://localhost:13005",
    [int]$Port = 13005,
    [string]$Profile = "stub"
)

$ErrorActionPreference = "Stop"
$Jar = Get-ChildItem "examples\travel\agent-read-a2a\target\agent-read-a2a-*.jar" |
    Where-Object { $_.Name -notlike "*-sources*" -and $_.Name -notlike "*-javadoc*" } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $Jar) {
    Write-Error "未找到 agent-read-a2a jar，请先执行: ./mvnw -f examples/travel/pom.xml -pl agent-read-a2a package -DskipTests"
    exit 1
}

Write-Host "==> 启动 agent-read-a2a ($Profile profile): $($Jar.FullName)"
$proc = Start-Process -FilePath "java" `
    -ArgumentList "-jar", $Jar.FullName, "--spring.profiles.active=$Profile", "--server.port=$Port" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput "read-agent-smoke.out.log" `
    -RedirectStandardError "read-agent-smoke.err.log"

try {
    Write-Host "==> 等待服务就绪 (max 40s)..."
    $ready = $false
    foreach ($i in 1..40) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -UseBasicParsing "$BaseUrl/actuator/health" -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ready = $true; Write-Host "    服务已就绪 ($i s)"; break }
        } catch { }
    }
    if (-not $ready) { Write-Error "服务未能在 40s 内就绪，查看 read-agent-smoke.err.log"; exit 1 }

    Write-Host ""
    Write-Host "==> [1] 校验 AgentCard"
    $card = Invoke-WebRequest -UseBasicParsing "$BaseUrl/.well-known/agent-card.json" -TimeoutSec 5 |
        Select-Object -ExpandProperty Content | ConvertFrom-Json
    Write-Host "    name=$($card.name)  skills=$($card.skills.id -join ',')"
    if ($card.name -ne "read-agent") { throw "AgentCard.name != read-agent" }

    Write-Host ""
    Write-Host "==> [2] 发送 pricing 请求 (火山方舟定价)"
    $pricingBody = Get-Content "examples\travel\agent-read-a2a\a2a-fixtures\read-round1-volcengine.json" -Raw
    $resp = Invoke-WebRequest -UseBasicParsing -Method Post "$BaseUrl/a2a" `
        -ContentType "application/json" -Body $pricingBody -TimeoutSec 60
    Write-Host "    HTTP $($resp.StatusCode)"
    Write-Host "    响应: $($resp.Content.Substring(0, [Math]::Min(400, $resp.Content.Length)))"

    Write-Host ""
    Write-Host "==> [3] 发送 SPA 请求 (应被识别为 spa_blocked)"
    $spaBody = Get-Content "examples\travel\agent-read-a2a\a2a-fixtures\read-round2-spa-blocked.json" -Raw
    $resp2 = Invoke-WebRequest -UseBasicParsing -Method Post "$BaseUrl/a2a" `
        -ContentType "application/json" -Body $spaBody -TimeoutSec 60
    Write-Host "    HTTP $($resp2.StatusCode)"
    Write-Host "    响应: $($resp2.Content.Substring(0, [Math]::Min(400, $resp2.Content.Length)))"

    Write-Host ""
    Write-Host "==> 冒烟测试完成"
}
finally {
    Write-Host "==> 关闭服务 (pid=$($proc.Id))"
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
}
