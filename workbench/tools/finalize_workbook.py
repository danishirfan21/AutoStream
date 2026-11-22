"""Post-build step: mark the workbook to recalculate fully when opened (the build Excel cannot calculate XLOOKUP, so the
saved cached values are errors until a modern Excel recalculates). Usage: python tools/finalize_workbook.py [file.xlsx]"""
import shutil, sys, zipfile
from pathlib import Path

p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "AutoStream_DQ_Workbench.xlsx"
tmp = p.with_suffix(".tmp")
with zipfile.ZipFile(p) as zi, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
    for i in zi.infolist():
        d = zi.read(i.filename)
        if i.filename == "xl/workbook.xml" and b"fullCalcOnLoad" not in d:
            d = d.replace(b'<calcPr calcId="181029"/>', b'<calcPr calcId="181029" fullCalcOnLoad="1"/>')
            assert b"fullCalcOnLoad" in d, "calcPr not found"
        zo.writestr(i, d)
shutil.move(tmp, p)
print("finalized", p)
