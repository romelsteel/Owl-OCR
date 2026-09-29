@echo off
REM ============================================================
REM  Sestaví PDF -> Markdown do jednoho .exe (Windows).
REM  Vysledek: dist\PDF-to-Markdown.exe  (staci dvojklik)
REM ============================================================
cd /d "%~dp0"

echo Instaluji PyInstaller a zavislosti (pokud chybi)...
py -m pip install --upgrade pyinstaller >nul
py -m pip install -r requirements.txt >nul

echo.
echo Sestavuji EXE, muze to trvat nekolik minut...
py -m PyInstaller --noconfirm --onefile --windowed --name "PDF-to-Markdown" ^
  --icon "wolf.ico" ^
  --add-data "index.html;." ^
  --collect-all markitdown ^
  --collect-all magika ^
  --collect-all onnxruntime ^
  --collect-all pdfminer ^
  --collect-all pdfplumber ^
  --collect-all pptx ^
  --collect-all webview ^
  --collect-all clr_loader ^
  --collect-all pythonnet ^
  app.py

echo.
echo Hotovo. EXE najdes zde: dist\PDF-to-Markdown.exe
pause
