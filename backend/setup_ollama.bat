@echo off
echo Starting Ollama setup...
where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama not found. Install from https://ollama.com/download/windows
  exit /b 1
)

start "" ollama serve
timeout /t 3 >nul
ollama pull qwen2.5:7b
if errorlevel 1 (
  echo Failed to pull model qwen2.5:7b
  exit /b 1
)
echo Ollama ready with model qwen2.5:7b
