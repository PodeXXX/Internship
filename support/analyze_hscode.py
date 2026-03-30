import pandas as pd
from sqlalchemy import create_engine, text
import os

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = r'LOCALHOST\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

def extract_first_two_words(name):
    """Hàm trích xuất 2 từ đầu tiên của tên sản phẩm"""
    if not name or pd.isna(name): return "UNKNOWN"
    words = str(name).strip().split()
    # Lấy tối đa 2 từ đầu tiên, viết hoa để dễ nhóm
    return " ".join(words[:2]).upper() if len(words) >= 2 else str(name).strip().upper()

def main():
    print("⏳ Đang rút dữ liệu từ Database...")
    engine = create_engine(CONN_STR)
    
    # 1. Truy vấn lấy mã HS và Tên SP (loại bỏ rác)
    query = text("""
        SELECT CodeHS, Name
        FROM [pode].[dbo].[B20ItemHQ]
        WHERE CodeHS IS NOT NULL 
          AND LTRIM(RTRIM(CodeHS)) <> ''
          AND CodeHS NOT IN ('#N/A', '0')
    """)
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
        
    print(f"✅ Rút thành công {len(df)} dòng dữ liệu hợp lệ.")
    
    # 2. Xử lý dữ liệu: Tạo cột "Nhóm sản phẩm" dựa trên 2 từ đầu tiên
    df['Product_Group'] = df['Name'].apply(extract_first_two_words)
    
    # 3. Thống kê: Nhóm theo HS Code và Nhóm sản phẩm, đếm số lượng
    summary = df.groupby(['CodeHS', 'Product_Group']).size().reset_index(name='Frequency')
    
    # Sắp xếp: Ưu tiên hiển thị Mã HS trước, nhóm nào xuất hiện nhiều nhất đứng đầu
    summary = summary.sort_values(by=['CodeHS', 'Frequency'], ascending=[True, False])
    
    # 4. In ra Terminal (Chỉ in ra top 3 nhóm phổ biến nhất của mỗi mã để khỏi rối mắt)
    print("\n📊 BẢNG TÓM TẮT MÃ HS VÀ NHÓM SẢN PHẨM:")
    print("=" * 60)
    
    unique_codes = summary['CodeHS'].unique()
    for code in unique_codes:
        print(f"\n🏷️ MÃ HS: {code}")
        # Lấy các nhóm sản phẩm thuộc mã này
        subset = summary[summary['CodeHS'] == code]
        total_products = subset['Frequency'].sum()
        print(f"   Tổng cộng: {total_products} sản phẩm")
        
        # In chi tiết top 5
        top_5 = subset.head(5)
        for _, row in top_5.iterrows():
            print(f"   ├── [{row['Frequency']:>4} lần] : {row['Product_Group']}")
            
        if len(subset) > 5:
            print(f"   └── ... và {len(subset) - 5} nhóm khác nhỏ lẻ hơn.")

    print("=" * 60)
    
    # 5. Xuất toàn bộ ra file CSV
    output_file = "hscode_summary.csv"
    summary.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"🎉 Đã xuất toàn bộ báo cáo chi tiết ra file: {os.path.abspath(output_file)}")

if __name__ == "__main__":
    main()