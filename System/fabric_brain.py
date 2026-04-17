import os
import re
import pandas as pd
from sqlalchemy import create_engine, text

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

class FabricBrain:
    def __init__(self):
        self.db_engine = create_engine(CONN_STR)
        self.fabric_names = []
        self.fabric_triggers = ["vải", "nỉ", "nhung", "da", "simili", "fabric", "leather", "pu", "canvas", "linen", "ghế"]
        
        # Khởi động là nạp ngay từ điển CSV vào não
        self._load_fabric_dictionary()

    def _load_fabric_dictionary(self):
        """Đọc file CSV và lưu vào bộ nhớ đệm"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(base_dir, "support", "english_fabric_names_final.csv")
        
        try:
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                if 'CleanedName' in df.columns:
                    raw_names = df['CleanedName'].dropna().astype(str).str.strip().tolist()
                    # Sắp xếp theo độ dài giảm dần (từ dài nhất đến ngắn nhất) để bắt chuẩn xác nhất
                    self.fabric_names = sorted(raw_names, key=len, reverse=True)
                    print(f"[FABRIC_BRAIN] ✅ Đã nạp thành công {len(self.fabric_names)} tên vải từ CSV.")
                else:
                    print("[FABRIC_BRAIN] ⚠️ Cảnh báo: File CSV không có cột 'CleanedName'.")
            else:
                print(f"[FABRIC_BRAIN] ⚠️ Không tìm thấy file từ điển tại: {csv_path}")
        except Exception as e:
            print(f"[FABRIC_BRAIN] 🚨 Lỗi đọc file CSV: {e}")

    def is_fabric_intent(self, text_input):
        text_lower = text_input.lower()
        
        if any(t in text_lower for t in self.fabric_triggers):
            return True
            
        for fabric in self.fabric_names:
            if len(fabric) > 3 and fabric.lower() in text_lower:
                return True
                
        return False

    def process_fabric(self, text_input):
        text_lower = text_input.lower()
        found_fabric = ""
        
        # =========================================================
        # BƯỚC 1: QUÉT KHỚP CHÍNH XÁC VỚI TỪ ĐIỂN CSV
        # =========================================================
        for fabric in self.fabric_names:
            if len(fabric) >= 3 and fabric.lower() in text_lower:
                found_fabric = fabric
                break 
        
        if not found_fabric:
            match = re.search(r'(?:vải|màu)\s+([a-zA-Z0-9\s]+)', text_lower)
            if match:
                words = match.group(1).split()
                found_fabric = " ".join(words[:2]) 
            else:
                return {"status": "error", "msg": "Không nhận diện được tên vải. Bạn có thể gõ rõ: 'tìm ghế vải Agnes'"}

        # =========================================================
        # BƯỚC 2: ĐÂM THẲNG VÀO DATABASE (Hiển thị Ingredient & Random)
        # =========================================================
        try:
            # 1. Quét cả Name và Ingredient
            # 2. Thay chữ B20ItemHQ bằng nội dung cột Ingredient
            # 3. ORDER BY NEWID() để xáo trộn ngẫu nhiên, chống "trùng trùng"
            query = text("""
                SELECT Code, Name, SourceTable FROM (
                    SELECT 
                        Code, 
                        Name, 
                        N'Thành phẩm' AS SourceTable 
                    FROM dbo.B20Product 
                    WHERE Name LIKE :fab
                    
                    UNION ALL
                    
                    SELECT 
                        Code, 
                        Name, 
                        ISNULL(CAST(Ingredient AS NVARCHAR(500)), N'Chưa khai báo') AS SourceTable 
                    FROM dbo.B20ItemHQ 
                    WHERE Name LIKE :fab OR ISNULL(CAST(Ingredient AS NVARCHAR(MAX)), '') LIKE :fab
                ) AS T
                ORDER BY NEWID()
            """)
            
            with self.db_engine.connect() as conn:
                df = pd.read_sql(query, conn, params={"fab": f"%{found_fabric}%"})
            
            if df.empty:
                return {
                    "status": "success",
                    "keyword": found_fabric,
                    "count": 0,
                    "data": []
                }
            
            results_list = df.to_dict('records')
            
            return {
                "status": "success",
                "keyword": found_fabric,
                "count": len(results_list),
                "data": results_list
            }
            
        except Exception as e:
            print(f"Lỗi SQL tại Fabric_Brain: {e}")
            return {"status": "error", "msg": f"Lỗi truy vấn Database khi tìm vải: {str(e)}"}