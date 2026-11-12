# CadTkgpm – plugin AutoCAD lệnh `TKGPM`

Plugin .NET (C#, .NET Framework 4.8) chạy trên AutoCAD 2020 đến 2026.
Import nhanh các entity từ file DWG đã convert từ DGN vào bản vẽ hiện tại.

## Lệnh

| Lệnh | Chức năng |
|------|-----------|
| `TKGPM` | Mở menu: `Import` hoặc `Info` |
| `TKGPMIMPORT` | Chọn file DWG và import ngay |
| `TKGPMINFO` | Hiện phiên bản, năm AutoCAD và ngày build |

## Yêu cầu build

- Windows, Visual Studio 2022 hoặc .NET SDK 6+ (lệnh `dotnet`).
- AutoCAD đã cài cho năm muốn build, mặc định tại `C:\Program Files\Autodesk\AutoCAD <năm>`.

## Build

Build tất cả các năm 2020–2026 (chỉ năm nào đã cài AutoCAD mới được build):

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Build một năm:

```powershell
dotnet build CadTkgpm.csproj -c Release -p:AcadYear=2026
```

Override đường dẫn AutoCAD nếu cài khác chỗ mặc định:

```powershell
dotnet build CadTkgpm.csproj -c Release -p:AcadYear=2024 -p:AcadRoot="D:\Autodesk\AutoCAD 2024"
```

## Tên file đầu ra (có đuôi ngày)

Mỗi lần build, DLL có đuôi `yyyyMMdd`:

```
dist\AutoCAD2026\CadTkgpm_AC2026_20261112.dll
dist\AutoCAD2025\CadTkgpm_AC2025_20261112.dll
...
```

Ngày build mặc định là ngày hiện tại. Có thể đặt ngày cố định bằng `-p:BuildDate=20261231`.

## Nạp plugin trong AutoCAD

1. Gõ `NETLOAD` rồi chọn DLL trong thư mục `dist\AutoCAD<năm>\`.
2. Gõ `TKGPM`.

Để tự nạp mỗi khi mở AutoCAD: thêm đường dẫn DLL vào `APPAUTOLOAD` hoặc dùng `Startup Suite` trong `Options`.
Lưu ý: DLL của năm nào chỉ nạp được trong AutoCAD đúng năm đó.

## Quy trình xử lý DGN

Plugin chỉ đọc DWG. Cần convert DGN → DWG trước (ví dụ bằng ODA SDK, MicroStation hoặc ODA File Converter), rồi dùng `TKGPM` → `Import` để đưa vào bản vẽ. Import theo lô bằng `WblockCloneObjects` nên nhanh hơn insert từng entity.

## Cấu trúc

```
CadTkgpm/
  CadTkgpm.csproj   # cấu hình build đa năm và đuôi ngày trong tên DLL
  Commands.cs       # lệnh TKGPM, TKGPMIMPORT, TKGPMINFO
  DwgImporter.cs    # logic import DWG
  build.ps1         # build cho 2020–2026
  dist/             # DLL đầu ra (tạo khi build)
```

## Lưu ý

- Mã đã được viết nhưng chưa được compile/test trên máy có AutoCAD. Hãy build và thử trên file nhỏ trước.
- Năm AutoCAD và ngày build được ghi vào metadata DLL qua `AssemblyAttribute` trong `CadTkgpm.csproj`, nên `TKGPMINFO` hiển thị đúng.
- Chưa có AutoCAD trong môi trường đã viết mã này nên chưa compile được. Nếu `dotnet build` báo lỗi, gửi log lỗi để sửa.
