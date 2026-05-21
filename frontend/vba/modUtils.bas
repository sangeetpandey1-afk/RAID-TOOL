Attribute VB_Name = "modUtils"
'==================================================================
' modUtils — small helpers used across the workbook.
'==================================================================
Option Explicit

Public Sub Info(ByVal msg As String, Optional title As String = "Raid System")
    MsgBox msg, vbInformation, title
End Sub

Public Sub Warn(ByVal msg As String, Optional title As String = "Raid System")
    MsgBox msg, vbExclamation, title
End Sub

Public Sub Fail(ByVal msg As String, Optional title As String = "Raid System")
    MsgBox msg, vbCritical, title
End Sub

' Print API error from envelope, return False so callers can early-exit.
Public Function ShowApiError(env As Object) As Boolean
    Fail "API error: " & ApiError(env)
    ShowApiError = False
End Function

Public Function SheetByName(ByVal name As String) As Worksheet
    On Error Resume Next
    Set SheetByName = ThisWorkbook.Worksheets(name)
    On Error GoTo 0
End Function

' Clear a rectangle from row..endRow (inclusive) on a sheet.
Public Sub ClearRows(ws As Worksheet, ByVal startRow As Long, _
                     ByVal endRow As Long, ByVal lastCol As Long)
    If endRow < startRow Then Exit Sub
    ws.Range(ws.Cells(startRow, 1), ws.Cells(endRow, lastCol)).ClearContents
End Sub

Public Function NowStamp() As String
    NowStamp = Format$(Now, "yyyy-mm-dd hh:nn:ss")
End Function

' Read a 2-D table from a sheet starting at startRow until first blank
' anchor cell in column 1. Returns a Collection of Dictionaries.
Public Function ReadTableAsList(ws As Worksheet, ByVal startRow As Long, _
                                ByRef headers() As String) As Collection
    Dim out As New Collection, r As Long, i As Long
    r = startRow
    Do While Len(Trim$(CStr(ws.Cells(r, 1).Value))) > 0
        Dim d As Object: Set d = NewDict()
        For i = LBound(headers) To UBound(headers)
            d(headers(i)) = ws.Cells(r, i + 1).Value
        Next i
        out.Add d
        r = r + 1
    Loop
    Set ReadTableAsList = out
End Function
