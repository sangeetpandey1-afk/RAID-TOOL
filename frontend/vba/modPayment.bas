Attribute VB_Name = "modPayment"
'==================================================================
' modPayment — record a payment against the current case and pull the
' latest list onto the Payments sheet.
'==================================================================
Option Explicit

Public Sub RecordPayment()
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then Fail "No case loaded.": Exit Sub

    Dim amtS As String, recpt As String, mode As String, comp As String
    amtS  = InputBox("Amount?", "Record Payment", "")
    If Len(amtS) = 0 Or Not IsNumeric(amtS) Then Exit Sub
    recpt = InputBox("Receipt number?", "Record Payment", "")
    mode  = InputBox("Method (cash/online/cheque)?", "Record Payment", "cash")
    comp  = InputBox("Component (assessment/compounding/admin)?", _
                     "Record Payment", "assessment")

    Dim req As Object: Set req = NewDict()
    req("amount") = CDbl(amtS)
    req("receipt_number") = recpt
    req("payment_method") = mode
    req("component") = comp
    req("payment_type") = "partial"
    req("user") = "vba_excel"

    Dim env As Object
    Set env = ApiPost("/api/cases/" & caseId & "/payments", req)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim data As Object: Set data = ApiData(env)
    Dim summary As Object: Set summary = data("summary")
    Info "Payment recorded. Total paid: " & FormatNumber(summary("total_paid"), 2) & _
         vbCrLf & "Balance: " & FormatNumber(summary("balance"), 2) & _
         vbCrLf & "Status: " & data("case_status")

    RefreshPayments
End Sub

Public Sub RefreshPayments()
    Dim caseId As String: caseId = NamedStr("nrCurrentCaseId")
    If Len(caseId) = 0 Then Exit Sub
    Dim ws As Worksheet: Set ws = SheetByName("Payments")
    If ws Is Nothing Then Exit Sub

    Dim env As Object: Set env = ApiGet("/api/cases/" & caseId & "/payments")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)

    ClearRows ws, 4, 500, 7
    Dim list As Object: Set list = data("payments")
    Dim i As Long
    For i = 1 To list.Count
        Dim p As Object: Set p = list(i)
        ws.Cells(3 + i, 1).Value = p("payment_date")
        ws.Cells(3 + i, 2).Value = p("amount")
        ws.Cells(3 + i, 3).Value = p("payment_type")
        ws.Cells(3 + i, 4).Value = p("component")
        ws.Cells(3 + i, 5).Value = p("receipt_number")
        ws.Cells(3 + i, 6).Value = p("payment_method")
        ws.Cells(3 + i, 7).Value = p("remarks")
    Next i
End Sub
