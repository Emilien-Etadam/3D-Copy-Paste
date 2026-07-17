Attribute VB_Name = "OD_PasteFromExternal"
' OD_CopyPasteExternal - Paste From External (SolidWorks, Parasolid side-channel)
'
' Imports the ODSolidData.x_t exchange file (docs/FORMAT.md section 7)
' written by Plasticity (File > Export > Parasolid to that path), another
' SolidWorks, or any application with native Parasolid export. The exact
' B-rep geometry opens as an imported part document.
'
' Install: Tools > Macro > New, then File > Import this .bas module
' (or paste its contents), save as OD_PasteFromExternal.swp, and bind it to
' a toolbar button or keyboard shortcut.

Option Explicit

Const swMbWarning As Long = 1
Const swMbInformation As Long = 2
Const swMbOk As Long = 2

Function ExchangeDir() As String
    Dim p As String
    p = Environ$("OD_CPE_PATH")
    If Len(p) = 0 Then p = Environ$("TEMP")
    If Right$(p, 1) <> "\" Then p = p & "\"
    ExchangeDir = p
End Function

Sub main()
    Dim swApp As Object
    Dim doc As Object
    Dim path As String
    Dim errs As Long

    Set swApp = Application.SldWorks
    path = ExchangeDir() & "ODSolidData.x_t"
    If Dir$(path) = "" Then
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: no exchange file at " & path & _
            " - copy something first (SolidWorks macro, or Plasticity File > Export > Parasolid to that path).", _
            swMbWarning, swMbOk
        Exit Sub
    End If

    Set doc = swApp.LoadFile4(path, "r", Nothing, errs)
    If doc Is Nothing Then
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: Parasolid import failed (error " & errs & ").", swMbWarning, swMbOk
    Else
        doc.ViewZoomtofit2
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: pasted " & path, swMbInformation, swMbOk
    End If
End Sub
