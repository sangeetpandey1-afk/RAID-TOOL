Attribute VB_Name = "modBackup"
'==================================================================
' modBackup — trigger /api/backup/now and show the result.
'==================================================================
Option Explicit

Public Sub RunBackup()
    Dim env As Object: Set env = ApiPost("/api/backup/now", NewDict())
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim data As Object: Set data = ApiData(env)
    Dim files As Object: Set files = data("files")

    Dim msg As String
    msg = "Backup created: " & data("zip_name") & vbCrLf & _
          "Size: " & FormatNumber(data("zip_size") / 1024, 1) & " KB" & vbCrLf & _
          "Files — DB: " & files("db") & "   master_data: " & files("master_data") & _
          "   docs: " & files("docs") & vbCrLf

    Dim gd As Object: Set gd = data("gdrive")
    If Not gd Is Nothing Then
        If CBool(gd("ok")) Then
            msg = msg & "Google Drive: uploaded (" & gd("drive_link") & ")"
        Else
            msg = msg & "Google Drive: skipped (" & gd("reason") & ")"
        End If
    End If
    Info msg
End Sub

Public Sub ListBackups()
    Dim env As Object: Set env = ApiGet("/api/backup/list")
    If Not ApiOk(env) Then ShowApiError env: Exit Sub
    Dim list As Object: Set list = ApiData(env)
    Dim msg As String, i As Long
    msg = list.Count & " backups in backup/:" & vbCrLf
    For i = 1 To list.Count
        Dim b As Object: Set b = list(i)
        msg = msg & b("name") & "  (" & FormatNumber(b("size_kb"), 1) & " KB)  " & _
              b("modified") & vbCrLf
    Next i
    Info msg
End Sub
