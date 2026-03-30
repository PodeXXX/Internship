import pandas as pd
import pyodbc
import os

def export_fabric_names_to_csv():
    # 1. Cấu hình kết nối SQL Server
    server = 'LOCALHOST\\SQLEXPRESS'
    database = 'pode'
    
    conn_str = (
        f"Driver={{SQL Server}};"
        f"Server={server};"
        f"Database={database};"
        f"Trusted_Connection=yes;"
    )
    
    output_file = 'fabric_names.csv'

    print(f"🔄 Đang kết nối đến database [{database}]...")

    # 2. Câu lệnh SQL (Đã sửa tên bảng: ItemHQ -> B20ItemHQ, Item -> B20Item)
    sql_query = """
    -- PHẦN 1: Lấy từ B20ItemHQ (Cột Ingredient)
    SELECT LTRIM(RTRIM(REPLACE(Ingredient, N'vải', ''))) AS FabricName
    FROM [dbo].[B20ItemHQ]
    WHERE Ingredient IS NOT NULL 
        AND Ingredient <> ''
        AND Ingredient NOT LIKE N'%gỗ thông%' 
        AND Ingredient NOT LIKE N'%ván ép%'

    UNION

    -- PHẦN 2: Lấy từ B20Item (Cột Name - Giữa 2 dấu phẩy)
    SELECT LTRIM(RTRIM(REPLACE(
        SUBSTRING(
            Name, 
            CHARINDEX(',', Name) + 1, 
            CHARINDEX(',', Name, CHARINDEX(',', Name) + 1) - CHARINDEX(',', Name) - 1
        ), 
        N'vải', 
        ''
    )))
    FROM [dbo].[B20Item]
    WHERE CHARINDEX(',', Name) > 0 
      AND CHARINDEX(',', Name, CHARINDEX(',', Name) + 1) > 0
    """

    try:
        # 3. Thực thi và đưa vào DataFrame
        conn = pyodbc.connect(conn_str)
        print("✅ Kết nối thành công! Đang truy vấn dữ liệu...")
        
        # Sửa lỗi warning của pandas bằng cách dùng context manager (with) hoặc gán trực tiếp
        # pd.read_sql tự động dùng SQLAlchemy nếu có, nhưng với pyodbc raw connection vẫn chạy tốt
        df = pd.read_sql(sql_query, conn)
        conn.close()

        # 4. Hậu xử lý
        if not df.empty:
            df['FabricName'] = df['FabricName'].astype(str).str.strip()
            df = df[df['FabricName'] != '']
            df = df.drop_duplicates().sort_values(by='FabricName')

            count = len(df)
            print(f"📊 Tìm thấy {count} loại vải hợp lệ.")

            # 5. Xuất file CSV
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"🎉 Đã xuất thành công file: {os.path.abspath(output_file)}")
        else:
            print("⚠️ Không tìm thấy dữ liệu nào thỏa mãn điều kiện.")

    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {str(e)}")

if __name__ == "__main__":
    export_fabric_names_to_csv()
    
    