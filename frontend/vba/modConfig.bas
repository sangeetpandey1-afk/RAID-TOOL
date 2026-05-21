Attribute VB_Name = "modConfig"
'==================================================================
' modConfig — central configuration for the Excel VBA front-end.
'
' All other modules read the API base URL from the named range
' `nrApiBase` on the Settings sheet so the user can switch between
' localhost / LAN / staging without editing code.
'==================================================================
Option Explicit

Public Const APP_NAME As String = "Raid Management System"
Public Const APP_VERSION As String = "1.0.0"

Public Const DEFAULT_API_BASE As String = "http://127.0.0.1:5000"
Public Const HTTP_TIMEOUT_MS As Long = 30000   ' 30 seconds

' Default values prefilled into Inputs when a new case starts
Public Const DEFAULT_CATEGORY As String = "LMV-1"
Public Const DEFAULT_SECTION As String = "135"

Public Function ApiBase() As String
    Dim v As Variant
    On Error Resume Next
    v = ThisWorkbook.Names("nrApiBase").RefersToRange.Value
    On Error GoTo 0
    If Len(CStr(v)) = 0 Then
        ApiBase = DEFAULT_API_BASE
    Else
        ApiBase = CStr(v)
        ' strip trailing slash
        If Right$(ApiBase, 1) = "/" Then
            ApiBase = Left$(ApiBase, Len(ApiBase) - 1)
        End If
    End If
End Function

' Read a named range as a String, defaulting to "" if missing/empty.
Public Function NamedStr(name As String, Optional ByVal default As String = "") As String
    Dim v As Variant
    On Error Resume Next
    v = ThisWorkbook.Names(name).RefersToRange.Value
    On Error GoTo 0
    If IsEmpty(v) Or IsNull(v) Then
        NamedStr = default
    Else
        NamedStr = Trim$(CStr(v))
    End If
End Function

' Read a named range as a Double, defaulting to 0.
Public Function NamedDbl(name As String, Optional ByVal default As Double = 0#) As Double
    Dim s As String: s = NamedStr(name, "")
    If Len(s) = 0 Or Not IsNumeric(s) Then
        NamedDbl = default
    Else
        NamedDbl = CDbl(s)
    End If
End Function

Public Sub SetNamedValue(name As String, value As Variant)
    On Error Resume Next
    ThisWorkbook.Names(name).RefersToRange.Value = value
    On Error GoTo 0
End Sub
