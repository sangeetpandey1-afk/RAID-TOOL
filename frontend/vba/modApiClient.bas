Attribute VB_Name = "modApiClient"
'==================================================================
' modApiClient — late-bound HTTP client.
'
' Public API:
'   ApiGet(path)       -> Dictionary (parsed envelope)
'   ApiPost(path, dict)-> Dictionary
'   ApiOk(env)         -> Boolean
'   ApiData(env)       -> Variant   (env("data"))
'   ApiError(env)      -> String    (env("error"))
'==================================================================
Option Explicit

Public Function ApiGet(ByVal path As String) As Object
    Set ApiGet = HttpRequest("GET", path, Nothing)
End Function

Public Function ApiPost(ByVal path As String, _
                        Optional ByVal body As Object) As Object
    Set ApiPost = HttpRequest("POST", path, body)
End Function

Public Function ApiOk(env As Object) As Boolean
    On Error Resume Next
    ApiOk = False
    If env Is Nothing Then Exit Function
    If TypeName(env) <> "Dictionary" Then Exit Function
    If env.Exists("ok") Then ApiOk = CBool(env("ok"))
    On Error GoTo 0
End Function

Public Function ApiData(env As Object) As Variant
    If env Is Nothing Then ApiData = Empty: Exit Function
    If env.Exists("data") Then
        If IsObject(env("data")) Then
            Set ApiData = env("data")
        Else
            ApiData = env("data")
        End If
    Else
        ApiData = Empty
    End If
End Function

Public Function ApiError(env As Object) As String
    If env Is Nothing Then ApiError = "no response": Exit Function
    If env.Exists("error") Then
        ApiError = CStr(env("error"))
    ElseIf env.Exists("_network_error") Then
        ApiError = "Network: " & CStr(env("_network_error"))
    Else
        ApiError = "unknown error"
    End If
End Function

'-------------------------------------------------------------- core
Private Function HttpRequest(ByVal method As String, _
                             ByVal path As String, _
                             ByVal body As Object) As Object
    Dim url As String
    If Left$(path, 4) = "http" Then
        url = path
    Else
        url = ApiBase() & path
    End If

    Dim http As Object
    Set http = CreateObject("MSXML2.XMLHTTP.6.0")

    On Error GoTo HttpFail
    http.Open method, url, False
    http.setRequestHeader "Content-Type", "application/json; charset=utf-8"
    http.setRequestHeader "Accept", "application/json"
    If body Is Nothing Then
        http.send
    Else
        http.send JsonStringify(body)
    End If
    On Error GoTo 0

    Dim raw As String: raw = http.responseText
    Dim parsed As Variant
    parsed = JsonParse(raw)
    If IsObject(parsed) Then
        Set HttpRequest = parsed
    Else
        ' non-object response — wrap so callers always get a Dictionary
        Set HttpRequest = NewDict()
        HttpRequest("ok") = False
        HttpRequest("error") = "Non-JSON response (HTTP " & http.Status & ")"
        HttpRequest("_raw") = raw
    End If
    Exit Function

HttpFail:
    Dim e As Object
    Set e = NewDict()
    e("ok") = False
    e("error") = "Network error: " & Err.Description
    e("_network_error") = Err.Description
    Set HttpRequest = e
End Function
