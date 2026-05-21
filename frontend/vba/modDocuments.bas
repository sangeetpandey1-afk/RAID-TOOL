Attribute VB_Name = "modDocuments"
'==================================================================
' modDocuments — generate one or all documents for the current case.
'==================================================================
Option Explicit

Private Const ALL_KINDS As String = _
    "provisional_consumer,provisional_office,section3,section5," & _
    "thanedari,deposit_slip,envelope,compounding_order,noc"

Public Sub GenerateAllDocuments()
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then
        Fail "No case loaded. Save a case first or set Cases!B1 to a case_id."
        Exit Sub
    End If

    Dim parts() As String: parts = Split(ALL_KINDS, ",")
    Dim i As Long, ok As Long, fail As Long
    Dim summary As String
    For i = 0 To UBound(parts)
        Dim env As Object
        Set env = ApiPost("/api/cases/" & caseId & "/document/" & parts(i), NewDict())
        If ApiOk(env) Then
            ok = ok + 1
            summary = summary & "[OK] " & parts(i) & vbCrLf
        Else
            fail = fail + 1
            summary = summary & "[FAIL] " & parts(i) & ": " & ApiError(env) & vbCrLf
        End If
    Next i

    Info "Documents for " & caseId & ":" & vbCrLf & vbCrLf & summary & _
         vbCrLf & "OK: " & ok & "   FAIL: " & fail & vbCrLf & vbCrLf & _
         "Files saved under: docs\" & caseId & "\"
End Sub

Public Sub GenerateOneDocument()
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then
        Fail "No case loaded."
        Exit Sub
    End If
    Dim kind As String
    kind = InputBox("Document kind?" & vbCrLf & "(provisional_consumer / " & _
                    "provisional_office / section3 / section5 / thanedari / " & _
                    "deposit_slip / envelope / compounding_order / noc)", _
                    "Generate Document", "provisional_consumer")
    If Len(kind) = 0 Then Exit Sub
    Dim env As Object
    Set env = ApiPost("/api/cases/" & caseId & "/document/" & kind, NewDict())
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Info "Generated: " & data("file_path")
End Sub
