import re
import pandas as pd
from sqlalchemy import create_engine, text

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

class CBMBrain:
    def __init__(self):
        self.db_engine = create_engine(CONN_STR)
        self.cbm_triggers = ["cbm", "thể tích", "bao nhiêu khối", "tổng khối", "tổng cbm", "khối lượng"]

    def is_cbm_intent(self, text_input):
        text_lower = text_input.lower()
        return any(t in text_lower for t in self.cbm_triggers)

    def process_cbm(self, text_input):
        steps = ["📦 CBM_BRAIN: Đã nhận luồng xử lý CBM độc lập."]
        exact_kw = text_input
        
        # 1. Xóa từ khóa mồi
        words_to_remove = ["tính", "tổng", "cho", "của", "các", "những", "cái", "chiếc", "bộ", "mã", "số"] + self.cbm_triggers
        for w in words_to_remove:
            exact_kw = re.sub(rf'(?i)\b{w}\b', '', exact_kw)
        
        # 2. Cắt câu thành mảng các sản phẩm
        raw_items = re.split(r'(?i);|\b và \b|\n', exact_kw)
        
        results_list = []
        not_found_list = []
        grand_total_cbm = 0.0

        # 3. Quét từng sản phẩm
        for item_str in raw_items:
            item_str = item_str.strip(' ,.:;-')
            if not item_str: continue 
            
            # Tìm số lượng
            qty_match = re.match(r'^(\d+)\s+', item_str)
            if qty_match:
                quantity = int(qty_match.group(1))
                item_name = item_str[qty_match.end():]
            else:
                quantity = 1
                item_name = item_str
            
            item_name = " ".join(item_name.split()).strip(' ,.:;-')
            
            if item_name:
                try:
                    # LẦN TÌM 1: KHỚP CHÍNH XÁC 100%
                    query_exact = text("""
                        SELECT TOP 1
                            CAST(c.Code AS VARCHAR(50)) AS Code, 
                            CAST(c.Name AS NVARCHAR(MAX)) AS Name, 
                            CAST(c.[mm_3] AS FLOAT) / 1000000000.0 AS Unit_CBM,
                            CASE 
                                WHEN p.Code IS NOT NULL THEN N'Có trong Product'
                                WHEN i.Code IS NOT NULL THEN N'Có trong ItemHQ'
                                ELSE N'❌ KHÔNG CÓ TRONG KHO'
                            END AS Check_Kho
                        FROM [dbo].[Item + mm^3] c
                        LEFT JOIN [dbo].[B20Product] p ON CAST(c.Code AS VARCHAR(50)) = CAST(p.Code AS VARCHAR(50))
                        LEFT JOIN [dbo].[B20ItemHQ] i ON CAST(c.Code AS VARCHAR(50)) = CAST(i.Code AS VARCHAR(50))
                        WHERE LTRIM(RTRIM(CAST(c.Name AS NVARCHAR(MAX)))) = :kw OR LTRIM(RTRIM(CAST(c.Code AS VARCHAR(50)))) = :kw
                    """)
                    
                    with self.db_engine.connect() as conn:
                        df_item = pd.read_sql(query_exact, conn, params={"kw": item_name})
                        
                        # LẦN TÌM 2 (FALLBACK): NẾU CHUỖI COPY TỪ EXCEL QUÁ DÀI -> TỰ BÓC TÁCH MÃ SẢN PHẨM ĐỂ TÌM
                        if df_item.empty:
                            # Bắt các mã phổ biến: MD 1801, PAB016, 50005284...
                            fallback_match = re.search(r'\b([A-Za-z]{2,4}[\s\-]*\d{3,5}|\d{6,20})\b', item_name, re.IGNORECASE)
                            if fallback_match:
                                fb_kw = fallback_match.group(1).replace('-', ' ') # Đổi MD-1801 thành MD 1801
                                
                                query_fallback = text("""
                                    SELECT TOP 1
                                        CAST(c.Code AS VARCHAR(50)) AS Code, 
                                        CAST(c.Name AS NVARCHAR(MAX)) AS Name, 
                                        CAST(c.[mm_3] AS FLOAT) / 1000000000.0 AS Unit_CBM,
                                        CASE 
                                            WHEN p.Code IS NOT NULL THEN N'Có trong Product'
                                            WHEN i.Code IS NOT NULL THEN N'Có trong ItemHQ'
                                            ELSE N'❌ KHÔNG CÓ TRONG KHO'
                                        END AS Check_Kho
                                    FROM [dbo].[Item + mm^3] c
                                    LEFT JOIN [dbo].[B20Product] p ON CAST(c.Code AS VARCHAR(50)) = CAST(p.Code AS VARCHAR(50))
                                    LEFT JOIN [dbo].[B20ItemHQ] i ON CAST(c.Code AS VARCHAR(50)) = CAST(i.Code AS VARCHAR(50))
                                    WHERE CAST(c.Code AS VARCHAR(50)) LIKE :fb OR CAST(c.Name AS NVARCHAR(MAX)) LIKE :fb
                                """)
                                df_item = pd.read_sql(query_fallback, conn, params={"fb": f"%{fb_kw}%"})
                    
                    # XỬ LÝ KẾT QUẢ VÀ TÍNH TOÁN
                    if not df_item.empty:
                        # Bọc lỗi giá trị CBM trống (NULL)
                        val = df_item.iloc[0]['Unit_CBM']
                        unit_cbm = float(val) if pd.notna(val) else 0.0
                        total_cbm = unit_cbm * quantity
                        grand_total_cbm += total_cbm
                        
                        row_safe = {
                            "Code": str(df_item.iloc[0]['Code']),
                            "Name": str(df_item.iloc[0]['Name']),
                            "Unit_CBM": unit_cbm,
                            "Request_Qty": quantity,
                            "Total_CBM": total_cbm,
                            "Check_Kho": str(df_item.iloc[0]['Check_Kho'])
                        }
                        results_list.append(row_safe)
                    else:
                        not_found_list.append(item_name)
                        
                except Exception as e:
                    print(f"Lỗi SQL tại cbm_brain: {e}")
                    steps.append(f"⚠️ Lỗi DB khi tìm: {item_name}")
        
        # 4. Trả kết quả về
        if results_list or not_found_list:
            return {
                "status": "ok",
                "search_mode": "cbm_multi",
                "data": results_list,
                "not_found": not_found_list,
                "grand_total": float(grand_total_cbm),
                "steps": steps
            }
        else:
            return {
                "status": "ok",
                "search_mode": "chitchat",
                "message": "⚠️ CBM_Brain không bóc tách được mã/tên sản phẩm nào. Đảm bảo bạn không nhập sai cú pháp.",
                "steps": steps
            }