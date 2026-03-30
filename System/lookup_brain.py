import os
import re
import pandas as pd
from pathlib import Path # [THÊM] Thư viện xử lý đường dẫn xịn hơn
from sqlalchemy import create_engine, text

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

# [MỚI] Sử dụng Path để bọc đường dẫn an toàn
IMAGE_DIR = Path(r"D:\ĐẠI HỌC TÔN ĐỨC THẮNG\Công ty Nhân Hoàng\Images")

class LookupBrain:
    def __init__(self):
        self.db_engine = create_engine(CONN_STR)

    def is_lookup_intent(self, text_input):
        """Kiểm tra xem câu lệnh có phải là yêu cầu tra mã không."""
        text_clean = text_input.strip()
        
        # Nhận diện nếu câu chỉ có toàn số (dài từ 6-20 ký tự)
        if re.match(r'^\d{6,20}$', text_clean):
            return True
            
        # Nhận diện nếu bắt đầu bằng các từ khóa tra cứu
        text_lower = text_clean.lower()
        if any(text_lower.startswith(kw) for kw in ["tra mã", "tìm mã", "mã số", "code"]):
            return True
            
        return False

    def process_lookup(self, text_input):
        text_clean = text_input.strip()
        
        # Bóc tách lấy đúng phần mã số
        code_to_search = text_clean
        code_match = re.search(r'\b(\d{6,20})\b', text_clean)
        if code_match:
            code_to_search = code_match.group(1)

        if code_to_search:
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
                    
                    # ==========================================
                    # [MỚI] TÌM ẢNH SẢN PHẨM TRONG FOLDER
                    # ==========================================
                    found_image = None
                    prefix = code_to_search[:8] # Lấy 8 số đầu
                    
                    # Kiểm tra xem thư mục có tồn tại hay không
                    if IMAGE_DIR.exists() and IMAGE_DIR.is_dir():
                        for filepath in IMAGE_DIR.iterdir():
                            filename = filepath.name
                            if filename.startswith(prefix) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                                found_image = filename
                                print(f"[LOOKUP_BRAIN] ✅ Tìm thấy ảnh cho mã {prefix}: {filename}")
                                break
                        if not found_image:
                            print(f"[LOOKUP_BRAIN] ⚠️ Không tìm thấy file ảnh bắt đầu bằng '{prefix}' trong thư mục.")
                    else:
                        print(f"[LOOKUP_BRAIN] 🚨 LỖI: Thư mục ảnh không tồn tại hoặc sai đường dẫn: {IMAGE_DIR}")

                    return {
                        "status": "ok",
                        "search_mode": "lookup",
                        "keyword": code_to_search,
                        "data": results_list,
                        "image_filename": found_image  # Gửi kèm tên file ảnh về cho Frontend
                    }
                else:
                    return {
                        "status": "ok",
                        "search_mode": "chitchat",
                        "message": f"⚠️ Không tìm thấy sản phẩm nào mang mã số <b>'{code_to_search}'</b>."
                    }
            except Exception as e:
                print(f"Lỗi SQL tại Lookup: {e}")
                return {
                    "status": "error",
                    "msg": f"Lỗi truy vấn Database khi tra mã: {str(e)}"
                }
        
        return {"status": "ok", "search_mode": "chitchat", "message": "Không nhận diện được mã số cần tìm."}