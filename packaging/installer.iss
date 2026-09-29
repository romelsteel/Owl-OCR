; Inno Setup 6 script of Owl OCR. Compiled by packaging\build.py, which passes the defines below.
; Per-user install without administrator rights into %LOCALAPPDATA%\Programs\OwlOCR.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef RepoDir
  #define RepoDir ".."
#endif
#ifndef SourceDir
  #define SourceDir RepoDir + "\dist\OwlOCR"
#endif
#ifndef OutputDir
  #define OutputDir RepoDir + "\dist"
#endif
#ifndef IconFile
  #define IconFile RepoDir + "\build\owl.ico"
#endif

[Setup]
AppId={{6C1E2B7A-4F3D-4E9A-9B1C-2D7F0A8E5C31}
AppName=Owl OCR
AppVersion={#AppVersion}
AppVerName=Owl OCR {#AppVersion}
AppPublisher=romelsteel
AppPublisherURL=https://github.com/romelsteel/owl-ocr
AppSupportURL=https://github.com/romelsteel/owl-ocr/issues
AppUpdatesURL=https://github.com/romelsteel/owl-ocr/releases
DefaultDirName={localappdata}\Programs\OwlOCR
; The folder is fixed: no directory page, so {app} can never be a folder the user already had.
DisableDirPage=yes
DefaultGroupName=Owl OCR
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=OwlOCR-{#AppVersion}-setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\OwlOCR.exe
UninstallDisplayName=Owl OCR
LicenseFile={#RepoDir}\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[CustomMessages]
english.RemoveDataQuestion=Also delete the Owl OCR engine (about 10 GB), the queue and the settings?%n%nYour documents and the files Owl OCR wrote next to them are never deleted.
czech.RemoveDataQuestion=Smazat také engine Owl OCR (asi 10 GB), frontu a nastavení?%n%nVaše dokumenty a soubory, které Owl OCR uložil vedle nich, se nikdy nemažou.
english.CloseAppFirst=Owl OCR is running. Close it and start the uninstallation again.
czech.CloseAppFirst=Owl OCR je spuštěný. Zavřete ho a spusťte odinstalaci znovu.
english.RemoveDataFailed=Some Owl OCR data could not be deleted (a file may still be in use). The program itself is still being removed.%n%nYou can delete the remaining Owl OCR files by hand from this folder:%n%1
czech.RemoveDataFailed=Některá data Owl OCR se nepodařilo smazat (některý soubor může být ještě používán). Samotný program se přesto odinstaluje.%n%nZbývající soubory Owl OCR můžete smazat ručně z této složky:%n%1

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Owl OCR"; Filename: "{app}\OwlOCR.exe"
Name: "{autodesktop}\Owl OCR"; Filename: "{app}\OwlOCR.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OwlOCR.exe"; Description: "{cm:LaunchProgram,Owl OCR}"; Flags: nowait postinstall skipifsilent

; No UninstallDelete section: the uninstaller removes exactly the files it installed, and the app never writes into {app}.

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if Exec(ExpandConstant('{cmd}'), '/C tasklist /FI "IMAGENAME eq OwlOCR.exe" /NH | find /I "OwlOCR.exe"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0) then
  begin
    SuppressibleMsgBox(CustomMessage('CloseAppFirst'), mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

{ The data folder: the path in location.txt (kept by --remove-data when something stayed behind),
  else the default. Inno 6.7 reads UTF-8 files with or without a BOM. }
function OwlDataFolder(): String;
var
  Lines: TArrayOfString;
begin
  Result := ExpandConstant('{localappdata}\OwlOCR');
  if LoadStringsFromFile(ExpandConstant('{userappdata}\OwlOCR\location.txt'), Lines) then
    if (GetArrayLength(Lines) > 0) and (Trim(Lines[0]) <> '') then
      Result := Trim(Lines[0]);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if SuppressibleMsgBox(CustomMessage('RemoveDataQuestion'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    begin
      { A failure never stops the uninstall: the program files are removed either way. }
      if (not Exec(ExpandConstant('{app}\OwlOCR.exe'), '--remove-data', '', SW_HIDE, ewWaitUntilTerminated, ResultCode))
         or (ResultCode <> 0) then
        SuppressibleMsgBox(FmtMessage(CustomMessage('RemoveDataFailed'), [OwlDataFolder()]), mbError, MB_OK, IDOK);
    end;
  end;
end;
