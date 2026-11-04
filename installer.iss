; Script de instalador para Inno Setup Compiler (Genera setup.exe estándar de Windows)
; Para compilar con Inno Setup: iscc installer.iss

#define MyAppName "IA Background Remover & WebP Optimizer"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Antigravity AI"
#define MyAppExeName "IABackgroundRemover.exe"

[Setup]
AppId={{8B41E1C5-A8F2-4D3B-9872-4F11E1D9A74E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\IABackgroundRemover
DisableProgramGroupPage=yes
OutputBaseFilename=setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\IABackgroundRemover\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

