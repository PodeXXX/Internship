from sqlalchemy import create_engine, text

# ================= CẤU HÌNH KẾT NỐI DATABASE =================
SERVER = r'LOCALHOST\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

def extract_unique_hs_codes():
    print("⏳ Đang kết nối Database và trích xuất dữ liệu...")
    engine = create_engine(CONN_STR)
    
    # CÂU LỆNH SQL: 
    # - DISTINCT: Chỉ lấy các giá trị độc lập (không trùng).
    # - IS NOT NULL: Bỏ qua các dòng trống (như trong ảnh của bạn).
    # - LTRIM(RTRIM) <> '': Bỏ qua các dòng chỉ chứa khoảng trắng.
    query = text("""
        SELECT DISTINCT CodeHS 
        FROM [pode].[dbo].[B20ItemHQ] 
        WHERE CodeHS IS NOT NULL 
          AND LTRIM(RTRIM(CodeHS)) <> ''
        ORDER BY CodeHS
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()
            
            print("\n" + "="*40)
            print(f"✅ TÌM THẤY {len(rows)} MÃ HS CODE ĐỘC LẬP:")
            print("="*40)
            
            # In từng mã ra Terminal
            count = 1
            for row in rows:
                code_hs = row[0].strip() # Xóa khoảng trắng thừa nếu có
                print(f"{count}. {code_hs}")
                count += 1
                
            print("="*40)
            
    except Exception as e:
        print(f"❌ Lỗi truy vấn Database: {e}")

if __name__ == "__main__":
    extract_unique_hs_codes()