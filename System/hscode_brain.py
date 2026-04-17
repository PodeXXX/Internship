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

# ================= BỘ NÃO 1: SIÊU CÂY QUYẾT ĐỊNH (MASTER TREE) =================
class MasterTreeEngine:
    def evaluate(self, text):
        t = text.lower()
        
        def has_any(keywords): 
            # Dùng Regex để tìm từ ĐỘC LẬP, chống lỗi "da" nằm trong "daybed"
            for k in keywords:
                if re.search(r'(?<![\w])' + re.escape(k) + r'(?![\w])', t): return True
            return False
            
        def first_pos(keywords):
            positions = []
            for k in keywords:
                match = re.search(r'(?<![\w])' + re.escape(k) + r'(?![\w])', t)
                if match: positions.append(match.start())
            return min(positions) if positions else 9999

        # ==========================================
        # 1. CÁC NHÓM PHỤ KIỆN, MẪU VÀ VẬT TƯ
        # ==========================================
        if first_pos(["mẫu", "swatch"]) < 30:
            if has_any(["da", "leather"]): return {"code": "41079900", "note": "Mẫu vật liệu Da", "match": "Tree: Mẫu + Da"}
            if has_any(["gỗ", "wood"]): return {"code": "44219999", "note": "Mẫu vật liệu Gỗ", "match": "Tree: Mẫu + Gỗ"}
            return {"code": "63079090", "note": "Mẫu vật liệu Vải", "match": "Tree: Mẫu + Vải"}

        if first_pos(["bao", "áo ghế", "bao ghế", "vỏ", "cover", "case"]) < 30:
            return {"code": "63049190", "note": "Vỏ bọc (Vải/Da) không chứa ruột", "match": "Tree: Vỏ bọc"}

        if first_pos(["nệm", "cushion", "pillow", "gối"]) < 30:
            return {"code": "94049000", "note": "Đệm lót, tựa lưng, gối (đã nhồi ruột)", "match": "Tree: Đệm/Gối"}

        # Khai báo các biến vật liệu chung
        is_wood = has_any(["gỗ", "wood", "oak", "sồi", "rubber", "cao su", "beech", "plywood", "ván ép", "walnut", "óc chó", "tràm", "acacia", "pine", "thông"])
        is_metal = has_any(["sắt", "kim loại", "metal", "steel", "iron", "nhôm", "đồng", "brass"])
        is_upholstered = has_any(["bọc", "nệm", "upholstered", "foam", "vải", "fabric", "leather", "pu", "mút", "cushion", "da"])

        # ==========================================
        # 2. XÁC ĐỊNH NHÓM SẢN PHẨM CHÍNH NỘI THẤT
        # ==========================================
        pos_chair = first_pos(["ghế", "sofa", "đôn", "bench", "lounge", "ottoman", "barstool", "seat", "chaise", "daybed"])
        pos_bed = first_pos(["giường", "bed king", "king bed", "queen bed", "bed queen", "bed sun"]) 
        pos_table = first_pos(["bàn", "kệ", "tủ", "table", "cabinet", "shelf"])
        
        pos_bed_part = first_pos(["khung giường", "chân giường", "đầu giường", "bed frame", "headboard"])
        pos_chair_part = first_pos(["chân", "khung", "tay", "armrest", "cụm tay", "phụ kiện", "đinh", "nút", "pát", "bulon", "dây", "khung chân"])

        # Tìm TỪ KHÓA NÀO XUẤT HIỆN ĐẦU TIÊN
        min_pos = min(pos_chair, pos_bed, pos_table, pos_bed_part, pos_chair_part)

        if min_pos == 9999: return None

        # --- NHÁNH 1: BỘ PHẬN GIƯỜNG ---
        if min_pos == pos_bed_part:
            if is_wood and not is_metal: return {"code": "94039100", "note": "Bộ phận giường/nội thất bằng Gỗ", "match": "Tree: Bộ phận giường + Gỗ"}
            return {"code": "94039990", "note": "Bộ phận giường/nội thất bọc nệm hoặc Khác", "match": "Tree: Bộ phận giường + Khác"}

        # --- NHÁNH 2: BỘ PHẬN GHẾ ---
        if min_pos == pos_chair_part:
            if is_wood: return {"code": "94019100", "note": "Bộ phận của ghế bằng Gỗ", "match": "Tree: Bộ phận ghế + Gỗ"}
            return {"code": "94019999", "note": "Bộ phận của ghế bằng Kim loại/Nhựa/Khác", "match": "Tree: Bộ phận ghế + Khác"}

        # --- NHÁNH 3: GIƯỜNG NGUYÊN CHIẾC (94.03) ---
        if min_pos == pos_bed:
            if is_metal and not is_wood: return {"code": "94032090", "note": "Giường / Nội thất kim loại", "match": "Tree: Giường + Kim loại"}
            return {"code": "94035000", "note": "Giường / Nội thất phòng ngủ bằng Gỗ", "match": "Tree: Giường + Gỗ"}

        # --- NHÁNH 4: BÀN / TỦ / KỆ (94.03) ---
        if min_pos == pos_table:
            if is_metal and not is_wood: return {"code": "94032090", "note": "Bàn / Tủ / Kệ bằng Kim loại", "match": "Tree: Bàn/Tủ + Kim loại"}
            if has_any(["văn phòng", "desk", "office"]): return {"code": "94033000", "note": "Bàn / Tủ văn phòng bằng Gỗ", "match": "Tree: Bàn/Tủ + Văn phòng"}
            if has_any(["bếp", "kitchen"]): return {"code": "94034000", "note": "Tủ / Kệ bếp bằng Gỗ", "match": "Tree: Bàn/Tủ + Bếp"}
            return {"code": "94036090", "note": "Bàn / Kệ / Tủ nội thất Gỗ khác", "match": "Tree: Bàn/Tủ + Gỗ khác"}

        # --- NHÁNH 5: GHẾ NGUYÊN CHIẾC (94.01) ---
        if min_pos == pos_chair:
            is_swivel = has_any(["xoay", "swivel", "rotating", "mâm xoay"])
            is_not_swivel = has_any(["không xoay", "non-swivel", "non swivel", "fixed", "cố định"])
            
            if is_swivel and not is_not_swivel:
                if is_wood: return {"code": "94013100", "note": "Ghế xoay khung Gỗ", "match": "Tree: Xoay + Gỗ"}
                return {"code": "94013900", "note": "Ghế xoay khung Kim loại/Nhựa", "match": "Tree: Xoay + Khác"}

            if has_any(["daybed", "sofa bed", "sleeper", "convertible", "futon", "thành giường"]):
                if is_metal and not is_wood: return {"code": "94014900", "note": "Ghế thành giường khung Kim loại", "match": "Tree: Bed + Kim loại"}
                return {"code": "94014100", "note": "Ghế thành giường khung Gỗ", "match": "Tree: Bed + Gỗ"}

            if has_any(["nhựa", "plastic chair", "beanbag", "ghế lười"]) and not has_any(["đinh", "nút", "chân nhựa"]):
                return {"code": "94018000", "note": "Ghế nhựa / Ghế không khung", "match": "Tree: Nhựa/Beanbag"}

            if is_wood:
                if is_upholstered: return {"code": "94016100", "note": "Ghế khung gỗ, bọc nệm", "match": "Tree: Ghế thường + Gỗ + Bọc Nệm"}
                return {"code": "94016990", "note": "Ghế khung gỗ, không bọc nệm", "match": "Tree: Ghế thường + Gỗ + Trơn"}
            
            if is_metal:
                if is_upholstered: return {"code": "94017100", "note": "Ghế khung kim loại, bọc nệm", "match": "Tree: Ghế thường + Sắt + Bọc Nệm"}
                return {"code": "94017990", "note": "Ghế khung kim loại, không bọc nệm", "match": "Tree: Ghế thường + Sắt + Trơn"}

            if is_upholstered: return {"code": "94016100", "note": "Ghế bọc nệm (Tự động giả định khung gỗ)", "match": "Tree: Ghế bọc nệm (Mặc định)"}
            return {"code": "94016990", "note": "Ghế khung gỗ (Mặc định)", "match": "Tree: Ghế Gỗ (Mặc định)"}

        return None

# ================= BỘ NÃO 2: TÌM KIẾM VECTOR =================
class VectorRuleEngine:
    def __init__(self, json_path=RULES_FILE):
        self.json_path = json_path
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.client = chromadb.EphemeralClient() 
        self.collection = self.client.get_or_create_collection(name="hscode_rules", embedding_function=self.ef)
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
            "mẫu gỗ", "mẫu vải", "mẫu da", "swatch", "giường ngủ", "giường king", "giường queen",
            "chân bàn", "chân giường", "chân tủ", "đầu giường", "cushion", "nệm",
            "vải dệt", "dệt kim", "dệt thoi", "polyester", "giả da", "simili"
        ]
        stop_words = {"ghế", "sofa", "bọc", "vải", "da", "gỗ", "sắt", "kim", "loại", "màu", "cm", "mm", "kg", "gr", "m2"}
        
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
                    if exc_clean and re.search(r'\b' + re.escape(exc_clean) + r'\b', query_lower):
                        is_excluded = True; break
            if is_excluded: continue

            rule_words = extract_words(desc_lower) - stop_words
            query_words_clean = query_words - stop_words
            matched_words = query_words_clean.intersection(rule_words)
            overlap_count = len(matched_words)
            
            bonus = 0
            matched_bonus_phrases = []
            for phrase in core_phrases:
                if re.search(r'\b' + re.escape(phrase) + r'\b', query_lower) and re.search(r'\b' + re.escape(phrase) + r'\b', desc_lower):
                    matched_bonus_phrases.append(phrase) 
                    idx = query_lower.find(phrase)
                    if idx <= 30: bonus += 30 
                    else: bonus += 5  
                        
            total_score = (overlap_count * 2.0) + bonus - distance

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
        self.tree_engine = None 
        self.is_ready = False

    def load_resources(self, callback_msg):
        def _load():
            try:
                callback_msg("SYSTEM: Đang khởi tạo AI Model, Sách Luật và Cây Quyết Định...")
                self.rule_engine = VectorRuleEngine()
                self.tree_engine = MasterTreeEngine() 
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

        rule_code = None
        rule_res = None
        
        tree_result = self.tree_engine.evaluate(user_input_clean)
        if tree_result:
            rule_code = tree_result['code']
            rule_res = {'note': tree_result['note'], 'matched_words': [], 'matched_bonus': [tree_result['match']]}
            steps.append(f"🌳 LUẬT CÂY QUYẾT ĐỊNH: {rule_code}")
        else:
            vector_res = self.rule_engine.search(user_input_clean)
            if vector_res:
                rule_code = vector_res['code']
                rule_res = vector_res
                steps.append(f"🛡️ LUẬT VECTOR JSON: {rule_code}")
        
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

        part_hs_prefixes = ("94019", "94039", "6304", "4421", "4107", "9404") 
        exemption_keywords = ["bao", "áo", "vỏ", "mẫu", "swatch", "chân", "khung", "tay", "phụ kiện", "đinh", "nút", "pát", "gối", "pillow", "cover", "cushion"]
        
        if item_group_code:
            steps.append(f"⚖️ TRỌNG TÀI: Thuộc nhóm [{item_group_code}]")
            has_exemption = any(kw in user_input_lower for kw in exemption_keywords)
            
            if item_group_code in ["1551", "1561", "15514"]:
                # Nếu là thành phẩm nhưng mã trả ra là bộ phận/phụ kiện mà không có từ khóa hợp lệ -> CẤM
                if rule_code and rule_code.startswith(part_hs_prefixes) and not has_exemption:
                    rule_code = None 
            elif item_group_code == "BTP":
                if rule_code and not rule_code.startswith(part_hs_prefixes):
                    rule_code = None
            elif item_group_code in ["1521", "1522", "1523", "1526", "1531"]:
                if not has_exemption:
                    rule_code = "CẢNH BÁO"
                    rule_res = {"note": f"Mặt hàng thuộc nhóm Vật Liệu ({item_group_code}), tra cứu HS theo đặc tính nguyên liệu (Vải, Gỗ...) chứ không phải chương Nội Thất 94."}

        if rule_code and rule_code != "CẢNH BÁO" and rule_res:
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

        stop_words = {"ghế", "sofa", "bọc", "vải", "da", "gỗ", "sắt", "kim", "loại"}

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
            "ai_matched_words": [w for w in ai_matched_words if len(w) > 1 and not w.isnumeric() and w not in stop_words],
            "steps": steps
        }