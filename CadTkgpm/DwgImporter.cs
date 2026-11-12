using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;

namespace CadTkgpm
{
    /// <summary>
    /// Import nhanh các entity từ file DWG (đã convert từ DGN) vào bản vẽ hiện tại.
    /// Dùng WblockCloneObjects để copy cả lô trong một lần, không duyệt từng entity.
    /// </summary>
    public static class DwgImporter
    {
        public static void ImportWithDialog(Document doc)
        {
            var ed = doc.Editor;

            var pfo = new PromptOpenFileOptions("\nChọn file DWG đã convert từ DGN: ")
            {
                Filter = "AutoCAD Drawing (*.dwg)|*.dwg"
            };
            var pr = ed.GetFileNameForOpen(pfo);
            if (pr.Status != PromptStatus.OK) return;

            ImportFile(doc, pr.StringResult);
        }

        public static int ImportFile(Document doc, string dwgPath)
        {
            var ed = doc.Editor;
            var db = doc.Database;

            if (!System.IO.File.Exists(dwgPath))
            {
                ed.WriteMessage($"\n[TKGPM] Không tìm thấy file: {dwgPath}\n");
                return 0;
            }

            var sw = System.Diagnostics.Stopwatch.StartNew();
            object oldBlip = Application.GetSystemVariable("BLIPMODE");

            try
            {
                using (var src = new Database(false, true))
                {
                    src.ReadDwgFile(dwgPath, FileOpenMode.OpenForReadAndAllShare, true, null);
                    src.CloseInput(true);

                    var ids = new ObjectIdCollection();
                    using (var tr = src.TransactionManager.StartTransaction())
                    {
                        var ms = (BlockTableRecord)tr.GetObject(
                            SymbolUtilityServices.GetBlockModelSpaceId(src), OpenMode.ForRead);
                        foreach (ObjectId id in ms)
                        {
                            ids.Add(id);
                        }
                        tr.Commit();
                    }

                    if (ids.Count == 0)
                    {
                        ed.WriteMessage("\n[TKGPM] File DWG không có entity trong Model Space.\n");
                        return 0;
                    }

                    using (doc.LockDocument())
                    {
                        Application.SetSystemVariable("BLIPMODE", 0);

                        db.WblockCloneObjects(
                            ids,
                            db.CurrentSpaceId,
                            new IdMapping(),
                            DuplicateRecordCloning.Ignore,
                            false);
                    }

                    sw.Stop();
                    ed.WriteMessage($"\n[TKGPM] Đã import {ids.Count} entity từ '{System.IO.Path.GetFileName(dwgPath)}' trong {sw.Elapsed.TotalSeconds:F1} s.\n");
                    ed.Regen();
                    return ids.Count;
                }
            }
            catch (System.Exception ex)
            {
                ed.WriteMessage($"\n[TKGPM] Lỗi import: {ex.Message}\n");
                return 0;
            }
            finally
            {
                try { Application.SetSystemVariable("BLIPMODE", oldBlip); } catch { }
            }
        }
    }
}
