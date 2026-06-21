; ProcAI - Inno Setup installer script
; Build the EXE first:  pyinstaller installer/procai.spec --noconfirm
; Then compile this script with Inno Setup (ISCC.exe procai_installer.iss).
;
; This installer is transparent and standard:
;  - Per-user install by default (no admin needed); optional all-users.
;  - Creates Start Menu + optional Desktop shortcuts and an uninstaller.
;  - Optional, clearly-labelled "start at logon" entry (a visible Run key).
;  - Does NOT touch Windows Defender, UAC, or SmartScreen.
;  - Uninstall removes the startup entry and app files and ASKS whether to keep
;    the user's local data (reports, logs, database).

#define AppName "ProcAI"
#define AppVersion "2.0.0"
#define AppPublisher "ProcAI Project"
#define AppExeName "ProcAI.exe"
#define AppURL "https://example.com/procai"

[Setup]
AppId={{9F4A6C2E-1B7D-4E2A-9C3F-PROCAI0002000}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=ProcAI-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog
; Per-user by default so no admin prompt is required for a prototype.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=procai.ico
UninstallDisplayName={#AppName} Endpoint Protection
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "Start ProcAI background protection when I log on (visible in Task Manager Startup)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; The PyInstaller COLLECT output folder (dist\ProcAI\*).
Source: "..\dist\ProcAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ProcAI Dashboard"; Filename: "{app}\{#AppExeName}"
Name: "{group}\ProcAI (background service)"; Filename: "{app}\{#AppExeName}"; Parameters: "--service --tray"
Name: "{group}\Uninstall ProcAI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProcAI"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Optional, user-scoped, VISIBLE startup entry (only if the task is selected).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ProcAI"; \
    ValueData: """{app}\{#AppExeName}"" --service --tray"; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch ProcAI dashboard"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Best-effort: stop any running service before files are removed.
Filename: "{app}\{#AppExeName}"; Parameters: "--stop"; Flags: skipifdoesntexist runhidden; RunOnceId: "StopProcAI"

[Code]
// On uninstall, ask whether to keep the user's local data folder.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ProcAI');
    if DirExists(DataDir) then
    begin
      if MsgBox('Do you also want to delete your ProcAI data (alerts, logs, reports, '
        + 'database and settings)?' + #13#10 + #13#10
        + 'Choose No to keep your reports and history.',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
