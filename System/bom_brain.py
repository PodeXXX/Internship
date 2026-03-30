import re
import pandas as pd
from sqlalchemy import create_engine, text

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

class BOMBrain:
    def __init__(self):
        self.db_engine = create_engine(CONN_STR)
        self.bom_triggers = ["bom", "định mức", "nguyên vật liệu", "sản xuất", "vật tư", "chi tiết cấu thành"]

    def is_bom_intent(self, text_input):
        text_lower = text_input.lower()
        return any(t in text_lower for t in self.bom_triggers)

    def process_bom(self, text_input):
        steps = ["⚙️ BOM_BRAIN: Kích hoạt luồng Định mức nguyên vật liệu."]
        exact_kw = text_input.strip()
        
        # =================================================================
        # [MỚI] LUỒNG 1: NGƯỜI DÙNG BẤM NÚT CHỌN MODEL TỪ GIAO DIỆN WEB
        # =================================================================
        btn_match = re.search(r'Lọc BOM theo Model \[(.*?)\] cho mã \[(.*?)\] SL \[(\d+)\]', exact_kw, re.IGNORECASE)
        if btn_match:
            model_code = btn_match.group(1).strip()
            prod_code = btn_match.group(2).strip()
            quantity = int(btn_match.group(3))
            
            try:
                query_name = text("SELECT TOP 1 Name FROM dbo.B20ItemHQ WHERE Code = :code")
                with self.db_engine.connect() as conn:
                    name_res = conn.execute(query_name, {"code": prod_code}).fetchone()
                    prod_name = name_res[0] if name_res else "Unknown"
                
                return self._execute_sp(model_code, prod_code, prod_name, quantity, steps)
            except Exception as e:
                return {"status": "error", "msg": str(e)}

        # =================================================================
        # LUỒNG 2: NGƯỜI DÙNG TỰ GÕ TÌM KIẾM
        # =================================================================
        qty_match = re.search(r'\b(\d{1,5})\b', exact_kw)
        quantity = int(qty_match.group(1)) if qty_match else 1
        
        if qty_match:
            exact_kw = exact_kw.replace(qty_match.group(1), "", 1)
            
        words_to_remove = ["tính", "tra", "cho", "của", "các", "những", "cái", "chiếc", "bộ", "mã", "số", "để", "cần bao nhiêu"] + self.bom_triggers
        for w in words_to_remove:
            exact_kw = re.sub(rf'(?i)\b{w}\b', '', exact_kw)
            
        search_kw = " ".join(exact_kw.split()).strip(' ,.:;-')

        if not search_kw:
            return {"status": "ok", "search_mode": "chitchat", "message": "⚠️ Vui lòng nhập mã hoặc tên sản phẩm cần tra BOM."}

        try:
            # 1. Truy vấn ItemHQ trước để kiểm tra ModelCode có bị gộp không (Ví dụ: MD1723, MD1723FLAT...)
            query_item = text("""
                SELECT TOP 1 Code, Name, ModelCode 
                FROM dbo.B20ItemHQ 
                WHERE Code = :kw OR Name LIKE :kw_like
            """)
            
            with self.db_engine.connect() as conn:
                df_item = pd.read_sql(query_item, conn, params={"kw": search_kw, "kw_like": f"%{search_kw}%"})
            
            if df_item.empty:
                return {"status": "ok", "search_mode": "chitchat", "message": f"⚠️ Không tìm thấy sản phẩm <b>'{search_kw}'</b> trong hệ thống.", "steps": steps}

            prod_code = df_item.iloc[0]['Code']
            prod_name = df_item.iloc[0]['Name']
            raw_model_code = df_item.iloc[0]['ModelCode']

            if not raw_model_code or pd.isna(raw_model_code):
                return {"status": "ok", "search_mode": "chitchat", "message": f"⚠️ Sản phẩm <b>{prod_code}</b> chưa được gán ModelCode trên hệ thống.", "steps": steps}

            # 2. KIỂM TRA NẾU CÓ DẤU PHẨY -> BẬT CHẾ ĐỘ HIỂN THỊ NÚT BẤM (CHOICE MODE)
            if ',' in str(raw_model_code):
                model_list = [m.strip() for m in str(raw_model_code).split(',')]
                steps.append(f"🔄 Phát hiện nhiều ModelCode. Yêu cầu người dùng chọn.")
                return {
                    "status": "ok",
                    "search_mode": "bom_choice",
                    "product_code": prod_code,
                    "product_name": prod_name,
                    "quantity": quantity,
                    "models": model_list,
                    "steps": steps
                }
            
            # 3. NẾU CHỈ CÓ 1 MÃ -> CHẠY LUÔN STORED PROCEDURE
            return self._execute_sp(raw_model_code, prod_code, prod_name, quantity, steps)

        except Exception as e:
            return {"status": "error", "msg": f"Lỗi xử lý BOM: {str(e)}"}

    def _execute_sp(self, model_code, prod_code, prod_name, quantity, steps):
        """Hàm nội bộ để gọi Stored Procedure và trả về dữ liệu"""
        try:
            steps.append(f"🔍 Gọi SP 'sp_GetBOMByModelCode' với Model: {model_code}")
            
            # GỌI STORED PROCEDURE MỚI TẠO Ở BƯỚC TRƯỚC
            query_sp = text("EXEC sp_GetBOMByModelCode @TargetModelCode=:md, @TargetProductCode=:pc, @TargetProductName=:pn, @RequestQuantity=:qty")
            
            with self.db_engine.connect() as conn:
                df_bom = pd.read_sql(query_sp, conn, params={"md": model_code, "pc": prod_code, "pn": prod_name, "qty": quantity})
            
            if not df_bom.empty:
                product_info = f"{df_bom.iloc[0]['ProductCode']} - {df_bom.iloc[0]['ProductName']}"
                bom_id = df_bom.iloc[0]['BOMId']
                bom_desc = df_bom.iloc[0]['BOMDescription']
                bom_info_text = f"[ID: {bom_id}] {bom_desc}"
                
                df_bom = df_bom.fillna(0)
                results_list = df_bom.to_dict('records')
                
                return {
                    "status": "ok",
                    "search_mode": "bom",
                    "product_info": product_info,
                    "bom_info": bom_info_text,  
                    "quantity": quantity,
                    "data": results_list,
                    "steps": steps
                }
            else:
                return {
                    "status": "ok",
                    "search_mode": "chitchat",
                    "message": f"⚠️ Sản phẩm tồn tại, nhưng chưa có khai báo Vật tư BOM cho Model <b>'{model_code}'</b>.",
                    "steps": steps
                }
        except Exception as e:
            return {"status": "error", "msg": f"Lỗi SP: {str(e)}"}