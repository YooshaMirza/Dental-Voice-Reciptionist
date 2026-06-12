import pandas as pd
import openpyxl

excel_path = r"c:\Users\ASUS\Downloads\firoz lalani\DCAI pricing sheet.xlsx"
xls = pd.ExcelFile(excel_path)
print("Sheet Names:", xls.sheet_names)

for sheet_name in xls.sheet_names:
    print(f"\n--- Sheet: {sheet_name} ---")
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    print("Columns:", list(df.columns))
    for idx, row in df.iterrows():
        print(f"Row {idx}: {row.to_dict()}")
    print(df.info())
