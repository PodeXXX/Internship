import pandas as pd
import pyodbc
import os

def export_vai_products_from_mainitem():
    # 1. Cấu hình kết nối SQL Server
    server = 'LOCALHOST\\SQLEXPRESS'
    database = 'pode'
    
    conn_str = (
        f"Driver={{SQL Server}};"
        f"Server={server};"
        f"Database={database};"
        f"Trusted_Connection=yes;"
    )
    
    output_file = 'list_fabric_mainitem.csv'

    print(f"🔄 Đang kết nối đến database [{database}]...")

    # 2. Câu lệnh SQL (Đã sửa tên bảng thành B20MainItem)
    sql_query = """
    SELECT Name
    FROM [pode].[dbo].[B20MainItem]
    WHERE Name LIKE N'Vải%'
    """

    try:
        # 3. Thực thi và đưa vào DataFrame
        conn = pyodbc.connect(conn_str)
        print("✅ Kết nối thành công! Đang truy vấn dữ liệu từ bảng B20MainItem...")
        
        df = pd.read_sql(sql_query, conn)
        conn.close()

        # 4. Kiểm tra và xuất file
        if not df.empty:
            count = len(df)
            print(f"📊 Tìm thấy {count} sản phẩm bắt đầu bằng 'Vải'.")

            # Xuất ra CSV (encoding utf-8-sig để hiển thị tiếng Việt trong Excel)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            
            print(f"🎉 Đã xuất thành công file: {os.path.abspath(output_file)}")
        else:
            print("⚠️ Không tìm thấy sản phẩm nào bắt đầu bằng 'Vải' trong bảng B20MainItem.")

    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {str(e)}")

if __name__ == "__main__":
    # Yêu cầu cài đặt thư viện: pip install pandas pyodbc
    export_vai_products_from_mainitem()