' =================================================================
' import_vba.vbs — one-click VBA importer for RaidSystem.
'
' What it does:
'   1. Opens (or creates) frontend\RaidSystem.xlsm
'   2. Removes any previously-imported modules with the same names
'   3. Imports every .bas / .cls / .frm in frontend\vba\
'   4. Saves the workbook as .xlsm and exits
'
' Usage (Windows, double-click or from cmd):
'     cscript //nologo frontend\import_vba.vbs
'
' Pre-requisites:
'   * Microsoft Excel installed
'   * Trust Center -> Macro Settings -> "Trust access to the VBA project
'     object model" must be enabled (one-time, manual step Excel forces).
' =================================================================
Option Explicit

Const xlOpenXMLWorkbookMacroEnabled = 52   ' .xlsm

Dim fso, shell, scriptDir, repoRoot, frontendDir, vbaDir
Dim sourceXlsx, targetXlsm
Dim excel, wb

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir   = fso.GetParentFolderName(WScript.ScriptFullName)
frontendDir = scriptDir
repoRoot    = fso.GetParentFolderName(scriptDir)
vbaDir      = fso.BuildPath(frontendDir, "vba")

sourceXlsx  = fso.BuildPath(frontendDir, "RaidSystem.xlsx")
targetXlsm  = fso.BuildPath(frontendDir, "RaidSystem.xlsm")

If Not fso.FolderExists(vbaDir) Then
    WScript.Echo "ERROR: vba folder not found at: " & vbaDir
    WScript.Quit 1
End If

' Build the .xlsx if it isn't there yet
If Not fso.FileExists(sourceXlsx) Then
    WScript.Echo "RaidSystem.xlsx not found, building it..."
    Dim cmd
    cmd = "cmd /c cd /d """ & repoRoot & """ && python frontend\build_xlsm.py"
    shell.Run cmd, 1, True
End If

If Not fso.FileExists(sourceXlsx) Then
    WScript.Echo "ERROR: build_xlsm.py did not produce RaidSystem.xlsx"
    WScript.Quit 2
End If

' Open Excel
On Error Resume Next
Set excel = CreateObject("Excel.Application")
If Err.Number <> 0 Then
    WScript.Echo "ERROR: cannot start Excel.  Is Microsoft Excel installed?"
    WScript.Quit 3
End If
On Error GoTo 0

excel.Visible = False
excel.DisplayAlerts = False

' Open the source workbook (or existing .xlsm if already converted)
Dim openTarget
If fso.FileExists(targetXlsm) Then
    openTarget = targetXlsm
Else
    openTarget = sourceXlsx
End If

WScript.Echo "Opening " & openTarget & " ..."
On Error Resume Next
Set wb = excel.Workbooks.Open(openTarget)
If Err.Number <> 0 Then
    WScript.Echo "ERROR: could not open workbook: " & Err.Description
    excel.Quit
    WScript.Quit 4
End If
On Error GoTo 0

' --- Probe VBA project access ----------------------------------------
On Error Resume Next
Dim probe
probe = wb.VBProject.Name
If Err.Number <> 0 Then
    WScript.Echo ""
    WScript.Echo "ERROR: cannot access the VBA project."
    WScript.Echo "Please enable: File -> Options -> Trust Center ->"
    WScript.Echo "Trust Center Settings -> Macro Settings ->"
    WScript.Echo "[X] Trust access to the VBA project object model"
    WScript.Echo "Then re-run import_vba.vbs."
    Err.Clear
    On Error GoTo 0
    wb.Close False
    excel.Quit
    WScript.Quit 5
End If
On Error GoTo 0

' --- Remove any modules with names matching incoming files -----------
Dim files, file, baseName, comp
Set files = fso.GetFolder(vbaDir).Files
For Each file In files
    Select Case LCase(fso.GetExtensionName(file.Name))
    Case "bas", "cls", "frm"
        baseName = fso.GetBaseName(file.Name)
        ' Remove existing component with the same name (if any)
        On Error Resume Next
        Set comp = wb.VBProject.VBComponents(baseName)
        If Err.Number = 0 Then
            wb.VBProject.VBComponents.Remove comp
            WScript.Echo "  - removed existing module: " & baseName
        End If
        Err.Clear
        On Error GoTo 0
    End Select
Next

' --- Import each file ------------------------------------------------
Dim importedCount: importedCount = 0
For Each file In files
    Select Case LCase(fso.GetExtensionName(file.Name))
    Case "bas", "cls", "frm"
        On Error Resume Next
        Dim newComp
        Set newComp = wb.VBProject.VBComponents.Import(file.Path)
        If Err.Number = 0 Then
            WScript.Echo "  + imported: " & file.Name
            importedCount = importedCount + 1
        Else
            WScript.Echo "  ! FAILED:   " & file.Name & " — " & Err.Description
            Err.Clear
        End If
        On Error GoTo 0
    End Select
Next

WScript.Echo ""
WScript.Echo "Imported " & importedCount & " module(s)."

' --- Save as .xlsm ---------------------------------------------------
WScript.Echo "Saving " & targetXlsm & " ..."
On Error Resume Next
wb.SaveAs targetXlsm, xlOpenXMLWorkbookMacroEnabled
If Err.Number <> 0 Then
    WScript.Echo "ERROR saving: " & Err.Description
    On Error GoTo 0
    wb.Close False
    excel.Quit
    WScript.Quit 6
End If
On Error GoTo 0

wb.Close True
excel.Quit

WScript.Echo ""
WScript.Echo "DONE.  Open this file in Excel to use the VBA UI:"
WScript.Echo "    " & targetXlsm
