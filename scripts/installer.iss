; CastFlux Windows Installer (Inno Setup)
; Compile: ISCC.exe installer.iss

#define MyAppName "CastFlux"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "cybertronic23"
#define MyAppURL "https://github.com/cybertronic23/castflux"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
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
OutputBaseFilename=CastFlux_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
chinesesimplified.WelcomeLabel2=此安装程序将安装 [name] 到您的电脑上。%n%n只需点击"下一步"，全程自动完成。%n%n首次启动后请在设置中填入 API Key。

english.WelcomeLabel2=This will install [name] on your computer.%n%nJust click "Next" – everything is automatic.%n%nAfter first launch, fill in your API Keys in Settings.

[Files]
; 核心 Python 包
Source: "..\src\castflux\*.py"; DestDir: "{app}\src\castflux"; Flags: ignoreversion
Source: "..\src\castflux\__pycache__\*"; DestDir: "{app}\src\castflux\__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs
; 项目根目录文件
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
Name: "{commondesktop}\CastFlux"; Filename: "{app}\scripts\run_gui.bat"; WorkingDir: "{app}"; Comment: "CastFlux 直播切片工具"
Name: "{group}\CastFlux"; Filename: "{app}\scripts\run_gui.bat"; WorkingDir: "{app}"
Name: "{group}\卸载 CastFlux"; Filename: "{uninstallexe}"

[Run]
; 步骤1：安装 Python、UV、ffmpeg、项目依赖（静默运行 setup_gui.bat）
Filename: "{app}\scripts\setup_gui.bat"; StatusMsg: "正在配置环境（自动安装 Python / UV / ffmpeg）..."; Flags: runhidden waituntilterminated
; 步骤2：安装完成，可选启动 GUI
Filename: "{app}\scripts\run_gui.bat"; Description: "启动 CastFlux"; Flags: postinstall nowait skipifsilent shellexec unchecked

[UninstallRun]
Filename: "{app}\scripts\uninstall_env.bat"; Flags: runhidden

[Code]
var
  DetailPage: TOutputMsgMemoWizardPage;

procedure InitializeWizard;
begin
  DetailPage := CreateOutputMsgMemoPage(wpInstalling, '安装详情', '正在安装...',
    'CastFlux 正在自动配置环境，请耐心等待（首次需下载 Python 和模型）。'#13#10#13#10'请勿关闭此窗口。', '');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    DetailPage.RichEditViewer.Lines.Clear;
    DetailPage.RichEditViewer.Lines.Add('✅ 文件复制完成');
    DetailPage.RichEditViewer.Lines.Add('正在安装 Python / UV / ffmpeg...');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
end;
