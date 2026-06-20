; Instalador do Relatorio Processual - Clemon Campos
; Compilar com Inno Setup:  ISCC.exe installer.iss
; Gera installer\Instalar-Relatorio-Clemon.exe

#define AppName "Relatorio Processual - Clemon Campos"
#define AppVersion "1.0.0"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Clemon Campos Advocacia
DefaultDirName={localappdata}\ClemonRelatorios
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Instalar-Relatorio-Clemon
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; instalacao em LocalAppData: sem admin e gravavel (necessario p/ auto-update)

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\ClemonRelatorios\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Relatorio Processual Clemon"; Filename: "{app}\Iniciar Relatorios.bat"; WorkingDir: "{app}"
Name: "{userprograms}\Relatorio Processual Clemon"; Filename: "{app}\Iniciar Relatorios.bat"; WorkingDir: "{app}"

[Run]
Filename: "{app}\Iniciar Relatorios.bat"; Description: "Abrir o sistema agora"; Flags: nowait postinstall skipifsilent