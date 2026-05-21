Attribute VB_Name = "modImport"
'==================================================================
' modImport — wraps the previously-broken import endpoint.
' /api/import_all_master_data now returns a structured ImportReport
' instead of a silent HTTP 500.
'==================================================================
Option Explicit

Public Sub ImportAllMaster()
    Dim env As Object: Set env = ApiPost("/api/import_all_master_data")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Dim reports As Object: Set reports = data("reports")

    Dim ws As Worksheet: Set ws = SheetByName("Dashboard")
    Dim row As Long: row = 16

    ' write header
    ws.Cells(row, 1).Value = "Kind"
    ws.Cells(row, 2).Value = "Total"
    ws.Cells(row, 3).Value = "Inserted"
    ws.Cells(row, 4).Value = "Updated"
    ws.Cells(row, 5).Value = "Skipped"
    ws.Cells(row, 6).Value = "Errors"
    ws.Cells(row, 7).Value = "Warnings"
    row = row + 1

    Dim k As Variant
    Dim total As Long, inserted As Long, errors As Long
    For Each k In reports.Keys
        Dim r As Object: Set r = reports(k)
        ws.Cells(row, 1).Value = k
        ws.Cells(row, 2).Value = r("total_rows")
        ws.Cells(row, 3).Value = r("inserted")
        ws.Cells(row, 4).Value = r("updated")
        ws.Cells(row, 5).Value = r("skipped")
        ws.Cells(row, 6).Value = r("error_count")
        Dim warns As Object: Set warns = r("warnings")
        ws.Cells(row, 7).Value = IIf(warns Is Nothing, "", _
                                     Join(CollToArr(warns), " | "))
        total = total + CLng(r("total_rows"))
        inserted = inserted + CLng(r("inserted"))
        errors = errors + CLng(r("error_count"))
        row = row + 1
    Next k

    Info "Import done." & vbCrLf & _
         "Total rows: " & total & vbCrLf & _
         "Inserted: " & inserted & vbCrLf & _
         "Errors: " & errors
End Sub

Private Function CollToArr(c As Collection) As Variant
    Dim arr() As String
    If c Is Nothing Then CollToArr = Array(): Exit Function
    If c.Count = 0 Then CollToArr = Array(): Exit Function
    ReDim arr(0 To c.Count - 1)
    Dim i As Long
    For i = 1 To c.Count
        arr(i - 1) = CStr(c(i))
    Next i
    CollToArr = arr
End Function
