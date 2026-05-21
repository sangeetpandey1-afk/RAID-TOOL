Attribute VB_Name = "modNotice"
'==================================================================
' modNotice — add provisional / section3 / section5 notices and
' refresh the timeline.
'==================================================================
Option Explicit

Public Sub AddProvisionalNotice()
    AddNoticeOfKind "provisional"
End Sub

Public Sub AddSection3Notice()
    AddNoticeOfKind "section3"
End Sub

Public Sub AddSection5Notice()
    AddNoticeOfKind "section5"
End Sub

Private Sub AddNoticeOfKind(ByVal kind As String)
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then Fail "No case loaded.": Exit Sub

    Dim num As String
    num = InputBox("Notice number?", "Add " & kind & " notice", _
                   UCase$(Left$(kind, 1)) & "N-" & Format$(Now, "yyyymmdd-hhnnss"))
    If Len(num) = 0 Then Exit Sub

    Dim req As Object: Set req = NewDict()
    req("notice_type") = kind
    req("notice_number") = num
    req("user") = "vba_excel"

    Dim env As Object
    Set env = ApiPost("/api/cases/" & caseId & "/notices", req)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim data As Object: Set data = ApiData(env)
    Info "Notice added. Due date: " & data("due_date")
    RefreshNotices
End Sub

Public Sub RefreshNotices()
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then Exit Sub
    Dim ws As Worksheet: Set ws = SheetByName("Notices")
    If ws Is Nothing Then Exit Sub

    Dim env As Object: Set env = ApiGet("/api/cases/" & caseId & "/notices")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim list As Object: Set list = ApiData(env)

    ClearRows ws, 4, 200, 7
    Dim i As Long
    For i = 1 To list.Count
        Dim n As Object: Set n = list(i)
        ws.Cells(3 + i, 1).Value = n("notice_type")
        ws.Cells(3 + i, 2).Value = n("notice_number")
        ws.Cells(3 + i, 3).Value = n("notice_date")
        ws.Cells(3 + i, 4).Value = n("due_date")
        ws.Cells(3 + i, 5).Value = n("status")
        ws.Cells(3 + i, 6).Value = n("dispatch_method")
        ws.Cells(3 + i, 7).Value = n("created_at")
    Next i
End Sub
