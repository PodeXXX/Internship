import os
import pandas as pd
import torch
import pickle
import numpy as np
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments, EarlyStoppingCallback
from torch.utils.data import Dataset

# ================= 1. CẤU HÌNH HỆ THỐNG =================
SERVER = r'LOCALHOST\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

NEW_MODEL_DIR = r"live_db_hscode_model_v2"
BASE_MODEL_NAME = "vinai/phobert-base-v2"
MAX_LEN = 128

# ================= 2. CLASS DATASET =================
class HSCodeDataset(Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)

# ================= 3. HÀM TÍNH TOÁN CHỈ SỐ (METRICS) =================
def compute_metrics(pred):
    """Hàm này được gọi tự động sau mỗi Epoch và sau khi Eval xong"""
    labels = pred.label_ids
    # Lấy class có xác suất cao nhất làm dự đoán
    preds = pred.predictions.argmax(-1)
    
    # Tính các chỉ số trung bình (macro/weighted)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average='weighted', zero_division=0)
    acc = accuracy_score(labels, preds)
    
    return {
        'accuracy': acc,
        'f1': f1,
        'precision': precision,
        'recall': recall
    }

# ================= 4. HÀM VẼ BIỂU ĐỒ TRỰC QUAN =================
def plot_training_history(log_history, save_path="training_history.png"):
    """Rút trích lịch sử training và vẽ biểu đồ"""
    train_loss = []
    eval_loss = []
    eval_acc = []
    eval_f1 = []
    epochs = []

    for log in log_history:
        if 'loss' in log and 'epoch' in log:
            train_loss.append(log['loss'])
        if 'eval_loss' in log and 'epoch' in log:
            eval_loss.append(log['eval_loss'])
            eval_acc.append(log['eval_accuracy'])
            eval_f1.append(log['eval_f1'])
            epochs.append(log['epoch'])

    # Đảm bảo độ dài mảng bằng nhau để vẽ
    min_len = min(len(train_loss), len(eval_loss))
    epochs = epochs[:min_len]
    train_loss = train_loss[:min_len]
    eval_loss = eval_loss[:min_len]
    eval_acc = eval_acc[:min_len]
    eval_f1 = eval_f1[:min_len]

    if not epochs:
        print("⚠️ Không có đủ dữ liệu log để vẽ biểu đồ.")
        return

    plt.figure(figsize=(14, 6))

    # Biểu đồ 1: Biến thiên Loss (Train vs Eval)
    plt.subplot(1, 2, 1)
    plt.plot(epochs, train_loss, 'b-o', label='Training Loss')
    plt.plot(epochs, eval_loss, 'r-s', label='Validation Loss')
    plt.title('Biến thiên hàm mất mát (Loss) qua các Epoch')
    plt.xlabel('Epochs')
    plt.ylabel('Loss')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)

    # Biểu đồ 2: Biến thiên Độ chính xác (Accuracy) và F1-Score
    plt.subplot(1, 2, 2)
    plt.plot(epochs, eval_acc, 'g-o', label='Validation Accuracy')
    plt.plot(epochs, eval_f1, 'm-s', label='Validation F1-Score')
    plt.title('Hiệu suất dự đoán qua các Epoch')
    plt.xlabel('Epochs')
    plt.ylabel('Score')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    print(f"📊 Đã xuất biểu đồ trực quan ra file: {os.path.abspath(save_path)}")

# ================= 5. QUY TRÌNH TRAIN =================
def main():
    print("⏳ 1. Đang kết nối Database và rút dữ liệu...")
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
        
    print(f"✅ Rút thành công {len(df)} dòng dữ liệu hợp lệ.")
    
    df['text_input'] = df['Name'].astype(str) + " [SEP] Spec:  [SEP] Mat:  [SEP] Color: "
    
    print("⏳ 2. Đang chuẩn bị Label Encoder...")
    label_encoder = LabelEncoder()
    df['label'] = label_encoder.fit_transform(df['CodeHS'])
    
    num_labels = len(label_encoder.classes_)
    print(f"✅ Tổng số mã HS (Classes): {num_labels}")
    
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        df['text_input'].tolist(), 
        df['label'].tolist(), 
        test_size=0.2, 
        random_state=42
    )
    
    print("⏳ 3. Đang load Tokenizer và đóng gói dữ liệu...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME)
    
    train_encodings = tokenizer(train_texts, truncation=True, padding=True, max_length=MAX_LEN)
    val_encodings = tokenizer(val_texts, truncation=True, padding=True, max_length=MAX_LEN)
    
    train_dataset = HSCodeDataset(train_encodings, train_labels)
    val_dataset = HSCodeDataset(val_encodings, val_labels)
    
    print(f"⏳ 4. Đang khởi tạo Model PhoBERT với {num_labels} nhãn...")
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"🖥️ Thiết bị sử dụng: {device}")
    
    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL_NAME, num_labels=num_labels)
    model.to(device)
    
    training_args = TrainingArguments(
        output_dir='./results',          
        num_train_epochs=30,             # Tăng lên 30 epochs
        learning_rate=2e-5,              # Tinh chỉnh Learning Rate chuẩn cho Fine-tuning
        per_device_train_batch_size=8,   
        per_device_eval_batch_size=8,   
        warmup_steps=500,                
        weight_decay=0.01,               
        logging_dir='./logs',            
        logging_strategy="epoch",        # Log theo từng epoch để vẽ biểu đồ dễ hơn
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",      # Chọn model tốt nhất dựa trên F1
        save_total_limit=2               # Giữ lại 2 bản lưu gần nhất để tránh tốn ổ cứng
    )
    
    trainer = Trainer(
        model=model,                         
        args=training_args,                  
        train_dataset=train_dataset,         
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=4)] # Dừng sớm nếu 4 vòng liên tiếp không tiến bộ
    )
    
    print("🔥 5. BẮT ĐẦU TRAINING...")
    trainer.train()
    
    # ================= 6. VẼ BIỂU ĐỒ =================
    print("\n" + "="*50)
    print("📈 6. ĐANG TIẾN HÀNH ĐÁNH GIÁ VÀ VẼ BIỂU ĐỒ...")
    
    # Gọi hàm vẽ biểu đồ từ lịch sử của Trainer
    plot_training_history(trainer.state.log_history)
    
    # Lấy dự đoán trên tập Validation cho báo cáo text
    predictions = trainer.predict(val_dataset)
    metrics = predictions.metrics
    
    print("\n" + "="*50)
    print(f"🌟 BÁO CÁO HIỆU SUẤT MÔ HÌNH PHO-BERT (Dự đoán HS Code)")
    print("="*50)
    print(f"{'Chỉ số (Metric)':<20} | {'Giá trị (Value)':<15}")
    print("-" * 50)
    print(f"{'Accuracy (Độ chính xác)':<20} | {metrics['test_accuracy'] * 100:.2f} %")
    print(f"{'F1-Score (Trọng số)':<20} | {metrics['test_f1'] * 100:.2f} %")
    print(f"{'Precision (Độ chuẩn)':<20} | {metrics['test_precision'] * 100:.2f} %")
    print(f"{'Recall (Độ phủ)':<20} | {metrics['test_recall'] * 100:.2f} %")
    print(f"{'Eval Loss':<20} | {metrics['test_loss']:.4f}")
    print("=" * 50)
    
    preds = np.argmax(predictions.predictions, axis=-1)
    class_report = classification_report(val_labels, preds, target_names=label_encoder.classes_, zero_division=0)
    
    report_path = "evaluation_report.txt"
    with open(report_path, "w", encoding='utf-8') as f:
        f.write("BÁO CÁO TỔNG QUAN\n")
        f.write("="*50 + "\n")
        f.write(f"Accuracy : {metrics['test_accuracy']:.4f}\n")
        f.write(f"F1-Score : {metrics['test_f1']:.4f}\n")
        f.write("="*50 + "\n\n")
        f.write("BÁO CÁO CHI TIẾT TỪNG MÃ HS CODE\n")
        f.write(class_report)
        
    print(f"📁 Đã lưu Báo cáo phân loại chi tiết ra file: {os.path.abspath(report_path)}")
    
    print(f"\n✅ 7. Đang lưu model ra thư mục: {NEW_MODEL_DIR}")
    if not os.path.exists(NEW_MODEL_DIR):
        os.makedirs(NEW_MODEL_DIR)
        
    model.save_pretrained(NEW_MODEL_DIR)
    tokenizer.save_pretrained(NEW_MODEL_DIR)
    with open(os.path.join(NEW_MODEL_DIR, "label_encoder.pkl"), "wb") as f:
        pickle.dump(label_encoder, f)
        
    print("🎉 HOÀN TẤT!")

if __name__ == "__main__":
    main()