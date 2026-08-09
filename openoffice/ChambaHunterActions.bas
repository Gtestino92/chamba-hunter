REM  *****  BASIC  *****

Sub Ping(Optional sURL)
    MsgBox "CHAMBA HUNTER MACRO OK" & Chr(10) & Chr(10) & _
        "My Macros -> Standard -> ChambaHunterActions" & Chr(10) & _
        "Version: OPENOFFICE_ACTIONS_V1" & Chr(10) & Chr(10) & _
        "No DB changes were made.", 64, "Chamba Hunter"
End Sub

Sub MarkApplied(sURL As String)
    Dim sKind As String
    Dim sId As String
    Dim sSheet As String
    Dim sRow As String
    Dim sStatusCol As String
    Dim sRoot As String
    Dim sPython As String
    Dim sResult As String
    Dim sParams As String
    Dim sLine As String
    Dim nFile As Integer
    Dim aParts()
    Dim oSheet As Object
    Dim oStatusCell As Object

    sKind = GetArgumentFromURL(sURL, "kind")
    sId = GetArgumentFromURL(sURL, "id")
    sSheet = GetArgumentFromURL(sURL, "sheet")
    sRow = GetArgumentFromURL(sURL, "row")
    sStatusCol = GetArgumentFromURL(sURL, "status_col")

    If sKind = "" Or sId = "" Or sSheet = "" Or _
        sRow = "" Or sStatusCol = "" Then
        MsgBox "Missing APPLY arguments.", 48, "Chamba Hunter"
        Exit Sub
    End If

    sRoot = FindProjectRoot()

    If sRoot = "" Then
        MsgBox "Could not locate the Chamba Hunter project root." & _
            Chr(10) & Chr(10) & _
            "Expected .venv\Scripts\python.exe above the workbook.", _
            48, "Chamba Hunter"
        Exit Sub
    End If

    sPython = sRoot & "\.venv\Scripts\python.exe"
    sResult = sRoot & "\output\.chamba-openoffice-action-result.txt"

    If FileExists(sResult) Then
        Kill sResult
    End If

    sParams = "-m chamba_hunter.commands.openoffice_mark_applied " & _
        "--record-kind " & sKind & " " & _
        "--record-id " & sId & " " & _
        "--result-file " & Q(sResult)

    On Error GoTo ShellError
    Shell(ConvertToURL(sPython), 0, sParams, True)
    On Error GoTo 0

    If Not FileExists(sResult) Then
        MsgBox "Chamba Hunter finished without a result file.", _
            48, "Chamba Hunter"
        Exit Sub
    End If

    nFile = FreeFile
    Open sResult For Input As #nFile
    If Not EOF(nFile) Then
        Line Input #nFile, sLine
    End If
    Close #nFile

    If FileExists(sResult) Then
        Kill sResult
    End If

    aParts() = Split(sLine, "|")

    If UBound(aParts()) >= 1 And aParts(0) = "OK" Then
        oSheet = ThisComponent.Sheets.getByIndex(CLng(sSheet))
        oStatusCell = oSheet.getCellByPosition( _
            CLng(sStatusCol), CLng(sRow))
        oStatusCell.String = "APPLIED"

        MsgBox "Marked APPLIED." & Chr(10) & Chr(10) & _
            "Record Kind: " & sKind & Chr(10) & _
            "Record ID: " & sId, 64, "Chamba Hunter"
        Exit Sub
    End If

    If UBound(aParts()) >= 2 And aParts(0) = "ERROR" Then
        MsgBox "Could not mark APPLIED." & Chr(10) & Chr(10) & _
            aParts(1) & ": " & aParts(2), 48, "Chamba Hunter"
    Else
        MsgBox "Unexpected Chamba Hunter result:" & Chr(10) & _
            sLine, 48, "Chamba Hunter"
    End If
    Exit Sub

ShellError:
    MsgBox "Could not start Chamba Hunter Python." & Chr(10) & _
        "Error " & Err & ": " & Error$, 48, "Chamba Hunter"
End Sub

Function FindProjectRoot() As String
    Dim sPath As String
    Dim sCurrent As String
    Dim sPython As String
    Dim i As Integer

    FindProjectRoot = ""

    sPath = ConvertFromURL(ThisComponent.URL)
    sCurrent = ParentPath(sPath)

    For i = 0 To 8
        If sCurrent = "" Then Exit Function

        sPython = sCurrent & "\.venv\Scripts\python.exe"

        If FileExists(sPython) Then
            FindProjectRoot = sCurrent
            Exit Function
        End If

        sCurrent = ParentPath(sCurrent)
    Next i
End Function

Function ParentPath(sValue As String) As String
    Dim i As Integer

    ParentPath = ""

    For i = Len(sValue) To 1 Step -1
        If Mid(sValue, i, 1) = "\" Or Mid(sValue, i, 1) = "/" Then
            If i > 1 Then
                ParentPath = Left(sValue, i - 1)
            End If
            Exit Function
        End If
    Next i
End Function

Function Q(sValue As String) As String
    Q = Chr(34) & sValue & Chr(34)
End Function

Function GetArgumentFromURL(sURL As String, sName As String) As String
    Dim iStart As Integer
    Dim i As Integer
    Dim nNameLength As Integer
    Dim sArgs As String
    Dim aArgs()

    GetArgumentFromURL = ""
    iStart = InStr(sURL, "?")
    nNameLength = Len(sName)

    If iStart = 0 Or nNameLength = 0 Then Exit Function

    sArgs = Mid(sURL, iStart + 1)
    aArgs() = Split(sArgs, "&")

    For i = 0 To UBound(aArgs())
        If InStr(1, aArgs(i), sName & "=", 1) = 1 Then
            GetArgumentFromURL = Mid(aArgs(i), nNameLength + 2)
            Exit Function
        End If
    Next i
End Function
