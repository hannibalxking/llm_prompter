@echo off
REM Basic build script using PyInstaller for Windows via Poetry - RC Version
REM Strategy: Find correct python.exe via poetry, run pyinstaller as module with explicit python path.

set APP_NAME=PromptBuilder

echo Ensuring we are in the project root...
cd /d "%~dp0.."
set PROJECT_ROOT=%CD%
echo Project root detected as: %PROJECT_ROOT%

echo Cleaning previous builds...
if exist dist ( echo Removing existing dist directory... & rmdir /s /q dist )
if exist build ( echo Removing existing build directory... & rmdir /s /q build )

echo Finding virtual environment path...
REM Use poetry env info to get the venv path
for /f "tokens=*" %%i in ('poetry env info --path 2^>nul') do set VENV_PATH=%%i
if not defined VENV_PATH ( echo ERROR: Could not determine Poetry venv path. Run 'poetry install' first. & exit /b 1 )
if not exist "%VENV_PATH%" ( echo ERROR: Venv path does not exist: %VENV_PATH% & exit /b 1 )
echo Virtual environment path: %VENV_PATH%

REM --- Construct full path to the CORRECT python.exe ---
set PYTHON_EXE_PATH=%VENV_PATH%\Scripts\python.exe
echo Expected Python executable: %PYTHON_EXE_PATH%
if not exist "%PYTHON_EXE_PATH%" (
    echo ERROR: Python executable not found at %PYTHON_EXE_PATH%.
    echo Check venv integrity or python installation within venv.
    exit /b 1
)
REM --- END ---

echo Building %APP_NAME% executable for Windows using explicit Python path...

set PROMPTBUILDER_PROJECT_ROOT=%PROJECT_ROOT%
set SPEC_FILE_PATH=%PROJECT_ROOT%\scripts\freeze.spec
echo Using spec file: %SPEC_FILE_PATH%

REM --- Run PyInstaller as a module using the full path to the correct python.exe ---
REM No need to call activate.bat
echo Running PyInstaller via: "%PYTHON_EXE_PATH%" -m PyInstaller ...
"%PYTHON_EXE_PATH%" -m PyInstaller "%SPEC_FILE_PATH%"
set BUILD_EXIT_CODE=%errorlevel%
REM --- END ---

set PROMPTBUILDER_PROJECT_ROOT=

REM Check if build was successful
if %BUILD_EXIT_CODE% neq 0 ( echo Build failed with exit code %BUILD_EXIT_CODE%. & exit /b 1 )
echo Build successful! Executable is in the dist\%APP_NAME% directory.

REM --- FIX: Corrected Step 6 for cmd.exe syntax and target folder ---
REM ——— 6.  package OUTPUT FOLDER into zip ————————————————————————
echo Creating archive...
cd dist

REM Define the folder created by PyInstaller (should match APP_NAME in spec)
set "OUTPUT_FOLDER_NAME=%APP_NAME%"
set "ARCHIVE=..\%APP_NAME%_Windows.zip"

REM Check if the expected output folder exists
if not exist "%OUTPUT_FOLDER_NAME%" (
    echo ERROR: PyInstaller output folder '%OUTPUT_FOLDER_NAME%' not found in dist directory. Cannot create archive.
    cd ..
    goto EndBuildScript
)

where powershell >nul 2>nul
if %errorlevel% equ 0 (
    powershell -NoLogo -NoProfile -Command "Compress-Archive -Path '%OUTPUT_FOLDER_NAME%' -DestinationPath '%ARCHIVE%' -Force"
    echo Created %ARCHIVE% with PowerShell archiving folder %OUTPUT_FOLDER_NAME%
    goto EndArchive
)

where 7z >nul 2>nul
if %errorlevel% equ 0 (
    7z a "%ARCHIVE%" "%OUTPUT_FOLDER_NAME%\"
    echo Created %ARCHIVE% with 7-Zip archiving folder %OUTPUT_FOLDER_NAME%
    goto EndArchive
)

echo NOTE: PowerShell/7-Zip not found – skipping zip step.

:EndArchive
cd ..
REM --- END FIX ---

echo Build process finished.
exit /b 0