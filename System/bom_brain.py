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
        # LUỒNG 1: NGƯỜI DÙNG BẤM NÚT CHỌN MODEL TỪ GIAO DIỆN WEB
        # =================================================================
        btn_match = re.search(r'Lọc BOM theo Model \[(.*?)\] cho mã \[(.*?)\] SL \[(\d+)\]', exact_kw, re.IGNORECASE)
        if btn_match:
            model_code = btn_match.group(1).strip()
            prod_code = btn_match.group(2).strip()
            quantity = int(btn_match.group(3))
            
            try:
                # Query TÊN SẢN PHẨM từ cả 2 bảng
                query_name = text("""
                    SELECT TOP 1 Name FROM (
                        SELECT Code, Name FROM dbo.B20ItemHQ
                        UNION ALL
                        SELECT Code, Name FROM dbo.B20Product
                    ) AS T WHERE Code = :code
                """)
                with self.db_engine.connect() as conn:
                    name_res = conn.execute(query_name, {"code": prod_code}).fetchone()
                    prod_name = name_res[0] if name_res else "Unknown"
                
                return self._execute_sql_logic(model_code, prod_code, prod_name, quantity, steps)
            except Exception as e:
                return {"status": "ok", "search_mode": "chitchat", "message": f"🚨 Lỗi truy vấn tên SP: {str(e)}"}

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
            # Lấy ModelCode (đã vá lỗi thiếu cột cho bảng Product)
            query_item = text("""
                SELECT TOP 1 Code, Name, ModelCode FROM (
                    SELECT Code, Name, ModelCode FROM dbo.B20ItemHQ
                    UNION ALL
                    SELECT Code, Name, NULL AS ModelCode FROM dbo.B20Product
                ) AS T
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
                return {"status": "ok", "search_mode": "chitchat", "message": f"⚠️ Sản phẩm <b>{prod_code} - {prod_name}</b> chưa được gán ModelCode trên hệ thống để tra BOM.", "steps": steps}

            # BẬT CHẾ ĐỘ CHỌN MODEL NẾU CÓ DẤU PHẨY
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
            
            # NẾU CHỈ CÓ 1 MÃ -> CHẠY LUÔN LOGIC
            return self._execute_sql_logic(raw_model_code, prod_code, prod_name, quantity, steps)

        except Exception as e:
            return {"status": "ok", "search_mode": "chitchat", "message": f"🚨 <b>Lỗi Database:</b><br>{str(e)}"}

    def _execute_sql_logic(self, model_code, prod_code, prod_name, quantity, steps):
        """Thực thi Logic JOIN 3 BẢNG bằng Python thuần túy"""
        try:
            steps.append(f"🔍 BƯỚC 1: Tìm BOMId mới nhất cho Model: {model_code}")
            
            with self.db_engine.connect() as conn:
                # 1. Tìm ID của BOM trong bảng B20BOM
                query_bom_id = text("""
                    SELECT TOP 1 Id, Description 
                    FROM dbo.B20BOM 
                    WHERE ModelCode = LTRIM(RTRIM(:md)) 
                    ORDER BY Id DESC
                """)
                
                bom_header = conn.execute(query_bom_id, {"md": model_code}).fetchone()
                
                if not bom_header:
                    return {
                        "status": "ok",
                        "search_mode": "chitchat",
                        "message": f"⚠️ Đã quét bảng <b>B20BOM</b> nhưng không tìm thấy dữ liệu cấu thành cho Model <b>'{model_code}'</b>.",
                        "steps": steps
                    }
                
                target_bom_id = bom_header[0]
                target_bom_desc = bom_header[1]
                steps.append(f"✅ Đã tìm thấy BOM ID: {target_bom_id}")
                
                # 2. JOIN B20BOMDetail và B20Item để lấy chi tiết vật tư
                steps.append(f"🔍 BƯỚC 2: Quét bảng B20BOMDetail và JOIN với B20Item")
                query_bom_detail = text("""
                    SELECT 
                        :pc AS ProductCode,
                        :pn AS ProductName,
                        :bom_id AS BOMId,
                        :bom_desc AS BOMDescription,
                        comp.Code AS MaterialCode,
                        comp.Name AS MaterialName,
                        bd.Unit AS Unit,
                        CAST(bd.Quantity AS FLOAT) AS BaseQty,
                        CAST((bd.Quantity * :qty) AS FLOAT) AS TotalQty
                    FROM dbo.B20BOMDetail bd
                    JOIN dbo.B20Item comp ON bd.ItemId = comp.Id
                    WHERE bd.BOMId = :bom_id
                """)
                
                df_bom = pd.read_sql(query_bom_detail, conn, params={
                    "pc": prod_code, 
                    "pn": prod_name, 
                    "bom_id": target_bom_id,
                    "bom_desc": target_bom_desc,
                    "qty": quantity
                })
            
            if not df_bom.empty:
                product_info = f"{df_bom.iloc[0]['ProductCode']} - {df_bom.iloc[0]['ProductName']}"
                bom_id = df_bom.iloc[0]['BOMId']
                bom_desc = df_bom.iloc[0]['BOMDescription']
                bom_info_text = f"[ID: {bom_id}] {bom_desc}"
                
                df_bom = df_bom.fillna(0)
                results_list = df_bom.to_dict('records')
                
                steps.append(f"🎉 Hoàn tất bóc tách {len(results_list)} vật tư!")
                
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
                    "message": f"⚠️ Có tìm thấy ID BOM ({target_bom_id}) nhưng bảng <b>B20BOMDetail</b> lại trống trơn. Không có chi tiết vật tư nào.",
                    "steps": steps
                }
        except Exception as e:
            return {
                "status": "ok",
                "search_mode": "chitchat",
                "message": f"🚨 <b>Lỗi thực thi Logic BOM:</b><br>{str(e)}",
                "steps": steps
            }