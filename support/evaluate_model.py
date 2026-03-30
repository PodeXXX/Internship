import os
import pandas as pd
import torch
import pickle
import numpy as np
from sqlalchemy import create_engine, text
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ================= 1. CẤU HÌNH =================
SERVER = r'LOCALHOST\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

MODEL_DIR = r"live_db_hscode_model_v2"
MAX_LEN = 128
BATCH_SIZE = 16

def main():
    print("="*60)
    print("🔬 HỆ THỐNG ĐÁNH GIÁ MÔ HÌNH HS CODE (EVALUATION)")
    print("="*60)

    # 1. LOAD MODEL VÀ TOKENIZER TỪ Ổ CỨNG
    if not os.path.exists(MODEL_DIR):
        print(f"❌ Lỗi: Không tìm thấy mô hình tại {MODEL_DIR}. Hãy chạy file train_model.py trước.")
        return

    print("⏳ Đang tải Mô hình và Bộ giải mã...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"🖥️ Thiết bị sử dụng: {device}")
    
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.to(device)
    model.eval() # Bật chế độ Evaluation (Khóa cập nhật trọng số)

    with open(os.path.join(MODEL_DIR, "label_encoder.pkl"), "rb") as f:
        label_encoder = pickle.load(f)

    # 2. LẤY DỮ LIỆU TỪ DATABASE
    print("⏳ Đang rút dữ liệu từ Database...")
    engine = create_engine(CONN_STR)
    query = text("""
        SELECT Name, CodeHS 
        FROM [pode].[dbo].[B20ItemHQ] 
        WHERE CodeHS IS NOT NULL 
          AND LTRIM(RTRIM(CodeHS)) <> ''
          AND CodeHS NOT IN ('#N/A', '0')
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    df['text_input'] = df['Name'].astype(str) + " [SEP] Spec:  [SEP] Mat:  [SEP] Color: "
    df['label'] = label_encoder.transform(df['CodeHS'])

    # GIỮ ĐÚNG RANDOM_STATE=42 ĐỂ LẤY ĐƯỢC CHÍNH XÁC TẬP 20% TEST LÚC TRAIN
    _, val_texts, _, val_labels_encoded = train_test_split(
        df['text_input'].tolist(), 
        df['label'].tolist(), 
        test_size=0.2, 
        random_state=42
    )

    # 3. CHẠY DỰ ĐOÁN HÀNG LOẠT (INFERENCE)
    print(f"⏳ Đang tiến hành dự đoán trên {len(val_texts)} sản phẩm Test...")
    
    all_preds = []
    
    # Dự đoán theo lô (batch) để tránh đầy RAM
    with torch.no_grad():
        for i in range(0, len(val_texts), BATCH_SIZE):
            batch_texts = val_texts[i:i+BATCH_SIZE]
            inputs = tokenizer(batch_texts, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            outputs = model(**inputs)
            logits = outputs.logits
            preds = torch.argmax(logits, dim=-1).cpu().numpy()
            all_preds.extend(preds)

    # 4. TÍNH TOÁN CHỈ SỐ
    accuracy = accuracy_score(val_labels_encoded, all_preds)
    precision, recall, f1, _ = precision_recall_fscore_support(val_labels_encoded, all_preds, average='weighted', zero_division=0)
    
    print("\n" + "="*50)
    print(f"🌟 BÁO CÁO HIỆU SUẤT TỔNG THỂ")
    print("="*50)
    print(f"{'Accuracy (Độ chính xác)':<25} | {accuracy * 100:.2f} %")
    print(f"{'F1-Score (Trọng số)':<25} | {f1 * 100:.2f} %")
    print(f"{'Precision (Độ chuẩn)':<25} | {precision * 100:.2f} %")
    print(f"{'Recall (Độ phủ)':<25} | {recall * 100:.2f} %")
    print("=" * 50)

    # 5. XUẤT BÁO CÁO PHÂN TÍCH SAI SỐ (ERROR ANALYSIS) RA EXCEL
    # Lấy lại tên gốc của sản phẩm bằng cách cắt bỏ các thẻ [SEP]
    clean_names = [text.split(" [SEP]")[0] for text in val_texts]
    true_hs_codes = label_encoder.inverse_transform(val_labels_encoded)
    pred_hs_codes = label_encoder.inverse_transform(all_preds)

    result_df = pd.DataFrame({
        'Tên Sản Phẩm': clean_names,
        'Mã HS Thực tế (Đáp án)': true_hs_codes,
        'Mã HS AI Dự đoán': pred_hs_codes
    })

    # Lọc ra những dòng AI đoán sai
    errors_df = result_df[result_df['Mã HS Thực tế (Đáp án)'] != result_df['Mã HS AI Dự đoán']]
    
    error_file = "AI_Error_Analysis.xlsx"
    errors_df.to_excel(error_file, index=False)
    
    print(f"\n🚨 CẢNH BÁO: AI đã đoán sai {len(errors_df)} / {len(val_texts)} sản phẩm.")
    print(f"📁 Bảng phân tích chi tiết các sản phẩm bị đoán sai đã được xuất ra file: {os.path.abspath(error_file)}")
    print("💡 MẸO: Hãy mở file Excel này ra xem. Nó sẽ cho bạn biết những loại sản phẩm nào đang làm AI bối rối nhất!")

if __name__ == "__main__":
    main()