; Instalador de Remover Background IP (Inno Setup 6)
; Compilar con:  python build_release.py   (o: iscc installer.iss tras el build de PyInstaller)

#define MyAppName "Remover Background IP"
#ifndef MyAppVersion
  #define MyAppVersion "2.1.0"
#endif
#define MyAppPublisher "Importadora Premium"
#define MyAppExeName "RemoverBackgroundIP.exe"
#define MyAppMutex "RemoverBackgroundIP_Mutex"
; Nombres de la versión anterior (IA Background Remover), para cerrarla y limpiarla al actualizar
#define OldAppMutex "IABackgroundRemover_Mutex"
#define OldExeName "IABackgroundRemover.exe"
#define OldAppName "IA Background Remover"
#define DefaultPort "48765"
#define FirewallRule "Remover Background IP"

[Setup]
AppId={{8B41E1C5-A8F2-4D3B-9872-4F11E1D9A74E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RemoverBackgroundIP
UsePreviousAppDir=no
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=setup-{#MyAppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Se requiere administrador para instalar en Program Files y abrir el puerto en el Firewall
PrivilegesRequired=admin
; Cierra la app en ejecución (bandeja) antes de actualizar o desinstalar
AppMutex={#MyAppMutex},{#OldAppMutex}
CloseApplications=force
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Iniciar automáticamente con Windows (segundo plano, escuchando en la red)"; GroupDescription: "Segundo plano:"
Name: "firewall"; Description: "Permitir conexiones desde la red local en el Firewall de Windows (redes privadas)"; GroupDescription: "Segundo plano:"

[Files]
Source: "dist\RemoverBackgroundIP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RemoverBackgroundIP"; ValueData: """{app}\{#MyAppExeName}"" --background"; Flags: uninsdeletevalue; Tasks: autostart

; Quitar el inicio automático de la versión anterior
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "IABackgroundRemover"; ValueType: none; Flags: deletevalue

[InstallDelete]
; Restos de la versión anterior (IA Background Remover)
Type: filesandordirs; Name: "{autopf}\IABackgroundRemover"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"
Type: files; Name: "{autoprograms}\{#OldAppName}.lnk"

[Run]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#OldExeName}"; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#OldAppName}"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#FirewallRule}"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=private,domain"; Flags: runhidden waituntilterminated; Tasks: firewall
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser
Filename: "{app}\{#MyAppExeName}"; Parameters: "--background"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#FirewallRule}"""; Flags: runhidden; RunOnceId: "DelFirewall"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  PortPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  PortPage := CreateInputQueryPage(wpSelectTasks,
    'Puerto de red',
    'Puerto en el que la aplicación escuchará peticiones de la red local',
    'Los equipos de la misma red podrán consultar http://<IP-de-este-equipo>:<puerto>/health ' +
    'y enviar imágenes a /jobs. Puede cambiarlo después en Configuración.');
  PortPage.Add('Puerto (1024 - 65535):', False);
  PortPage.Values[0] := '{#DefaultPort}';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then
  begin
    Port := StrToIntDef(Trim(PortPage.Values[0]), 0);
    if (Port < 1024) or (Port > 65535) then
    begin
      MsgBox('Ingrese un puerto válido entre 1024 y 65535.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Port: String;
begin
  if CurStep = ssPostInstall then
  begin
    Port := IntToStr(StrToIntDef(Trim(PortPage.Values[0]), {#DefaultPort}));
    SaveStringToFile(ExpandConstant('{app}\server_defaults.json'),
      '{"server_port": ' + Port + '}', False);
  end;
end;
