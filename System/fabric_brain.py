import pyodbc
import pandas as pd
import re

class FabricBrain:
    def __init__(self):
        server = 'LOCALHOST\\SQLEXPRESS'
        database = 'pode'
        self.conn_str = (
            f"Driver={{SQL Server}};"
            f"Server={server};"
            f"Database={database};"
            f"Trusted_Connection=yes;"
        )
        self.fabric_triggers = ["vải ", "fabric ", "chất liệu ", "liệu ", "material "]

    def is_fabric_intent(self, text_input):
        text_lower = text_input.lower()
        return any(trig in text_lower for trig in self.fabric_triggers)

    def process_fabric(self, user_input):
        user_input_lower = user_input.lower().strip()
        fabric_keyword = ""

        # Trích xuất tên vải sau từ khóa
        for trigger in self.fabric_triggers:
            idx = user_input_lower.find(trigger)
            if idx != -1:
                fabric_keyword = user_input[idx + len(trigger):].strip()
                break
                
        if not fabric_keyword:
            return {"status": "error", "message": "⚠️ Vui lòng nhập rõ tên vải cần tìm."}

        sql_query = f"""
        SELECT TOP 200 Code as ProductCode, Name as ProductName, 'B20ItemHQ' as SourceTable
        FROM [dbo].[B20ItemHQ]
        WHERE Ingredient LIKE ? 
        UNION ALL
        SELECT Code as ProductCode, Name as ProductName, 'B20Item' as SourceTable
        FROM [dbo].[B20Item]
        WHERE Name LIKE ? AND CHARINDEX(',', Name) > 0
        """
        
        try:
            conn = pyodbc.connect(self.conn_str)
            df = pd.read_sql(sql_query, conn, params=[f'%{fabric_keyword}%', f'%{fabric_keyword}%'])
            conn.close()

            if df.empty:
                return {"status": "success", "keyword": fabric_keyword, "count": 0, "message": f"Không tìm thấy mẫu vải '{fabric_keyword}' trong kho."}

            return {
                "status": "success",
                "search_mode": "fabric",
                "keyword": fabric_keyword,
                "count": len(df),
                "data": df.to_dict('records')
            }
        except Exception as e:
            return {"status": "error", "message": f"Lỗi Database: {str(e)}"}