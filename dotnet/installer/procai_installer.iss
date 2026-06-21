; ProcAI (.NET) - Inno Setup installer
; 1) Publish first:  pwsh ..\build.ps1
;    (produces ..\publish\app\ProcAI.exe and ..\publish\service\ProcAI.Service.exe)
; 2) Compile this script with Inno Setup 6 (ISCC.exe procai_installer.iss)
;
; Transparent and standard: per-user install (no admin needed), Start Menu +
; optional desktop shortcuts, an optional VISIBLE "start at logon" entry, and a
; clean uninstaller that asks whether to keep local data. Does NOT touch Windows
; Defender, UAC or SmartScreen.

#define AppName "ProcAI"
#define AppVersion "2.0.0"
#define AppPublisher "ProcAI Project"
#define AppExe "ProcAI.exe"

[Setup]
AppId={{B2E9A7C4-2D55-4F1A-9E3B-PROCAINET20000}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=ProcAI-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName} Endpoint Protection

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startupicon"; Description: "Start ProcAI background protection when I log on (visible in Task Manager Startup)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Published single-file executables (self-contained; no .NET install required).
Source: "..\publish\app\*";     DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\publish\service\ProcAI.Service.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ProcAI Dashboard"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall ProcAI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ProcAI"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Optional, user-scoped, VISIBLE startup entry (only if the task is selected).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ProcAI"; \
    ValueData: """{app}\ProcAI.Service.exe"""; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch ProcAI dashboard"; \
    Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\ProcAI');
    if DirExists(DataDir) then
      if MsgBox('Do you also want to delete your ProcAI data (alerts, logs, reports, '
        + 'database and settings)?' + #13#10 + #13#10
        + 'Choose No to keep your reports and history.',
        mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
