from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import threading
import uvicorn
import os
import time
import re 
import signal 
import sqlite3
from datetime import datetime 

# Import 6 bộ não chính
from hscode_brain import HSCodeBrain
from cbm_brain import CBMBrain 
from lookup_brain import LookupBrain
from bom_brain import BOMBrain 
from color_brain import ColorBrain       
from fabric_brain import FabricBrain    

# 1. Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="HS Code & Kho Hàng",
    description="Hệ thống tra cứu Vải, Màu sắc, tính CBM, tra mã, BOM và dự đoán HS Code.",
    version="2.0.0" 
)

# 2. Tạo thư mục 'static'
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

# =========================================================
# MỞ CỬA CHO PHÉP WEB TẢI ẢNH TỪ Ổ D:
# =========================================================
app.mount("/images", StaticFiles(directory=r"D:\ĐẠI HỌC TÔN ĐỨC THẮNG\Công ty Nhân Hoàng\Images"), name="images")

# =========================================================
# KHỞI TẠO DATABASE SQLITE LƯU LỊCH SỬ CHAT
# =========================================================
def init_chat_db():
    conn = sqlite3.connect("chat_history.db")
    c = conn.cursor()
    # Bảng Quản lý Phiên chat (Sessions)
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (session_id TEXT PRIMARY KEY, title TEXT, updated_at DATETIME)''')
    # Bảng Quản lý Tin nhắn chi tiết (Messages)
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, sender TEXT, content TEXT, created_at DATETIME)''')
    conn.commit()
    conn.close()

init_chat_db() 

# 3. Khởi tạo các Não bộ
brain_hscode = HSCodeBrain()
brain_cbm = CBMBrain() 
brain_lookup = LookupBrain()
brain_bom = BOMBrain() 
brain_color = ColorBrain()     
brain_fabric = FabricBrain()   

def loading_callback(msg):
    print(f"[HỆ THỐNG] {msg}")

threading.Thread(target=brain_hscode.load_resources, args=(loading_callback,), daemon=True).start()

# 4. Định nghĩa cấu trúc dữ liệu
class ChatRequest(BaseModel):
    session_id: Optional[str] = "" 
    user_input: str

class SaveMessageRequest(BaseModel): 
    session_id: str
    sender: str
    content: str

# =========================================================
# BỘ NHỚ NGỮ CẢNH (CONTEXT MEMORY)
# =========================================================
CHAT_CONTEXT = {
    "last_product_name": "", 
    "last_intent": ""        
}

def extract_product_type(text):
    keywords = [
        "ghế sofa", "ghế ăn", "ghế đôn", "khung chân", "khung ghế", 
        "bàn ăn", "bàn trà", "bàn", "tủ quần áo", "tủ", "giường", "kệ", 
        "ghế", "chân", "nệm", "đệm", "mút", "sofa"
    ]
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            return kw
    return ""


# ================= CÁC ĐƯỜNG DẪN CHÍNH (ENDPOINTS) =================
@app.get("/", tags=["UI"])
async def serve_ui():
    return FileResponse("static/index.html")

@app.post("/api/analyze", tags=["API"])
async def analyze_product(request: ChatRequest):
    user_text = request.user_input
    original_text_lower = user_text.lower().strip()
    word_count = len(original_text_lower.split())
    
    color_words = brain_color.all_colors if hasattr(brain_color, 'all_colors') else ["màu", "xanh", "đỏ", "đen", "trắng", "blue", "green"]
    fabric_words = ["vải", "nhung", "nỉ", "da", "simili", "fabric", "leather", "pu", "canvas", "linen"]

    if word_count <= 5 and CHAT_CONTEXT["last_product_name"]:
        is_color_followup = any(c.lower() in original_text_lower for c in color_words)
        is_fabric_followup = any(f in original_text_lower for f in fabric_words)
        
        if is_color_followup or is_fabric_followup:
            user_text = f"Tìm {CHAT_CONTEXT['last_product_name']} {user_text}"
            print(f"[TRÍ NHỚ AI] Nối Tên SP: '{request.user_input}' -> '{user_text}'")

    if word_count <= 8 and CHAT_CONTEXT["last_intent"]:
        has_code_indicator = "mã" in original_text_lower or "số" in original_text_lower or re.search(r'\d{4,}', original_text_lower)
        
        if has_code_indicator:
            if CHAT_CONTEXT["last_intent"] == "bom" and not brain_bom.is_bom_intent(original_text_lower):
                user_text = f"Tra BOM {user_text}"
                print(f"[TRÍ NHỚ AI] Nối Hành động BOM: '{request.user_input}' -> '{user_text}'")
                
            elif CHAT_CONTEXT["last_intent"] == "cbm" and not brain_cbm.is_cbm_intent(original_text_lower):
                user_text = f"Tính CBM {user_text}"
                print(f"[TRÍ NHỚ AI] Nối Hành động CBM: '{request.user_input}' -> '{user_text}'")

    user_text_lower = user_text.lower().strip()

    chitchat_keywords = ["xin chào", "hello", "hi ", "bạn là ai", "giúp gì", "tạm biệt", "cảm ơn", "thành lập", "năm nào", "ở đâu", "công ty", "nhân hoàng", "giám đốc", "liên hệ", "sđt", "email", "tên gì"]
    if any(word in user_text_lower for word in chitchat_keywords):
        return {"status": "ok", "search_mode": "chitchat", "message": "👋 Xin chào! Tôi là Trợ Lý Ảo chuyên về **HS Code và Kho Hàng**. Tôi có thể giúp bạn tra cứu mã HS, định mức vật tư (BOM), tính CBM và kiểm tra tồn kho."}

    if brain_bom.is_bom_intent(user_text):
        CHAT_CONTEXT["last_intent"] = "bom"  
        CHAT_CONTEXT["last_product_name"] = "" 
        return brain_bom.process_bom(user_text)

    if brain_cbm.is_cbm_intent(user_text):
        CHAT_CONTEXT["last_intent"] = "cbm"  
        CHAT_CONTEXT["last_product_name"] = "" 
        return brain_cbm.process_cbm(user_text)
        
    # KHI NGƯỜI DÙNG YÊU CẦU TRA MÃ THÌ VÀO ĐÂY VÀ GỌI LOOKUP_BRAIN
    if brain_lookup.is_lookup_intent(user_text):
        CHAT_CONTEXT["last_intent"] = "lookup" 
        CHAT_CONTEXT["last_product_name"] = "" 
        return brain_lookup.process_lookup(user_text)

    force_search = any(w in user_text_lower for w in ["tìm", "kiếm", "lọc", "search", "có", "còn"])
    
    if brain_fabric.is_fabric_intent(user_text) and (force_search or word_count <= 5):
        CHAT_CONTEXT["last_intent"] = "search_info" 
        prod_type = extract_product_type(user_text)
        if prod_type: CHAT_CONTEXT["last_product_name"] = prod_type
        
        res = brain_fabric.process_fabric(user_text)
        if res.get('status') == 'success':
            hint = "Bạn có muốn tra mã HS cho sản phẩm dùng vải này? Hãy gõ: 'Mã HS của [tên SP]'"
            return {
                "status": "ok", 
                "search_mode": "fabric", 
                "fabric_data": res, 
                "next_action_hint": hint
            }

    color_res = brain_color.search_products_by_color(user_text)
    
    if color_res and (force_search or len(user_text.split()) <= 4):
        CHAT_CONTEXT["last_intent"] = "search_info" 
        prod_type = extract_product_type(user_text)
        if prod_type: CHAT_CONTEXT["last_product_name"] = prod_type
        
        return {
            "status": "ok", 
            "search_mode": "color_only", 
            "color_data": color_res, 
            "next_action_hint": f"Để biết mã HS, gõ: 'Phân tích HS Code [tên sản phẩm] màu {color_res['keyword']}'"
        }

    if brain_hscode.is_hscode_intent(user_text) or any(kw in user_text_lower for kw in ["ghế", "sofa", "bàn", "tủ", "giường", "kệ", "đôn", "khung", "chân", "mặt", "nệm", "gối"]):
        CHAT_CONTEXT["last_intent"] = "search_info" 
        prod_type = extract_product_type(user_text)
        if prod_type: CHAT_CONTEXT["last_product_name"] = prod_type

        result = brain_hscode.process_hscode(user_text)
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("msg", "Lỗi xử lý hệ thống."))
        
        rule_code = result.get('rule_code')
        ai_code = result.get('ai_code')
        ai_conf = result.get('ai_conf', 0)
        
        if rule_code and rule_code == ai_code: 
            result['recommendation'], result['msg_type'] = f"Tuyệt vời! Mã {rule_code} được xác nhận.", "success"
        elif rule_code and rule_code != ai_code: 
            result['recommendation'], result['msg_type'] = f"Xung đột: Luật {rule_code} - AI {ai_code}. Ưu tiên LUẬT.", "warning"
        else: 
            if ai_conf > 85: 
                result['recommendation'], result['msg_type'] = f"AI tự tin dự đoán mã {ai_code} ({ai_conf:.1f}%).", "info"
            else: 
                result['recommendation'], result['msg_type'] = "Cảnh báo: Độ tin cậy thấp.", "error"
                
        result['next_action_hint'] = "Bạn có thể gõ 'Tìm [tên sản phẩm] màu [tên màu]' để tra tồn kho."
        
        if color_res: result['color_data'] = color_res

        return result

    return {
        "status": "ok", 
        "search_mode": "chitchat", 
        "message": "⚠️ Tôi không nhận diện được tên sản phẩm hay hành động. Hãy thử: 'Sofa gỗ', 'Tìm ghế sofa màu xanh' hoặc 'Tính CBM 50 mã 10002586'."
    }

# =========================================================
# CÁC API PHỤC VỤ LƯU VÀ TẢI LỊCH SỬ CHAT
# =========================================================
@app.get("/api/history", tags=["History"])
async def get_history_list():
    """Lấy danh sách các phiên chat (Sidebar)"""
    conn = sqlite3.connect("chat_history.db")
    c = conn.cursor()
    c.execute("SELECT session_id, title, updated_at FROM sessions ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"session_id": r[0], "title": r[1], "created_at": r[2]} for r in rows]

@app.get("/api/history/{session_id}", tags=["History"])
async def get_session_messages(session_id: str):
    """Lấy chi tiết tin nhắn của 1 phiên chat để in lên màn hình"""
    conn = sqlite3.connect("chat_history.db")
    c = conn.cursor()
    c.execute("SELECT sender, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử")
    return {"session_id": session_id, "messages": [{"sender": r[0], "content": r[1]} for r in rows]}

@app.post("/api/history/save", tags=["History"])
async def save_chat_message(req: SaveMessageRequest):
    """Lưu tin nhắn (Của User hoặc Bot) vào Database"""
    conn = sqlite3.connect("chat_history.db")
    c = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Kiểm tra xem phiên chat này đã có chưa
    c.execute("SELECT session_id FROM sessions WHERE session_id = ?", (req.session_id,))
    if not c.fetchone():
        # Nếu là câu đầu tiên, lấy tối đa 30 ký tự để làm Tiêu đề phiên chat (Title)
        title = req.content[:30] + "..." if len(req.content) > 30 else req.content
        c.execute("INSERT INTO sessions (session_id, title, updated_at) VALUES (?, ?, ?)", (req.session_id, title, now_str))
    else:
        # Nếu đã có, chỉ cập nhật lại thời gian để đẩy phiên này lên đầu Sidebar
        c.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now_str, req.session_id))
        
    # Lưu nội dung tin nhắn
    c.execute("INSERT INTO messages (session_id, sender, content, created_at) VALUES (?, ?, ?, ?)",
              (req.session_id, req.sender, req.content, now_str))
    conn.commit()
    conn.close()
    return {"status": "saved"}

@app.delete("/api/history/{session_id}", tags=["History"])
async def delete_chat_session(session_id: str):
    """Xóa một phiên chat và toàn bộ tin nhắn bên trong"""
    conn = sqlite3.connect("chat_history.db")
    c = conn.cursor()
    # Xóa trong bảng sessions
    c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    # Xóa chi tiết trong bảng messages
    c.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# =========================================================
# API TẮT SERVER
# =========================================================
@app.post("/api/shutdown", tags=["API"])
async def shutdown_server():
    print("[HỆ THỐNG] Đã nhận lệnh tắt máy. Terminal sẽ đóng trong 1 giây...")
    def force_kill():
        time.sleep(1)
        try:
            os.kill(os.getppid(), signal.SIGTERM)
        except Exception: pass
        os._exit(0)
    threading.Thread(target=force_kill, daemon=True).start()
    return {"message": "Đang tắt hệ thống..."}

@app.get("/api/status", tags=["API"])
async def get_status():
    return {"status": "Online" if brain_hscode.is_ready else "Loading", "is_ready": brain_hscode.is_ready}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)