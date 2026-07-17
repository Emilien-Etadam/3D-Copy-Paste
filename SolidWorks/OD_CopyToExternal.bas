Attribute VB_Name = "OD_CopyToExternal"
' OD_CopyPasteExternal - Copy To External (SolidWorks, Parasolid side-channel)
'
' Exports the active part or assembly to the ODSolidData.x_t exchange file
' (see docs/FORMAT.md section 7: the B-rep side-channel). Any application
' with native Parasolid import - Plasticity, Rhino, another SolidWorks -
' can then paste the exact CAD geometry, no tessellation involved.
'
' Install: Tools > Macro > New, then File > Import this .bas module
' (or paste its contents), save as OD_CopyToExternal.swp, and bind it to a
' toolbar button or keyboard shortcut.

Option Explicit

' SolidWorks constants (literal values so no type-library reference is needed)
Const swDocPART As Long = 1
Const swDocASSEMBLY As Long = 2
Const swSaveAsCurrentVersion As Long = 0
Const swSaveAsOptions_Silent As Long = 1
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
    Dim errs As Long, warns As Long
    Dim ok As Boolean

    Set swApp = Application.SldWorks
    Set doc = swApp.ActiveDoc
    If doc Is Nothing Then
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: no active document.", swMbWarning, swMbOk
        Exit Sub
    End If
    If doc.GetType <> swDocPART And doc.GetType <> swDocASSEMBLY Then
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: open a part or assembly (drawings cannot be copied).", swMbWarning, swMbOk
        Exit Sub
    End If

    path = ExchangeDir() & "ODSolidData.x_t"
    ok = doc.Extension.SaveAs3(path, swSaveAsCurrentVersion, swSaveAsOptions_Silent, Nothing, Nothing, errs, warns)
    If ok Then
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: copied to " & path, swMbInformation, swMbOk
    Else
        swApp.SendMsgToUser2 "OD_CopyPasteExternal: Parasolid export failed (error " & errs & ").", swMbWarning, swMbOk
    End If
End Sub
