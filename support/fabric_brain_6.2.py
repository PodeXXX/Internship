import pyodbc
import pandas as pd
import re

class FabricBrain:
    def __init__(self):
        # Cấu hình kết nối
        self.server = 'LOCALHOST\\SQLEXPRESS'
        self.database = 'pode'
        self.conn_str = (
            f"Driver={{SQL Server}};"
            f"Server={self.server};"
            f"Database={self.database};"
            f"Trusted_Connection=yes;"
        )

    def search_product_by_fabric(self, fabric_name):
        """
        Tìm kiếm sản phẩm dựa trên tên vải/nguyên liệu.
        Có lọc chính xác từ khóa (Word Boundary) để tránh nhầm lẫn (VD: tìm '10' không ra '103').
        """
        if not fabric_name or len(fabric_name.strip()) < 2:
            return None

        clean_keyword = fabric_name.strip()
        # print(f"🧵 Đang tìm các sản phẩm sử dụng vải: '{clean_keyword}'...")

        try:
            conn = pyodbc.connect(self.conn_str)
            
            # 1. SQL LẤY RỘNG (Broad Match)
            # Vẫn dùng LIKE để lấy hết các khả năng, sau đó Python sẽ lọc kỹ lại.
            sql_query = """
            /* 1. Tìm trong B20Product (Thành phẩm) */
            SELECT Code AS ProductCode, Name AS ProductName, N'Thành phẩm (Product)' AS SourceTable, Name AS MatInfo
            FROM [dbo].[B20Product]
            WHERE Name LIKE ? AND Name NOT LIKE N'%Chân ghế%' AND Name NOT LIKE N'%Khung ghế%'

            UNION ALL

            /* 2. Tìm trong B20ItemHQ (Nguyên liệu) */
            SELECT Code AS ProductCode, Name AS ProductName, N'Nguyên liệu (ItemHQ)' AS SourceTable, Ingredient AS MatInfo
            FROM [dbo].[B20ItemHQ]
            WHERE Ingredient LIKE ? AND Name NOT LIKE N'%Gỗ%' AND Name NOT LIKE N'%Plywood%'

            UNION ALL

            /* 3. Tìm trong B20Item (Vật tư) */
            SELECT Code AS ProductCode, Name AS ProductName, N'Vật tư (Item)' AS SourceTable, Name AS MatInfo
            FROM [dbo].[B20Item]
            WHERE Name LIKE ? AND Name NOT LIKE N'%Leg%'
            """
            
            params = [f'%{clean_keyword}%', f'%{clean_keyword}%', f'%{clean_keyword}%']
            df = pd.read_sql(sql_query, conn, params=params)
            conn.close()

            if df.empty:
                return {"status": "empty", "message": f"Không tìm thấy vải '{clean_keyword}'"}

            # 2. LỌC CHÍNH XÁC (Exact Match Filter) bằng Python
            # Tạo Regex Pattern: \b là ranh giới từ.
            # Ví dụ: Tìm "Sunday 10" -> Regex sẽ là r"\bSunday 10\b"
            # Nó sẽ khớp: "Vải Sunday 10", "Sunday 10,"
            # Nó KHÔNG khớp: "Sunday 103" (vì sau số 0 là số 3, không phải biên từ)
            
            # Xử lý ký tự đặc biệt trong keyword trước khi đưa vào regex
            safe_keyword = re.escape(clean_keyword)
            # Pattern: \b + keyword + \b (Match nguyên cụm từ)
            # Tuy nhiên, một số ký tự như dấu #, - có thể không được coi là word boundary chuẩn.
            # Nên ta dùng lookaround hoặc đơn giản là check ranh giới số.
            
            # Logic tối ưu cho trường hợp số (VD: 10 vs 103):
            # Nếu ký tự cuối của keyword là số -> Đảm bảo ký tự tiếp theo trong chuỗi KHÔNG phải là số.
            
            def is_exact_match(text):
                if not text: return False
                text_lower = str(text).lower()
                keyword_lower = clean_keyword.lower()
                
                # Tìm vị trí xuất hiện của keyword
                start_idx = text_lower.find(keyword_lower)
                while start_idx != -1:
                    end_idx = start_idx + len(keyword_lower)
                    
                    # Kiểm tra ký tự ngay sau keyword (nếu có)
                    is_next_char_ok = True
                    if end_idx < len(text_lower):
                        next_char = text_lower[end_idx]
                        # Nếu keyword kết thúc là số, và ký tự tiếp theo cũng là số -> FALSE (VD: 10 vs 103)
                        if keyword_lower[-1].isdigit() and next_char.isdigit():
                            is_next_char_ok = False
                        # Nếu keyword kết thúc là chữ, và ký tự tiếp theo là chữ -> FALSE (VD: Sun vs Sunday)
                        elif keyword_lower[-1].isalpha() and next_char.isalpha():
                            is_next_char_ok = False
                    
                    # Kiểm tra ký tự ngay trước keyword (nếu có)
                    is_prev_char_ok = True
                    if start_idx > 0:
                        prev_char = text_lower[start_idx - 1]
                        # Nếu keyword bắt đầu là số, và ký tự trước đó là số -> FALSE (VD: 10 vs 110)
                        if keyword_lower[0].isdigit() and prev_char.isdigit():
                            is_prev_char_ok = False
                        elif keyword_lower[0].isalpha() and prev_char.isalpha():
                            is_prev_char_ok = False

                    if is_next_char_ok and is_prev_char_ok:
                        return True
                    
                    # Tìm tiếp ở vị trí sau
                    start_idx = text_lower.find(keyword_lower, start_idx + 1)
                
                return False

            # Áp dụng bộ lọc vào cột MatInfo (Thông tin chứa vải)
            df_filtered = df[df['MatInfo'].apply(is_exact_match)]

            if df_filtered.empty:
                return {"status": "empty", "message": f"Không tìm thấy vải chính xác '{clean_keyword}' (đã lọc các biến thể gần giống)."}

            df_filtered = df_filtered.sort_values(by='SourceTable', ascending=True)

            return {
                "status": "success",
                "keyword": clean_keyword,
                "count": len(df_filtered),
                "data": df_filtered.to_dict('records')
            }

        except Exception as e:
            # print(f"❌ Lỗi FabricBrain: {str(e)}")
            return {"status": "error", "message": str(e)}