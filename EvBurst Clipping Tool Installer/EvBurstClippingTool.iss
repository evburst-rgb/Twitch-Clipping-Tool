#define MyAppName "EvBurst Clipping Tool"
#define MyAppVersion "4.0"
#define MyAppPublisher "EvBurst"
#define MyAppExeName "EvBurst Clipping Tool.exe"

[Setup]
AppId={{8F6C8F9B-4A2D-4B3C-9A1F-EVBURSTCLIP}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=.
OutputBaseFilename=EvBurst-Clipping-Tool-Setup-v4.0
SetupIconFile=evburst_clipping_tool.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "EvBurst Clipping Tool.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "evburst_clipping_tool.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EvBurst Clipping Tool"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\evburst_clipping_tool.ico"
Name: "{group}\Uninstall EvBurst Clipping Tool"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EvBurst Clipping Tool"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\evburst_clipping_tool.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch EvBurst Clipping Tool"; Flags: nowait postinstall skipifsilent