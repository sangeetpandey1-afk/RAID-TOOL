Attribute VB_Name = "modJson"
'==================================================================
' modJson — minimal JSON encoder / decoder for VBA.
'
' Public API:
'   JsonStringify(value)          -> string
'   JsonParse(text)               -> Variant (Dictionary/Collection/scalar)
'   NewDict()                     -> Scripting.Dictionary
'   DictGet(d, key, default)      -> Variant
'
' Late-bound everywhere; no Tools->References needed.
'==================================================================
Option Explicit

Public Function NewDict() As Object
    Set NewDict = CreateObject("Scripting.Dictionary")
End Function

Public Function DictGet(d As Object, ByVal key As String, _
                        Optional ByVal default As Variant = "") As Variant
    On Error Resume Next
    If d Is Nothing Then DictGet = default: Exit Function
    If TypeName(d) = "Dictionary" Then
        If d.Exists(key) Then
            DictGet = d(key)
        Else
            DictGet = default
        End If
    Else
        DictGet = default
    End If
    On Error GoTo 0
End Function

'----------------------------------------------------------- Stringify
Public Function JsonStringify(ByVal value As Variant) As String
    JsonStringify = jsEncode(value)
End Function

Private Function jsEncode(ByVal v As Variant) As String
    If IsNull(v) Or IsEmpty(v) Then
        jsEncode = "null"
        Exit Function
    End If
    If IsArray(v) Then
        jsEncode = jsEncodeArray(v)
        Exit Function
    End If
    If IsObject(v) Then
        Select Case TypeName(v)
            Case "Dictionary"
                jsEncode = jsEncodeDict(v)
            Case "Collection"
                jsEncode = jsEncodeCollection(v)
            Case Else
                jsEncode = "null"
        End Select
        Exit Function
    End If
    Select Case VarType(v)
        Case vbBoolean: jsEncode = LCase$(CStr(v))
        Case vbInteger, vbLong, vbSingle, vbDouble, vbCurrency, vbDecimal
            jsEncode = Replace$(CStr(v), ",", ".")  ' locale safety
        Case vbString:  jsEncode = jsString(CStr(v))
        Case vbDate:    jsEncode = jsString(Format$(v, "yyyy-mm-dd"))
        Case Else:      jsEncode = jsString(CStr(v))
    End Select
End Function

Private Function jsEncodeDict(d As Object) As String
    Dim parts As String, k As Variant, first As Boolean: first = True
    parts = "{"
    For Each k In d.Keys
        If Not first Then parts = parts & ","
        parts = parts & jsString(CStr(k)) & ":" & jsEncode(d(k))
        first = False
    Next k
    jsEncodeDict = parts & "}"
End Function

Private Function jsEncodeCollection(c As Collection) As String
    Dim parts As String, i As Long, first As Boolean: first = True
    parts = "["
    For i = 1 To c.Count
        If Not first Then parts = parts & ","
        parts = parts & jsEncode(c(i))
        first = False
    Next i
    jsEncodeCollection = parts & "]"
End Function

Private Function jsEncodeArray(arr As Variant) As String
    Dim parts As String, i As Long, first As Boolean: first = True
    parts = "["
    For i = LBound(arr) To UBound(arr)
        If Not first Then parts = parts & ","
        parts = parts & jsEncode(arr(i))
        first = False
    Next i
    jsEncodeArray = parts & "]"
End Function

Private Function jsString(s As String) As String
    Dim out As String, i As Long, ch As String, code As Long
    out = """"
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        code = AscW(ch)
        If code = -1 Then code = Asc(ch)
        Select Case code
            Case 34: out = out & "\"""
            Case 92: out = out & "\\"
            Case 8:  out = out & "\b"
            Case 9:  out = out & "\t"
            Case 10: out = out & "\n"
            Case 12: out = out & "\f"
            Case 13: out = out & "\r"
            Case 0 To 31: out = out & "\u" & jsHex4(code)
            Case Else
                If code < 0 Then code = code + 65536&
                If code > 127 Then
                    out = out & "\u" & jsHex4(code)
                Else
                    out = out & ch
                End If
        End Select
    Next i
    jsString = out & """"
End Function

Private Function jsHex4(ByVal code As Long) As String
    Dim h As String: h = Hex$(code)
    jsHex4 = String$(4 - Len(h), "0") & h
End Function

'------------------------------------------------------------- Parse
' A small recursive-descent parser. Returns Dictionary / Collection / scalar.
Private gJsTxt As String
Private gJsPos As Long

Public Function JsonParse(ByVal txt As String) As Variant
    gJsTxt = txt
    gJsPos = 1
    jsSkip
    If gJsPos > Len(gJsTxt) Then
        JsonParse = Empty
    Else
        JsonParse = jsValue()
    End If
End Function

Private Sub jsSkip()
    Do While gJsPos <= Len(gJsTxt)
        Select Case Mid$(gJsTxt, gJsPos, 1)
            Case " ", vbTab, vbCr, vbLf
                gJsPos = gJsPos + 1
            Case Else
                Exit Sub
        End Select
    Loop
End Sub

Private Function jsValue() As Variant
    jsSkip
    Dim ch As String: ch = Mid$(gJsTxt, gJsPos, 1)
    Select Case ch
        Case "{"
            Set jsValue = jsObject()
        Case "["
            Set jsValue = jsArray()
        Case """"
            jsValue = jsStringP()
        Case "t", "f"
            jsValue = jsBool()
        Case "n"
            jsValue = jsNull()
        Case Else
            jsValue = jsNumber()
    End Select
End Function

Private Function jsObject() As Object
    Dim d As Object: Set d = NewDict()
    gJsPos = gJsPos + 1   ' consume {
    jsSkip
    If Mid$(gJsTxt, gJsPos, 1) = "}" Then
        gJsPos = gJsPos + 1
        Set jsObject = d
        Exit Function
    End If
    Do
        jsSkip
        Dim k As String: k = jsStringP()
        jsSkip
        gJsPos = gJsPos + 1   ' consume :
        Dim v As Variant
        v = jsValue()
        d(k) = v
        jsSkip
        If Mid$(gJsTxt, gJsPos, 1) = "," Then
            gJsPos = gJsPos + 1
        Else
            Exit Do
        End If
    Loop
    jsSkip
    gJsPos = gJsPos + 1   ' consume }
    Set jsObject = d
End Function

Private Function jsArray() As Collection
    Dim c As New Collection
    gJsPos = gJsPos + 1   ' consume [
    jsSkip
    If Mid$(gJsTxt, gJsPos, 1) = "]" Then
        gJsPos = gJsPos + 1
        Set jsArray = c
        Exit Function
    End If
    Do
        Dim v As Variant
        v = jsValue()
        If IsObject(v) Then c.Add v Else c.Add v
        jsSkip
        If Mid$(gJsTxt, gJsPos, 1) = "," Then
            gJsPos = gJsPos + 1
        Else
            Exit Do
        End If
    Loop
    jsSkip
    gJsPos = gJsPos + 1   ' consume ]
    Set jsArray = c
End Function

Private Function jsStringP() As String
    gJsPos = gJsPos + 1   ' opening "
    Dim out As String, ch As String
    Do While gJsPos <= Len(gJsTxt)
        ch = Mid$(gJsTxt, gJsPos, 1)
        If ch = """" Then
            gJsPos = gJsPos + 1
            jsStringP = out
            Exit Function
        ElseIf ch = "\" Then
            gJsPos = gJsPos + 1
            Dim esc As String: esc = Mid$(gJsTxt, gJsPos, 1)
            Select Case esc
                Case """": out = out & """"
                Case "\":  out = out & "\"
                Case "/":  out = out & "/"
                Case "b":  out = out & Chr$(8)
                Case "t":  out = out & vbTab
                Case "n":  out = out & vbLf
                Case "f":  out = out & Chr$(12)
                Case "r":  out = out & vbCr
                Case "u"
                    Dim hex4 As String
                    hex4 = Mid$(gJsTxt, gJsPos + 1, 4)
                    out = out & ChrW$(CLng("&H" & hex4))
                    gJsPos = gJsPos + 4
            End Select
            gJsPos = gJsPos + 1
        Else
            out = out & ch
            gJsPos = gJsPos + 1
        End If
    Loop
    jsStringP = out
End Function

Private Function jsBool() As Boolean
    If Mid$(gJsTxt, gJsPos, 4) = "true" Then
        gJsPos = gJsPos + 4
        jsBool = True
    Else
        gJsPos = gJsPos + 5
        jsBool = False
    End If
End Function

Private Function jsNull() As Variant
    gJsPos = gJsPos + 4
    jsNull = Null
End Function

Private Function jsNumber() As Variant
    Dim startP As Long: startP = gJsPos
    Dim ch As String
    Do While gJsPos <= Len(gJsTxt)
        ch = Mid$(gJsTxt, gJsPos, 1)
        If ch Like "[0-9]" Or ch = "-" Or ch = "+" Or ch = "." _
           Or ch = "e" Or ch = "E" Then
            gJsPos = gJsPos + 1
        Else
            Exit Do
        End If
    Loop
    Dim s As String: s = Mid$(gJsTxt, startP, gJsPos - startP)
    If InStr(s, ".") > 0 Or InStr(s, "e") > 0 Or InStr(s, "E") > 0 Then
        jsNumber = CDbl(s)
    Else
        jsNumber = CLng(s)
    End If
End Function
