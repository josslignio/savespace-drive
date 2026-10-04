; Installeur Windows de SaveSpace Drive (Inno Setup 6). Construit par .github/workflows/build.yml.
; Installation pour l'utilisateur seulement : aucun droit administrateur demandé.
#ifndef Version
  #define Version "0.1.0"
#endif

[Setup]
AppId={{8C1E6A52-5B7D-4D2B-9E61-3A0F2C7D9B11}
AppName=SaveSpace Drive
AppVersion={#Version}
AppPublisher=SaveSpace Drive
DefaultDirName={autopf}\SaveSpace Drive
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SaveSpace-Drive-{#Version}-windows-installeur
SetupIconFile=icone\SaveSpace.ico
UninstallDisplayIcon={app}\SaveSpace Drive.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer une icône sur le Bureau"; Flags: unchecked

[Files]
Source: "..\dist\SaveSpace Drive.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\SaveSpace Drive"; Filename: "{app}\SaveSpace Drive.exe"
Name: "{autodesktop}\SaveSpace Drive"; Filename: "{app}\SaveSpace Drive.exe"; Tasks: bureau

[Run]
Filename: "{app}\SaveSpace Drive.exe"; Description: "Ouvrir SaveSpace Drive"; Flags: nowait postinstall skipifsilent
