Attribute VB_Name = "modCalculator"
'==================================================================
' modCalculator — collect device entries from the Devices sheet,
' POST /api/calculate, and write the breakdown into the Calc sheet.
'
' Devices sheet layout (from row 3):
'   A: Device name
'   B: Load (W)
'   C: Factor
'   D: Hours / day
'   E: Days
'   F: Units (formula-filled by VBA after server response)
'
' Calc sheet:
'   B1  case_id (mirror)         B25 grand total
'   Slab table at A8:E12, Summary at A15:B22
'==================================================================
Option Explicit

Public Sub LiveCalc()
    Dim req As Object: Set req = BuildCalcRequest()
    If req Is Nothing Then Exit Sub

    Dim env As Object
    Set env = ApiPost("/api/calculate", req)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub

    Dim data As Object: Set data = ApiData(env)
    RenderCalc data
    Info "Calculation done. Grand total = " & FormatNumber(data("grand_total"), 2)
End Sub

Public Function BuildCalcRequest() As Object
    Dim ws As Worksheet: Set ws = SheetByName("Devices")
    If ws Is Nothing Then Fail "Devices sheet missing": Exit Function

    Dim devices As New Collection
    Dim r As Long: r = 3
    Do While Len(Trim$(CStr(ws.Cells(r, 1).Value))) > 0
        Dim d As Object: Set d = NewDict()
        d("name")   = CStr(ws.Cells(r, 1).Value)
        d("load")   = CDbl(Val(ws.Cells(r, 2).Value))
        d("factor") = CDbl(Val(ws.Cells(r, 3).Value))
        d("hours")  = CDbl(Val(ws.Cells(r, 4).Value))
        d("days")   = CDbl(Val(ws.Cells(r, 5).Value))
        devices.Add d
        r = r + 1
    Loop

    If devices.Count = 0 Then
        Fail "No devices entered (Devices sheet, row 3 onwards)"
        Exit Function
    End If

    Dim req As Object: Set req = NewDict()
    req("section") = NamedStr("nrSection", "135")
    req("category") = NamedStr("nrCategory", DEFAULT_CATEGORY)
    req("connected_load_kw") = NamedDbl("nrLoadKW", 0)
    req("inspection_date") = NamedStr("nrInspectionDate", "")
    req("devices") = devices
    Set BuildCalcRequest = req
End Function

Private Sub RenderCalc(data As Object)
    Dim ws As Worksheet: Set ws = SheetByName("Calc")
    If ws Is Nothing Then Exit Sub

    Application.ScreenUpdating = False

    ' clear previous output
    ws.Range("A6:F50").ClearContents

    ws.Range("A6").Value = "Slab #"
    ws.Range("B6").Value = "From"
    ws.Range("C6").Value = "To"
    ws.Range("D6").Value = "Rate"
    ws.Range("E6").Value = "Yearly Units"
    ws.Range("F6").Value = "Amount"

    Dim energy As Object: Set energy = data("energy_charges")
    Dim slabs As Object: Set slabs = energy("slabs")
    Dim i As Long, row As Long: row = 7
    For i = 1 To slabs.Count
        Dim s As Object: Set s = slabs(i)
        ws.Cells(row, 1).Value = i
        ws.Cells(row, 2).Value = s("slab_start")
        ws.Cells(row, 3).Value = s("slab_end")
        ws.Cells(row, 4).Value = s("rate")
        ws.Cells(row, 5).Value = s("yearly_units")
        ws.Cells(row, 6).Value = s("amount")
        row = row + 1
    Next i

    Dim fixed As Object: Set fixed = data("fixed_charges")
    Dim ed As Object:    Set ed    = data("electricity_duty")

    ws.Range("A15").Value = "Total Units"
    ws.Range("B15").Value = data("total_units_after_less_unit")
    ws.Range("A16").Value = "Months"
    ws.Range("B16").Value = data("months")
    ws.Range("A17").Value = "Multiplier"
    ws.Range("B17").Value = data("multiplier")
    ws.Range("A18").Value = "Fixed (final)"
    ws.Range("B18").Value = fixed("final")
    ws.Range("A19").Value = "Energy (final)"
    ws.Range("B19").Value = energy("final")
    ws.Range("A20").Value = "ED (" & ed("ed_percent") & "%)"
    ws.Range("B20").Value = ed("amount")
    ws.Range("A22").Value = "GRAND TOTAL"
    ws.Range("B22").Value = data("grand_total")
    ws.Range("B25").Value = data("grand_total")  ' nrCalcTotal mirror

    ' Mirror per-device units back to Devices sheet column F
    Dim devSheet As Worksheet: Set devSheet = SheetByName("Devices")
    Dim devs As Object: Set devs = data("devices")
    Dim r As Long: r = 3
    For i = 1 To devs.Count
        devSheet.Cells(r + i - 1, 6).Value = devs(i)("units")
    Next i

    Application.ScreenUpdating = True
End Sub
