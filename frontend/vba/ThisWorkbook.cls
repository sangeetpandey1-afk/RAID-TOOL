VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ThisWorkbook"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True
'==================================================================
' ThisWorkbook — runs on workbook open: pings the backend and writes
' the health status onto the Dashboard sheet so the officer immediately
' knows whether the server is reachable.
'==================================================================
Option Explicit

Private Sub Workbook_Open()
    On Error Resume Next
    CheckHealth
    On Error GoTo 0
End Sub

Public Sub CheckHealth()
    Dim ws As Worksheet: Set ws = SheetByName("Dashboard")
    If ws Is Nothing Then Exit Sub

    Dim env As Object
    Set env = ApiGet("/api/health")

    If Not ApiOk(env) Then
        ws.Range("B5").Value = "OFFLINE — " & ApiError(env)
        ws.Range("B5").Interior.Color = RGB(248, 215, 218)
        Exit Sub
    End If

    Dim data As Object: Set data = ApiData(env)
    ws.Range("B5").Value = "OK   v" & data("version") & "   " & _
                           "DB " & IIf(CBool(data("db_ok")), "ok", "FAIL")
    ws.Range("B5").Interior.Color = RGB(212, 237, 218)

    ' Refresh dashboard summary KPIs
    Set env = ApiGet("/api/dashboard/summary")
    If ApiOk(env) Then
        Dim s As Object: Set s = ApiData(env)
        ws.Range("B7").Value = s("total_cases")
        ws.Range("B8").Value = s("total_assessment")
        ws.Range("B9").Value = s("today_payment_count")
        ws.Range("B10").Value = s("today_payment_amount")
    End If
End Sub
