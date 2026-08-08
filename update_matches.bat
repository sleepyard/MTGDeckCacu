@echo off
rem 更新 MTGA 对局记录：扫描新比赛 + 胜率汇总 + 对手识别/复盘/风险点（最新一场）
rem 用法：双击运行，或 update_matches.bat 牌表名（给新记录挂牌表标签）
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if "%~1"=="" (
    python tools\mtga_log_tool.py scan --prev
) else (
    python tools\mtga_log_tool.py scan --prev --deck "%~1"
)

echo.
echo ===== 胜率汇总 =====
python tools\mtga_log_tool.py report

echo.
echo ===== 最新一场：对手已见牌 / 复盘 / 风险点 =====
python tools\mtga_log_tool.py opponent
python tools\mtga_log_tool.py replay
python tools\mtga_log_tool.py risk --all

echo.
pause
