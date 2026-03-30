import pandas as pd
import re
import os
from sqlalchemy import create_engine, text

# --- HÀM XỬ LÝ CHUỖI ---
def contains_vietnamese_accent(text):
    """Kiểm tra dấu tiếng Việt"""
    vietnamese_chars = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    for char in text.lower():
        if char in vietnamese_chars:
            return True
    return False

def extract_and_clean_fabric(row):
    """
    Hàm xử lý thông minh:
    - Nếu nguồn là B20Item (dạng chuỗi dài có dấu phẩy): Tự tách và tìm đoạn chứa 'Vải'.
    - Sau đó áp dụng bộ lọc Tiếng Anh nghiêm ngặt.
    """
    raw_text = str(row['RawText'])
    source = row['Source']
    
    # BƯỚC 1: TRÍCH XUẤT ĐOẠN CHỨA VẢI
    candidate_text = raw_text
    
    # Nếu là B20Item, tên vải nằm sau dấu phẩy. Ta phải tách ra tìm.
    if source == 'B20Item' and ',' in raw_text:
        parts = raw_text.split(',')
        found = False
        for part in parts:
            part = part.strip()
            # Tìm đoạn nào bắt đầu bằng 'Vải'
            if part.lower().startswith('vải'):
                candidate_text = part
                found = True
                break
        if not found:
            return None # Không tìm thấy đoạn nào chứa vải

    # BƯỚC 2: LỌC SẠCH (NHƯ CŨ)
    candidate_text = candidate_text.strip()
    
    # Phải bắt đầu bằng 'Vải'
    if not candidate_text.lower().startswith('vải'):
        return None

    # Cắt bỏ chữ "Vải"
    clean_name = re.sub(r'^Vải\s*', '', candidate_text, flags=re.IGNORECASE).strip()

    if not clean_name:
        return None

    # Chặn Tiếng Việt có dấu
    if contains_vietnamese_accent(clean_name):
        return None

    # Blacklist từ rác
    blacklist = [
        'gia da', 'simili', 'nhung', 'bo', 'khach', 'gam', 'ni', 'luoi', 
        'my', 'han quoc', 'trung quoc', 'tho', 'det', 'kim', 'boc', 'lot', 'tam', 
        'ghe', 'nem', 'dem', 'mut', 'chan', 'khung', 'go', 'thun', 'phi'
    ]
    
    first_word = clean_name.split()[0].lower()
    if first_word in blacklist:
        return None
    
    for bad in blacklist:
        if clean_name.lower().startswith(bad):
            return None

    # Cắt bỏ số/kích thước phía sau
    match = re.search(r'\d', clean_name)
    if match:
        clean_name = clean_name[:match.start()]

    clean_name = clean_name.strip()
    
    # Loại bỏ tên quá ngắn (ví dụ: 'D')
    if len(clean_name) < 2:
        return None

    return clean_name

# --- HÀM CHÍNH ---
def export_data():
    # Cấu hình kết nối bằng SQLAlchemy (An toàn hơn, không bị warning)
    server = 'LOCALHOST\\SQLEXPRESS'
    database = 'pode'
    
    # Connection String chuẩn cho SQL Server
    connection_url = f"mssql+pyodbc://{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
    
    print(f"🔄 Đang kết nối database [{database}]...")
    
    try:
        engine = create_engine(connection_url)
        
        # SQL ĐƠN GIẢN HÓA (Không dùng SUBSTRING để tránh lỗi)
        sql_query = """
        /* 1. B20MainItem: Lấy dòng bắt đầu bằng Vải */
        SELECT Name AS RawText, 'B20MainItem' as Source
        FROM [dbo].[B20MainItem]
        WHERE Name LIKE N'Vải%'

        UNION ALL

        /* 2. B20ItemHQ: Lấy dòng bắt đầu bằng Vải */
        SELECT Ingredient AS RawText, 'B20ItemHQ' as Source
        FROM [dbo].[B20ItemHQ]
        WHERE Ingredient LIKE N'Vải%'
          AND Ingredient NOT LIKE N'%gỗ%' 
          AND Ingredient NOT LIKE N'%ván%'

        UNION ALL

        /* 3. B20Item: Lấy toàn bộ tên có chứa chữ Vải (Python sẽ tự cắt) */
        SELECT Name AS RawText, 'B20Item' as Source
        FROM [dbo].[B20Item]
        WHERE Name LIKE N'%,%Vải%,%' -- Chỉ lấy dòng có dấu phẩy và có chữ Vải
        """
        
        # Dùng pandas đọc qua engine của sqlalchemy
        df = pd.read_sql(text(sql_query), engine.connect())

        if df.empty:
            print("⚠️ Không tìm thấy dữ liệu thô.")
            return

        print(f"📊 Đang xử lý {len(df)} dòng dữ liệu...")

        # Áp dụng hàm xử lý
        df['CleanedName'] = df.apply(extract_and_clean_fabric, axis=1)

        # Lọc và xuất file
        df_clean = df.dropna(subset=['CleanedName'])
        unique_fabrics = df_clean[['CleanedName']].drop_duplicates().sort_values(by='CleanedName')

        output_file = 'english_fabric_names_final.csv'
        
        if not unique_fabrics.empty:
            print(f"✅ Tìm thấy {len(unique_fabrics)} tên vải Tiếng Anh hợp lệ.")
            unique_fabrics.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"🎉 Đã xuất file: {os.path.abspath(output_file)}")
            print("\nPreview:")
            print(unique_fabrics.head(10))
        else:
            print("⚠️ Không tìm thấy tên vải nào sau khi lọc.")

    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")

if __name__ == "__main__":
    export_data()