import torch
import pickle
import json
import os
import re
import threading
import chromadb
from chromadb.utils import embedding_functions
from sqlalchemy import create_engine, text
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ================= CẤU HÌNH HỆ THỐNG =================
SERVER = 'LOCALHOST\\SQLEXPRESS' 
DATABASE = 'pode'
CONN_STR = f'mssql+pyodbc://{SERVER}/{DATABASE}?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes'

MODEL_DIR = os.path.join(os.path.dirname(__file__), "live_db_hscode_model_v2")
RULES_FILE = "rules.json"
MAX_LEN = 128

class VectorRuleEngine:
    def __init__(self, json_path=RULES_FILE):
        self.json_path = json_path
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.client = chromadb.EphemeralClient() 
        self.collection = self.client.create_collection(name="hscode_rules", embedding_function=self.ef)
        self._reload_rules()

    def _reload_rules(self):
        try:
            if not os.path.exists(self.json_path): return
            with open(self.json_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            ids, docs, metadatas = [], [], []
            for idx, rule in enumerate(rules):
                ids.append(str(idx))
                docs.append(f"{rule['desc']}") 
                metadatas.append({
                    "code": rule['code'],
                    "excludes": ",".join(rule.get('excludes', [])),
                    "note": rule.get('note', '')
                })
            if docs:
                self.collection.add(ids=ids, documents=docs, metadatas=metadatas)
        except Exception as e: print(f"Lỗi Vector DB: {e}")

    def search(self, query_text, top_k=20): 
        if not self.collection: return None
        results = self.collection.query(query_texts=[query_text], n_results=top_k)
        if not results['documents'] or not results['documents'][0]: return None
        
        query_lower = query_text.lower()
        
        def extract_words(text):
            clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
            return set([w for w in clean_text.split() if len(w) > 1 and not w.isnumeric()])
            
        query_words = extract_words(query_lower)
        
        special_phrases = [
            "bao áo", "áo ghế", "bao ghế", "vỏ gối", "bao nệm", "mặt bàn", 
            "mẫu gỗ", "mẫu vải", "mẫu da", "swatch", "sofa bed", "daybed", "giường",
            "chân ghế", "khung ghế", "chân sắt", "tay ghế", "cụm tay", "khung chân", "chân gỗ", "khung gỗ",
            "khung giường", "bed frame", "chân giường", 
            "đầu giường", "nệm ngồi", "tựa lưng", "gối", "mâm xoay",
            "ghế xoay", "ghế ăn", "dining chair", "ghế lười", "beanbag",
            "đôn", "ottoman", "băng", "bench", "chaise", "lounge", "sectional", "sofa"
        ]
        
        PART_CODES = ["94019100", "94019991", "94019999", "94019099", "94039100", "94039990"]
        PART_KEYWORDS = ["chân", "khung", "tay", "mặt bàn", "đầu giường", "bộ phận", "parts", "armrest"]

        best_rule = None
        best_score = -999
        
        for i in range(len(results['ids'][0])):
            distance = results['distances'][0][i]
            meta = results['metadatas'][0][i]
            desc = results['documents'][0][i]
            desc_lower = desc.lower()
            
            is_excluded = False
            if meta['excludes']:
                exclude_list = meta['excludes'].split(',')
                for exc in exclude_list:
                    exc_clean = exc.strip().lower()
                    if exc_clean and exc_clean in query_lower:
                        is_excluded = True; break
            if is_excluded: continue

            rule_words = extract_words(desc_lower)
            overlap_count = len(query_words.intersection(rule_words))
            
            bonus = 0
            for phrase in special_phrases:
                if phrase in query_lower and phrase in desc_lower:
                    idx = query_lower.find(phrase)
                    if idx <= 15: bonus += 50 
                    elif idx <= 35: bonus += 15
                    else: bonus += 5
                    
            total_score = (overlap_count * 3.0) + bonus - distance
            
            if meta['code'] in PART_CODES:
                first_part_idx = 999
                for pk in PART_KEYWORDS:
                    idx = query_lower.find(pk)
                    if idx != -1 and idx < first_part_idx:
                        first_part_idx = idx
                if query_lower.startswith(("ghế", "sofa", "giường", "bàn", "tủ", "đôn")) and first_part_idx > 25:
                    total_score -= 100 

            if bonus > 0 or overlap_count >= 2:
                if total_score > best_score:
                    best_score = total_score
                    best_rule = {"code": meta['code'], "desc": desc, "note": meta['note']}
                    
        return best_rule

class HSCodeBrain:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = None
        self.model = None
        self.label_encoder = None
        self.db_engine = None
        self.rule_engine = None
        self.is_ready = False

    def load_resources(self, callback_msg):
        def _load():
            try:
                callback_msg("SYSTEM: Đang khởi tạo AI Model và Vector Rules...")
                self.rule_engine = VectorRuleEngine()
                self.db_engine = create_engine(CONN_STR)
                
                if os.path.exists(MODEL_DIR):
                    self.tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
                    self.model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
                    with open(os.path.join(MODEL_DIR, "label_encoder.pkl"), "rb") as f:
                        self.label_encoder = pickle.load(f)
                    self.model.to(self.device)
                    self.is_ready = True
                    callback_msg("SYSTEM: HS Code Brain Đã Sẵn Sàng!")
                else:
                    callback_msg("SYSTEM: Lỗi - Không tìm thấy thư mục model.")
            except Exception as e: callback_msg(f"SYSTEM: Lỗi khởi tạo - {str(e)}")
        threading.Thread(target=_load, daemon=True).start()

    def is_hscode_intent(self, text_input):
        text_lower = text_input.lower()
        hscode_triggers = ["phân tích", "mã hs", "hs code", "hscode", "tra mã", "check", "mã số"]
        
        # Nếu người dùng có các từ mồi trên -> Chắc chắn là tra mã
        if any(trig in text_lower for trig in hscode_triggers):
            return True
            
        # NẾU CÂU QUÁ DÀI VÀ CÓ CHỨA MÃ SỐ/CHỮ TIẾNG ANH (Như tên sản phẩm), mặc định ném vào tra HS Code
        if len(text_input.split()) > 3:
            return True
            
        return False

    def process_hscode(self, user_input):
        if not self.is_ready: return {"status": "error", "msg": "Hệ thống AI đang khởi động..."}
        
        user_input_clean = user_input.replace("-", " ").replace("_", " ").strip()
        steps = []
        
        material_found = ""
        try:
# [CẬP NHẬT] Lấy thêm ItemGroupCode để làm Luật Thép
            query = text("""
                SELECT TOP 1 
                    P.Code, 
                    COALESCE(I_ID.FootTypeCode, I_Code.FootTypeCode, '') as Mat,
                    COALESCE(I_ID.ItemGroupCode, I_Code.ItemGroupCode, '') as ItemGroupCode
                FROM dbo.B20Product P 
                LEFT JOIN dbo.B20Item I_ID ON P.ItemId = I_ID.Id 
                LEFT JOIN dbo.B20Item I_Code ON LEFT(P.Code, 8) = I_Code.Code
                WHERE P.Name LIKE :name OR P.Code = :code
            """)
            item_group_code = ""
            with self.db_engine.connect() as conn:
                db_info = conn.execute(query, {"name": f"%{user_input_clean}%", "code": user_input_clean}).fetchone()
                if db_info:
                    steps.append(f"🔍 SQL: Tìm thấy mã nội bộ {db_info.Code}")
                    if db_info.Mat: material_found = db_info.Mat
                    if db_info.ItemGroupCode: item_group_code = db_info.ItemGroupCode
            with self.db_engine.connect() as conn:
                db_info = conn.execute(query, {"name": f"%{user_input_clean}%", "code": user_input_clean}).fetchone()
                if db_info:
                    steps.append(f"🔍 SQL: Tìm thấy mã nội bộ {db_info.Code}")
                    if db_info.Mat: material_found = db_info.Mat
        except: pass

        rule_res = self.rule_engine.search(user_input_clean)
        rule_code = None
        if rule_res:
            rule_code = rule_res['code']
            steps.append(f"🛡️ RULE: {rule_code}")
        
        steps.append("🤖 AI: Đang suy luận HS Code...")
        full_text_ai = f"{user_input_clean} [SEP] Spec:  [SEP] Mat: {material_found} [SEP] Color: "
        inputs = self.tokenizer(full_text_ai, return_tensors="pt", padding=True, truncation=True, max_length=MAX_LEN)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
        probs = outputs.logits.softmax(dim=1)
        conf, idx = torch.max(probs, dim=1)
        ai_code = self.label_encoder.inverse_transform(idx.cpu().numpy())[0]
        confidence = conf.item() * 100
        steps.append(f"🤖 AI: {ai_code} ({confidence:.1f}%)")

        return {
            "status": "ok", 
            "search_mode": "hscode",
            "rule_code": rule_code, 
            "rule_note": rule_res['note'] if rule_res else "",
            "ai_code": ai_code, 
            "ai_conf": confidence,
            "steps": steps
        }