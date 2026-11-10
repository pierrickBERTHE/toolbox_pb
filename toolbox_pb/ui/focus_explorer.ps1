param(
    [Parameter(Mandatory = $true)]
    [string]$Target
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ExplorerWindow {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}
'@

$shell = New-Object -ComObject Shell.Application
$expectedPath = [IO.Path]::GetFullPath($Target).TrimEnd('\')
# Keep existing Explorer windows out of the candidate list: the new window
# opened below is the only one eligible to receive foreground focus.
$knownHandles = @(
    $shell.Windows() | ForEach-Object { [Int64]$_.HWND }
)
# The comma is part of Explorer's command-line syntax: without it, Explorer
# may ignore the path and reuse its default location.  /n requests a distinct
# Explorer window for this folder.
Start-Process explorer.exe -ArgumentList ('/n,"{0}"' -f $Target)

for ($attempt = 0; $attempt -lt 20; $attempt++) {
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
        if ($knownHandles -contains [Int64]$window.HWND) {
            continue
        }

        # 9 restores the newly opened Explorer window before bringing it forward.
        [ExplorerWindow]::ShowWindowAsync([IntPtr]$window.HWND, 9) | Out-Null
        [ExplorerWindow]::SetForegroundWindow([IntPtr]$window.HWND) | Out-Null
        exit 0
    }
}

# Explorer accepted the /n request above.  Its COM window can appear later
# than the short focus polling loop, especially when Explorer is busy.  In
# that case the new window still opens; returning an error would only show a
# misleading failure in Streamlit.
exit 0
