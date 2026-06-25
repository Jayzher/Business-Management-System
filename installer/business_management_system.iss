; Inno Setup Script for Business Management System
; Version: 1.0.1

#define MyAppName "Business Management System"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "PsyChoNyMouz"
#define MyAppExeName "BusinessManagementSystem.exe"

[Setup]
AppId={{BMS-PYQT5-DJANGO-2026-6-7}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\BusinessManagementSystem
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=BMS_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
CloseApplications=yes
AppMutex=BMS_Desktop_App_Mutex
SetupIconFile=..\desktop_app\resources\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; User data (db.sqlite3, logs, sessions, cache, media) lives under
; {localappdata}\BusinessManagementSystem and is created on first run.

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
