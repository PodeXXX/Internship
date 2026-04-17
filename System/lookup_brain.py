import os
import re
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

IMAGE_DIR = Path(r"D:\ĐẠI HỌC TÔN ĐỨC THẮNG\Công ty Nhân Hoàng\Images")

class LookupBrain:
    def __init__(self):
        self.db_engine = create_engine(CONN_STR)

    def is_lookup_intent(self, text_input):
        """Kiểm tra xem câu lệnh có phải là yêu cầu tra mã không."""
        text_clean = text_input.strip().lower()
        
        # 1. Nếu người dùng CHỈ GÕ mỗi dãy số (VD: "10005520")
        if re.match(r'^\d{5,20}$', text_clean):
            return True
            
        # 2. Nếu gõ từ khóa KÈM dãy số (VD: "check mã 10005520", "thông tin 10005520")
        lookup_keywords = ["tra", "tìm", "check", "thông tin", "chi tiết", "mã sp", "mã số", "code", "mã"]
        has_keyword = any(kw in text_clean for kw in lookup_keywords)
        has_code = bool(re.search(r'\d{5,20}', text_clean))
        
        # Bắt dính ngay lập tức nếu câu có cả từ khóa và mã số
        if has_keyword and has_code:
            return True
            
        return False

    def process_lookup(self, text_input):
        text_clean = text_input.strip()
        
        # Bóc tách lấy đúng phần mã số (Dãy từ 5 số trở lên)
        code_to_search = text_clean
        code_match = re.search(r'\d{5,20}', text_clean)
        if code_match:
            code_to_search = code_match.group(0)

        if code_to_search and code_to_search.isdigit():
            try:
                # Quét đồng loạt trên cả 3 bảng
                query = text("""
                    SELECT CAST(Code AS VARCHAR(50)) AS Code, CAST(Name AS NVARCHAR(MAX)) AS Name, N'B20Product (Thành phẩm)' AS SourceTable 
                    FROM [dbo].[B20Product] WHERE CAST(Code AS VARCHAR(50)) = :code
                    UNION ALL
                    SELECT CAST(Code AS VARCHAR(50)) AS Code, CAST(Name AS NVARCHAR(MAX)) AS Name, N'B20ItemHQ (Nguyên vật liệu)' AS SourceTable 
                    FROM [dbo].[B20ItemHQ] WHERE CAST(Code AS VARCHAR(50)) = :code
                    UNION ALL
                    SELECT CAST(Code AS VARCHAR(50)) AS Code, CAST(Name AS NVARCHAR(MAX)) AS Name, N'Bảng CBM (Item + mm^3)' AS SourceTable 
                    FROM [dbo].[Item + mm^3] WHERE CAST(Code AS VARCHAR(50)) = :code
                """)
                
                with self.db_engine.connect() as conn:
                    df = pd.read_sql(query, conn, params={"code": code_to_search})
                
                if not df.empty:
                    results_list = df.to_dict('records')
                    
                    # TÌM ẢNH SẢN PHẨM TRONG FOLDER
                    found_image = None
                    prefix = code_to_search[:8] 
                    
                    if IMAGE_DIR.exists() and IMAGE_DIR.is_dir():
                        for filepath in IMAGE_DIR.iterdir():
                            filename = filepath.name
                            if filename.startswith(prefix) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                found_image = filename
                                print(f"[LOOKUP_BRAIN] ✅ Tìm thấy ảnh: {filename}")
                                break
                                
                    return {
                        "status": "ok",
                        "search_mode": "lookup",
                        "keyword": code_to_search,
                        "data": results_list,
                        "image_filename": found_image 
                    }
                else:
                    return {
                        "status": "ok",
                        "search_mode": "chitchat",
                        "message": f"⚠️ Không tìm thấy sản phẩm nào mang mã số <b>'{code_to_search}'</b> trong hệ thống."
                    }
            except Exception as e:
                print(f"Lỗi SQL tại Lookup: {e}")
                return {
                    "status": "error",
                    "msg": f"Lỗi truy vấn Database khi tra mã: {str(e)}"
                }
        
        return {"status": "ok", "search_mode": "chitchat", "message": "Không nhận diện được mã số hợp lệ."}