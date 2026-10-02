; Inno Setup script: a per-user installer for the PyInstaller folder (no administrator needed).
; Build with:  iscc /DAppVersion=0.1.0 packaging\sheet-dj.iss      (see build.ps1)
; Installing again over an older copy upgrades it; the AppId is what ties them together.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Sheet DJ"
#define AppExe "sheet-dj.exe"

[Setup]
AppId={{2211ED52-BE70-4F21-9CA4-BD1DB0FECC8D}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=sheet-dj.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\build\installer
OutputBaseFilename=sheet-dj-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "..\build\dist\sheet-dj\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent

[Code]
// The server keeps running after the browser tab is closed, and Windows will not replace or
// delete the files of a running program. Stop it first, quietly.
procedure StopRunningApp();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM {#AppExe}', '', SW_HIDE,
    ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopRunningApp();
  Result := True;
end;
