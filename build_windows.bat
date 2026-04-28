@echo off
setlocal

set PYTHON=python
if not "%~1"=="" set PYTHON=%~1

%PYTHON% -m pip install -r requirements.txt
%PYTHON% -m pip install -r requirements-dev.txt

%PYTHON% -m PyInstaller --noconfirm --clean --onefile --name ByteSweep ^
  --add-data "config.json;." ^
  --add-data "locales;locales" ^
  --add-data "themes;themes" ^
  --add-data "profiles;profiles" ^
  --add-data "plugins;plugins" ^
  --add-data "core/wordlist.txt;core" ^
  main.py

echo Build complete: dist\ByteSweep.exe
endlocal
