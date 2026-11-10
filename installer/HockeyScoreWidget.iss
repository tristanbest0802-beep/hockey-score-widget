; Hockey Score Widget installer (Inno Setup 6).
; Built by .github/workflows/release.yml:
;   iscc /DAppVersion=1.0.0 installer\HockeyScoreWidget.iss
; Input: dist\HockeyScoreWidget.exe. Output: dist\HockeyScoreWidget-Setup.exe.
;
; Per-user install: no administrator prompt (UAC), folder %LOCALAPPDATA%\Programs\Hockey Score Widget.
; Settings stay in %APPDATA%\HockeyScoreWidget: an update or an uninstall never touches them.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; Numeric version for the file properties (1.0.0-test -> 1.0.0).
#ifndef NumVersion
  #define NumVersion AppVersion
#endif
#define AppName "Hockey Score Widget"
#define AppExe "HockeyScoreWidget.exe"
#define RepoURL "https://github.com/tristanbest0802-beep/hockey-score-widget"

[Setup]
; Fixed AppId: a new version replaces the old one instead of installing next to it.
AppId={{D502104E-C279-43CE-A518-51FF0790FC7F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Blackoune
AppPublisherURL={#RepoURL}
AppSupportURL={#RepoURL}/issues
AppUpdatesURL={#RepoURL}/releases
AppCopyright=© Blackoune, GPL-3.0
VersionInfoVersion={#NumVersion}
VersionInfoDescription={#AppName} - installation

PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

; Keep the Welcome page: it shows the big logo panel, like the Finish page.
DisableWelcomePage=no
DisableDirPage=no
WizardStyle=modern
WizardSizePercent=110
SetupIconFile=..\assets\icon.ico
WizardImageFile=wizard-100.bmp,wizard-200.bmp
WizardSmallImageFile=petit-100.bmp,petit-200.bmp
WizardImageStretch=no
WizardImageBackColor=$141211

LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=HockeyScoreWidget-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"; InfoBeforeFile: "infos-fr.txt"
Name: "en"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "infos-en.txt"

[Tasks]
Name: "bureau"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; DestName: "THIRD_PARTY_NOTICES.txt"; Flags: ignoreversion
Source: "..\hockey_widget\fonts\OFL.txt"; DestDir: "{app}"; DestName: "OFL-Barlow-Condensed.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: bureau

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
