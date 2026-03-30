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
        self.raw_rules = [] 
        self._reload_rules()

    def _reload_rules(self):
        try:
            if not os.path.exists(self.json_path): return
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.raw_rules = json.load(f)
            ids, docs, metadatas = [], [], []
            for idx, rule in enumerate(self.raw_rules):
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
        
        core_phrases = [
            "bao áo", "áo ghế", "bao ghế", "vỏ gối", "bao nệm", "mặt bàn", 
            "mẫu gỗ", "mẫu vải", "mẫu da", "swatch", "sofa bed", "daybed", "giường",
            "chân ghế", "khung ghế", "chân sắt", "tay ghế", "cụm tay", "khung chân", "chân gỗ", "khung gỗ",
            "khung giường", "bed frame", "chân giường", 
            "đầu giường", "nệm ngồi", "nệm tựa", "tựa lưng", "gối", "mâm xoay",
            "ghế xoay", "ghế ăn", "dining", "ghế lười", "beanbag",
            "đôn", "ottoman", "băng", "bench", "chaise", "lounge", "sectional", "sofa",
            "vải dệt", "dệt kim", "dệt thoi", "polyester", "giả da", "simili", "vải"
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
                    # [SỬA LỖI] Dùng \b để đảm bảo cấm đúng từ, không cấm chuỗi con ("da" không dính "daybed")
                    if exc_clean and re.search(r'\b' + re.escape(exc_clean) + r'\b', query_lower):
                        is_excluded = True; break
            if is_excluded: continue

            rule_words = extract_words(desc_lower)
            matched_words = query_words.intersection(rule_words)
            overlap_count = len(matched_words)
            
            bonus = 0
            matched_bonus_phrases = []
            for phrase in core_phrases:
                # [SỬA LỖI] Tìm từ khóa độc lập, không dính chùm
                if re.search(r'\b' + re.escape(phrase) + r'\b', query_lower) and re.search(r'\b' + re.escape(phrase) + r'\b', desc_lower):
                    matched_bonus_phrases.append(phrase) 
                    idx = query_lower.find(phrase)
                    # [SỬA LỖI] Trọng số vị trí: Keyword xuất hiện đầu câu quyết định tính chất sản phẩm!
                    if idx <= 30: 
                        bonus += 30 
                    else: 
                        bonus += 5  
                        
            total_score = (overlap_count * 2.0) + bonus - distance
            
            if meta['code'] in PART_CODES:
                first_part_idx = 999
                for pk in PART_KEYWORDS:
                    idx = query_lower.find(pk)
                    if idx != -1 and idx < first_part_idx:
                        first_part_idx = idx
                if query_lower.startswith(("ghế", "sofa", "giường", "bàn", "tủ", "đôn")) and first_part_idx > 25:
                    total_score -= 100 

            # Chỉ cần có từ trùng khớp là tính, ưu tiên điểm cao nhất
            if total_score > best_score and (bonus > 0 or overlap_count > 0):
                best_score = total_score
                best_rule = {
                    "code": meta['code'], 
                    "desc": desc, 
                    "note": meta['note'],
                    "matched_words": list(matched_words),             
                    "matched_bonus": list(set(matched_bonus_phrases)) 
                }
                    
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
        if any(trig in text_lower for trig in hscode_triggers): return True
        if len(text_input.split()) > 3: return True
        return False

    def process_hscode(self, user_input):
        if not self.is_ready: return {"status": "error", "msg": "Hệ thống AI đang khởi động..."}
        
        user_input_raw = user_input.strip() 
        user_input_clean = user_input.replace("-", " ").replace("_", " ").strip()
        user_input_lower = user_input_clean.lower()
        steps = []
        
        material_found = ""
        item_group_code = ""
        item_group_name = "" 
        
        try:
            code_match = re.search(r'\b\d{7,8}\b', user_input_raw)
            search_code = code_match.group(0) if code_match else user_input_raw

            query = text("""
                SELECT TOP 1 
                    P.Code, 
                    COALESCE(I_ID.FootTypeCode, I_Code.FootTypeCode, '') as Mat,
                    LTRIM(RTRIM(COALESCE(I_ID.ItemGroupCode, I_Code.ItemGroupCode, ''))) as ItemGroupCode,
                    LTRIM(RTRIM(IG.Name)) as ItemGroupName
                FROM dbo.B20Product P 
                LEFT JOIN dbo.B20Item I_ID ON P.ItemId = I_ID.Id 
                LEFT JOIN dbo.B20Item I_Code ON LEFT(P.Code, 8) = I_Code.Code
                LEFT JOIN dbo.B20ItemGroup IG ON LTRIM(RTRIM(COALESCE(I_ID.ItemGroupCode, I_Code.ItemGroupCode))) = LTRIM(RTRIM(IG.Code))
                WHERE P.Name LIKE :name OR P.Code = :code
            """)
            with self.db_engine.connect() as conn:
                result = conn.execute(query, {"name": f"%{user_input_raw}%", "code": search_code}).fetchone()
                
                if result:
                    p_code = result[0]
                    mat = result[1]
                    ig_code = result[2]
                    ig_name = result[3]
                    
                    steps.append(f"🔍 SQL: Tìm thấy mã nội bộ {p_code}")
                    if mat: material_found = mat
                    if ig_code: item_group_code = ig_code
                    if ig_name: item_group_name = ig_name
        except Exception as e: 
            print(f"Lỗi SQL HSCodeBrain: {e}")

        rule_res = self.rule_engine.search(user_input_clean)
        rule_code = rule_res['code'] if rule_res else None
        if rule_code: steps.append(f"🛡️ RULE: {rule_code}")
        
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

        # =========================================================
        # TRỌNG TÀI THÉP VÀ QUYỀN CỨU GIÁ CỦA AI
        # =========================================================
        part_hs_prefixes = ("94019", "94039", "6304", "4421", "4107") 
        exemption_keywords = ["bao áo", "áo", "vỏ", "mẫu", "swatch"]
        
        if item_group_code:
            steps.append(f"⚖️ TRỌNG TÀI: Thuộc nhóm [{item_group_code}]")
            has_exemption = any(kw in user_input_lower for kw in exemption_keywords)
            
            if item_group_code in ["1551", "1561", "15514"]:
                if rule_code and rule_code.startswith(part_hs_prefixes) and not has_exemption:
                    rule_code = None 
            elif item_group_code == "BTP":
                if rule_code and not rule_code.startswith(part_hs_prefixes):
                    rule_code = None
            elif item_group_code in ["1521", "1522", "1523", "1526", "1531"]:
                rule_code = "CẢNH BÁO"
                rule_res = {"note": f"Mặt hàng thuộc nhóm Vật Liệu ({item_group_code}), tra cứu HS theo đặc tính nguyên liệu (Vải, Gỗ...) chứ không phải chương Nội Thất 94."}

        # [QUYỀN CỨU GIÁ CỦA AI] 
        # Nếu AI tự tin > 50% và khác chương với Luật, ĐỒNG THỜI Luật không bắt được Từ khóa Sát thủ nào (matched_bonus = 0)
        # Chứng tỏ Luật chỉ đang đoán mò dựa trên các từ chung chung -> Nhường sân cho AI!
        if rule_code and rule_code != "CẢNH BÁO":
            if confidence > 50.0 and len(rule_res.get('matched_bonus', [])) == 0 and rule_code[:2] != ai_code[:2]:
                 steps.append("⚠️ CẢNH BÁO LUẬT: Luật bắt yếu. AI đang rất tự tin. Ưu tiên AI!")
                 rule_code = None 

        ai_matched_words = []
        user_words = set(re.sub(r'[^\w\s]', ' ', user_input_clean.lower()).split())
        for r in self.rule_engine.raw_rules:
            if r['code'] == ai_code:
                ai_rule_words = set(re.sub(r'[^\w\s]', ' ', r['desc'].lower()).split())
                ai_matched_words = list(user_words.intersection(ai_rule_words))
                break

        return {
            "status": "ok", 
            "search_mode": "hscode",
            "item_group_code": item_group_code,
            "item_group_name": item_group_name,
            "rule_code": rule_code, 
            "rule_note": rule_res['note'] if rule_res else "",
            "rule_matched_words": rule_res.get('matched_words', []) if rule_res else [],
            "rule_matched_bonus": rule_res.get('matched_bonus', []) if rule_res else [],
            "ai_code": ai_code, 
            "ai_conf": confidence,
            "ai_matched_words": [w for w in ai_matched_words if len(w) > 1 and not w.isnumeric()],
            "steps": steps
        }