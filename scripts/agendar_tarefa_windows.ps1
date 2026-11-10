# Registra (ou atualiza) a tarefa do Agendador do Windows que roda o pipeline
# nos dias úteis às 19h, com o usuário atual. Saída em logs\agendador.log.
#
# Uso (PowerShell, na raiz do projeto):
#   powershell -ExecutionPolicy Bypass -File scripts\agendar_tarefa_windows.ps1
# Remover:
#   schtasks /Delete /TN "PipelineETL_Indicadores" /F

$nome = "PipelineETL_Indicadores"
$bat = Join-Path $PSScriptRoot "rodar_pipeline.bat"

schtasks /Create /TN $nome /TR "`"$bat`"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 19:00 /F
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Por padrão o schtasks só inicia tarefas na tomada; em notebook na bateria a execução
# fica na fila ("Queued"). O pipeline leva segundos, então pode rodar na bateria.
# StartWhenAvailable: se o computador estiver desligado às 19h, roda quando ligar.
$configuracoes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Set-ScheduledTask -TaskName $nome -Settings $configuracoes | Out-Null

schtasks /Query /TN $nome /FO LIST
