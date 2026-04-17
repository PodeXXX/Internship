# Version 3
import pandas as pd
import re
from sqlalchemy import create_engine, text

class ColorBrain:
    def __init__(self):
        # 1. Kết nối chuẩn bằng SQLAlchemy
        SERVER = 'LOCALHOST\\SQLEXPRESS' 
        DATABASE = 'pode'
        CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'
        self.engine = create_engine(CONN_STR)
        
        # 2. DANH SÁCH MÀU
        self.base_colors = [
            'Beige', 'Black', 'Blue', 'Brown', 'Cream', 'Gold', 'Green', 'Grey', 'Gray',
            'Orange', 'Pink', 'Purple', 'Red', 'Silver', 'White', 'Yellow', 'Rust', 'Tan',
            'Teal', 'Turquoise', 'Violet', 'Indigo', 'Ivory', 'Khaki', 'Magenta', 'Maroon',
            'Camel', 'Sand', 'Ochre', 'Olive', 'Navy', 'Mustard', 'Petrol', 'Taupe', 'Stone', 'Zinc', 'Copper'
        ]

        self.compound_colors = [
            'Midnight Blue', 'Dust Blue', 'Dusty Blue', 'Pigeon Blue', 'Sky Blue', 
            'Royal Blue', 'Dark Blue', 'Light Blue', 'Pale Blue', 'Steel Blue', 
            'Electric Blue', 'Baby Blue', 'Ice Blue', 'Denim Blue', 'Petrol Blue', 
            'Mineral Blue', 'Ocean Blue', 'Ink Blue', 'Shadow Blue', 'Legion Blue',
            'Cobalt Blue', 'Duck Egg Blue', 'Smoke Blue', 'Aqua Blue',
            'Dark Green', 'Light Green', 'Moss Green', 'Grey Green', 'Gray Green',
            'Olive Green', 'Lime Green', 'Forest Green', 'Sage Green', 'Mint Green',
            'Emerald Green', 'Grass Green', 'Apple Green', 'Bottle Green', 'Hunter Green',
            'Jade Green', 'Woodland Green',
            'Dark Grey', 'Light Grey', 'Charcoal Grey', 'Dark Gray', 'Light Gray',
            'Blue Grey', 'Blue Gray', 'Warm Grey', 'Cool Grey', 'Slate Grey', 'Steel Grey',
            'Dawn Grey', 'Mouse Grey',
            'Dark Brown', 'Light Brown', 'Dark Red', 'Brick Red', 'Rose Red', 'Barn Red',
            'Mustard Yellow', 'Pale Pink', 'Dusty Pink', 'Rose Pink', 'Hot Pink',
            'Old Rosa', 'Golden Beige', 'Dark Beige', 'Burnt Orange', 'Rusty Orange'
        ]
        
        self.all_colors = list(set(self.base_colors + self.compound_colors))
        self.vocab_sorted = sorted(self.all_colors, key=len, reverse=True)

        # 3. TỪ KHÓA SẢN PHẨM & TỪ ĐIỂN LOẠI TRỪ
        self.product_keywords = [
            'ghế', 'sofa', 'bàn', 'table', 'chair', 'giường', 'bed', 
            'tủ', 'cabinet', 'kệ', 'shelf', 'đôn', 'ottoman', 'bench', 
            'bao', 'vỏ', 'cover', 'case', 'gối', 'pillow', 'nệm', 'đệm', 
            'khung', 'frame', 'chân', 'leg', 'áo'
        ]

        self.product_exclusions = {
            'ghế': ['bao', 'vỏ', 'áo', 'cover', 'case', 'chân', 'leg', 'khung', 'frame'],
            'sofa': ['bao', 'vỏ', 'áo', 'cover', 'case', 'chân', 'leg', 'khung', 'frame'],
            'chair': ['cover', 'case', 'leg', 'frame'],
            'gối': ['bao', 'vỏ', 'áo', 'cover', 'case'], 
            'pillow': ['cover', 'case'],
            'giường': ['khung', 'dát', 'frame', 'slat'],
            'bed': ['frame', 'slat'],
            'bàn': ['mặt', 'top', 'chân', 'leg'],
            'table': ['top', 'leg']
        }

    def search_products_by_color(self, user_input):
        if not user_input: return None
        
        user_input_lower = user_input.lower().strip()
        target_color = None
        target_product_kw = None
        
        # =======================================================
        # A. THUẬT TOÁN TÌM MÀU 
        # =======================================================
        match = re.search(r'\b(?:màu|color)\s+([a-zA-ZÀ-ỹ0-9_ -]{3,30})', user_input_lower, re.IGNORECASE)
        if match:
            raw_color = match.group(1).strip()
            clean_color = re.split(r'(?i)(bóng|option|hệ|nc|pu|qc|cm|mm|\()', raw_color)[0].strip()
            if len(clean_color) > 2:
                target_color = clean_color
        
        if not target_color:
            for color in self.vocab_sorted:
                pattern = f"\\b{re.escape(color.lower())}\\b"
                if re.search(pattern, user_input_lower):
                    target_color = color 
                    break 
        
        if not target_color: return None

        # =======================================================
        # B. TÌM TỪ KHÓA SẢN PHẨM
        # =======================================================
        for kw in self.product_keywords:
            if kw.lower() in user_input_lower:
                target_product_kw = kw.lower()
                break 

        try:
            query = text("SELECT TOP 500 Name, ColorVIE, Code FROM [dbo].[B20ItemHQ] WHERE ColorVIE LIKE :color")
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={"color": f"%{target_color}%"})

            df = df.fillna("")

            if df.empty: 
                return {
                    "search_type": "color",
                    "keyword": target_color,
                    "product_filter": target_product_kw,
                    "products": [],
                    "count": 0,
                    "message": f"Không tìm thấy màu '{target_color}' trong kho."
                }

            # =======================================================
            # C. LỌC MÀU CHÍNH XÁC (Khắc phục Green vs Dark Green)
            # =======================================================
            def is_true_color_match(row_text):
                if not row_text: return False
                text_lower = str(row_text).lower()
                target_lower = target_color.lower()
                
                best_match_in_row = None
                for vocab in self.vocab_sorted:
                    if re.search(rf"\b{re.escape(vocab.lower())}\b", text_lower):
                        best_match_in_row = vocab.lower()
                        break 
                
                if best_match_in_row:
                    if target_lower in best_match_in_row and target_lower != best_match_in_row:
                        return False
                return True

            df_filtered = df[df['ColorVIE'].apply(is_true_color_match)]

            # =======================================================
            # D. LỌC THEO TÊN SẢN PHẨM (Negative Filter)
            # =======================================================
            if target_product_kw:
                df_filtered = df_filtered[df_filtered['Name'].str.contains(target_product_kw, case=False, na=False)]
                
                exclusions = self.product_exclusions.get(target_product_kw, [])
                if exclusions:
                    def is_clean_product(row_name):
                        if not row_name: return False
                        name_lower = str(row_name).lower()
                        for exc in exclusions:
                            if exc in name_lower and exc not in user_input_lower:
                                return False 
                        return True
                    df_filtered = df_filtered[df_filtered['Name'].apply(is_clean_product)]

            if df_filtered.empty: 
                return {
                    "search_type": "color",
                    "keyword": target_color,
                    "product_filter": target_product_kw,
                    "products": [],
                    "count": 0,
                    "message": f"Kho có màu '{target_color}' nhưng không có sản phẩm '{target_product_kw}' nào."
                }

            # =======================================================
            # E. TRỘN ĐA DẠNG KẾT QUẢ ĐỂ HIỂN THỊ
            # =======================================================
            # Lấy 1 sản phẩm đại diện cho mỗi loại vải/màu (ColorVIE) để đẩy lên đầu
            df_unique_sources = df_filtered.drop_duplicates(subset=['ColorVIE'])
            # Lấy các sản phẩm trùng lặp còn lại
            df_rest = df_filtered.drop(df_unique_sources.index)
            # Ghép lại: Dòng độc nhất lên đầu, dòng trùng lặp xuống dưới cùng
            df_diverse = pd.concat([df_unique_sources, df_rest])

            return {
                "search_type": "color",
                "keyword": target_color,
                "product_filter": target_product_kw,
                "products": df_diverse.to_dict('records'), # Trả về list đã trộn
                "count": len(df_filtered) # Số lượng thực tế không đổi
            }

        except Exception as e:
            print(f"🚨 Lỗi truy vấn màu (ColorBrain): {e}")
            return None