import pyodbc
import pandas as pd

conn_str = (
    "Driver={SQL Server};"
    "Server=localhost\\SQLEXPRESS;" 
    "Database=pode;"
    "Trusted_Connection=yes;"
)

try:
    conn = pyodbc.connect(conn_str)
    # Lấy dữ liệu từ bảng B20ItemHQ
    query = "SELECT DISTINCT ColorVIE FROM [dbo].[B20ItemHQ] WHERE ColorVIE IS NOT NULL ORDER BY ColorVIE"
    
    df = pd.read_sql(query, conn)
    df.to_csv("Danh_Sach_Mau_Sac.csv", index=False, encoding='utf-8-sig')
    print("Đã xuất file thành công!")
except Exception as e:
    print(f"Lỗi rồi: {e}")
finally:
    if 'conn' in locals():
        conn.close()