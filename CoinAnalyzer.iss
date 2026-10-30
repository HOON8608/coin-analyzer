
[Setup]
AppId={{C01A2026-1234-4567-89AB-123456789ABC}}
AppName=코인 분석실
AppVersion=1.0.0
AppPublisher=Coin Analyzer
DefaultDirName={autopf}\CoinAnalyzer
DefaultGroupName=코인 분석실
OutputDir=Output
OutputBaseFilename=CoinAnalyzer_Setup
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\CoinAnalyzer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\코인 분석실"; Filename: "{app}\CoinAnalyzer.exe"
Name: "{autodesktop}\코인 분석실"; Filename: "{app}\CoinAnalyzer.exe"

[Run]
Filename: "{app}\CoinAnalyzer.exe"; Description: "코인 분석실 실행"; Flags: postinstall nowait skipifsilent
