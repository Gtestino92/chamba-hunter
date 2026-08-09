REM  *****  BASIC  *****

Sub InstallChambaHunter(Optional sURL)
    Dim oSourceLibrary As Object
    Dim oDestinationLibrary As Object
    Dim sModuleSource As String

    On Error GoTo InstallError

    BasicLibraries.loadLibrary("Standard")
    oSourceLibrary = BasicLibraries.getByName("Standard")
    oDestinationLibrary = GlobalScope.BasicLibraries.getByName("Standard")

    sModuleSource = oSourceLibrary.getByName("ChambaHunterActions")

    If oDestinationLibrary.hasByName("ChambaHunterActions") Then
        oDestinationLibrary.replaceByName("ChambaHunterActions", sModuleSource)
    Else
        oDestinationLibrary.insertByName("ChambaHunterActions", sModuleSource)
    End If

    MsgBox "INSTALL OK" & Chr(10) & Chr(10) & _
        "Installed into:" & Chr(10) & _
        "My Macros -> Standard -> ChambaHunterActions" & Chr(10) & Chr(10) & _
        "Version: OPENOFFICE_ACTIONS_V1" & Chr(10) & _
        "No DB action was executed by the installer.", 64, "Chamba Hunter"
    Exit Sub

InstallError:
    MsgBox "INSTALL FAILED" & Chr(10) & Chr(10) & _
        "Error " & Err & ": " & Error$, 48, "Chamba Hunter"
End Sub
