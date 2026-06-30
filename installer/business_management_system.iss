; Business Management System — Inno Setup Script
; MyAppVersion is injected at build time via /DMyAppVersion=x.x.x
; so the version never needs to be edited here manually.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName      "Business Management System"
#define MyAppShortName "BusinessManagementSystem"
#define MyAppPublisher "PsyChoNyMouz"
#define MyAppExeName   "BusinessManagementSystem.exe"
#define MyAppId        "BMS-PYQT5-DJANGO-2026-6-7"

; ── Setup metadata ────────────────────────────────────────────────────────────
[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; EXE lives here; user data (db, logs, media) is always written to
; %LOCALAPPDATA%\BusinessManagementSystem\ by the app itself.
DefaultDirName={localappdata}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=BMS_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
; No admin rights needed — installs per-user under %LOCALAPPDATA%
PrivilegesRequired=lowest
; Automatically close a running instance before overwriting the EXE
CloseApplications=yes
CloseApplicationsFilter=*{#MyAppExeName}
RestartApplications=no
AppMutex=BMS_Desktop_App_Mutex
SetupIconFile=..\desktop_app\resources\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
WizardStyle=modern
DisableProgramGroupPage=yes
DisableWelcomePage=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup

; ── Languages ─────────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Optional tasks ────────────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ── Files to install ──────────────────────────────────────────────────────────
[Files]
; ignoreversion = always overwrite regardless of version stamp (update-safe)
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; ── Shortcuts ─────────────────────────────────────────────────────────────────
[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon

; ── Post-install: offer to launch the app ─────────────────────────────────────
[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

; ── Pascal Script ─────────────────────────────────────────────────────────────
[Code]

var
  RemoveDataOnUninstall: Boolean;

{ Read the currently installed version from the registry (empty if not installed). }
function GetInstalledVersion(): String;
var
  Ver: String;
begin
  if RegQueryStringValue(HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1',
      'DisplayVersion', Ver) then
    Result := Ver
  else
    Result := '';
end;

{ ── Install: detect existing install and confirm update ── }
function InitializeSetup(): Boolean;
var
  OldVer: String;
begin
  Result := True;
  OldVer := GetInstalledVersion();
  if OldVer <> '' then
  begin
    if MsgBox(
        'Version ' + OldVer + ' is already installed.' + #13#10 +
        'This will update it to version {#MyAppVersion}.' + #13#10#13#10 +
        'Your database, media files and logs will not be affected.' + #13#10#13#10 +
        'Continue with the update?',
        mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

{ ── Uninstall: ask whether to wipe user data too ── }
function InitializeUninstall(): Boolean;
var
  DataDir: String;
begin
  Result := True;
  RemoveDataOnUninstall := False;
  DataDir := ExpandConstant('{localappdata}\{#MyAppShortName}');
  if DirExists(DataDir) then
  begin
    if MsgBox(
        'Do you also want to remove all application data?' + #13#10 +
        '(database, uploaded files, logs, sessions)' + #13#10#13#10 +
        'YES  — delete everything (clean uninstall)' + #13#10 +
        'NO   — keep your data (safe if you plan to reinstall)',
        mbConfirmation, MB_YESNO) = IDYES then
      RemoveDataOnUninstall := True;
  end;
end;

{ Delete user data folder only if the user agreed above. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and RemoveDataOnUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#MyAppShortName}');
    if DirExists(DataDir) then
      DelTree(DataDir, True, True, True);
  end;
end;
