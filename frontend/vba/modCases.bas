Attribute VB_Name = "modCases"
'==================================================================
' modCases — refresh the Cases sheet with the most recent saved cases.
'==================================================================
Option Explicit

Public Sub RefreshCases()
    Dim ws As Worksheet: Set ws = SheetByName("Cases")
    If ws Is Nothing Then Exit Sub

    Dim env As Object
    Set env = ApiGet("/api/cases/search?limit=200")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim list As Object: Set list = ApiData(env)
    ClearRows ws, 4, 1000, 8

    Dim i As Long
    For i = 1 To list.Count
        Dim c As Object: Set c = list(i)
        ws.Cells(3 + i, 1).Value = c("case_id")
        ws.Cells(3 + i, 2).Value = c("account_number")
        ws.Cells(3 + i, 3).Value = DictGet(c, "consumer_name", _
                                           DictGet(c, "user_name", ""))
        ws.Cells(3 + i, 4).Value = c("section")
        ws.Cells(3 + i, 5).Value = c("inspection_date")
        ws.Cells(3 + i, 6).Value = c("total_assessment")
        ws.Cells(3 + i, 7).Value = c("compounding_amount")
        ws.Cells(3 + i, 8).Value = c("case_status")
    Next i
End Sub

' Double-click the case_id column to load that case as the active one.
Public Sub LoadSelectedCase()
    Dim ws As Worksheet: Set ws = SheetByName("Cases")
    If ws Is Nothing Then Exit Sub
    Dim cid As String: cid = Trim$(CStr(ActiveCell.Value))
    If Len(cid) = 0 Or Left$(cid, 3) <> "RC-" Then
        Fail "Click a Case ID cell first."
        Exit Sub
    End If
    SetNamedValue "nrCurrentCaseId", cid
    Info "Active case set to " & cid
End Sub
