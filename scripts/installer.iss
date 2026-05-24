; CastFlux Windows Installer (Inno Setup)
; Compile: ISCC.exe installer.iss

#define MyAppName "CastFlux"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "cybertronic23"
#define MyAppURL "https://github.com/cybertronic23/castflux"

[Setup]
AppId={{584E0B1C-1C8B-4B8E-8F6C-8D6E3F2A1C5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\CastFlux
DefaultGroupName=CastFlux
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=CastFlux_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; 核心 Python 包
Source: "..\src\castflux\*.py"; DestDir: "{app}\src\castflux"; Flags: ignoreversion
Source: "..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\uv.lock"; DestDir: "{app}"; Flags: ignoreversion
; .env 模板（不含真实密钥）
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env"; Flags: ignoreversion onlyifdoesntexist
; 脚本
Source: "run_gui.bat"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "setup_gui.bat"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "castflux.bat"; DestDir: "{app}\scripts"; Flags: ignoreversion
; 输出目录占位
Source: "..\output_slices\.gitkeep"; DestDir: "{app}\output_slices"; Flags: ignoreversion

[Icons]
Name: "{commondesktop}\CastFlux"; Filename: "{app}\scripts\run_gui.bat"; WorkingDir: "{app}"; Comment: "CastFlux"
Name: "{group}\CastFlux"; Filename: "{app}\scripts\run_gui.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall CastFlux"; Filename: "{uninstallexe}"

[Run]
; 运行 setup_gui.bat 安装 Python、UV、ffmpeg、项目依赖
Filename: "{app}\scripts\setup_gui.bat"; StatusMsg: "Installing Python / UV / ffmpeg..."; Flags: runhidden waituntilterminated
; 安装完成，可选启动 GUI
Filename: "{app}\scripts\run_gui.bat"; Description: "Launch CastFlux"; Flags: postinstall nowait skipifsilent shellexec unchecked
