; Inno Setup script for Engineering App (Windows)
; Requires dist/JobManager built via: python build_exe.py

#define MyAppName "Engineering App"
#define MyAppVersion "0.1.31"
#define MyAppPublisher "MaddogSTD"
#define MyAppExeName "JobManager.exe"

[Setup]
AppId={{8F34D7D2-5F7E-4F71-BA3F-8B7E4E2F7B55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Engineering App
DefaultGroupName=Engineering App
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=EngineeringAppSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "..\dist\JobManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Engineering App"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Engineering App"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Engineering App"; Flags: nowait postinstall skipifsilent
