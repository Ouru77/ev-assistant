' E.V. silent launcher — double-click to start with no console window.
Option Explicit
Dim sh, fso, proj, ollama, electron
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' The script's own folder is the project root (portable across machines).
proj = fso.GetParentFolderName(WScript.ScriptFullName)
ollama = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Ollama\ollama.exe"
electron = proj & "\node_modules\electron\dist\electron.exe"

sh.CurrentDirectory = proj

' Start Ollama quietly (harmless if it's already running).
If fso.FileExists(ollama) Then
    sh.Run """" & ollama & """ serve", 0, False
End If

' Launch the E.V. app (no console).
If fso.FileExists(electron) Then
    sh.Run """" & electron & """ .", 0, False
Else
    MsgBox "E.V. not found. Setup may be incomplete.", 48, "E.V."
End If
