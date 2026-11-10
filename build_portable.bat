@echo off
chcp 65001 >nul
title Compilador Portable - Optimizador y Compresor Masivo Pro

echo ==============================================================================
echo        COMPILADOR PORTABLE - OPTIMIZADOR Y COMPRESOR MASIVO PRO
echo ==============================================================================
echo.
echo Verificando entorno de compilación...

:: 1. Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no está instalado o no se encuentra en el PATH del sistema.
    pause
    exit /b 1
)

:: 2. Verificar PyInstaller
pyinstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AVISO] PyInstaller no está instalado. Instalando dependencias de requirements.txt...
    pip install -r requirements.txt
)

:: 3. Verificar o generar app_icon.ico
if not exist "app_icon.ico" (
    echo [INFO] Generando app_icon.ico profesional...
    python generate_icon.py
)

:: 4. Verificar binarios de FFmpeg
if not exist "ffmpeg.exe" (
    echo [AVISO] 'ffmpeg.exe' no encontrado en el directorio actual.
    echo Buscando en el sistema para copiarlo automáticamente...
    powershell -Command "$f = (Get-Command ffmpeg -ErrorAction SilentlyContinue); if ($f) { Copy-Item $f.Source .\ffmpeg.exe; Write-Host 'ffmpeg.exe copiado exitosamente.' } else { Write-Host 'ffmpeg no encontrado en PATH.' }"
)

if not exist "ffprobe.exe" (
    echo [AVISO] 'ffprobe.exe' no encontrado en el directorio actual.
    echo Buscando en el sistema para copiarlo automáticamente...
    powershell -Command "$f = (Get-Command ffprobe -ErrorAction SilentlyContinue); if ($f) { Copy-Item $f.Source .\ffprobe.exe; Write-Host 'ffprobe.exe copiado exitosamente.' } else { Write-Host 'ffprobe no encontrado en PATH.' }"
)

echo.
echo ==============================================================================
echo Iniciando empaquetado con PyInstaller (OneFile Portable)...
echo ==============================================================================
echo.

pyinstaller --noconsole --onefile --add-data "app_icon.ico;." --add-data "ffmpeg.exe;." --add-data "ffprobe.exe;." --icon=app_icon.ico --name "Optimizador_Archivos_Portable" main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ==============================================================================
    echo [ÉXITO] ¡Compilación completada exitosamente!
    echo El ejecutable portable se encuentra en la carpeta: dist\Optimizador_Archivos_Portable.exe
    echo Puedes copiarlo directamente a cualquier memoria USB y funcionará sin dependencias.
    echo ==============================================================================
) else (
    echo.
    echo [ERROR] Ocurrió un error durante la compilación con PyInstaller.
)

echo.
pause
