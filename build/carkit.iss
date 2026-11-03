[Setup]
AppId=carkit-desktop
AppName=carkit
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\carkit
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\carkit.exe
OutputDir=..\dist
OutputBaseFilename=carkit-{#AppVersion}-setup
Compression=lzma2/fast
CloseApplications=yes
CloseApplicationsFilter=carkit.exe
RestartApplications=no
RestartIfNeededByRun=no
DisableStartupPrompt=yes
WizardStyle=modern

[Files]
Source: "..\dist\carkit.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "carkit-installed.marker"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\carkit"; Filename: "{app}\carkit.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\carkit.exe"; Parameters: "{code:LaunchParameters}"; WorkingDir: "{app}"; Flags: nowait; Check: ShouldRelaunch
Filename: "{app}\carkit.exe"; Description: "Launch carkit"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent; Check: ShouldOfferLaunch

[Code]
// Inno Setup 6 uses a 32-bit setup process even in 64-bit install mode.
function OpenProcess(DesiredAccess: Cardinal; InheritHandle: LongBool; ProcessId: Cardinal): Cardinal;
  external 'OpenProcess@kernel32.dll stdcall setuponly';
function WaitForSingleObject(Handle: Cardinal; Milliseconds: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall setuponly';
function CloseHandle(Handle: Cardinal): LongBool;
  external 'CloseHandle@kernel32.dll stdcall setuponly';

function InitializeSetup(): Boolean;
var
  Value: String;
  ProcessId: Integer;
  ProcessHandle: Cardinal;
begin
  Result := True;
  Value := ExpandConstant('{param:WAITPID|}');
  if Value = '' then
    Exit;

  ProcessId := StrToIntDef(Value, 0);
  if ProcessId <= 0 then
    RaiseException('Invalid carkit process ID.');

  // Wait for the bootloader, which releases the installed EXE after Python exits.
  ProcessHandle := OpenProcess($00100000, False, ProcessId);
  if ProcessHandle = 0 then begin
    if DLLGetLastError = 87 then
      Exit;  // The process already exited.
    RaiseException('Could not wait for carkit to close.');
  end;
  try
    if WaitForSingleObject(ProcessHandle, 90000) <> 0 then
      RaiseException('carkit is still running. Close it, then run setup again.');
  finally
    CloseHandle(ProcessHandle);
  end;
end;

function ShouldRelaunch(): Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|}') = '1';
end;

function ShouldOfferLaunch(): Boolean;
begin
  Result := not ShouldRelaunch();
end;

function LaunchParameters(Param: String): String;
var
  WorkDir: String;
  Last: Integer;
begin
  Result := '';
  WorkDir := ExpandConstant('{param:WORKDIR|}');
  if WorkDir = '' then
    Exit;
  if Pos('"', WorkDir) > 0 then
    RaiseException('Invalid carkit work directory.');

  // A quoted Windows argument needs one extra slash per trailing backslash.
  Last := Length(WorkDir);
  while Last > 0 do begin
    if WorkDir[Last] <> '\' then
      Break;
    WorkDir := WorkDir + '\';
    Last := Last - 1;
  end;
  Result := '"' + WorkDir + '"';
end;
