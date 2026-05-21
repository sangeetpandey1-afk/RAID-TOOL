Attribute VB_Name = "modOffense"
'==================================================================
' modOffense — multi-level offense check on the active account.
' (Already in modCaseSave but exposed here as a standalone macro
'  so a button on the Search sheet can call it independently.)
'==================================================================
Option Explicit

Public Sub OffenseCheckOnSelected()
    Dim ws As Worksheet: Set ws = SheetByName("Search")
    If ws Is Nothing Then Exit Sub
    Dim acct As String
    On Error Resume Next
    acct = Trim$(CStr(ActiveCell.Value))
    On Error GoTo 0
    If Len(acct) = 0 Then
        Fail "Click an account number cell on the Search sheet first."
        Exit Sub
    End If
    Dim env As Object: Set env = ApiGet("/api/consumers/" & acct & "/offense-check")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Dim hist As Object: Set hist = data("history")

    Info "Account: " & acct & vbCrLf & _
         "Previous offenses: " & hist("total_offenses") & vbCrLf & _
         "Repeat: " & data("is_repeat_offender") & vbCrLf & _
         "Suggested multiplier: " & data("suggested_multiplier") & "x"
End Sub
