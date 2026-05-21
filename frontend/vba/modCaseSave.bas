Attribute VB_Name = "modCaseSave"
'==================================================================
' modCaseSave — collect inputs + devices + flags and POST /api/cases.
'==================================================================
Option Explicit

Public Sub SaveCase()
    Dim req As Object: Set req = BuildCaseRequest()
    If req Is Nothing Then Exit Sub

    Dim env As Object
    Set env = ApiPost("/api/cases", req)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim data As Object: Set data = ApiData(env)
    Dim caseObj As Object: Set caseObj = data("case")
    SetNamedValue "nrCurrentCaseId", caseObj("case_id")
    Info "Case saved (" & data("action") & "): " & caseObj("case_id") & _
         vbCrLf & "Total assessment: " & FormatNumber(caseObj("total_assessment"), 2)
End Sub

Public Function BuildCaseRequest() As Object
    Dim req As Object: Set req = NewDict()
    req("account_number") = NamedStr("nrAccount")
    If Len(req("account_number")) = 0 Then
        Fail "Account number is required (Inputs!B3 / nrAccount)"
        Exit Function
    End If

    req("name")          = NamedStr("nrName")
    req("father_name")   = NamedStr("nrFather")
    req("village")       = NamedStr("nrVillage")
    req("post_office")   = NamedStr("nrPost")
    req("pin_code")      = NamedStr("nrPin")
    req("mobile")        = NamedStr("nrMobile")
    req("section")       = NamedStr("nrSection", DEFAULT_SECTION)
    req("inspection_date") = NamedStr("nrInspectionDate")
    req("category")      = NamedStr("nrCategory", DEFAULT_CATEGORY)
    req("connected_load_kw") = NamedDbl("nrLoadKW", 0)
    req("je_name")       = NamedStr("nrJE")
    req("sub_substation") = NamedStr("nrSubStation")
    req("checking_type") = NamedStr("nrCheckingType")
    req("supply_type")   = "Domestic"
    req("calculate_compounding") = True
    req("created_by")    = "vba_excel"

    ' Devices
    Dim calc As Object: Set calc = BuildCalcRequest()
    If calc Is Nothing Then Exit Function
    req("devices") = calc("devices")

    Set BuildCaseRequest = req
End Function

Public Sub OffenseCheck()
    Dim acct As String: acct = NamedStr("nrAccount")
    If Len(acct) = 0 Then
        Fail "Enter an account number first (Inputs!B3)"
        Exit Sub
    End If
    Dim env As Object: Set env = ApiGet("/api/consumers/" & acct & "/offense-check")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Dim hist As Object: Set hist = data("history")

    Dim msg As String
    msg = "Account: " & acct & vbCrLf & _
          "Total previous offenses: " & hist("total_offenses") & vbCrLf & _
          "Repeat offender: " & data("is_repeat_offender") & vbCrLf & _
          "Suggested multiplier: " & data("suggested_multiplier") & "x" & vbCrLf & _
          "First offense date: " & hist("first_offense_date") & vbCrLf & _
          "Last offense date: " & hist("last_offense_date")
    Info msg
End Sub
