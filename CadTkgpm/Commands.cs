using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;

namespace CadTkgpm
{
    /// <summary>
    /// Điểm vào của plugin. Gõ TKGPM trong AutoCAD để mở menu lệnh.
    /// </summary>
    public class Commands : IExtensionApplication
    {
        public const string PluginName = "TKGPM";

        public void Initialize()
        {
            var ed = Application.DocumentManager.MdiActiveDocument?.Editor;
            ed?.WriteMessage($"\n[{PluginName}] Đã nạp plugin ({AssemblyInfo.Summary}). Gõ TKGPM để bắt đầu.\n");
        }

        public void Terminate()
        {
        }

        [CommandMethod("TKGPM", CommandFlags.Modal)]
        public void TkgpmCommand()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            var ed = doc.Editor;

            var kw = new PromptKeywordOptions($"\n[{PluginName}] Chọn chức năng [Import/Info]: ")
            {
                AllowNone = true
            };
            kw.Keywords.Add("Import");
            kw.Keywords.Add("Info");
            kw.Keywords.Default = "Import";

            var res = ed.GetKeywords(kw);
            if (res.Status == PromptStatus.Cancel) return;

            string choice = res.Status == PromptStatus.None ? "Import" : res.StringResult;

            switch (choice)
            {
                case "Import":
                    DwgImporter.ImportWithDialog(doc);
                    break;
                case "Info":
                    ShowInfo(ed);
                    break;
            }
        }

        [CommandMethod("TKGPMIMPORT", CommandFlags.Modal)]
        public void TkgpmImport()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            DwgImporter.ImportWithDialog(doc);
        }

        [CommandMethod("TKGPMINFO", CommandFlags.Modal)]
        public void TkgpmInfo()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            ShowInfo(doc.Editor);
        }

        private static void ShowInfo(Editor ed)
        {
            ed.WriteMessage($"\n[{PluginName}] {AssemblyInfo.Summary}");
            ed.WriteMessage($"\n  Phiên bản: {AssemblyInfo.Version}");
            ed.WriteMessage($"\n  Ngày build: {AssemblyInfo.BuildDate}");
            ed.WriteMessage($"\n  Build cho AutoCAD: {AssemblyInfo.AcadYear}\n");
        }
    }

    /// <summary>
    /// Thông tin build. AcadYear và BuildDate được MSBuild ghi vào metadata của DLL (xem CadTkgpm.csproj).
    /// </summary>
    internal static class AssemblyInfo
    {
        private static readonly string Meta_AcadYear = ReadMeta("AcadYear");
        private static readonly string Meta_BuildDate = ReadMeta("BuildDate");

        public static string Version => "1.0.0";
        public static string AcadYear => "AutoCAD " + Meta_AcadYear;
        public static string BuildDate => Meta_BuildDate;
        public static string Summary => $"CadTkgpm {Version} cho {AcadYear} (build {BuildDate})";

        private static string ReadMeta(string key)
        {
            var asm = System.Reflection.Assembly.GetExecutingAssembly();
            foreach (System.Reflection.AssemblyMetadataAttribute a in
                     asm.GetCustomAttributes(typeof(System.Reflection.AssemblyMetadataAttribute), false))
            {
                if (a.Key == key) return a.Value;
            }
            return "?";
        }
    }
}
