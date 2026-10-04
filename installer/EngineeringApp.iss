; Inno Setup script for Engineering App (Windows)
; Requires dist/JobManager.exe built via: python build_exe.py

#define MyAppName "Engineering App"
#define MyAppVersion "1.0.0"
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
SetupIconFile=..\assets\engineering-app.ico
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\engineering-app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Engineering App"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\engineering-app.ico"
Name: "{autodesktop}\Engineering App"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\engineering-app.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Engineering App"; Flags: nowait postinstall skipifsilent
