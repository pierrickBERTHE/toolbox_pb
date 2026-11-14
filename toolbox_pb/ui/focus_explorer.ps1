param(
    [Parameter(Mandatory = $true)]
    [string]$Target
)

if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
    Write-Error "Dossier introuvable : $Target"
    exit 2
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ExplorerWindow {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}
'@

$shell = New-Object -ComObject Shell.Application
$activator = New-Object -ComObject WScript.Shell
$expectedPath = [IO.Path]::GetFullPath($Target).TrimEnd('\')
# Open the folder with the native Explorer executable. Passing only the path
# is more reliable than Explorer's optional /n command-line syntax.
try {
    Start-Process -FilePath explorer.exe -ArgumentList ('"{0}"' -f $expectedPath) -ErrorAction Stop
} catch {
    Write-Error "Impossible de lancer l’Explorateur Windows : $($_.Exception.Message)"
    exit 3
}

for ($attempt = 0; $attempt -lt 50; $attempt++) {
    Start-Sleep -Milliseconds 100
    foreach ($window in @($shell.Windows())) {
        try {
            $folderPath = $window.Document.Folder.Self.Path
        } catch {
            continue
        }
        if ([IO.Path]::GetFullPath($folderPath).TrimEnd('\') -ne $expectedPath) {
            continue
        }
        # Restore and activate the matching Explorer window. AppActivate is more
        # reliable than SetForegroundWindow alone when this script is started
        # by Streamlit in a background PowerShell process.
        $window.Visible = $true
        [ExplorerWindow]::ShowWindowAsync([IntPtr]$window.HWND, 9) | Out-Null
        [ExplorerWindow]::BringWindowToTop([IntPtr]$window.HWND) | Out-Null
        $activator.AppActivate([int]$window.HWND) | Out-Null
        [ExplorerWindow]::SetForegroundWindow([IntPtr]$window.HWND) | Out-Null
        Write-Output "Explorateur Windows ouvert : $expectedPath"
        exit 0
    }
}

# Explorer can take longer to expose its COM window. It was launched above,
# but Windows did not let this background script activate it in time.
Write-Output "Explorateur Windows demandé : $expectedPath (activation au premier plan non confirmée)."
exit 0
