' E.V. sessiz başlatıcı — çift tıkla, konsol penceresi göstermeden aç.
Option Explicit
Dim sh, fso, proj, ollama, electron
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

proj = "A:\Claude Projelerim\E.V"
ollama = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Ollama\ollama.exe"
electron = proj & "\node_modules\electron\dist\electron.exe"

sh.CurrentDirectory = proj

' Ollama'yı sessizce başlat (zaten çalışıyorsa zararsız).
If fso.FileExists(ollama) Then
    sh.Run """" & ollama & """ serve", 0, False
End If

' E.V. uygulamasını başlat (konsol yok).
If fso.FileExists(electron) Then
    sh.Run """" & electron & """ .", 0, False
Else
    MsgBox "E.V. bulunamadı. Kurulum eksik olabilir.", 48, "E.V."
End If
