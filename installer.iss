; LocalWhisper — Inno Setup 6 installer script
; Download Inno Setup 6: https://jrsoftware.org/isinfo.php

#define AppName      "LocalWhisper"
#define AppVersion   "0.1.0"
#define AppPublisher "Pedro"
#define AppExeName   "LocalWhisper.exe"
#define DistDir      "dist\LocalWhisper"

[Setup]
AppId={{B6C31D5E-4A8F-4D2B-9C7A-E3F2108D0B54}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=LocalWhisper-Setup
SetupIconFile=localwhisper\resources\icons\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; No UAC prompt — installs to %LOCALAPPDATA%\Programs per-user
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupentry"; Description: "Start LocalWhisper automatically when Windows starts"; GroupDescription: "Windows startup:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: startupentry

[Registry]
; Windows startup via Run key (mirrors the in-app auto_launch setting)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startupentry

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Kill the running process before uninstalling
Filename: "taskkill"; Parameters: "/f /im {#AppExeName}"; \
  Flags: runhidden; RunOnceId: "KillApp"
