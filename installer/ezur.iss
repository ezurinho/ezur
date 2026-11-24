; Instalador de ezur (Inno Setup 6).
;
; Se compila con (winget lo instala por usuario, no en Program Files):
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\ezur.iss
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
; El árbol del programa, salvo lo que es del usuario: su configuración y su base
; de datos. Eso va aparte, se instala solo si no existe y no se toca al
; actualizar ni al desinstalar.
Source: "..\dist_exe\ezur\*"; DestDir: "{app}"; Excludes: "data\config.json,data\*.db,data\*.db-wal,data\*.db-shm,profiles\demo\config.json,profiles\okx\config.json"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist_exe\ezur\data\config.json"; DestDir: "{app}\data"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\profiles\demo\config.json"; DestDir: "{app}\profiles\demo"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\profiles\okx\config.json"; DestDir: "{app}\profiles\okx"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent

; Sin [UninstallDelete]: desinstalar quita el programa, no el historial. La base
; de datos (`data\terminal.db`) y la configuración son del usuario y se quedan
; donde están, así que volver a instalar retoma el estado anterior. Para
; borrarlo todo hay que eliminar la carpeta a mano.
