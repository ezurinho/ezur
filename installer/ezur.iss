; Instalador de ezur (Inno Setup 6).
;
; Se compila con:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ezur.iss
; y deja dist_installer\ezur-setup-0.1.0.exe
;
; Instalación por usuario en %LOCALAPPDATA%\ezur, sin privilegios de
; administrador: la app escribe su base de datos, su configuración y sus logs
; junto al ejecutable, así que instalarla en Program Files la dejaría sin
; permisos de escritura.

#define AppName "ezur"
#define AppVersion "0.1.0"
#define AppExe "ezur.exe"
#define AppUrl "https://github.com/ezurinho"

[Setup]
AppId={{6F1C2B54-7E3A-4E0B-9E4C-2F5A1D8C4B70}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ezur
AppPublisherURL={#AppUrl}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
OutputDir=..\dist_installer
OutputBaseFilename=ezur-setup-{#AppVersion}
SetupIconFile=ezur.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; El árbol onedir son ~80 MB comprimidos: avisar antes de empezar.
ExtraDiskSpaceRequired=0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist_exe\ezur\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Configuración inicial: no se pisa una que ya exista (una actualización
; respeta el perfil del usuario).
Source: "..\profiles\demo\config.json"; DestDir: "{app}\profiles\demo"; Flags: onlyifdoesntexist
Source: "..\profiles\okx\config.json"; DestDir: "{app}\profiles\okx"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; La base de datos y los logs son del usuario, no del programa: se borran solo
; si viven dentro de la carpeta de instalación, que es el caso por defecto.
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\profiles"
