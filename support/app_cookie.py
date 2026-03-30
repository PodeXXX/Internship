import streamlit as st
import time
import pandas as pd
import json
import os
import uuid
import extra_streamlit_components as stx # Thư viện Cookie
from datetime import datetime
from hscode_brain import HSCodeBrain

# --- 1. CẤU HÌNH TRANG WEB ---
st.set_page_config(
    page_title="HS Code & Kho Hàng",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded" # Mặc định mở Sidebar
)

# --- 2. QUẢN LÝ COOKIE & DỮ LIỆU ---
def get_manager():
    return stx.CookieManager()

def get_user_id(cookie_manager):
    # Lấy cookie
    user_id = cookie_manager.get(cookie="user_device_id")
    # Nếu chưa có -> Tạo mới
    if not user_id:
        new_id = str(uuid.uuid4())[:8] 
        cookie_manager.set("user_device_id", new_id, expires_at=datetime(2030, 1, 1))
        return None # Chờ reload
    return user_id

def get_history_file(user_id):
    if not os.path.exists("user_data"):
        os.makedirs("user_data")
    return f"user_data/history_{user_id}.json"

def load_user_sessions(user_id):
    if not user_id: return {}
    file_path = get_history_file(user_id)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_user_sessions(user_id, sessions):
    if not user_id: return
    file_path = get_history_file(user_id)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=4)
    except Exception as e: print(f"Lỗi lưu file: {e}")

def create_new_session(user_id):
    session_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_sessions = load_user_sessions(user_id)
    all_sessions[session_id] = {
        "created_at": timestamp,
        "title": "Đoạn chat mới",
        "messages": []
    }
    save_user_sessions(user_id, all_sessions)
    return session_id

def update_current_session(user_id, session_id, messages, user_input=None):
    all_sessions = load_user_sessions(user_id)
    if session_id in all_sessions:
        all_sessions[session_id]["messages"] = messages
        if len(messages) == 2 and user_input:
            short_title = user_input[:30] + "..." if len(user_input) > 30 else user_input
            all_sessions[session_id]["title"] = short_title
        save_user_sessions(user_id, all_sessions)

# --- 3. KHỞI TẠO LOGIC ---
st.markdown("""
<style>
    /* Chỉ ẩn thanh cầu vồng, KHÔNG ẩn Header để tránh mất nút Sidebar */
    [data-testid="stDecoration"] {display: none;}
    
    .result-card {padding: 15px; border-radius: 8px; margin-bottom: 10px; font-size: 0.9rem; border: 1px solid #ddd;}
    .rule-box {background-color: #e8f5e9; border-color: #c8e6c9; color: #1b5e20;}
    .ai-box {background-color: #e3f2fd; border-color: #bbdefb; color: #0d47a1;}
    .fabric-alert {background-color: #e8eaf6; color: #283593; padding: 15px; border-radius: 8px; border: 1px solid #c5cae9; margin-bottom: 10px; font-size: 1rem;}
    .color-alert {background-color: #fce4ec; color: #c2185b; padding: 15px; border-radius: 8px; border: 1px solid #f8bbd0; margin-bottom: 10px; font-size: 1rem;}
    .welcome-container {text-align: center; padding: 30px 20px; background-color: #f8f9fa; border-radius: 15px; margin-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

cookie_manager = get_manager()
user_id = get_user_id(cookie_manager)

# Chờ Cookie load
if not user_id:
    st.stop()

@st.cache_resource
def load_brain_cached():
    brain = HSCodeBrain()
    def loading_callback(msg): print(msg) 
    brain.load_resources(loading_callback)
    while not brain.is_ready: time.sleep(0.5)
    return brain

try:
    brain = load_brain_cached()
except Exception as e:
    st.error(f"Lỗi khởi động hệ thống: {e}")
    st.stop()

# --- 4. STATE ---
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = create_new_session(user_id)

all_sessions_data = load_user_sessions(user_id)
curr_id = st.session_state.current_session_id

if curr_id in all_sessions_data:
    st.session_state.messages = all_sessions_data[curr_id]["messages"]
else:
    st.session_state.current_session_id = create_new_session(user_id)
    st.session_state.messages = []

# --- 5. SIDEBAR (CHẮC CHẮN SẼ HIỆN VÌ KHÔNG BỊ CSS ẨN) ---
with st.sidebar:
    st.title("🗂️ Lịch sử Chat")
    
    if st.button("➕ Chat Mới", use_container_width=True, type="primary"):
        st.session_state.current_session_id = create_new_session(user_id)
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    
    # Hiển thị danh sách chat
    sorted_sessions = sorted(all_sessions_data.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)
    
    for s_id, s_data in sorted_sessions:
        title = s_data.get("title", "Không có tiêu đề")
        prefix = "👉" if s_id == st.session_state.current_session_id else "💬"
        if st.button(f"{prefix} {title}", key=s_id, use_container_width=True):
            st.session_state.current_session_id = s_id
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Xóa hết lịch sử", use_container_width=True):
        save_user_sessions(user_id, {}) 
        st.session_state.current_session_id = create_new_session(user_id)
        st.rerun()

# --- 6. HIỂN THỊ KẾT QUẢ ---
def display_response(data):
    search_mode = data.get('search_mode', 'hscode') 
    
    if search_mode == 'chitchat':
        st.info(data.get('message', 'Tôi không hiểu ý bạn.'))

    elif search_mode == 'fabric':
        fabric_data = data.get('fabric_data')
        if fabric_data and fabric_data['status'] == 'success':
            st.markdown(f"""<div class="fabric-alert"><strong>🧵 TÌM THẤY VẢI</strong><br>Từ khóa: <strong>'{fabric_data['keyword']}'</strong>. Tìm thấy <strong>{fabric_data['count']}</strong> mục.</div>""", unsafe_allow_html=True)
            with st.expander(f"📄 Xem danh sách ({fabric_data['count']} mục)", expanded=False):
                st.dataframe(pd.DataFrame(fabric_data['data'])[['ProductCode', 'ProductName', 'SourceTable', 'MatInfo']], use_container_width=True, hide_index=True)
        else: st.warning(fabric_data.get('message', 'Lỗi'))

    elif search_mode == 'color_only':
        color_data = data.get('color_data')
        st.markdown(f"""<div class="color-alert"><strong>🎨 TÌM THẤY MÀU</strong><br>Màu: <strong>'{color_data['keyword']}'</strong>. Tìm thấy <strong>{color_data['count']}</strong> sp.</div>""", unsafe_allow_html=True)
        with st.expander(f"📄 Xem danh sách ({color_data['count']} sp)", expanded=False):
            st.dataframe(pd.DataFrame(color_data['products'])[['Code', 'Name', 'ColorVIE']], use_container_width=True, hide_index=True)

    else: # HS CODE
        rule_code = data.get('rule_code')
        ai_code = data.get('ai_code')
        ai_conf = data.get('ai_conf', 0)
        col1, col2 = st.columns(2)
        with col1:
            if rule_code: st.markdown(f"""<div class="result-card rule-box"><strong>🛡️ LUẬT:</strong> <b>{rule_code}</b><br><span style="font-size:0.8em">{data.get('rule_note','')}</span></div>""", unsafe_allow_html=True)
            else: st.markdown("""<div class="result-card not-found-box"><strong>🛡️ LUẬT:</strong> Không tìm thấy.</div>""", unsafe_allow_html=True)
        with col2: st.markdown(f"""<div class="result-card ai-box"><strong>🤖 AI:</strong> <b>{ai_code}</b><br><span style="font-size:0.8em">Tin cậy: {ai_conf:.1f}%</span></div>""", unsafe_allow_html=True)
        
        if data.get('color_data'): st.info(f"💡 Phát hiện màu **'{data['color_data']['keyword']}'**.")
        
        rec_text, msg_type = data.get('recommendation', ''), data.get('msg_type', 'info')
        if msg_type == 'success': st.success(rec_text, icon="✅")
        elif msg_type == 'warning': st.warning(rec_text, icon="⚠️")
        elif msg_type == 'error': st.error(rec_text, icon="🛑")
        else: st.info(rec_text, icon="ℹ️")

# --- 7. CHAT (CHECK COOKIE TẠI ĐÂY) ---
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-container">
        <div class="welcome-title">👋 Xin chào!</div>
        <div class="welcome-subtitle">Hỗ trợ tra cứu HS Code, Màu sắc và Vải.</div>
    </div>
    """, unsafe_allow_html=True)
    
    # === [CHECK] HIỂN THỊ COOKIE ID RA GIỮA MÀN HÌNH ===
    st.info(f"🍪 **Đã kết nối ID:** `{user_id}` (Lịch sử chat sẽ được lưu theo mã này)")
    # ====================================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user": st.write(message["content"])
        else: display_response(message["content"])

if prompt := st.chat_input("Nhập thông tin..."):
    with st.chat_message("user"): st.write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    update_current_session(user_id, st.session_state.current_session_id, st.session_state.messages, user_input=prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            result = brain.analyze_product(prompt)
            # HS CODE RECOMMENDATION LOGIC
            if result.get('search_mode') == 'hscode':
                rule, ai, conf = result.get('rule_code'), result.get('ai_code'), result.get('ai_conf', 0)
                if rule and rule == ai: result['recommendation'], result['msg_type'] = f"Tuyệt vời! Mã **{rule}** được xác nhận.", "success"
                elif rule and rule != ai: result['recommendation'], result['msg_type'] = f"Xung đột: Luật **{rule}** - AI **{ai}**. Ưu tiên LUẬT.", "warning"
                else: result['recommendation'], result['msg_type'] = (f"AI tự tin dự đoán mã **{ai}** ({conf:.1f}%).", "info") if conf > 85 else ("Cảnh báo: Độ tin cậy thấp.", "error")
            display_response(result)
            
    st.session_state.messages.append({"role": "assistant", "content": result})
    update_current_session(user_id, st.session_state.current_session_id, st.session_state.messages)