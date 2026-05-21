Attribute VB_Name = "modReports"
'==================================================================
' modReports — trigger Excel/PDF exports.  The backend writes the file
' under backup\reports\, returns the relative download URL, and we
' just open the URL in Internet Explorer / default browser so the
' officer can save it locally.
'==================================================================
Option Explicit

Public Sub ExportCases()
    Dim env As Object: Set env = ApiGet("/api/reports/cases.xlsx")
    OpenDownload env, "Export Cases"
End Sub

Public Sub ExportPayments()
    Dim env As Object: Set env = ApiGet("/api/reports/payments.xlsx")
    OpenDownload env, "Export Payments"
End Sub

Public Sub ExportNotices()
    Dim env As Object: Set env = ApiGet("/api/reports/notices.xlsx")
    OpenDownload env, "Export Notices"
End Sub

Public Sub ExportDashboardPDF()
    Dim env As Object: Set env = ApiGet("/api/reports/dashboard.pdf")
    OpenDownload env, "Dashboard PDF"
End Sub

Private Sub OpenDownload(env As Object, ByVal title As String)
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Dim url As String: url = ApiBase() & data("download")
    Info title & " ready: " & data("file") & vbCrLf & _
         "Opening: " & url
    On Error Resume Next
    ' Attempt to open via shell (default browser)
    Dim sh As Object: Set sh = CreateObject("Shell.Application")
    sh.Open url
    On Error GoTo 0
End Sub
