Attribute VB_Name = "modConsumerSearch"
'==================================================================
' modConsumerSearch — populate the Search sheet with results.
'
' Search sheet expected layout:
'   A1 "Account"   B1 <input>
'   A2 "Name"      B2 <input>
'   A3 "Village"   B3 <input>
'   Header row 5: Account | Name | Father | Village | Mobile | Category
'==================================================================
Option Explicit

Public Sub SearchConsumer()
    Dim ws As Worksheet: Set ws = SheetByName("Search")
    If ws Is Nothing Then Fail "Search sheet missing": Exit Sub

    Dim qry As String, parts() As String, params As String
    Dim accountQ As String, nameQ As String, villageQ As String
    accountQ = Trim$(CStr(ws.Range("B1").Value))
    nameQ    = Trim$(CStr(ws.Range("B2").Value))
    villageQ = Trim$(CStr(ws.Range("B3").Value))

    Dim qs As String
    If Len(accountQ) > 0 Then qs = qs & "&account=" & UrlEncode(accountQ)
    If Len(nameQ)    > 0 Then qs = qs & "&name=" & UrlEncode(nameQ)
    If Len(villageQ) > 0 Then qs = qs & "&village=" & UrlEncode(villageQ)
    If Len(qs) = 0 Then
        Fail "Enter at least one search field (account / name / village)"
        Exit Sub
    End If
    qs = "?" & Mid$(qs, 2)

    Dim env As Object
    Set env = ApiGet("/api/consumers/search" & qs)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim rows As Object: Set rows = ApiData(env)
    ' Clear previous results (rows 6 onward, 6 cols)
    ClearRows ws, 6, 1000, 6

    Dim i As Long
    For i = 1 To rows.Count
        Dim r As Object: Set r = rows(i)
        ws.Cells(5 + i, 1).Value = r("account_number")
        ws.Cells(5 + i, 2).Value = r("name")
        ws.Cells(5 + i, 3).Value = r("father_name")
        ws.Cells(5 + i, 4).Value = r("village")
        ws.Cells(5 + i, 5).Value = r("mobile")
        ws.Cells(5 + i, 6).Value = r("category")
    Next i
    Info "Found " & rows.Count & " consumers."
End Sub

Private Function UrlEncode(ByVal s As String) As String
    Dim i As Long, ch As String, code As Long, out As String
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        code = AscW(ch)
        If (code >= Asc("0") And code <= Asc("9")) Or _
           (code >= Asc("A") And code <= Asc("Z")) Or _
           (code >= Asc("a") And code <= Asc("z")) Or _
           ch = "-" Or ch = "_" Or ch = "." Or ch = "~" Then
            out = out & ch
        Else
            ' UTF-8 encoding
            Dim utf8() As Byte
            utf8 = StrConv(ch, vbFromUnicode)
            Dim j As Long
            For j = 0 To UBound(utf8)
                out = out & "%" & Right$("0" & Hex$(utf8(j)), 2)
            Next j
        End If
    Next i
    UrlEncode = out
End Function
