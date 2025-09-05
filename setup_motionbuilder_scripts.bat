@echo off
echo =============================================
echo MotionBuilder 2025 Python Scripts Setup
echo =============================================
echo.

REM Set the target directory
set "MOTIONBUILDER_CONFIG=C:\Program Files\Autodesk\MotionBuilder 2025\bin\config"
set "PYTHON_CUSTOM_SCRIPTS=%MOTIONBUILDER_CONFIG%\PythonCustomScripts"
set "PYTHON_STARTUP=%MOTIONBUILDER_CONFIG%\PythonStartup"

echo Setting up MotionBuilder Python scripts...
echo Target directory: %MOTIONBUILDER_CONFIG%
echo.

REM Check if MotionBuilder is installed
if not exist "%MOTIONBUILDER_CONFIG%" (
    echo ERROR: MotionBuilder 2025 not found at expected location!
    echo Please ensure MotionBuilder 2025 is installed at: C:\Program Files\Autodesk\MotionBuilder 2025\
    pause
    exit /b 1
)

REM Create PythonCustomScripts directory if it doesn't exist
echo Creating PythonCustomScripts directory...
if not exist "%PYTHON_CUSTOM_SCRIPTS%" (
    mkdir "%PYTHON_CUSTOM_SCRIPTS%"
    echo Created: %PYTHON_CUSTOM_SCRIPTS%
) else (
    echo Directory already exists: %PYTHON_CUSTOM_SCRIPTS%
)

REM Create PythonStartup directory if it doesn't exist
echo Creating PythonStartup directory...
if not exist "%PYTHON_STARTUP%" (
    mkdir "%PYTHON_STARTUP%"
    echo Created: %PYTHON_STARTUP%
) else (
    echo Directory already exists: %PYTHON_STARTUP%
)

echo.
echo Moving files to their correct locations...

REM Copy all Python scripts to PythonCustomScripts (excluding setup files)
echo Copying Python scripts to PythonCustomScripts...
for %%f in (*.py) do (
    if not "%%f"=="setup_motionbuilder_scripts.py" (
        if not "%%f"=="StartupScriptShelf.py" (
            copy "%%f" "%PYTHON_CUSTOM_SCRIPTS%\" >nul
            echo   Copied: %%f
        )
    )
)

REM Move PythonScriptIcons folder to config directory
echo Moving PythonScriptIcons to config directory...
if exist "PythonScriptIcons" (
    if exist "%MOTIONBUILDER_CONFIG%\PythonScriptIcons" (
        echo   Removing existing PythonScriptIcons folder...
        rmdir /s /q "%MOTIONBUILDER_CONFIG%\PythonScriptIcons"
    )
    xcopy "PythonScriptIcons" "%MOTIONBUILDER_CONFIG%\PythonScriptIcons\" /e /i /y >nul
    echo   Moved: PythonScriptIcons folder
) else (
    echo   WARNING: PythonScriptIcons folder not found in current directory
)

REM Move StartupScriptShelf.py to PythonStartup
echo Moving StartupScriptShelf.py to PythonStartup...
if exist "StartupScriptShelf.py" (
    copy "StartupScriptShelf.py" "%PYTHON_STARTUP%\" >nul
    echo   Moved: StartupScriptShelf.py
) else (
    echo   WARNING: StartupScriptShelf.py not found in current directory
)

echo.
echo =============================================
echo Setup completed successfully!
echo =============================================
echo.
echo Files have been installed to:
echo   Python Scripts: %PYTHON_CUSTOM_SCRIPTS%
echo   Script Icons:   %MOTIONBUILDER_CONFIG%\PythonScriptIcons
echo   Startup Script: %PYTHON_STARTUP%\StartupScriptShelf.py
echo.
echo You can now start MotionBuilder 2025 and access your custom Python scripts.
echo.
pause