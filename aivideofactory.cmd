@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Ambiente Python ausente. Execute nesta pasta:
    echo   python -m pip install --user uv
    echo   python -m uv sync
    popd
    exit /b 1
)
if "%~1"=="" (
    ".venv\Scripts\python.exe" -m ai_video_factory.cli --help
) else (
    ".venv\Scripts\python.exe" -m ai_video_factory.cli %*
)
set "AVF_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %AVF_EXIT_CODE%
